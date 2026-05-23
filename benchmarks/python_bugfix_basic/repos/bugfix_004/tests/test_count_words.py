"""Public tests for ``bugfix_004`` — cover normal-string behaviour."""

from count_words import count_words


def test_counts_words_in_sentence():
    assert count_words("the quick brown fox") == 4


def test_counts_single_word():
    assert count_words("hello") == 1
