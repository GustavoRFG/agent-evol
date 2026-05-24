"""Demo-output persistence for the verified evaluation pipeline.

The Week 7 Day 2 integrated helper builds combined verified comparison +
claim analysis Markdown in memory. This module saves that text to disk for
demos, capstone scripts, and interview walk-throughs.

It performs no agent execution, no patch application, no test execution, and
no network calls — only text I/O. Standard library only.
"""

from __future__ import annotations

from pathlib import Path


class VerifiedDemoPersistenceError(ValueError):
    """Raised when a verified-demo output cannot be written."""


def save_text_file(text: str, path: str | Path) -> Path:
    """Write ``text`` to ``path`` as UTF-8, creating parent directories.

    Returns the resolved destination :class:`Path`.

    Raises:
        VerifiedDemoPersistenceError: If ``text`` is not a string, if ``path``
            is not a string/Path, or if the write fails.
    """
    if not isinstance(text, str):
        raise VerifiedDemoPersistenceError(
            f"text must be a string, got {type(text).__name__}"
        )
    if not isinstance(path, (str, Path)):
        raise VerifiedDemoPersistenceError(
            f"path must be a string or Path, got {type(path).__name__}"
        )

    target = Path(path)
    try:
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise VerifiedDemoPersistenceError(
            f"failed to write text to {target}: {exc}"
        ) from exc
    return target


def save_verified_comparison_with_claims_markdown(
    markdown: str,
    path: str | Path,
) -> Path:
    """Save combined verified-comparison + claim-analysis Markdown to ``path``.

    Thin wrapper over :func:`save_text_file` that exists to give the demo
    flow a focused, well-named save call. This function does *not* build the
    Markdown — use Week 7 Day 2's
    :func:`build_and_render_verified_comparison_with_claims_markdown` for
    that. Keeping save and build separate lets tests assert on text without
    running real verification subprocesses.

    Raises:
        VerifiedDemoPersistenceError: If ``markdown`` is not a string, or if
            the write fails (propagated from :func:`save_text_file`).
    """
    if not isinstance(markdown, str):
        raise VerifiedDemoPersistenceError(
            f"markdown must be a string, got {type(markdown).__name__}"
        )
    return save_text_file(markdown, path)


def save_verified_demo_outputs(
    *,
    markdown: str,
    output_dir: str | Path,
    basename: str = "verified_agent_eval_demo",
) -> dict[str, Path]:
    """Save the combined verified-demo Markdown under ``output_dir``.

    The Markdown is written to ``output_dir / f"{basename}.md"``. The output
    directory is created if needed. Returns a mapping with one entry,
    ``{"markdown": <path>}``, so the helper can grow extra outputs later
    (e.g. a JSON sidecar) without changing its return shape.

    Raises:
        VerifiedDemoPersistenceError: For invalid ``basename`` / ``markdown``
            / ``output_dir`` types, or if writing fails.
    """
    if not isinstance(markdown, str):
        raise VerifiedDemoPersistenceError(
            f"markdown must be a string, got {type(markdown).__name__}"
        )
    if not isinstance(output_dir, (str, Path)):
        raise VerifiedDemoPersistenceError(
            f"output_dir must be a string or Path, got {type(output_dir).__name__}"
        )
    if not isinstance(basename, str) or not basename.strip():
        raise VerifiedDemoPersistenceError(
            "basename must be a non-empty string"
        )

    md_path = save_verified_comparison_with_claims_markdown(
        markdown, Path(output_dir) / f"{basename}.md"
    )
    return {"markdown": md_path}


__all__ = [
    "VerifiedDemoPersistenceError",
    "save_text_file",
    "save_verified_comparison_with_claims_markdown",
    "save_verified_demo_outputs",
]
