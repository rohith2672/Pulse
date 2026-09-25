"""Row-level validation rules for incoming order events."""

from datetime import datetime

REQUIRED_STRING_FIELDS = (
    "event_id",
    "order_id",
    "user_id",
    "product_id",
    "category",
    "city",
    "event_timestamp",
)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_iso_timestamp(value: str):
    # Python < 3.11 (the Spark image ships 3.10) rejects a trailing "Z".
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def validate_order(order) -> list:
    """Return the list of reasons `order` is invalid; an empty list means valid."""
    # Spark's from_json yields an all-null struct for unparseable input.
    if order is None or all(v is None for v in order.values()):
        return ["malformed_json"]

    errors = []

    for field in REQUIRED_STRING_FIELDS:
        value = order.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"missing_{field}")

    price = order.get("price")
    if price is None:
        errors.append("missing_price")
    elif not _is_number(price) or price <= 0:
        errors.append("invalid_price")

    quantity = order.get("quantity")
    if quantity is None:
        errors.append("missing_quantity")
    elif not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        errors.append("invalid_quantity")

    timestamp = order.get("event_timestamp")
    if isinstance(timestamp, str) and timestamp.strip():
        try:
            _parse_iso_timestamp(timestamp)
        except ValueError:
            errors.append("invalid_event_timestamp")

    return errors
