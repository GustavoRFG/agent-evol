"""In-memory standard format for an external agent run artifact.

AgentEval Forge does **not** execute agents. Real agents (Claude Code, Codex,
ForgeAgent, DGM, etc.) run outside this framework. The framework ingests the
artifacts they produce: diff text, transcript text, final message, claimed
commands, and metadata.

This module only defines and validates the in-memory shape of those artifacts.
It performs no disk I/O, no patch application, no test execution, and no
network calls. Standard library only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


class AgentRunArtifactError(ValueError):
    """Raised when an :class:`AgentRunArtifact` fails structural validation."""


@dataclass
class AgentRunArtifact:
    """Standard in-memory format for a single external agent run.

    The artifact captures what an external agent produced for one task on one
    run. It carries no execution semantics: ``diff_text`` is just text until a
    later pipeline stage parses or applies it; ``claimed_*`` fields are the
    agent's self-report, not a verified result.
    """

    agent_name: str
    task_id: str
    run_id: str
    diff_text: str = ""
    final_message: str = ""
    transcript_text: str = ""
    claimed_commands: list[str] = field(default_factory=list)
    claimed_public_tests_passed: bool | None = None
    claimed_hidden_tests_passed: bool | None = None
    metadata: dict[str, str] = field(default_factory=dict)


def _require_non_empty(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise AgentRunArtifactError(
            f"{field_name} must be a string, got {type(value).__name__}"
        )
    if not value.strip():
        raise AgentRunArtifactError(f"{field_name} must be non-empty")


def _require_string(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise AgentRunArtifactError(
            f"{field_name} must be a string, got {type(value).__name__}"
        )


def _require_optional_bool(value: object, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, bool):
        raise AgentRunArtifactError(
            f"{field_name} must be True, False, or None, got {type(value).__name__}"
        )


def validate_agent_run_artifact(artifact: AgentRunArtifact) -> None:
    """Validate an :class:`AgentRunArtifact` without mutating it.

    Raises:
        AgentRunArtifactError: If any field has an invalid type or value.
    """
    if not isinstance(artifact, AgentRunArtifact):
        raise AgentRunArtifactError(
            f"artifact must be an AgentRunArtifact, got {type(artifact).__name__}"
        )

    _require_non_empty(artifact.agent_name, "agent_name")
    _require_non_empty(artifact.task_id, "task_id")
    _require_non_empty(artifact.run_id, "run_id")

    _require_string(artifact.diff_text, "diff_text")
    _require_string(artifact.final_message, "final_message")
    _require_string(artifact.transcript_text, "transcript_text")

    if not isinstance(artifact.claimed_commands, list):
        raise AgentRunArtifactError(
            "claimed_commands must be a list of strings, "
            f"got {type(artifact.claimed_commands).__name__}"
        )
    for index, command in enumerate(artifact.claimed_commands):
        if not isinstance(command, str):
            raise AgentRunArtifactError(
                f"claimed_commands[{index}] must be a string, "
                f"got {type(command).__name__}"
            )

    _require_optional_bool(
        artifact.claimed_public_tests_passed, "claimed_public_tests_passed"
    )
    _require_optional_bool(
        artifact.claimed_hidden_tests_passed, "claimed_hidden_tests_passed"
    )

    if not isinstance(artifact.metadata, dict):
        raise AgentRunArtifactError(
            "metadata must be a dict of string keys and string values, "
            f"got {type(artifact.metadata).__name__}"
        )
    for key, value in artifact.metadata.items():
        if not isinstance(key, str):
            raise AgentRunArtifactError(
                f"metadata keys must be strings, got {type(key).__name__}"
            )
        if not isinstance(value, str):
            raise AgentRunArtifactError(
                f"metadata[{key!r}] must be a string, got {type(value).__name__}"
            )


def agent_run_artifact_to_dict(artifact: AgentRunArtifact) -> dict:
    """Return a JSON-friendly dict representation of ``artifact``.

    The returned ``claimed_commands`` list and ``metadata`` dict are fresh
    copies, so mutating the returned data cannot affect the original artifact.
    """
    validate_agent_run_artifact(artifact)
    data = asdict(artifact)
    data["claimed_commands"] = list(artifact.claimed_commands)
    data["metadata"] = dict(artifact.metadata)
    return data


def agent_run_artifact_from_dict(data: dict) -> AgentRunArtifact:
    """Reconstruct an :class:`AgentRunArtifact` from a dict.

    Optional fields fall back to safe defaults (empty strings, empty list,
    empty dict, ``None``). The reconstructed artifact is validated before being
    returned.

    Raises:
        AgentRunArtifactError: If ``data`` is not a dict or any field is
            invalid.
    """
    if not isinstance(data, dict):
        raise AgentRunArtifactError(
            f"data must be a dict, got {type(data).__name__}"
        )

    try:
        artifact = AgentRunArtifact(
            agent_name=data.get("agent_name", ""),
            task_id=data.get("task_id", ""),
            run_id=data.get("run_id", ""),
            diff_text=data.get("diff_text", ""),
            final_message=data.get("final_message", ""),
            transcript_text=data.get("transcript_text", ""),
            claimed_commands=list(data.get("claimed_commands", [])),
            claimed_public_tests_passed=data.get("claimed_public_tests_passed"),
            claimed_hidden_tests_passed=data.get("claimed_hidden_tests_passed"),
            metadata=dict(data.get("metadata", {})),
        )
    except TypeError as exc:
        raise AgentRunArtifactError(f"invalid artifact data: {exc}") from exc

    validate_agent_run_artifact(artifact)
    return artifact


def make_agent_run_id(agent_name: str, task_id: str, suffix: str = "") -> str:
    """Build a deterministic, readable run id from agent and task names.

    Spaces are normalized to underscores and the result is lowercased. If
    ``suffix`` is provided, it is appended with the same normalization.
    """
    if not isinstance(agent_name, str) or not isinstance(task_id, str):
        raise AgentRunArtifactError("agent_name and task_id must be strings")
    if not isinstance(suffix, str):
        raise AgentRunArtifactError("suffix must be a string")

    def normalize(value: str) -> str:
        return value.strip().replace(" ", "_").lower()

    parts = [normalize(agent_name), normalize(task_id)]
    if suffix.strip():
        parts.append(normalize(suffix))
    return ":".join(parts)
