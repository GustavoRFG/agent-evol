"""Reference implementation for the ``bugfix_004`` benchmark task.

The implementation is intentionally broken: it calls ``text.split()``
unconditionally. ``None`` therefore raises ``AttributeError``, and other
non-string types fail with confusing low-level errors instead of a clear
``TypeError``.
"""


def count_words(text):
    """Return the number of whitespace-separated words in ``text``.

    Should return ``0`` for ``None`` or an empty string and raise
    ``TypeError`` for other non-string inputs, but currently does neither.
    """
    return len(text.split())
