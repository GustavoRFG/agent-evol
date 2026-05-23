"""Reference implementation for the ``bugfix_003`` benchmark task.

The implementation is intentionally broken: it lowercases and collapses
internal whitespace correctly, but it does not strip leading or trailing
whitespace from the input.
"""

import re


def normalize_name(name):
    """Return ``name`` lowercased with internal whitespace runs collapsed.

    Should also strip leading and trailing whitespace, but currently does
    not.
    """
    return re.sub(r"\s+", " ", name.lower())
