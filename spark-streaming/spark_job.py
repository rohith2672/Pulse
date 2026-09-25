"""
Pulse — Spark Structured Streaming Job

Pipeline stages:
  Kafka `orders` → parse + validate ─┬─ invalid → orders_dlq
                                     └─ valid → enrich (category_reference)
                                                 ├─ windowed aggregates → category_metrics, city_metrics
                                                 └─ anomaly filter      → order_anomalies
"""

import os

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    array,
    array_contains,
    array_union,
    avg,
    broadcast,
    coalesce,
    col,
    count,
    from_json,
    lit,
    round as _round,
    size,
    sum as _sum,
    to_timestamp,
    udf,
    when,
    window,
)
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from anomaly import is_anomaly
from validation import validate_order

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

ANOMALY_REVENUE_THRESHOLD = float(os.getenv("ANOMALY_REVENUE_THRESHOLD", "1500"))

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

# ── UDFs ──────────────────────────────────────────────────────────────────────

@udf(ArrayType(StringType()))
def _validate_udf(order_row):
    return validate_order(order_row.asDict() if order_row is not None else None)


_anomaly_udf = udf(is_anomaly, BooleanType())

# ── Transformation stages ─────────────────────────────────────────────────────

def parse_and_validate(raw_df: DataFrame) -> DataFrame:
    """Parse Kafka `value` bytes into order columns plus a `validation_errors` array."""
    parsed = (
        raw_df
        .select(col("value").cast("string").alias("raw_value"))
        .withColumn("d", from_json("raw_value", ORDER_SCHEMA))
        .withColumn("event_time", to_timestamp("d.event_timestamp"))
        .withColumn("py_errors", _validate_udf(col("d")))
    )

    # Spark's own timestamp parser is what the windowing relies on, so a value it
    # cannot parse must be rejected even if the Python check accepted it.
    errs = col("py_errors")
    spark_ts_failed = (
        col("event_time").isNull()
        & ~array_contains(errs, "missing_event_timestamp")
        & ~array_contains(errs, "malformed_json")
    )
    return (
        parsed
        .withColumn(
            "validation_errors",
            when(spark_ts_failed, array_union(errs, array(lit("invalid_event_timestamp"))))
            .otherwise(errs),
        )
        .select("raw_value", "d.*", "event_time", "validation_errors")
    )


def select_invalid(validated_df: DataFrame) -> DataFrame:
    return (
        validated_df
        .filter(size("validation_errors") > 0)
        .select("raw_value", "validation_errors")
    )


def select_valid(validated_df: DataFrame) -> DataFrame:
    return (
        validated_df
        .filter(size("validation_errors") == 0)
        .drop("raw_value", "validation_errors")
        .withColumn("revenue", col("price") * col("quantity"))
    )


def enrich_orders(orders_df: DataFrame, reference_df: DataFrame) -> DataFrame:
    """Join category reference data onto each order; unknown categories get no tax."""
    reference = reference_df.select(
        "category",
        "department",
        col("tax_rate").cast(DoubleType()).alias("tax_rate"),
    )
    return (
        orders_df
        .join(broadcast(reference), on="category", how="left")
        .withColumn("tax_amount", col("revenue") * coalesce(col("tax_rate"), lit(0.0)))
    )


def compute_category_metrics(orders_df: DataFrame, window_duration: str) -> DataFrame:
    return (
        orders_df
        .groupBy(window("event_time", window_duration), "category")
        .agg(
            _round(_sum("revenue"), 2)   .alias("total_revenue"),
            count("order_id")            .alias("order_count"),
            _round(avg("price"), 2)      .alias("avg_order_value"),
            _sum("quantity")             .alias("total_quantity"),
            _round(_sum("tax_amount"), 2).alias("total_tax"),
        )
        .select(
            col("window.start").alias("window_start"),
            col("window.end")  .alias("window_end"),
            "category",
            "total_revenue",
            "order_count",
            "avg_order_value",
            "total_quantity",
            "total_tax",
        )
    )


def compute_city_metrics(orders_df: DataFrame, window_duration: str) -> DataFrame:
    return (
        orders_df
        .groupBy(window("event_time", window_duration), "city")
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


def detect_anomalies(orders_df: DataFrame, threshold: float) -> DataFrame:
    return (
        orders_df
        .filter(_anomaly_udf(col("revenue"), lit(float(threshold))))
        .select(
            "event_id",
            "order_id",
            "category",
            "department",
            "city",
            "price",
            "quantity",
            _round("revenue", 2).alias("revenue"),
            "event_time",
        )
    )

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


def start_sink(df: DataFrame, table: str):
    return (
        df.writeStream
        .outputMode("append")
        .foreachBatch(make_jdbc_writer(table))
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/{table}")
        .trigger(processingTime=TRIGGER_INTERVAL)
        .start()
    )


def load_category_reference(spark: SparkSession) -> DataFrame:
    reference = spark.read.jdbc(url=JDBC_URL, table="category_reference", properties=JDBC_PROPS).cache()
    print(f"[Pulse] Loaded {reference.count()} rows from category_reference")
    return reference

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
    print(f"[Pulse] Anomaly  : revenue > {ANOMALY_REVENUE_THRESHOLD}")

    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    validated = parse_and_validate(raw)
    enriched = enrich_orders(select_valid(validated), load_category_reference(spark))
    watermarked = enriched.withWatermark("event_time", WATERMARK_DELAY)

    # Aggregates use outputMode("append"): each completed window emits exactly
    # once, after the watermark passes window_end + WATERMARK_DELAY, so no
    # upsert logic is needed.
    start_sink(compute_category_metrics(watermarked, WINDOW_DURATION), "category_metrics")
    start_sink(compute_city_metrics(watermarked, WINDOW_DURATION), "city_metrics")
    start_sink(select_invalid(validated), "orders_dlq")
    start_sink(detect_anomalies(enriched, ANOMALY_REVENUE_THRESHOLD), "order_anomalies")

    print("[Pulse] All streaming queries active. Awaiting termination...")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
