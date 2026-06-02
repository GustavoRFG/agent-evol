"""Tests for the Week 7 Day 5 final design / capstone document."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN_DOC_PATH = (
    REPO_ROOT / "docs" / "design_of_robust_ai_coding_evaluation_framework.md"
)
README_PATH = REPO_ROOT / "README.md"

REQUIRED_PHRASES = (
    "AgentRunArtifact",
    "TaskEvidence",
    "EvaluationResult",
    "RunReport",
    "ComparisonReport",
    "public and hidden tests",
    "claim reliability",
    "claims are not evidence",
    "GitHub Actions",
    "controlled execution",
    "isolated workspace",
    "verified evaluation",
)

REQUIRED_SECTION_HEADERS = (
    "## 1. Problem statement",
    "## 2. Design goals",
    "## 3. High-level architecture",
    "## 4. Benchmark design",
    "## 5. Controlled execution model",
    "## 6. External agent artifacts",
    "## 7. Verified evaluation pipeline",
    "## 8. Claim versus verified outcome analysis",
    "## 9. Reporting and comparison",
    "## 10. CI and engineering discipline",
    "## 11. Failure modes handled",
    "## 12. Current limitations",
    "## 13. Future work",
    "## 14. Interview-ready summary",
)


def _doc_text() -> str:
    assert DESIGN_DOC_PATH.is_file(), (
        f"missing design document at {DESIGN_DOC_PATH}"
    )
    return DESIGN_DOC_PATH.read_text(encoding="utf-8")


def test_design_document_exists():
    assert DESIGN_DOC_PATH.is_file()


def test_design_document_has_expected_title():
    text = _doc_text()
    assert "# Design of a Robust AI Coding Evaluation Framework" in text


def test_design_document_contains_required_phrases():
    text = _doc_text()
    missing = [phrase for phrase in REQUIRED_PHRASES if phrase not in text]
    assert not missing, f"design doc missing required phrases: {missing}"


def test_design_document_contains_all_section_headers():
    text = _doc_text()
    missing = [
        header for header in REQUIRED_SECTION_HEADERS if header not in text
    ]
    assert not missing, f"design doc missing section headers: {missing}"


def test_design_document_mentions_simulated_demo():
    # The doc should be honest about the demo using simulated artifacts.
    text = _doc_text()
    assert "simulated" in text.lower()


def test_design_document_mentions_no_real_agent_execution():
    text = _doc_text()
    lowered = text.lower()
    # Phrased as an explicit boundary, not just an absence of features.
    assert "no real agent execution" in lowered or (
        "does not execute agents" in lowered
    )


def test_design_document_has_text_diagram_in_architecture_section():
    text = _doc_text()
    architecture = (
        text.split("## 3. High-level architecture", 1)[1]
        .split("## 4. Benchmark design", 1)[0]
    )
    # Look for a fenced block whose content uses ASCII box-drawing.
    assert "```" in architecture
    assert "AgentRunArtifact" in architecture
    assert "RunReport" in architecture
    assert "ComparisonReport" in architecture


def test_readme_links_to_design_document():
    assert README_PATH.is_file()
    text = README_PATH.read_text(encoding="utf-8")
    # Either an explicit "Design document" section or a direct link to the
    # design doc. Both should be acceptable for callers reading the README.
    assert "design_of_robust_ai_coding_evaluation_framework.md" in text


def test_design_document_interview_summary_is_concise():
    text = _doc_text()
    # The Section 14 summary is the last section; pull it out and assert
    # it is non-empty but not absurdly long (a few short paragraphs).
    summary = text.split("## 14. Interview-ready summary", 1)[1].strip()
    assert summary, "interview summary section is empty"
    # Soft upper bound — section should fit on a single screen.
    assert len(summary) < 2500, (
        f"interview summary is {len(summary)} chars; aim for under 2500"
    )
