"""Hidden tests for ``bugfix_005`` — cover lower and upper boundary inclusivity."""

from is_within_range import is_within_range


def test_lower_bound_is_inclusive():
    assert is_within_range(1, 1, 10) is True


def test_upper_bound_is_inclusive():
    assert is_within_range(10, 1, 10) is True
