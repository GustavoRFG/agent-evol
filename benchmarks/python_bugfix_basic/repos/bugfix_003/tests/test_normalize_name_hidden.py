"""Hidden tests for ``bugfix_003`` — cover leading/trailing whitespace."""

from normalize_name import normalize_name


def test_strips_leading_whitespace():
    assert normalize_name("   Ada Lovelace") == "ada lovelace"


def test_strips_trailing_whitespace():
    assert normalize_name("Ada Lovelace   ") == "ada lovelace"
