# Pulse

**Real-time e-commerce order stream processing pipeline built with Apache Kafka, PySpark Structured Streaming, and PostgreSQL — fully containerized with Docker Compose.**

![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?logo=apachekafka&logoColor=white)
![Apache Spark](https://img.shields.io/badge/Apache%20Spark-E25A1C?logo=apachespark&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)

---

## Overview

Pulse simulates a high-throughput e-commerce order feed and processes it in real time. A Python producer continuously generates fake order events (via [Faker](https://faker.readthedocs.io/)) and publishes them to Kafka at ~5 events/sec. A PySpark Structured Streaming job runs them through a multi-stage pipeline:

1. **Validate** — every event is checked for missing fields, non-positive price/quantity, and unparseable timestamps. Bad events are routed to a dead-letter table (`orders_dlq`) with the reasons they failed instead of being silently dropped.
2. **Enrich** — valid orders are joined against a `category_reference` lookup table to add `department`, `tax_rate`, and a derived `tax_amount`.
3. **Aggregate** — event-time windowed aggregations with watermarking produce per-category and per-city revenue metrics over 1-minute tumbling windows.
4. **Detect anomalies** — in parallel, individual orders whose revenue exceeds `ANOMALY_REVENUE_THRESHOLD` are written to `order_anomalies`.

**Tech stack:**
- **Confluent Kafka 7.6.1** — event transport and buffering
- **PySpark 3.5.0** — Structured Streaming with event-time processing
- **PostgreSQL 16** — metric storage with proper indexing
- **Docker Compose** — single-command local deployment, no local installs needed

---

## Architecture

```
┌──────────┐  orders   ┌─────────┐
│ Producer │─────────► │  Kafka  │
│ (Faker)  │  ~5 ev/s  │ orders  │
└──────────┘           └────┬────┘
                            │
┌───────────────────────────┼──────────── Spark Job (PySpark 3.5) ─────────────┐
│                           ▼                                                  │
│                ┌──────────────────────┐                                      │
│                │ 1. Parse + validate  │── invalid ──────────────────────────────► orders_dlq
│                └──────────┬───────────┘                                      │
│                           │ valid (revenue = price × qty)                    │
│                           ▼                                                  │
│                ┌──────────────────────┐    ┌────────────────────┐            │
│                │ 2. Enrich            │◄───│ category_reference │ (broadcast)│
│                │  + department        │    └────────────────────┘            │
│                │  + tax_amount        │                                      │
│                └──────────┬───────────┘                                      │
│              ┌────────────┴─────────────┐                                    │
│              ▼                          ▼                                    │
│  ┌───────────────────────┐   ┌──────────────────────┐                        │
│  │ 3. Windowed aggregates│   │ 4. Anomaly detection │─────────────────────────► order_anomalies
│  │  10-min watermark,    │   │  revenue > threshold │                        │
│  │  1-min windows        │   └──────────────────────┘                        │
│  └───────────┬───────────┘                                                   │
└──────────────┼───────────────────────────────────────────────────────────────┘
               ├──────────► category_metrics  (per category/window, incl. total_tax)
               └──────────► city_metrics      (per city/window)

                                              All tables live in PostgreSQL 16 → Grafana
```

**Data flow:** Producer → Kafka (`orders` topic) → Spark (validate → enrich → aggregate / detect anomalies) → PostgreSQL → Grafana

### Validation rules

An event is sent to `orders_dlq` if any of these fail (all failing rules are recorded in `validation_errors`):

| Reason | Condition |
|---|---|
| `malformed_json` | Payload is not valid JSON, or doesn't match the event schema |
| `missing_<field>` | Any of `event_id`, `order_id`, `user_id`, `product_id`, `category`, `city`, `event_timestamp`, `price`, `quantity` is null or blank |
| `invalid_price` | `price` is not a number or is `<= 0` |
| `invalid_quantity` | `quantity` is not an integer or is `<= 0` |
| `invalid_event_timestamp` | `event_timestamp` is not a parseable ISO-8601 timestamp |

Orders whose category isn't in `category_reference` are kept (not rejected) with a null `department` and zero tax.

---

## Event Schema

The producer emits JSON events with this structure:

```json
{
  "event_id":        "550e8400-e29b-41d4-a716-446655440000",
  "order_id":        "ord_a3f9b12c84",
  "user_id":         "usr_f3a1b2c4",
  "product_id":      "prd_9d8e7f6a",
  "category":        "electronics",
  "price":           149.99,
  "quantity":        2,
  "city":            "New York",
  "event_timestamp": "2026-03-11T10:23:45Z"
}
```

**Categories:** `electronics`, `fashion`, `home`, `beauty`, `sports`, `books`, `grocery`

**Key derived field:** `revenue = price × quantity` (computed in Spark, not stored in Kafka)

---

## Prerequisites

- **Docker Desktop** (includes Docker Compose v2) — no local Python, Java, or Spark required
- ~2 GB RAM available for containers
- Ports `2181`, `9092`, `5432` free on your host machine

---

## Quick Start

### 1. Clone and start the stack

```bash
git clone https://github.com/rohith2672/Pulse.git
cd Pulse
docker compose up -d --build
```

This starts 4 services: Zookeeper, Kafka, PostgreSQL (with auto schema init), and the Spark job.

### 2. Verify services are running

```bash
docker compose ps
```

All 4 services should show `running` (or `Up`). The Spark job may show `restarting` briefly while Kafka finishes initializing — it will stabilize within ~30 seconds.

### 3. Start the producer

**On Linux/macOS:**
```bash
docker run --rm -it --network pulse_default \
  -e KAFKA_BOOTSTRAP_SERVERS=kafka:29092 \
  -v "$(pwd)/producer:/app" -w /app python:3.11-slim \
  bash -c "pip install confluent-kafka==2.4.0 faker==24.9.0 python-dateutil==2.9.0.post0 && python producer.py"
```

**On Windows (Git Bash):**
```bash
MSYS_NO_PATHCONV=1 docker run --rm -it --network pulse_default \
  -e KAFKA_BOOTSTRAP_SERVERS=kafka:29092 \
  -v "$(pwd)/producer:/app" --workdir //app python:3.11-slim \
  bash -c "pip install confluent-kafka==2.4.0 faker==24.9.0 python-dateutil==2.9.0.post0 && python producer.py"
```

**On Windows (PowerShell/CMD):**
```powershell
docker run --rm -it --network pulse_default `
  -e KAFKA_BOOTSTRAP_SERVERS=kafka:29092 `
  -v "%cd%\producer:/app" -w /app python:3.11-slim `
  bash -c "pip install confluent-kafka==2.4.0 faker==24.9.0 python-dateutil==2.9.0.post0 && python producer.py"
```

You should see output like:
```
[Pulse Producer Starting]
Bootstrap Server: kafka:29092
Topic: orders
Events per second: 5.0
--------------------------------------------------
Sent 100 events | Avg rate: 5.01 events/sec
```

### 4. Wait for the watermark

The Spark job uses a **10-minute watermark** to handle late data. Results first appear in PostgreSQL ~11 minutes after the producer starts (10-min watermark + 1-min window duration).

### 5. Verify results in PostgreSQL

```bash
docker exec -it pulse-postgres psql -U pulse -d pulse
```

```sql
-- Check category metrics
SELECT category, total_revenue, order_count, avg_order_value, total_quantity
FROM category_metrics
ORDER BY window_start DESC, total_revenue DESC
LIMIT 20;

-- Check city metrics
SELECT city, total_revenue, order_count
FROM city_metrics
ORDER BY window_start DESC, total_revenue DESC
LIMIT 10;

-- Enrichment: tax collected per category
SELECT category, total_revenue, total_tax
FROM category_metrics
ORDER BY window_start DESC, total_tax DESC
LIMIT 10;

-- Anomalies (written immediately, no watermark wait)
SELECT order_id, category, department, city, revenue, event_time
FROM order_anomalies
ORDER BY flagged_at DESC
LIMIT 10;

-- Dead-letter queue
SELECT validation_errors, raw_value, received_at
FROM orders_dlq
ORDER BY received_at DESC
LIMIT 10;

-- Count rows per table
SELECT 'category_metrics' AS tbl, COUNT(*) FROM category_metrics
UNION ALL SELECT 'city_metrics',    COUNT(*) FROM city_metrics
UNION ALL SELECT 'order_anomalies', COUNT(*) FROM order_anomalies
UNION ALL SELECT 'orders_dlq',      COUNT(*) FROM orders_dlq;
```

Expected: all 7 categories present in `category_metrics`, multiple cities in `city_metrics`, each row representing a 1-minute window. `order_anomalies` fills up within ~30 seconds, since orders above 1500 revenue are fairly common with the generator's price and quantity ranges. `orders_dlq` stays empty with the stock producer, because every event it generates is valid. To exercise it, publish a bad event by hand:

```bash
echo '{"event_id":"x","price":-1}' | docker exec -i pulse-kafka \
  kafka-console-producer --bootstrap-server localhost:9092 --topic orders
```

---

## Configuration

All settings are controlled via environment variables (defaults match `docker-compose.yml`).

### Producer

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `KAFKA_TOPIC` | `orders` | Topic to publish events to |
| `EVENTS_PER_SECOND` | `5` | Event throughput rate |

### Spark Job

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `KAFKA_TOPIC` | `orders` | Topic to consume from |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `pulse` | Database name |
| `POSTGRES_USER` | `pulse` | Database user |
| `POSTGRES_PASSWORD` | `pulse` | Database password |
| `WATERMARK_DELAY` | `10 minutes` | Late data tolerance window |
| `WINDOW_DURATION` | `1 minute` | Tumbling window size |
| `TRIGGER_INTERVAL` | `30 seconds` | Spark micro-batch interval |
| `CHECKPOINT_DIR` | `/tmp/spark-checkpoints` | State recovery directory |
| `ANOMALY_REVENUE_THRESHOLD` | `1500` | Orders with `price × quantity` above this are written to `order_anomalies` |

---

## Running Tests

Tests cover the producer's event generator, the validation and anomaly rules, and the Spark transformation stages (parse/validate, enrichment join, windowed aggregation, anomaly filter). The Spark tests use local-mode PySpark with static DataFrames, so no Kafka or Postgres is needed — only Java 17+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r producer/requirements-dev.txt -r spark-streaming/requirements-dev.txt
pytest
```

---

## Performance Notes

**Expected end-to-end latency: ~11 minutes**

This is by design. The watermark mechanism works as follows:

1. Spark tracks the maximum `event_timestamp` seen across all events
2. Events older than `max_event_time - WATERMARK_DELAY` are considered "late" and dropped
3. A window closes (and is written to PostgreSQL) only after the watermark advances past `window_end`
4. With a 10-minute watermark and 1-minute windows: a window at T+0:00–T+1:00 closes at ~T+11:00

**Tuning:**
- **Lower latency** → reduce `WATERMARK_DELAY` (e.g., `2 minutes`) — but late events will be dropped sooner
- **Larger aggregation windows** → increase `WINDOW_DURATION` (e.g., `5 minutes`)
- **More frequent micro-batches** → reduce `TRIGGER_INTERVAL` (e.g., `10 seconds`) — increases CPU usage

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `column "total_tax" does not exist` or missing `orders_dlq` / `order_anomalies` / `category_reference` tables | Postgres volume was created with an older `schema.sql` (it only runs on first start), or Spark checkpoints hold the old query state | `docker compose down -v` then `docker compose up -d --build` |
| `InconsistentClusterIdException` in Kafka logs | Stale `kafka_data` volume from a previous run | `docker compose down -v` then `docker compose up -d --build` |
| Spark container keeps restarting | Spark started before Kafka finished creating the `orders` topic | Wait ~30s then `docker compose restart spark-job` |
| No rows in PostgreSQL after 15 minutes | Spark may have crashed before producer started | Check `docker compose logs spark-job`; restart if needed |
| Git Bash path mangling (`/app` → `C:/Program Files/Git/app`) | MSYS auto-converts Unix paths | Use `MSYS_NO_PATHCONV=1` and `--workdir //app` (double slash) |
| `confluent-kafka` pip install fails on Windows | Requires Microsoft C++ Build Tools | Run producer inside Docker (see Quick Start step 3) |
| Spark logs are very verbose | Default log level is INFO | Already set to WARN in `spark_job.py` — check `docker compose logs -f spark-job` |

---

## Project Structure

```
Pulse/
├── docker-compose.yml          # Orchestrates all services
├── pytest.ini                  # Test discovery for both packages
├── database/
│   └── schema.sql              # Tables + category_reference seed data, auto-applied on first start
├── producer/
│   ├── producer.py             # Kafka event generator (confluent-kafka + Faker)
│   ├── requirements.txt        # confluent-kafka, faker, python-dateutil
│   ├── requirements-dev.txt    # + pytest
│   └── tests/                  # Event generator tests
├── spark-streaming/
│   ├── spark_job.py            # Pipeline stages + streaming wiring
│   ├── validation.py           # validate_order() rules
│   ├── anomaly.py              # is_anomaly() rule
│   ├── Dockerfile              # eclipse-temurin:17-jre + PySpark + connector JARs
│   ├── entrypoint.sh           # spark-submit wrapper (auto-discovers JARs)
│   ├── requirements-dev.txt    # pyspark, pytest
│   └── tests/                  # Validation, anomaly, and Spark stage tests
└── docs/
    └── progress.md             # Session-by-session build log
```

---

## License

MIT
