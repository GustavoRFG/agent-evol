"""Attach patch evidence to an :class:`EvaluationResult`.

These producer helpers take raw unified diff text (as a coding agent would
emit it), parse it into a :class:`PatchSummary`, and return an
:class:`EvaluationResult` that carries the patch evidence.

They perform **no** agent execution, patch application, or test execution —
they only move already-textual diff evidence into the data model. Standard
library only.
"""

from __future__ import annotations

from dataclasses import replace

from agenteval.core.schemas import EvaluationResult, PatchSummary
from agenteval.patches.diff_summary import parse_unified_diff


def attach_patch_to_result(
    result: EvaluationResult,
    diff_text: str,
) -> EvaluationResult:
    """Parse ``diff_text`` and return a copy of ``result`` carrying it.

    The diff is parsed via :func:`parse_unified_diff`. The original ``result``
    is **not** mutated: a new :class:`EvaluationResult` is returned with every
    existing field preserved and only ``patch_summary`` set. An empty or
    whitespace-only diff still produces a :class:`PatchSummary` (empty file
    lists, ``diff_text`` preserved verbatim).

    Args:
        result: The evaluation result to attach evidence to.
        diff_text: Raw unified diff text.

    Returns:
        A new :class:`EvaluationResult` with ``patch_summary`` populated.
    """
    patch_summary = parse_unified_diff(diff_text)
    return replace(result, patch_summary=patch_summary)


def attach_patch_summary_to_result(
    result: EvaluationResult,
    patch_summary: PatchSummary,
) -> EvaluationResult:
    """Return a copy of ``result`` with an existing ``patch_summary`` attached.

    The original ``result`` is **not** mutated. Useful when a
    :class:`PatchSummary` has already been built elsewhere.

    Args:
        result: The evaluation result to attach evidence to.
        patch_summary: An already-parsed patch summary.

    Returns:
        A new :class:`EvaluationResult` carrying ``patch_summary``.
    """
    return replace(result, patch_summary=patch_summary)
