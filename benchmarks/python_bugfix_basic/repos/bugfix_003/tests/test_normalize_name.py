"""Public tests for ``bugfix_003`` — cover lowercasing and internal collapse."""

from normalize_name import normalize_name


def test_lowercases_letters():
    assert normalize_name("Ada Lovelace") == "ada lovelace"


def test_collapses_internal_spaces():
    assert normalize_name("Ada    Lovelace") == "ada lovelace"
