"""Parse unified diff text into a structured :class:`PatchSummary`.

This module turns the raw diff produced by an agent into patch *evidence*:
which files were changed, added, or deleted. It only reads text — it does not
apply patches, touch the filesystem, or run any tests. Standard library only.

Supported unified diff headers (common ``git diff`` output):

* modified file::

    diff --git a/file.py b/file.py
    --- a/file.py
    +++ b/file.py

* added file::

    --- /dev/null
    +++ b/new_file.py

* deleted file::

    --- a/old_file.py
    +++ /dev/null
"""

from __future__ import annotations

from agenteval.core.schemas import PatchSummary

_DEV_NULL = "/dev/null"
_DIFF_GIT_PREFIX = "diff --git "


def parse_unified_diff(diff_text: str) -> PatchSummary:
    """Parse unified diff text into a :class:`PatchSummary`.

    The original ``diff_text`` is always preserved verbatim on the returned
    summary. File lists keep the order in which files first appear and contain
    no duplicates. An empty or whitespace-only diff yields a summary with empty
    file lists.

    Args:
        diff_text: Unified diff text (typically ``git diff`` output).

    Returns:
        A :class:`PatchSummary` with ``changed_files``, ``added_files``,
        ``deleted_files``, and the preserved ``diff_text``.
    """
    summary = PatchSummary(diff_text=diff_text)

    if not diff_text or not diff_text.strip():
        return summary

    changed: list[str] = []
    added: list[str] = []
    deleted: list[str] = []
    buckets = {"changed": changed, "added": added, "deleted": deleted}

    for block in _split_into_file_blocks(diff_text):
        classification, path = _classify_block(block)
        if path is None:
            continue
        bucket = buckets[classification]
        if path not in bucket:  # deterministic order, no duplicates
            bucket.append(path)

    summary.changed_files = changed
    summary.added_files = added
    summary.deleted_files = deleted
    return summary


def _split_into_file_blocks(diff_text: str) -> list[list[str]]:
    """Split diff text into per-file blocks, one block per ``diff --git`` header.

    If the diff contains no ``diff --git`` header, the whole text is returned as
    a single block (handles a plain single-file unified diff).
    """
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in diff_text.splitlines():
        if line.startswith(_DIFF_GIT_PREFIX):
            if current:
                blocks.append(current)
            current = [line]
        else:
            current.append(line)

    if current:
        blocks.append(current)
    return blocks


def _classify_block(lines: list[str]) -> tuple[str, str | None]:
    """Classify one file block and return ``(classification, path)``.

    ``classification`` is one of ``"changed"``, ``"added"``, ``"deleted"``.
    ``path`` is ``None`` when the block describes no file. Only header lines
    (before the first ``@@`` hunk) are inspected, so diff *content* lines can
    never be mistaken for headers.
    """
    git_path: str | None = None
    minus_path: str | None = None
    plus_path: str | None = None

    for line in lines:
        if line.startswith("@@"):
            break  # headers always precede the first hunk
        if line.startswith(_DIFF_GIT_PREFIX):
            git_path = _parse_diff_git_line(line)
        elif line.startswith("--- ") and minus_path is None:
            minus_path = _extract_path(line[4:])
        elif line.startswith("+++ ") and plus_path is None:
            plus_path = _extract_path(line[4:])

    if minus_path is not None and plus_path is not None:
        if minus_path == _DEV_NULL:
            return "added", _normalize(plus_path)
        if plus_path == _DEV_NULL:
            return "deleted", _normalize(minus_path)
        return "changed", _normalize(plus_path)

    # No ---/+++ headers (e.g. a pure rename or mode change): fall back to the
    # path from the "diff --git" line and treat it as a change.
    if git_path is not None:
        return "changed", git_path
    return "changed", None


def _parse_diff_git_line(line: str) -> str | None:
    """Extract the normalized file path from a ``diff --git a/X b/Y`` line."""
    rest = line[len(_DIFF_GIT_PREFIX):].strip()
    tokens = rest.split()
    if not tokens:
        return None
    return _normalize(tokens[-1])


def _extract_path(text: str) -> str:
    """Extract a file path from the text following ``--- `` or ``+++ ``.

    Non-git unified diffs may append a tab and timestamp; only the part before
    the first tab is kept.
    """
    return text.split("\t", 1)[0].strip()


def _normalize(path: str) -> str:
    """Strip a leading ``a/`` or ``b/`` prefix from a diff path."""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path
