# bugfix_004 — Guard `count_words` against `None` and non-string input

## Function to fix

`count_words(text)` in `count_words.py`.

## Expected behaviour

- For a non-empty string, return the number of whitespace-separated words.
- For `None` or an empty string, return `0`.
- For any other (non-`None`, non-`str`) input, raise `TypeError` with a
  clear message.
- Do not change the signature or the behaviour for normal strings.

## Tests

- The public tests in `tests/test_count_words.py` cover the normal-string
  cases.
- The hidden tests in `tests/test_count_words_hidden.py` cover the `None`
  and non-string input cases.
