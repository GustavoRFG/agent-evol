"""Hidden tests for ``bugfix_004`` — cover None and non-string inputs."""

import pytest

from count_words import count_words


def test_none_input_returns_zero():
    assert count_words(None) == 0


def test_non_string_input_raises_type_error():
    with pytest.raises(TypeError):
        count_words(42)
