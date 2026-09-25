-- Pulse PostgreSQL Schema
-- Automatically applied on first container start via /docker-entrypoint-initdb.d/

-- ── Category metrics ──────────────────────────────────────────────────────────
-- One row per (category, 1-minute tumbling window), written after the watermark
-- guarantees no more late events for that window.

CREATE TABLE IF NOT EXISTS category_metrics (
    id              BIGSERIAL    PRIMARY KEY,
    window_start    TIMESTAMPTZ  NOT NULL,
    window_end      TIMESTAMPTZ  NOT NULL,
    category        VARCHAR(100) NOT NULL,
    total_revenue   NUMERIC(14, 2),
    order_count     BIGINT,
    avg_order_value NUMERIC(10, 2),
    total_quantity  BIGINT,
    total_tax       NUMERIC(14, 2),
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT uq_category_window UNIQUE (window_start, window_end, category)
);

CREATE INDEX IF NOT EXISTS idx_cat_window   ON category_metrics (window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_cat_category ON category_metrics (category);

-- ── City metrics ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS city_metrics (
    id            BIGSERIAL    PRIMARY KEY,
    window_start  TIMESTAMPTZ  NOT NULL,
    window_end    TIMESTAMPTZ  NOT NULL,
    city          VARCHAR(200) NOT NULL,
    total_revenue NUMERIC(14, 2),
    order_count   BIGINT,
    created_at    TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT uq_city_window UNIQUE (window_start, window_end, city)
);

CREATE INDEX IF NOT EXISTS idx_city_window ON city_metrics (window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_city_city   ON city_metrics (city);

-- ── Category reference (enrichment lookup) ────────────────────────────────────
-- Read once by the Spark job at startup and broadcast-joined onto every order.

CREATE TABLE IF NOT EXISTS category_reference (
    category   VARCHAR(100) PRIMARY KEY,
    department VARCHAR(100) NOT NULL,
    tax_rate   NUMERIC(5, 4) NOT NULL
);

INSERT INTO category_reference (category, department, tax_rate) VALUES
    ('electronics', 'Technology',        0.0800),
    ('fashion',     'Apparel',           0.0600),
    ('home',        'Home & Living',     0.0700),
    ('beauty',      'Health & Beauty',   0.0650),
    ('sports',      'Outdoor & Fitness', 0.0700),
    ('books',       'Media',             0.0000),
    ('grocery',     'Food',              0.0200)
ON CONFLICT (category) DO NOTHING;

-- ── Dead-letter queue ─────────────────────────────────────────────────────────
-- Events that failed validation, kept verbatim with the reasons they failed.

CREATE TABLE IF NOT EXISTS orders_dlq (
    id                BIGSERIAL   PRIMARY KEY,
    raw_value         TEXT,
    validation_errors TEXT[]      NOT NULL,
    received_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dlq_received ON orders_dlq (received_at);

-- ── Order anomalies ───────────────────────────────────────────────────────────
-- Individual orders whose revenue exceeds ANOMALY_REVENUE_THRESHOLD.

CREATE TABLE IF NOT EXISTS order_anomalies (
    id          BIGSERIAL    PRIMARY KEY,
    event_id    VARCHAR(64)  NOT NULL,
    order_id    VARCHAR(64)  NOT NULL,
    category    VARCHAR(100) NOT NULL,
    department  VARCHAR(100),
    city        VARCHAR(200) NOT NULL,
    price       NUMERIC(10, 2),
    quantity    INTEGER,
    revenue     NUMERIC(14, 2),
    event_time  TIMESTAMPTZ  NOT NULL,
    flagged_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomaly_event_time ON order_anomalies (event_time);
CREATE INDEX IF NOT EXISTS idx_anomaly_category   ON order_anomalies (category);
