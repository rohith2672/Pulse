# Pulse — Progress Log

---

## Session: 2026-03-10

### Completed
- Built `spark-streaming/spark_job.py` — PySpark Structured Streaming job
  - Reads JSON order events from Kafka `orders` topic
  - Enforces schema, derives `revenue = price × quantity`
  - Event-time processing with 10-minute watermark
  - Two 1-minute tumbling window aggregations:
    - `category_metrics`: total_revenue, order_count, avg_order_value, total_quantity per category
    - `city_metrics`: total_revenue, order_count per city
  - Writes to PostgreSQL via `foreachBatch` + JDBC (append mode)
  - Checkpointing enabled for fault-tolerant restarts

- Built `spark-streaming/Dockerfile`
  - Based on `eclipse-temurin:17-jre-jammy` (stable, no bitnami/apache image dependency)
  - Installs PySpark 3.5.0 via pip
  - Pre-downloads 5 connector JARs at build time (Kafka, PostgreSQL JDBC)

- Built `spark-streaming/entrypoint.sh`
  - Runs `spark-submit --jars <all jars> --master local[2]`

- Built `database/schema.sql`
  - `category_metrics` and `city_metrics` tables
  - Unique constraints on (window_start, window_end, category/city)
  - Indexes on window and dimension columns
  - Auto-applied on first Postgres container start via `/docker-entrypoint-initdb.d`

- Updated `docker-compose.yml`
  - Added healthcheck to postgres service
  - Added `spark-job` service (depends on postgres healthy + kafka started)
  - Added `spark_checkpoints` volume
  - Mounted `./database` → `/docker-entrypoint-initdb.d` for auto schema init

- Fixed `producer/requirements.txt`
  - Changed `kafka-python` → `confluent-kafka==2.4.0` to match what `producer.py` actually imports

### Issues Hit & Fixes
- `bitnami/spark:3.5` and `apache/spark-py:v3.5.0` — both not found on Docker Hub
  - Fixed: switched to `eclipse-temurin:17-jre-jammy` + `pip install pyspark==3.5.0`

- Kafka container crash on restart: `InconsistentClusterIdException`
  - Cause: stale `kafka_data` volume from a previous run
  - Fixed: `docker compose down -v` to wipe volumes before restarting

- `confluent-kafka` pip install failing on Windows (requires C++ Build Tools)
  - Fixed: run producer inside Docker on the same network
  ```
  docker run --rm -it --network pulse_default \
    -e KAFKA_BOOTSTRAP_SERVERS=kafka:29092 \
    -v "%cd%\producer:/app" -w /app python:3.11-slim \
    bash -c "pip install confluent-kafka faker && python producer.py"
  ```

### Current State
- All 4 services running: zookeeper, kafka, postgres, spark-job
- Kafka `orders` topic created (1 partition, default replication)
- Producer running via Docker, streaming events to Kafka
- Spark job consuming and aggregating — results appear in Postgres after ~11 minutes (watermark delay)

### Pending
- ~~Verify data in Postgres~~ ✓
- Deployment: AWS EC2 setup (`deployment/` still empty)
- Optional: Kubernetes manifests
- Optional: dashboard / visualization layer on top of the metrics tables

---

## Session: 2026-03-11

### Completed
- Full end-to-end pipeline smoke test — verified Kafka → Spark → Postgres is working
- Ran `docker compose down -v` + `docker compose up -d --build` for a clean restart
- Confirmed producer streams ~5 events/sec via Docker (MSYS_NO_PATHCONV=1 workaround for Git Bash path mangling)
- Confirmed Kafka `orders` topic accumulating messages (794+ offsets verified via `kafka-run-class GetOffsetShell`)
- Confirmed Spark micro-batches processing every 30 seconds
- Queried Postgres after watermark passed — data confirmed in both tables:
  - `category_metrics`: all 7 categories with correct revenue, order count, avg order value, quantity per 1-min window
  - `city_metrics`: per-city revenue and order count per 1-min window

### Issues Hit & Fixes
- Spark-job crashed on first start with `UnknownTopicOrPartitionException`
  - Cause: Spark started before Kafka finished creating the `orders` topic
  - Fixed: `docker compose restart spark-job` after topic was confirmed present
  - Long-term fix: pre-create topic in docker-compose or add a retry loop in entrypoint

- Git Bash path mangling with `-w /app` in `docker run`
  - Cause: Git Bash converts `/app` → `C:/Program Files/Git/app`
  - Fixed: use `MSYS_NO_PATHCONV=1` env var + `--workdir //app` (double slash)

### Current State
- Pipeline fully verified end-to-end
- All services healthy, data flowing into Postgres

### Pending
- AWS EC2 deployment (`deployment/` still empty)
- Optional: Kubernetes manifests
- Optional: dashboard / visualization layer on top of the metrics tables
