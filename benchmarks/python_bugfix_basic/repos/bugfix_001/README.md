# bugfix_001 — Fix off-by-one error in inclusive range summation

## Function to fix

`sum_range(start, end)` in `sum_range.py`.

## Expected behaviour

- Return the sum of every integer from `start` to `end` inclusive.
- `sum_range(1, 3)` should return `6` (1 + 2 + 3).
- `sum_range(5, 5)` should return `5`.
- Negative ranges should work as long as `start <= end`.
- Do not change the function signature.

## Tests

- The public tests in `tests/test_sum_range.py` cover the basic
  inclusive-range behaviour and the single-element case.
- The hidden tests in `tests/test_sum_range_hidden.py` cover the
  endpoint-inclusion edge case and a negative-range case.
