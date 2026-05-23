"""Hidden tests for ``bugfix_001`` — cover endpoint and negative-range edges."""

from sum_range import sum_range


def test_endpoint_is_included():
    assert sum_range(1, 4) == 10


def test_negative_range():
    assert sum_range(-3, 2) == -3
