"""Verified per-agent :class:`RunReport` generation from external artifacts.

This is the verified counterpart of :mod:`agenteval.agent_runs.reporting`.
Week 5 Day 6 produced unverified per-agent ``RunReport``s by ingesting
artifacts and emitting :class:`WeaknessCode.VERIFY`-tagged results without
running anything. Week 6 Day 3 produces ``RunReport``s whose attempted-task
results are *real*: the artifact's diff is applied inside an isolated copy of
the fixture, public and hidden tests are executed via the Week 4 harness, and
the actual outcomes drive the :class:`EvaluationResult`. Tasks the agent did
not attempt are still recorded as unverified.

It performs **no** real agent execution and **no** network calls; the original
fixture is never patched. Standard library only.
"""

from __future__ import annotations

import re
from pathlib import Path

from agenteval.agent_runs.artifacts import AgentRunArtifact
from agenteval.agent_runs.discovery import load_agent_run_artifacts_from_dir
from agenteval.agent_runs.verification import (
    verify_agent_run_artifacts,
)
from agenteval.core.schemas import (
    BenchmarkPack,
    EvaluationResult,
    RunReport,
    TaskSpec,
)
from agenteval.evaluation.batch_builder import build_run_for_task
from agenteval.evaluation.result_builder import build_unverified_result
from agenteval.fixtures import TaskFixtureLayout
from agenteval.reports.run_report import build_run_report

_UNATTEMPTED_RATIONALE = (
    "No external agent artifact was provided for this task; result recorded "
    "as unverified by AgentEval Forge."
)

_UNSAFE_SUBDIR_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class VerifiedAgentRunReportingError(ValueError):
    """Raised when building a verified :class:`RunReport` from artifacts fails."""


def _check_agent_name(agent_name: str) -> None:
    if not isinstance(agent_name, str) or not agent_name.strip():
        raise VerifiedAgentRunReportingError(
            "agent_name must be a non-empty string"
        )


def _sanitize_for_subdir(value: str) -> str:
    cleaned = _UNSAFE_SUBDIR_CHARS.sub("_", value).strip("._-")
    return cleaned or "agent"


def _select_artifacts_for_agent(
    pack: BenchmarkPack,
    agent_name: str,
    artifacts: list[AgentRunArtifact],
) -> dict[str, AgentRunArtifact]:
    """Filter to this agent's artifacts, indexed by task_id.

    Mirrors the unverified-reporting selector — same rules for unknown tasks
    and same-agent duplicates — but raises the verified-reporting error type.
    """
    pack_task_ids = {task.task_id for task in pack.tasks}
    by_task_id: dict[str, AgentRunArtifact] = {}
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, AgentRunArtifact):
            raise VerifiedAgentRunReportingError(
                f"artifacts[{index}] must be an AgentRunArtifact, "
                f"got {type(artifact).__name__}"
            )
        if artifact.agent_name != agent_name:
            continue
        if artifact.task_id not in pack_task_ids:
            raise VerifiedAgentRunReportingError(
                f"artifact for agent={agent_name!r} references task_id="
                f"{artifact.task_id!r} which is not in pack {pack.name!r} "
                f"(run_id={artifact.run_id!r})"
            )
        if artifact.task_id in by_task_id:
            existing = by_task_id[artifact.task_id]
            raise VerifiedAgentRunReportingError(
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


def build_verified_run_report_from_agent_artifacts(
    pack: BenchmarkPack,
    agent_name: str,
    artifacts: list[AgentRunArtifact],
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> RunReport:
    """Build a verified :class:`RunReport` for one agent from external artifacts.

    Behavior mirrors :func:`build_run_report_from_agent_artifacts` (Week 5
    Day 6), but attempted tasks are actually verified — the patch is applied
    in an isolated copy of the fixture, public and hidden tests are run, and
    the real outcomes drive the result. Tasks the agent did not attempt are
    still recorded as unverified.

    Each agent's verification batch runs inside its own per-agent subfolder of
    ``workspace_root`` so concurrent agents (or sequential calls) cannot
    collide.

    Args:
        pack: The benchmark pack to report against.
        agent_name: Name of the agent whose artifacts should be used.
        artifacts: External artifacts; only those whose ``agent_name`` matches
            are verified.
        layouts_by_task_id: Resolved fixture layouts for the pack's tasks.
        workspace_root: Parent directory for the per-agent workspace folder.
        timeout_seconds: Subprocess timeout forwarded to verification.
        continue_on_error: When ``True``, per-run verification failures become
            unverified results in the final report; when ``False``, they are
            propagated as :class:`VerifiedAgentRunReportingError`.

    Raises:
        VerifiedAgentRunReportingError: For invalid arguments, unknown tasks,
            duplicate artifacts for the same agent, or — when
            ``continue_on_error`` is ``False`` — the first verification
            failure (with run_id / task_id context).
    """
    _check_agent_name(agent_name)
    if not isinstance(pack, BenchmarkPack):
        raise VerifiedAgentRunReportingError(
            f"pack must be a BenchmarkPack, got {type(pack).__name__}"
        )
    if not isinstance(artifacts, list):
        raise VerifiedAgentRunReportingError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )
    if not isinstance(layouts_by_task_id, dict):
        raise VerifiedAgentRunReportingError(
            "layouts_by_task_id must be a dict, "
            f"got {type(layouts_by_task_id).__name__}"
        )

    selected = _select_artifacts_for_agent(pack, agent_name, artifacts)

    tasks_by_id = {task.task_id: task for task in pack.tasks}

    # Verify the selected artifacts (if any) inside a per-agent workspace.
    agent_workspace = Path(workspace_root) / _sanitize_for_subdir(agent_name)
    selected_artifacts = list(selected.values())

    try:
        verified_results = verify_agent_run_artifacts(
            tasks_by_id,
            selected_artifacts,
            layouts_by_task_id,
            workspace_root=agent_workspace,
            timeout_seconds=timeout_seconds,
            continue_on_error=continue_on_error,
        )
    except Exception as exc:
        # Surface batch-verification failures as a reporting error so callers
        # have a single exception type to catch from this entry point.
        raise VerifiedAgentRunReportingError(
            f"verification failed for agent={agent_name!r}: {exc}"
        ) from exc

    results_by_task_id: dict[str, EvaluationResult] = {}
    for artifact, result in zip(selected_artifacts, verified_results):
        results_by_task_id[artifact.task_id] = result

    # Assemble final results in pack-task order, filling unattempted slots.
    final_results: list[EvaluationResult] = []
    for task in pack.tasks:
        if task.task_id in results_by_task_id:
            final_results.append(results_by_task_id[task.task_id])
        else:
            final_results.append(
                _unverified_result_for_missing_task(task, agent_name)
            )

    return build_run_report(pack, agent_name, final_results)


def build_verified_run_reports_from_agent_artifacts(
    pack: BenchmarkPack,
    artifacts: list[AgentRunArtifact],
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> list[RunReport]:
    """Build one verified :class:`RunReport` per distinct agent in ``artifacts``.

    Reports are returned sorted by ``agent_name`` for deterministic ordering.
    An empty ``artifacts`` list yields an empty list.
    """
    if not isinstance(pack, BenchmarkPack):
        raise VerifiedAgentRunReportingError(
            f"pack must be a BenchmarkPack, got {type(pack).__name__}"
        )
    if not isinstance(artifacts, list):
        raise VerifiedAgentRunReportingError(
            f"artifacts must be a list, got {type(artifacts).__name__}"
        )

    agent_names: list[str] = []
    seen: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, AgentRunArtifact):
            raise VerifiedAgentRunReportingError(
                f"artifacts[{index}] must be an AgentRunArtifact, "
                f"got {type(artifact).__name__}"
            )
        name = artifact.agent_name
        if name not in seen:
            seen.add(name)
            agent_names.append(name)

    return [
        build_verified_run_report_from_agent_artifacts(
            pack,
            name,
            artifacts,
            layouts_by_task_id,
            workspace_root=workspace_root,
            timeout_seconds=timeout_seconds,
            continue_on_error=continue_on_error,
        )
        for name in sorted(agent_names)
    ]


def build_verified_run_reports_from_agent_artifact_dir(
    pack: BenchmarkPack,
    root: str | Path,
    layouts_by_task_id: dict[str, TaskFixtureLayout],
    *,
    workspace_root: str | Path,
    skip_invalid: bool = False,
    timeout_seconds: int = 30,
    continue_on_error: bool = True,
) -> list[RunReport]:
    """Load every artifact under ``root`` and aggregate into verified per-agent reports.

    Thin convenience over :func:`load_agent_run_artifacts_from_dir` +
    :func:`build_verified_run_reports_from_agent_artifacts`. Still no real
    agent execution.
    """
    artifacts = load_agent_run_artifacts_from_dir(
        root, skip_invalid=skip_invalid
    )
    return build_verified_run_reports_from_agent_artifacts(
        pack,
        artifacts,
        layouts_by_task_id,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
        continue_on_error=continue_on_error,
    )


__all__ = [
    "VerifiedAgentRunReportingError",
    "build_verified_run_report_from_agent_artifacts",
    "build_verified_run_reports_from_agent_artifact_dir",
    "build_verified_run_reports_from_agent_artifacts",
]
