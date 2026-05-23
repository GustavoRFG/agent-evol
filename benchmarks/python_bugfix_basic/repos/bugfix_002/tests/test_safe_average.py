"""Public tests for ``bugfix_002`` — cover basic averaging behaviour."""

from safe_average import safe_average


def test_simple_integer_average():
    assert safe_average([1, 2, 3, 4]) == 2.5


def test_average_of_floats():
    assert safe_average([0.5, 1.5, 2.5]) == 1.5
