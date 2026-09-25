"""Rule-based anomaly detection for individual order events."""


def is_anomaly(revenue, threshold: float) -> bool:
    """Flag an order whose revenue (price x quantity) exceeds `threshold`."""
    if revenue is None:
        return False
    return revenue > threshold
