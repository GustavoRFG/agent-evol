"""Reference implementation for the ``bugfix_001`` benchmark task.

The implementation is intentionally broken: it uses ``range(start, end)``
instead of ``range(start, end + 1)``, so the endpoint is excluded from the
summation.
"""


def sum_range(start, end):
    """Return the sum of every integer from ``start`` to ``end`` inclusive.

    Currently off by one: the endpoint is excluded from the sum.
    """
    total = 0
    for value in range(start, end):
        total += value
    return total
