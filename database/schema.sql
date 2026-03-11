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
