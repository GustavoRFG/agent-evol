"""Public tests for ``bugfix_001`` — cover basic inclusive-range behaviour."""

from sum_range import sum_range


def test_basic_range():
    assert sum_range(1, 3) == 6


def test_single_element():
    assert sum_range(5, 5) == 5
