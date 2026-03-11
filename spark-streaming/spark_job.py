"""
Pulse — Spark Structured Streaming Job

Reads order events from Kafka, applies event-time windowed aggregations
with watermarking, and persists computed metrics to PostgreSQL.
"""

import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    from_json,
    window,
    sum as _sum,
    count,
    avg,
    round as _round,
    to_timestamp,
)
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

# ── Configuration ─────────────────────────────────────────────────────────────

KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC      = os.getenv("KAFKA_TOPIC",             "orders")

PG_HOST          = os.getenv("POSTGRES_HOST",           "localhost")
PG_PORT          = os.getenv("POSTGRES_PORT",           "5432")
PG_DB            = os.getenv("POSTGRES_DB",             "pulse")
PG_USER          = os.getenv("POSTGRES_USER",           "pulse")
PG_PASSWORD      = os.getenv("POSTGRES_PASSWORD",       "pulse")

CHECKPOINT_DIR   = os.getenv("CHECKPOINT_DIR",          "/tmp/spark-checkpoints")

# Event-time processing knobs
WATERMARK_DELAY  = os.getenv("WATERMARK_DELAY",         "10 minutes")
WINDOW_DURATION  = os.getenv("WINDOW_DURATION",         "1 minute")
TRIGGER_INTERVAL = os.getenv("TRIGGER_INTERVAL",        "30 seconds")

JDBC_URL   = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DB}"
JDBC_PROPS = {
    "user":     PG_USER,
    "password": PG_PASSWORD,
    "driver":   "org.postgresql.Driver",
}

# ── Schema ────────────────────────────────────────────────────────────────────

ORDER_SCHEMA = StructType([
    StructField("event_id",        StringType(),  True),
    StructField("order_id",        StringType(),  True),
    StructField("user_id",         StringType(),  True),
    StructField("product_id",      StringType(),  True),
    StructField("category",        StringType(),  True),
    StructField("price",           DoubleType(),  True),
    StructField("quantity",        IntegerType(), True),
    StructField("city",            StringType(),  True),
    StructField("event_timestamp", StringType(),  True),
])

# ── Sink helpers ──────────────────────────────────────────────────────────────

def make_jdbc_writer(table: str):
    """Return a foreachBatch sink function that appends a micro-batch to `table`."""
    def write_batch(batch_df, batch_id: int):
        row_count = batch_df.count()
        if row_count == 0:
            return
        batch_df.write.jdbc(
            url=JDBC_URL,
            table=table,
            mode="append",
            properties=JDBC_PROPS,
        )
        print(f"[batch {batch_id}] wrote {row_count} rows → {table}")
    return write_batch


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    spark = (
        SparkSession.builder
        .appName("Pulse-StreamProcessor")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    print(f"[Pulse] Kafka    : {KAFKA_BOOTSTRAP}  topic={KAFKA_TOPIC}")
    print(f"[Pulse] Postgres : {JDBC_URL}")
    print(f"[Pulse] Window   : {WINDOW_DURATION}  watermark={WATERMARK_DELAY}")
    print(f"[Pulse] Trigger  : {TRIGGER_INTERVAL}")

    # ── Ingest from Kafka ─────────────────────────────────────────────────────
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    # ── Parse JSON and derive revenue ─────────────────────────────────────────
    orders = (
        raw
        .select(from_json(col("value").cast("string"), ORDER_SCHEMA).alias("d"))
        .select("d.*")
        .withColumn("event_time", to_timestamp("event_timestamp"))
        .filter(col("event_time").isNotNull())
        .withColumn("revenue", col("price") * col("quantity"))
        .withWatermark("event_time", WATERMARK_DELAY)
    )

    # ── Aggregation 1: metrics per category per window ────────────────────────
    category_metrics = (
        orders
        .groupBy(window("event_time", WINDOW_DURATION), "category")
        .agg(
            _round(_sum("revenue"), 2).alias("total_revenue"),
            count("order_id")         .alias("order_count"),
            _round(avg("price"), 2)   .alias("avg_order_value"),
            _sum("quantity")          .alias("total_quantity"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end")  .alias("window_end"),
            "category",
            "total_revenue",
            "order_count",
            "avg_order_value",
            "total_quantity",
        )
    )

    # ── Aggregation 2: metrics per city per window ────────────────────────────
    city_metrics = (
        orders
        .groupBy(window("event_time", WINDOW_DURATION), "city")
        .agg(
            _round(_sum("revenue"), 2).alias("total_revenue"),
            count("order_id")         .alias("order_count"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end")  .alias("window_end"),
            "city",
            "total_revenue",
            "order_count",
        )
    )

    # ── Write streams to Postgres via foreachBatch ────────────────────────────
    #
    # outputMode("append") — each completed window emits exactly once,
    # after the watermark advances past window_end + WATERMARK_DELAY.
    # This guarantees no duplicate rows without needing upsert logic.

    cat_query = (
        category_metrics.writeStream
        .outputMode("append")
        .foreachBatch(make_jdbc_writer("category_metrics"))
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/category_metrics")
        .trigger(processingTime=TRIGGER_INTERVAL)
        .start()
    )

    city_query = (
        city_metrics.writeStream
        .outputMode("append")
        .foreachBatch(make_jdbc_writer("city_metrics"))
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/city_metrics")
        .trigger(processingTime=TRIGGER_INTERVAL)
        .start()
    )

    print("[Pulse] Both streaming queries active. Awaiting termination...")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
