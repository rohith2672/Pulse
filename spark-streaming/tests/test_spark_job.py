import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from spark_job import (
    compute_category_metrics,
    compute_city_metrics,
    detect_anomalies,
    enrich_orders,
    parse_and_validate,
    select_invalid,
    select_valid,
)


def order(**overrides):
    event = {
        "event_id": "evt-1",
        "order_id": "ord_1",
        "user_id": "usr_1",
        "product_id": "prd_1",
        "category": "electronics",
        "price": 100.0,
        "quantity": 2,
        "city": "Austin",
        "event_timestamp": "2026-03-11T10:00:15Z",
    }
    event.update(overrides)
    return event


def kafka_df(spark, *values):
    """Mimic the Kafka source: a binary `value` column."""
    rows = [
        (v.encode("utf-8") if isinstance(v, str) else json.dumps(v).encode("utf-8"),)
        for v in values
    ]
    return spark.createDataFrame(rows, "value binary")


@pytest.fixture
def reference(spark):
    # Matches the types Spark reads from Postgres NUMERIC(5, 4).
    return spark.createDataFrame(
        [
            ("electronics", "Technology", Decimal("0.0800")),
            ("books", "Media", Decimal("0.0000")),
        ],
        "category string, department string, tax_rate decimal(5,4)",
    )


def pipeline(spark, reference, *values):
    return enrich_orders(select_valid(parse_and_validate(kafka_df(spark, *values))), reference)


# ── Validation / DLQ ──────────────────────────────────────────────────────────

def test_valid_event_has_no_errors_and_parsed_time(spark):
    row = parse_and_validate(kafka_df(spark, order())).collect()[0]
    assert row.validation_errors == []
    assert row.event_time == datetime(2026, 3, 11, 10, 0, 15)
    assert row.category == "electronics"


def test_malformed_json_goes_to_dlq_with_raw_value(spark):
    validated = parse_and_validate(kafka_df(spark, "{not json", order()))
    dlq = select_invalid(validated).collect()
    assert len(dlq) == 1
    assert dlq[0].raw_value == "{not json"
    assert dlq[0].validation_errors == ["malformed_json"]
    assert select_valid(validated).count() == 1


def test_business_rule_violations_go_to_dlq(spark):
    validated = parse_and_validate(
        kafka_df(spark, order(price=-5.0), order(quantity=0), order(city=None))
    )
    errors = sorted(r.validation_errors[0] for r in select_invalid(validated).collect())
    assert errors == ["invalid_price", "invalid_quantity", "missing_city"]
    assert select_valid(validated).count() == 0


def test_bad_timestamp_reported_once(spark):
    validated = parse_and_validate(kafka_df(spark, order(event_timestamp="not-a-date")))
    assert select_invalid(validated).collect()[0].validation_errors == ["invalid_event_timestamp"]


def test_valid_orders_get_revenue(spark):
    row = select_valid(parse_and_validate(kafka_df(spark, order(price=19.5, quantity=3)))).collect()[0]
    assert row.revenue == pytest.approx(58.5)
    assert "raw_value" not in row.asDict()
    assert "validation_errors" not in row.asDict()


# ── Enrichment ────────────────────────────────────────────────────────────────

def test_enrichment_adds_department_and_tax(spark, reference):
    row = pipeline(spark, reference, order(price=100.0, quantity=2)).collect()[0]
    assert row.department == "Technology"
    assert row.tax_rate == pytest.approx(0.08)
    assert row.tax_amount == pytest.approx(16.0)


def test_unknown_category_is_kept_with_zero_tax(spark, reference):
    rows = pipeline(spark, reference, order(category="garden")).collect()
    assert len(rows) == 1
    assert rows[0].department is None
    assert rows[0].tax_amount == pytest.approx(0.0)


# ── Aggregation ───────────────────────────────────────────────────────────────

def test_category_metrics_per_window(spark, reference):
    enriched = pipeline(
        spark,
        reference,
        order(event_id="a", order_id="o1", price=100.0, quantity=2, event_timestamp="2026-03-11T10:00:10Z"),
        order(event_id="b", order_id="o2", price=50.0, quantity=1, event_timestamp="2026-03-11T10:00:50Z"),
        order(event_id="c", order_id="o3", price=10.0, quantity=1, event_timestamp="2026-03-11T10:01:05Z"),
        order(event_id="d", order_id="o4", category="books", price=20.0, quantity=1,
              event_timestamp="2026-03-11T10:00:30Z"),
    )
    rows = {
        (r.window_start, r.category): r
        for r in compute_category_metrics(enriched, "1 minute").collect()
    }
    assert len(rows) == 3

    first = rows[(datetime(2026, 3, 11, 10, 0), "electronics")]
    assert first.window_end == datetime(2026, 3, 11, 10, 1)
    assert first.total_revenue == pytest.approx(250.0)
    assert first.order_count == 2
    assert first.avg_order_value == pytest.approx(75.0)
    assert first.total_quantity == 3
    assert first.total_tax == pytest.approx(20.0)

    second = rows[(datetime(2026, 3, 11, 10, 1), "electronics")]
    assert second.order_count == 1
    assert second.total_tax == pytest.approx(0.8)

    books = rows[(datetime(2026, 3, 11, 10, 0), "books")]
    assert books.total_tax == pytest.approx(0.0)


def test_city_metrics_per_window(spark, reference):
    enriched = pipeline(
        spark,
        reference,
        order(event_id="a", city="Austin", price=10.0, quantity=1),
        order(event_id="b", city="Austin", price=20.0, quantity=2),
        order(event_id="c", city="Boston", price=5.0, quantity=1),
    )
    rows = {r.city: r for r in compute_city_metrics(enriched, "1 minute").collect()}
    assert rows["Austin"].total_revenue == pytest.approx(50.0)
    assert rows["Austin"].order_count == 2
    assert rows["Boston"].order_count == 1


# ── Anomaly branch ────────────────────────────────────────────────────────────

def test_detect_anomalies_flags_only_orders_above_threshold(spark, reference):
    enriched = pipeline(
        spark,
        reference,
        order(event_id="big", price=450.0, quantity=5),
        order(event_id="edge", price=300.0, quantity=5),
        order(event_id="small", price=10.0, quantity=1),
    )
    rows = detect_anomalies(enriched, 1500).collect()
    assert [r.event_id for r in rows] == ["big"]
    assert rows[0].revenue == pytest.approx(2250.0)
    assert rows[0].department == "Technology"
    assert rows[0].event_time == datetime(2026, 3, 11, 10, 0, 15)
    assert set(rows[0].asDict()) == {
        "event_id", "order_id", "category", "department", "city",
        "price", "quantity", "revenue", "event_time",
    }
