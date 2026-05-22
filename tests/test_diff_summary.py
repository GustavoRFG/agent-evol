"""Tests for the unified diff -> PatchSummary parser."""

from agenteval.core.schemas import PatchSummary
from agenteval.patches.diff_summary import parse_unified_diff

MODIFIED_DIFF = """diff --git a/file.py b/file.py
index 1234567..89abcde 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def f():
-    return 1
+    return 2
"""

ADDED_DIFF = """diff --git a/new_module.py b/new_module.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new_module.py
@@ -0,0 +1,2 @@
+def hello():
+    return "hi"
"""

DELETED_DIFF = """diff --git a/old_module.py b/old_module.py
deleted file mode 100644
index 1234567..0000000
--- a/old_module.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def gone():
-    pass
"""

SUM_RANGE_DIFF = """diff --git a/sum_range.py b/sum_range.py
index abc1234..def5678 100644
--- a/sum_range.py
+++ b/sum_range.py
@@ -1,2 +1,2 @@
 def sum_range(start, end):
-    return sum(range(start, end))
+    return sum(range(start, end + 1))
"""


def test_empty_diff_returns_empty_file_lists():
    summary = parse_unified_diff("")
    assert isinstance(summary, PatchSummary)
    assert summary.changed_files == []
    assert summary.added_files == []
    assert summary.deleted_files == []
    assert summary.diff_text == ""


def test_whitespace_only_diff_returns_empty_file_lists():
    summary = parse_unified_diff("   \n\t\n")
    assert summary.changed_files == []
    assert summary.added_files == []
    assert summary.deleted_files == []
    assert summary.diff_text == "   \n\t\n"


def test_modified_file_is_detected_as_changed():
    summary = parse_unified_diff(MODIFIED_DIFF)
    assert summary.changed_files == ["file.py"]
    assert summary.added_files == []
    assert summary.deleted_files == []


def test_added_file_is_detected_as_added():
    summary = parse_unified_diff(ADDED_DIFF)
    assert summary.added_files == ["new_module.py"]
    assert summary.changed_files == []
    assert summary.deleted_files == []


def test_deleted_file_is_detected_as_deleted():
    summary = parse_unified_diff(DELETED_DIFF)
    assert summary.deleted_files == ["old_module.py"]
    assert summary.changed_files == []
    assert summary.added_files == []


def test_multiple_files_are_handled():
    summary = parse_unified_diff(MODIFIED_DIFF + ADDED_DIFF + DELETED_DIFF)
    assert summary.changed_files == ["file.py"]
    assert summary.added_files == ["new_module.py"]
    assert summary.deleted_files == ["old_module.py"]


def test_duplicate_file_headers_do_not_create_duplicates():
    summary = parse_unified_diff(MODIFIED_DIFF + MODIFIED_DIFF)
    assert summary.changed_files == ["file.py"]


def test_paths_are_normalized_removing_a_and_b_prefixes():
    summary = parse_unified_diff(MODIFIED_DIFF + ADDED_DIFF + DELETED_DIFF)
    all_files = (
        summary.changed_files + summary.added_files + summary.deleted_files
    )
    for name in all_files:
        assert not name.startswith("a/")
        assert not name.startswith("b/")


def test_diff_text_is_preserved_exactly():
    summary = parse_unified_diff(SUM_RANGE_DIFF)
    assert summary.diff_text == SUM_RANGE_DIFF


def test_realistic_sum_range_diff_detects_changed_file():
    summary = parse_unified_diff(SUM_RANGE_DIFF)
    assert "sum_range.py" in summary.changed_files


def test_diff_content_lines_are_not_mistaken_for_headers():
    # A removed/added line whose content itself starts with "-- "/"++ "
    # must not be parsed as a file header (it appears after the @@ hunk).
    tricky_diff = """diff --git a/notes.py b/notes.py
index 1111111..2222222 100644
--- a/notes.py
+++ b/notes.py
@@ -1,2 +1,2 @@
 x = 1
-- old marker line
++ new marker line
"""
    summary = parse_unified_diff(tricky_diff)
    assert summary.changed_files == ["notes.py"]
    assert summary.added_files == []
    assert summary.deleted_files == []
