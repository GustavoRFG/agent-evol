"""Load and fail-closed-verify a persisted EvoForge episode.

This loader reads an EvoForge run directory, parses ``episode.json``, and binds
to the grounded evidence by verifying every declared artifact hash against the
bytes currently on disk. It is the security boundary of the export hook: if the
evidence changed after EvoForge recorded it, or an artifact path tries to escape
the run directory, loading fails closed and **no** report is produced.

It only reads. It never writes to the run directory, never executes commands,
never applies patches, and never reruns tests. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The core ForgeAgent-origin evidence files an episode is expected to bind.
CORE_EVIDENCE_FILES: tuple[str, ...] = (
    "task.md",
    "commands.log",
    "patch.diff",
    "tests.log",
)

_SHA256_HEX_LEN = 64


class EvoForgeEpisodeError(ValueError):
    """Raised when an EvoForge episode cannot be safely loaded or bound."""


@dataclass
class LoadedEpisode:
    """A verified, hash-bound view of one EvoForge episode.

    Every entry in :attr:`verified_hashes` has been confirmed against the bytes
    currently on disk. :attr:`evidence_paths` maps each *core* evidence file that
    exists and verified to its on-disk path; missing core files are simply absent
    from the mapping (the evaluator turns that into a ``needs_review`` judgment,
    not a hard load failure).
    """

    run_dir: Path
    run_id: str
    trace_id: str
    episode: dict[str, Any]
    verified_hashes: dict[str, str] = field(default_factory=dict)
    evidence_paths: dict[str, Path] = field(default_factory=dict)
    source: dict[str, Any] | None = None

    def core_present(self) -> dict[str, bool]:
        """Return, for each core evidence file, whether it is present and bound."""
        return {name: name in self.evidence_paths for name in CORE_EVIDENCE_FILES}

    def read_supplementary_json(self, name: str) -> dict[str, Any] | None:
        """Read an optional supplementary JSON artifact (e.g. ``eval.json``).

        Returns ``None`` when the file is absent or cannot be parsed as a JSON
        object. Supplementary context is read defensively and is never allowed
        to influence the independent verdict — callers use it for reporting and
        comparison only.
        """
        path = self.run_dir / name
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _is_valid_digest(digest: object) -> bool:
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return False
    hex_part = digest[len("sha256:") :]
    return len(hex_part) == _SHA256_HEX_LEN and all(
        c in "0123456789abcdef" for c in hex_part
    )


def _safe_evidence_path(run_dir: Path, name: str) -> Path:
    """Resolve ``name`` to a path provably inside ``run_dir`` (fail closed).

    Rejects absolute paths, drive-qualified paths, parent traversal, and symlink
    escapes. ``run_dir`` must already be resolved.
    """
    if not isinstance(name, str) or not name.strip():
        raise EvoForgeEpisodeError("artifact name must be non-empty text")

    candidate = Path(name)
    if candidate.is_absolute() or candidate.drive or candidate.anchor:
        raise EvoForgeEpisodeError(f"unsafe absolute artifact path: {name!r}")
    if any(part == ".." for part in candidate.parts):
        raise EvoForgeEpisodeError(f"path traversal in artifact path: {name!r}")

    target = run_dir / candidate
    # A symlink anywhere in the evidence path is an escape risk; reject it.
    if target.is_symlink():
        raise EvoForgeEpisodeError(f"symlink artifact path is not allowed: {name!r}")
    resolved = target.resolve()
    if resolved != run_dir and run_dir not in resolved.parents:
        raise EvoForgeEpisodeError(f"symlink escape in artifact path: {name!r}")
    return target


def _require_episode_text(episode: dict[str, Any], key: str) -> str:
    value = episode.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvoForgeEpisodeError(f"episode.json missing required text field: {key}")
    return value


def load_evoforge_episode(run_dir: Path | str) -> LoadedEpisode:
    """Load an EvoForge episode and verify its hash binding fail-closed.

    Args:
        run_dir: Path to an EvoForge run directory containing ``episode.json``.

    Returns:
        A :class:`LoadedEpisode` whose declared artifact hashes have all been
        verified against the current bytes on disk.

    Raises:
        EvoForgeEpisodeError: If the run directory or ``episode.json`` is
            missing/invalid, a required identifier is absent, a declared hash is
            malformed or references a missing file, the on-disk bytes no longer
            match a declared hash, a present core evidence file has no recorded
            hash, or any artifact path is unsafe (absolute, traversal, symlink).
    """
    resolved_dir = Path(run_dir).resolve()
    if not resolved_dir.is_dir():
        raise EvoForgeEpisodeError(f"run directory not found: {run_dir}")

    episode_path = resolved_dir / "episode.json"
    if not episode_path.is_file():
        raise EvoForgeEpisodeError(f"missing episode.json in run directory: {run_dir}")

    try:
        episode = json.loads(episode_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvoForgeEpisodeError(f"invalid episode.json: {exc}") from exc
    except OSError as exc:
        raise EvoForgeEpisodeError(f"cannot read episode.json: {exc}") from exc
    if not isinstance(episode, dict):
        raise EvoForgeEpisodeError("episode.json must contain a JSON object")

    run_id = _require_episode_text(episode, "run_id")

    trace = episode.get("trace")
    if not isinstance(trace, dict):
        raise EvoForgeEpisodeError("episode.json missing trace object")
    trace_id = trace.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise EvoForgeEpisodeError("episode.json missing trace.trace_id")

    declared = episode.get("artifact_hashes")
    if not isinstance(declared, dict):
        raise EvoForgeEpisodeError("episode.json missing artifact_hashes object")

    verified: dict[str, str] = {}
    for name, stored_hash in declared.items():
        path = _safe_evidence_path(resolved_dir, name)
        if not _is_valid_digest(stored_hash):
            raise EvoForgeEpisodeError(f"malformed stored hash for {name!r}")
        if not path.is_file():
            raise EvoForgeEpisodeError(
                f"declared artifact is missing on disk: {name!r}"
            )
        actual = _sha256_file(path)
        if actual != stored_hash:
            raise EvoForgeEpisodeError(
                f"artifact hash mismatch (evidence changed): {name!r}"
            )
        verified[name] = actual

    # A core evidence file present on disk but never hashed is unverifiable; we
    # refuse to evaluate it silently.
    evidence_paths: dict[str, Path] = {}
    for name in CORE_EVIDENCE_FILES:
        path = resolved_dir / name
        if path.is_file():
            if name not in verified:
                raise EvoForgeEpisodeError(
                    f"core evidence file has no recorded hash: {name!r}"
                )
            evidence_paths[name] = path

    source = episode.get("source")
    if not isinstance(source, dict):
        source = None

    return LoadedEpisode(
        run_dir=resolved_dir,
        run_id=run_id,
        trace_id=trace_id,
        episode=episode,
        verified_hashes=verified,
        evidence_paths=evidence_paths,
        source=source,
    )
