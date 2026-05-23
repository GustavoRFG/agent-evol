# bugfix_003 — Make `normalize_name` strip leading and trailing whitespace

## Function to fix

`normalize_name(name)` in `normalize_name.py`.

## Expected behaviour

- Return a canonical form of a name: lowercased, with every run of
  internal whitespace collapsed to a single space, and with no leading
  or trailing whitespace.
- Do not change the signature or the behaviour for already-normalized
  inputs.

## Tests

- The public tests in `tests/test_normalize_name.py` cover lowercasing
  and the collapse of internal whitespace runs.
- The hidden tests in `tests/test_normalize_name_hidden.py` cover
  leading and trailing whitespace stripping.
