"""Hidden tests for ``bugfix_002`` — cover the empty-list edge case."""

from safe_average import safe_average


def test_empty_list_returns_zero_float():
    result = safe_average([])
    assert result == 0.0
    assert isinstance(result, float)


def test_single_element_list():
    assert safe_average([7]) == 7
