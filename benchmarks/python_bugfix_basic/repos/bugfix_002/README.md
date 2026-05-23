# bugfix_002 — Return 0.0 from `safe_average` for an empty input list

## Function to fix

`safe_average(values)` in `safe_average.py`.

## Expected behaviour

- For a non-empty iterable of numbers, return the arithmetic mean of the
  values (a `float`).
- For an empty list, return `0.0` instead of raising `ZeroDivisionError`.
- Do not change the signature or the behaviour for non-empty inputs.

## Tests

- The public tests in `tests/test_safe_average.py` cover the basic
  averaging behaviour.
- The hidden tests in `tests/test_safe_average_hidden.py` cover the
  empty-list edge case and a single-element list.
