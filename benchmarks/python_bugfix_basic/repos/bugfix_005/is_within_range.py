"""Reference implementation for the ``bugfix_005`` benchmark task.

The implementation is intentionally broken: it uses strict inequalities,
so values exactly equal to ``low`` or ``high`` are wrongly reported as
outside the range.
"""


def is_within_range(value, low, high):
    """Return ``True`` when ``value`` lies between ``low`` and ``high``.

    The function should be inclusive on both bounds, but currently uses
    strict inequalities.
    """
    return low < value < high
