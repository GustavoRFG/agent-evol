"""Aggregate external agent artifacts into :class:`RunReport` objects.

This module composes existing Week 2/3/5 helpers to turn a list of external
:class:`AgentRunArtifact` objects into a pack-scoped :class:`RunReport`, while
preserving the unverified boundary established in Week 5 Days 4 and 5: no
patches are applied, no tests are executed, and the agent's ``claimed_*`` test
flags are never trusted as real outcomes.

Standard library only.
"""

from __future__ import annotations

from pathlib import Path

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.agent_runs.discovery import load_agent_run_artifacts_from_dir
from agenteval.agent_runs.evaluation import (
    AgentRunEvaluationError,
    build_evaluation_result_from_ingested_run,
)
from agenteval.agent_runs.ingestion import (
    AgentRunIngestionError,
    ingest_agent_run_artifact,
)
from agenteval.core.schemas import (
    BenchmarkPack,
    EvaluationResult,
    RunReport,
    TaskSpec,
)
from agenteval.evaluation.batch_builder import build_run_for_task
from agenteval.evaluation.result_builder import build_unverified_result
from agenteval.reports.run_report import build_run_report

_UNATTEMPTED_RATIONALE = (
    "No external agent artifact was provided for this task; result recorded "
    "as unverified by AgentEval Forge."
)


class AgentRunReportingError(ValueError):
    """Raised when building a :class:`RunReport` from artifacts fails."""


def _check_agent_name(agent_name: str) -> None:
    if not isinstance(agent_name, str) or not agent_name.strip():
        raise AgentRunReportingError("agent_name must be a non-empty string")


def _select_artifacts_for_agent(
    pack: BenchmarkPack,
    agent_name: str,
    artifacts: list[AgentRunArtifact],
) -> dict[str, AgentRunArtifact]:
    """Filter to this agent's artifacts, indexed by task_id.

    Raises:
        AgentRunReportingError: For unknown task_ids or duplicate artifacts for
            the same (agent_name, task_id) pair.
    """
    pack_task_ids = {task.task_id for task in pack.tasks}
    by_task_id: dict[str, AgentRunArtifact] = {}
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, AgentRunArtifact):
            raise AgentRunReportingError(
                f"artifacts[{index}] must be an AgentRunArtifact, "
                f"got {type(artifact).__name__}"
            )
        if artifact.agent_name != agent_name:
            continue
        if artifact.task_id not in pack_task_ids:
            raise AgentRunReportingError(
                f"artifact for agent={agent_name!r} references task_id="
                f"{artifact.task_id!r} which is not in pack {pack.name!r} "
                f"(run_id={artifact.run_id!r})"
            )
        if artifact.task_id in by_task_id:
            existing = by_task_id[artifact.task_id]
            raise AgentRunReportingError(
                f"duplicate artifacts for agent={agent_name!r} task_id="
                f"{artifact.task_id!r}: run_ids "
                f"{existing.run_id!r} and {artifact.run_id!r}"
            )
        by_task_id[artifact.task_id] = artifact
    return by_task_id


def _unverified_result_for_missing_task(
    task: TaskSpec, agent_name: str
) -> EvaluationResult:
    run = build_run_for_task(task, agent_name)
    return build_unverified_result(task, run, rationale=_UNATTEMPTED_RATIONALE)


def build_run_report_from_agent_artifacts(
    pack: BenchmarkPack,
    agent_name: str,
    artifacts: list[AgentRunArtifact],
) -> RunReport:
    """Build a :class:`RunReport` for one agent from external artifacts.

    Behavior:

    * Only artifacts whose ``agent_name`` matches the requested agent are used.
    * Every used artifact's ``task_id`` must belong to ``pack``.
    * At most one artifact per task per agent is allowed.
    * Tasks in ``pack`` that have no matching artifact become unverified
      results (:class:`WeaknessCode.VERIFY`).
    * The final report preserves ``pack.tasks`` order.
    * No patches are applied; no tests are run; agent claims are not trusted.

    Raises:
        AgentRunReportingError: For invalid ``agent_name``, non-list
            ``artifacts``, an artifact targeting an unknown task, duplicate
            artifacts for the same agent/task, or ingestion/evaluation
            failures (with run_id context).
    """
    _check_agent_name(agent_name)
    if not isinstance(pack, BenchmarkPack):
        raise AgentRunReportingError(
            f"pack must be a BenchmarkPack, got {type(pack).__name__}"
        )
    if not isinstance(artifacts, list):
        raise AgentRunReportingError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    selected = _select_artifacts_for_agent(pack, agent_name, artifacts)

    results: list[EvaluationResult] = []
    for task in pack.tasks:
        artifact = selected.get(task.task_id)
        if artifact is None:
            results.append(_unverified_result_for_missing_task(task, agent_name))
            continue
        try:
            ingested = ingest_agent_run_artifact(artifact)
        except AgentRunIngestionError as exc:
            raise AgentRunReportingError(
                f"failed to ingest artifact for agent={agent_name!r} "
                f"task_id={task.task_id!r} (run_id={artifact.run_id!r}): {exc}"
            ) from exc
        try:
            results.append(
                build_evaluation_result_from_ingested_run(task, ingested)
            )
        except AgentRunEvaluationError as exc:
            raise AgentRunReportingError(
                f"failed to evaluate artifact for agent={agent_name!r} "
                f"task_id={task.task_id!r} (run_id={artifact.run_id!r}): {exc}"
            ) from exc

    return build_run_report(pack, agent_name, results)


def build_run_reports_from_agent_artifacts(
    pack: BenchmarkPack,
    artifacts: list[AgentRunArtifact],
) -> list[RunReport]:
    """Build one :class:`RunReport` per distinct agent in ``artifacts``.

    Reports are returned sorted by ``agent_name`` for deterministic ordering.
    An empty ``artifacts`` list yields an empty list.
    """
    if not isinstance(pack, BenchmarkPack):
        raise AgentRunReportingError(
            f"pack must be a BenchmarkPack, got {type(pack).__name__}"
        )
    if not isinstance(artifacts, list):
        raise AgentRunReportingError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    agent_names: list[str] = []
    seen: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, AgentRunArtifact):
            raise AgentRunReportingError(
                f"artifacts[{index}] must be an AgentRunArtifact, "
                f"got {type(artifact).__name__}"
            )
        name = artifact.agent_name
        if name not in seen:
            seen.add(name)
            agent_names.append(name)

    return [
        build_run_report_from_agent_artifacts(pack, name, artifacts)
        for name in sorted(agent_names)
    ]


def build_run_reports_from_agent_artifact_dir(
    pack: BenchmarkPack,
    root: str | Path,
    *,
    skip_invalid: bool = False,
) -> list[RunReport]:
    """Load every artifact under ``root`` and aggregate into per-agent reports.

    This is a thin convenience over :func:`load_agent_run_artifacts_from_dir`
    + :func:`build_run_reports_from_agent_artifacts`. It still applies no
    patches and runs no tests.
    """
    artifacts = load_agent_run_artifacts_from_dir(
        root, skip_invalid=skip_invalid
    )
    return build_run_reports_from_agent_artifacts(pack, artifacts)


__all__ = [
    "AgentRunReportingError",
    "build_run_report_from_agent_artifacts",
    "build_run_reports_from_agent_artifact_dir",
    "build_run_reports_from_agent_artifacts",
]
