"""Public tests for ``bugfix_005`` — cover strictly inside / strictly outside."""

from is_within_range import is_within_range


def test_value_strictly_inside_range():
    assert is_within_range(5, 1, 10) is True


def test_value_strictly_outside_range():
    assert is_within_range(15, 1, 10) is False
