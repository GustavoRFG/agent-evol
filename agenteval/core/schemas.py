"""Core data models for AgentEval Forge.

These dataclasses and enums describe the structured data produced while
evaluating an agentic coding system: the task given to the agent, the run the
agent performed, a summary of the patch it produced, and the resulting
evaluation. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WeaknessCode(str, Enum):
    """Taxonomy of agent failure modes observed during an evaluation.

    Inherits from ``str`` so values serialize cleanly (e.g. to JSON) and
    compare naturally with plain strings.
    """

    INST = "INST"          # Did not follow the instructions / task spec.
    OVERENG = "OVERENG"    # Overengineered the solution beyond the request.
    TOOL = "TOOL"          # Misused tools or chose the wrong tool.
    LAZY = "LAZY"          # Incomplete or low-effort work.
    VERIFY = "VERIFY"      # Skipped verification of its own work.
    FALSE = "FALSE"        # Made false claims (e.g. "tests passed").
    ROOT = "ROOT"          # Patched a symptom instead of the root cause.
    DESTRUCT = "DESTRUCT"  # Took a destructive or unsafe action.
    FILE = "FILE"          # Edited the wrong files or mishandled files.
    HALLUC = "HALLUC"      # Hallucinated APIs, files, or facts.
    DOCS = "DOCS"          # Missing or incorrect documentation.
    VERBOSE = "VERBOSE"    # Excessively verbose output or changes.


@dataclass
class TaskSpec:
    """A benchmark task presented to an agent."""

    task_id: str
    title: str
    description: str = ""
    repo_path: str = ""
    public_tests: list[str] = field(default_factory=list)
    hidden_tests: list[str] = field(default_factory=list)


@dataclass
class AgentRun:
    """A single execution of an agent against a :class:`TaskSpec`."""

    run_id: str
    agent_name: str
    task_id: str
    transcript_path: str = ""
    final_message: str = ""
    commands_run: list[str] = field(default_factory=list)


@dataclass
class PatchSummary:
    """A summary of the code changes an agent produced during a run."""

    changed_files: list[str] = field(default_factory=list)
    added_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    diff_text: str = ""


@dataclass
class EvaluationResult:
    """The structured outcome of evaluating one :class:`AgentRun`."""

    task_id: str
    run_id: str
    score: float = 0.0
    passed_public_tests: bool = False
    passed_hidden_tests: bool = False
    weaknesses: list[WeaknessCode] = field(default_factory=list)
    rationale: str = ""
