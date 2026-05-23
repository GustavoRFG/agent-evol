# bugfix_005 — Make `is_within_range` inclusive of both numeric boundaries

## Function to fix

`is_within_range(value, low, high)` in `is_within_range.py`.

## Expected behaviour

- Return `True` when `value` lies between `low` and `high` inclusive,
  and `False` otherwise.
- Do not change the signature or the behaviour for values strictly
  inside or strictly outside the range.

## Tests

- The public tests in `tests/test_is_within_range.py` cover values that
  are strictly inside or strictly outside the range.
- The hidden tests in `tests/test_is_within_range_hidden.py` cover the
  lower and upper boundary inclusivity cases.
