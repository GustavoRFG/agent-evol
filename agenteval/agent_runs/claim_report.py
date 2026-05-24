"""Aggregate per-result claim-vs-verified summaries into per-agent rollups.

Week 6 Day 5 compares one :class:`AgentRunArtifact` against one
:class:`EvaluationResult` and produces a per-result
:class:`ClaimVerificationSummary`. This module rolls those summaries up by
``agent_name`` so callers can answer "did agent X overclaim?", "which runs
mismatched?", and "what are the global totals?" without re-deriving anything.

It performs no I/O, no agent execution, no patch application, and no test
execution. Scoring and :class:`EvaluationResult.weaknesses` are not touched.
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.agent_runs.claim_analysis import (
    ClaimVerificationSummary,
    build_claim_verification_summaries,
)
from agenteval.core.schemas import EvaluationResult


class ClaimReportError(ValueError):
    """Raised when a :class:`ClaimAnalysisReport` cannot be built."""


@dataclass
class AgentClaimRollup:
    """Per-agent counters over a batch of :class:`ClaimVerificationSummary`.

    Public and hidden buckets are tallied independently — a single result
    that overclaims on both buckets contributes 1 to ``mismatching_claims``
    (one *result* with mismatches) but 2 to the bucket-level
    ``public_mismatches`` + ``hidden_mismatches`` totals, and 2 to
    ``overclaims``. ``mismatch_run_ids`` is the deduplicated, order-preserved
    list of run_ids with at least one mismatched bucket.

    The ``*_rate`` and ``claim_reliability`` properties are derived,
    informational metrics — they do not affect scoring or comparison ranking
    and return ``None`` when the relevant denominator is zero. No rounding is
    applied at the data-model layer; rendering decides display formatting.
    """

    agent_name: str
    total_results: int = 0
    results_with_any_claim: int = 0
    results_with_no_claim: int = 0
    matching_claims: int = 0
    mismatching_claims: int = 0
    public_mismatches: int = 0
    hidden_mismatches: int = 0
    overclaims: int = 0
    underclaims: int = 0
    mismatch_run_ids: list[str] = field(default_factory=list)

    @property
    def explicit_claims(self) -> int:
        """Number of bucket-level explicit claims (matches + mismatches)."""
        return self.matching_claims + self.mismatching_claims

    @property
    def claim_reliability(self) -> float | None:
        """Fraction of explicit claims that matched verified outcomes."""
        explicit = self.explicit_claims
        if explicit <= 0:
            return None
        return self.matching_claims / explicit

    @property
    def mismatch_rate(self) -> float | None:
        """Fraction of explicit claims that disagreed with verified outcomes."""
        explicit = self.explicit_claims
        if explicit <= 0:
            return None
        return self.mismatching_claims / explicit

    @property
    def overclaim_rate(self) -> float | None:
        """Fraction of explicit claims that overclaimed (claimed pass, was fail)."""
        explicit = self.explicit_claims
        if explicit <= 0:
            return None
        return self.overclaims / explicit

    @property
    def underclaim_rate(self) -> float | None:
        """Fraction of explicit claims that underclaimed (claimed fail, was pass)."""
        explicit = self.explicit_claims
        if explicit <= 0:
            return None
        return self.underclaims / explicit

    @property
    def no_claim_rate(self) -> float | None:
        """Fraction of results in which the agent made no claim at all."""
        if self.total_results <= 0:
            return None
        return self.results_with_no_claim / self.total_results


@dataclass
class ClaimAnalysisReport:
    """A claim-vs-verified report aggregated across many runs and agents.

    ``summaries`` keeps the original per-result order. ``rollups_by_agent`` is
    inserted in deterministic alphabetical order so iteration is stable.
    """

    summaries: list[ClaimVerificationSummary] = field(default_factory=list)
    rollups_by_agent: dict[str, AgentClaimRollup] = field(default_factory=dict)
    total_summaries: int = 0
    total_mismatches: int = 0
    total_overclaims: int = 0
    total_underclaims: int = 0


def _validate_summaries(summaries: object) -> list[ClaimVerificationSummary]:
    if not isinstance(summaries, list):
        raise ClaimReportError(
            f"summaries must be a list, got {type(summaries).__name__}"
        )
    for index, summary in enumerate(summaries):
        if not isinstance(summary, ClaimVerificationSummary):
            raise ClaimReportError(
                f"summaries[{index}] must be a ClaimVerificationSummary, "
                f"got {type(summary).__name__}"
            )
    return summaries


def _bucket_contribution(
    *, claim: bool | None, verified: bool
) -> tuple[bool, bool, bool]:
    """Return ``(is_match, is_overclaim, is_underclaim)`` for one bucket.

    ``(False, False, False)`` is returned when the agent made no claim for
    this bucket (``claim is None``); the bucket contributes nothing.
    """
    if claim is None:
        return False, False, False
    if claim is verified:
        return True, False, False
    # Mismatch — distinguish over- and under-claim.
    return False, bool(claim and not verified), bool((not claim) and verified)


def build_claim_analysis_report(
    summaries: list[ClaimVerificationSummary],
) -> ClaimAnalysisReport:
    """Aggregate per-result claim summaries into a :class:`ClaimAnalysisReport`.

    Input order is preserved on ``summaries`` and on each agent's
    ``mismatch_run_ids``. Agent rollups are returned in alphabetical
    ``agent_name`` order for deterministic iteration.

    Raises:
        ClaimReportError: If ``summaries`` is not a list of
            :class:`ClaimVerificationSummary`.
    """
    validated = _validate_summaries(summaries)

    rollups: dict[str, AgentClaimRollup] = {}

    total_mismatches = 0
    total_overclaims = 0
    total_underclaims = 0

    for summary in validated:
        agent = summary.agent_name
        rollup = rollups.get(agent)
        if rollup is None:
            rollup = AgentClaimRollup(agent_name=agent)
            rollups[agent] = rollup

        rollup.total_results += 1
        if summary.has_any_claim:
            rollup.results_with_any_claim += 1
        else:
            rollup.results_with_no_claim += 1

        public_match, public_over, public_under = _bucket_contribution(
            claim=summary.claimed_public_tests_passed,
            verified=summary.verified_public_tests_passed,
        )
        hidden_match, hidden_over, hidden_under = _bucket_contribution(
            claim=summary.claimed_hidden_tests_passed,
            verified=summary.verified_hidden_tests_passed,
        )

        if public_match:
            rollup.matching_claims += 1
        if hidden_match:
            rollup.matching_claims += 1

        if public_over:
            rollup.public_mismatches += 1
            rollup.mismatching_claims += 1
            rollup.overclaims += 1
            total_overclaims += 1
        if public_under:
            rollup.public_mismatches += 1
            rollup.mismatching_claims += 1
            rollup.underclaims += 1
            total_underclaims += 1

        if hidden_over:
            rollup.hidden_mismatches += 1
            rollup.mismatching_claims += 1
            rollup.overclaims += 1
            total_overclaims += 1
        if hidden_under:
            rollup.hidden_mismatches += 1
            rollup.mismatching_claims += 1
            rollup.underclaims += 1
            total_underclaims += 1

        if summary.has_mismatch:
            total_mismatches += 1
            if summary.run_id not in rollup.mismatch_run_ids:
                rollup.mismatch_run_ids.append(summary.run_id)

    sorted_rollups: dict[str, AgentClaimRollup] = {
        name: rollups[name] for name in sorted(rollups)
    }

    return ClaimAnalysisReport(
        summaries=list(validated),
        rollups_by_agent=sorted_rollups,
        total_summaries=len(validated),
        total_mismatches=total_mismatches,
        total_overclaims=total_overclaims,
        total_underclaims=total_underclaims,
    )


def build_claim_analysis_report_from_artifacts_and_results(
    artifacts: list[AgentRunArtifact],
    results: list[EvaluationResult],
) -> ClaimAnalysisReport:
    """Build a :class:`ClaimAnalysisReport` directly from artifacts + results.

    Pairs artifacts and results by ``run_id`` via Week 6 Day 5's
    :func:`build_claim_verification_summaries`, then aggregates.

    Raises:
        ClaimReportError: If ``artifacts`` is not a list of
            :class:`AgentRunArtifact`, if ``results`` is not a list, or if
            two artifacts share the same ``run_id``.
    """
    if not isinstance(artifacts, list):
        raise ClaimReportError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )
    if not isinstance(results, list):
        raise ClaimReportError(
            f"results must be a list, got {type(results).__name__}"
        )

    artifacts_by_run_id: dict[str, AgentRunArtifact] = {}
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, AgentRunArtifact):
            raise ClaimReportError(
                f"artifacts[{index}] must be an AgentRunArtifact, "
                f"got {type(artifact).__name__}"
            )
        if artifact.run_id in artifacts_by_run_id:
            existing = artifacts_by_run_id[artifact.run_id]
            raise ClaimReportError(
                f"duplicate run_id={artifact.run_id!r} in artifacts "
                f"(agents {existing.agent_name!r} and {artifact.agent_name!r})"
            )
        artifacts_by_run_id[artifact.run_id] = artifact

    try:
        summaries = build_claim_verification_summaries(
            artifacts_by_run_id, results
        )
    except Exception as exc:
        raise ClaimReportError(
            f"failed to build claim verification summaries: {exc}"
        ) from exc

    return build_claim_analysis_report(summaries)


def format_optional_rate(value: float | None) -> str:
    """Render a 0–1 rate as a percentage with one decimal, or ``"n/a"``.

    ``None`` (the "no denominator" sentinel used throughout the rollup
    properties) is rendered as ``"n/a"`` so the table stays readable.
    """
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def summarize_agent_claim_reliability(rollup: AgentClaimRollup) -> str:
    """Return a short human-readable sentence about one agent's claim reliability.

    Examples:
        * ``"No explicit claims were made."``
        * ``"Claims matched verified outcomes 100.0% of the time."``
        * ``"Claims mismatched verified outcomes 50.0% of the time, with 2 overclaims."``
    """
    if not isinstance(rollup, AgentClaimRollup):
        raise ClaimReportError(
            f"rollup must be an AgentClaimRollup, got {type(rollup).__name__}"
        )
    if rollup.explicit_claims <= 0:
        return "No explicit claims were made."
    reliability = rollup.claim_reliability
    if rollup.mismatching_claims == 0:
        return (
            f"Claims matched verified outcomes "
            f"{format_optional_rate(reliability)} of the time."
        )
    mismatch_rate = rollup.mismatch_rate
    return (
        f"Claims mismatched verified outcomes "
        f"{format_optional_rate(mismatch_rate)} of the time, "
        f"with {rollup.overclaims} overclaim"
        f"{'s' if rollup.overclaims != 1 else ''}."
    )


def _format_run_ids(run_ids: list[str], limit: int = 5) -> str:
    if not run_ids:
        return "—"
    shown = run_ids[:limit]
    text = ", ".join(f"`{rid}`" for rid in shown)
    if len(run_ids) > limit:
        text += f", … (+{len(run_ids) - limit} more)"
    return text


def render_claim_analysis_report_markdown(
    report: ClaimAnalysisReport,
) -> str:
    """Render a :class:`ClaimAnalysisReport` as Markdown (no file I/O).

    Includes global totals, a per-agent rollup table, and a per-agent
    mismatch-detail section. A standing note reminds readers that claim
    analysis is informational only — it does not change scores.
    """
    if not isinstance(report, ClaimAnalysisReport):
        raise ClaimReportError(
            f"report must be a ClaimAnalysisReport, got {type(report).__name__}"
        )

    lines: list[str] = ["# Agent claim analysis report", ""]

    lines.append("## Totals")
    lines.append("")
    lines.append(f"- Total summaries: {report.total_summaries}")
    lines.append(f"- Results with at least one mismatched bucket: {report.total_mismatches}")
    lines.append(f"- Overclaims (claimed pass, verified fail): {report.total_overclaims}")
    lines.append(f"- Underclaims (claimed fail, verified pass): {report.total_underclaims}")
    lines.append("")

    lines.append("## Per-agent rollup")
    lines.append("")
    if not report.rollups_by_agent:
        lines.append("_No agents in this report._")
    else:
        lines.append(
            "| Agent | Total | With claims | No claims | Mismatches | "
            "Overclaims | Underclaims | Public mism. | Hidden mism. | "
            "Reliability | Mismatch rate | Overclaim rate | "
            "Underclaim rate | No-claim rate |"
        )
        lines.append(
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: | ---: |"
        )
        for name, rollup in report.rollups_by_agent.items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        name,
                        str(rollup.total_results),
                        str(rollup.results_with_any_claim),
                        str(rollup.results_with_no_claim),
                        str(rollup.mismatching_claims),
                        str(rollup.overclaims),
                        str(rollup.underclaims),
                        str(rollup.public_mismatches),
                        str(rollup.hidden_mismatches),
                        format_optional_rate(rollup.claim_reliability),
                        format_optional_rate(rollup.mismatch_rate),
                        format_optional_rate(rollup.overclaim_rate),
                        format_optional_rate(rollup.underclaim_rate),
                        format_optional_rate(rollup.no_claim_rate),
                    ]
                )
                + " |"
            )
    lines.append("")

    lines.append("## Mismatch details")
    lines.append("")
    any_mismatches = False
    for name, rollup in report.rollups_by_agent.items():
        if not rollup.mismatch_run_ids:
            continue
        any_mismatches = True
        lines.append(
            f"- **{name}** — mismatched run_ids: "
            f"{_format_run_ids(rollup.mismatch_run_ids)}"
        )
    if not any_mismatches:
        lines.append("_No mismatches recorded._")
    lines.append("")

    lines.append(
        "_Note: claim analysis is informational. It does not affect "
        "EvaluationResult scores or weaknesses unless a caller explicitly "
        "chooses to apply it._"
    )
    return "\n".join(lines) + "\n"


__all__ = [
    "AgentClaimRollup",
    "ClaimAnalysisReport",
    "ClaimReportError",
    "build_claim_analysis_report",
    "build_claim_analysis_report_from_artifacts_and_results",
    "format_optional_rate",
    "render_claim_analysis_report_markdown",
    "summarize_agent_claim_reliability",
]
