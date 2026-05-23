"""Reference implementation for the ``bugfix_002`` benchmark task.

The implementation is intentionally broken: it does not guard the empty-list
case and therefore raises ``ZeroDivisionError`` when called with ``[]``.
"""


def safe_average(values):
    """Return the arithmetic mean of ``values``.

    Should return ``0.0`` for an empty list, but currently divides by zero.
    """
    return sum(values) / len(values)
