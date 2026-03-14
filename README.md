# Pulse

**Real-time e-commerce order stream processing pipeline built with Apache Kafka, PySpark Structured Streaming, and PostgreSQL — fully containerized with Docker Compose.**

![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?logo=apachekafka&logoColor=white)
![Apache Spark](https://img.shields.io/badge/Apache%20Spark-E25A1C?logo=apachespark&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)

---

## Overview

Pulse simulates a high-throughput e-commerce order feed and processes it in real time. A Python producer continuously generates fake order events and publishes them to Kafka at ~5 events/sec. A PySpark Structured Streaming job consumes those events, applies event-time windowed aggregations with watermarking for late-data tolerance, and writes the results to PostgreSQL — producing per-category and per-city revenue metrics over 1-minute tumbling windows.

**Tech stack:**
- **Confluent Kafka 7.6.1** — event transport and buffering
- **PySpark 3.5.0** — Structured Streaming with event-time processing
- **PostgreSQL 16** — metric storage with proper indexing
- **Docker Compose** — single-command local deployment, no local installs needed

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                           │
│                                                                 │
│  ┌──────────┐   orders   ┌───────────────┐                     │
│  │ Producer │──────────►│     Kafka      │                     │
│  │ (Python) │  ~5 ev/s  │  orders topic  │                     │
│  └──────────┘           └───────┬───────┘                     │
│                                 │                               │
│                                 ▼                               │
│                        ┌────────────────┐                      │
│                        │  Spark Job     │                      │
│                        │  (PySpark 3.5) │                      │
│                        │                │                      │
│                        │  • JSON parse  │                      │
│                        │  • revenue =   │                      │
│                        │    price×qty   │                      │
│                        │  • 10-min      │                      │
│                        │    watermark   │                      │
│                        │  • 1-min       │                      │
│                        │    windows     │                      │
│                        └───────┬────────┘                      │
│                                │                                │
│               ┌────────────────┴────────────────┐              │
│               ▼                                  ▼              │
│   ┌───────────────────────┐   ┌───────────────────────────┐    │
│   │   category_metrics    │   │      city_metrics         │    │
│   │  (per category/window)│   │   (per city/window)       │    │
│   │                       │   │                           │    │
│   │ • window_start/end    │   │ • window_start/end        │    │
│   │ • total_revenue       │   │ • total_revenue           │    │
│   │ • order_count         │   │ • order_count             │    │
│   │ • avg_order_value     │   └───────────────────────────┘    │
│   │ • total_quantity      │                                     │
│   └───────────────────────┘           PostgreSQL 16            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Data flow:** Producer → Kafka (`orders` topic) → Spark Structured Streaming → PostgreSQL

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

-- Count rows per table
SELECT 'category_metrics' AS tbl, COUNT(*) FROM category_metrics
UNION ALL
SELECT 'city_metrics', COUNT(*) FROM city_metrics;
```

Expected: all 7 categories present in `category_metrics`, multiple cities in `city_metrics`, each row representing a 1-minute window.

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
├── docker-compose.yml          # Orchestrates all 4 services
├── database/
│   └── schema.sql              # Auto-applied on Postgres first start
├── producer/
│   ├── producer.py             # Kafka event generator (confluent-kafka + Faker)
│   └── requirements.txt        # confluent-kafka, faker, python-dateutil
├── spark-streaming/
│   ├── spark_job.py            # PySpark Structured Streaming job
│   ├── Dockerfile              # eclipse-temurin:17-jre + PySpark + connector JARs
│   └── entrypoint.sh           # spark-submit wrapper (auto-discovers JARs)
└── docs/
    └── progress.md             # Session-by-session build log
```

---

## License

MIT
