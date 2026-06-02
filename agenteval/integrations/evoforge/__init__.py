"""Native EvoForge evaluation export hook for AgentEval Forge.

This package lets AgentEval Forge read a persisted EvoForge episode, verify its
run / trace / artifact hashes, independently judge the grounded trace evidence,
and emit a structured external evaluation report that EvoForge can attach with::

    evoforge attach-agenteval <run-dir> <evaluation-json>

It is a *read-only* judge over persisted evidence. It never executes
``commands.log``, never applies ``patch.diff``, never reruns tests, never calls a
network or LLM, and never modifies the EvoForge episode. It does not import any
EvoForge source code at runtime — compatibility is governed solely by the
explicit contract in :mod:`agenteval.integrations.evoforge.contract`.

The governance rule is strict: AgentEval Forge judges evidence independently. It
may read EvoForge's local ``eval.json`` and ``promotion_decision.json`` only as
supplementary context — never as the source of its own verdict.
"""

from agenteval.integrations.evoforge.contract import (
    ALLOWED_CHECK_STATUSES,
    ALLOWED_VERDICTS,
    EVALUATION_SCHEMA_VERSION,
    SCORE_FIELDS,
    SOURCE_SYSTEM,
    EvoForgeContractError,
    validate_evaluation_report,
)
from agenteval.integrations.evoforge.episode_loader import (
    EvoForgeEpisodeError,
    LoadedEpisode,
    load_evoforge_episode,
)
from agenteval.integrations.evoforge.evaluator import (
    EvidenceJudgment,
    evaluate_evoforge_episode,
)
from agenteval.integrations.evoforge.exporter import (
    EvoForgeExportError,
    export_evoforge_evaluation,
)

__all__ = [
    "ALLOWED_CHECK_STATUSES",
    "ALLOWED_VERDICTS",
    "EVALUATION_SCHEMA_VERSION",
    "SCORE_FIELDS",
    "SOURCE_SYSTEM",
    "EvidenceJudgment",
    "EvoForgeContractError",
    "EvoForgeEpisodeError",
    "EvoForgeExportError",
    "LoadedEpisode",
    "evaluate_evoforge_episode",
    "export_evoforge_evaluation",
    "load_evoforge_episode",
    "validate_evaluation_report",
]
