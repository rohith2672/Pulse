import pytest

from anomaly import is_anomaly


@pytest.mark.parametrize(
    ("revenue", "threshold", "expected"),
    [
        (1500.01, 1500, True),
        (1500.0, 1500, False),
        (1499.99, 1500, False),
        (0.0, 0, False),
        (None, 1500, False),
    ],
)
def test_is_anomaly(revenue, threshold, expected):
    assert is_anomaly(revenue, threshold) is expected
