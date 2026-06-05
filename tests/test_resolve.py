"""Tests for resolve.py — mutations on tmp copies."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.resolve import resolve_paths, _target_relative_path
from deadreckoning.scan import scan_r_scripts

FIXTURE_NO_LOCKFILE = Path(__file__).parent / "fixtures" / "r_no_lockfile"


# ---------------------------------------------------------------------------
# Target path derivation (pure function)
# ---------------------------------------------------------------------------

def test_target_path_strips_to_basename():
    assert _target_relative_path("/Users/jsmith/Dropbox/paper/data/lfs_2019.dta") == "data/lfs_2019.dta"
    assert _target_relative_path("//server/share/results/tab1.tex") == "data/tab1.tex"


def test_target_path_windows():
    assert _target_relative_path(r"C:\Users\jsmith\data\survey.csv") == "data/survey.csv"


# ---------------------------------------------------------------------------
# Path rewriting on working copy
# ---------------------------------------------------------------------------

@pytest.fixture()
def working_copy(tmp_path):
    copy = tmp_path / "project"
    shutil.copytree(FIXTURE_NO_LOCKFILE, copy)
    return copy


def test_resolve_rewrites_absolute_paths(working_copy):
    scan = scan_r_scripts(working_copy)
    result = resolve_paths(working_copy, scan)
    assert result.rewrite_count > 0


def test_resolve_original_paths_removed_from_scripts(working_copy):
    scan = scan_r_scripts(working_copy)
    resolve_paths(working_copy, scan)

    # After resolution, no script should still contain the original Dropbox path
    for script in working_copy.rglob("*.R"):
        text = script.read_text()
        assert "/Users/jsmith/Dropbox" not in text, f"{script.name} still has absolute path"


def test_resolve_target_paths_appear_in_scripts(working_copy):
    scan = scan_r_scripts(working_copy)
    result = resolve_paths(working_copy, scan)

    # Each rewrite target should now appear somewhere in the scripts
    all_text = "\n".join(
        s.read_text() for s in working_copy.rglob("*.R")
    )
    for rw in result.rewrites:
        assert rw.rewritten in all_text, f"target {rw.rewritten!r} not found after rewrite"


def test_resolve_writes_data_manifest(working_copy):
    scan = scan_r_scripts(working_copy)
    resolve_paths(working_copy, scan)
    manifest = working_copy / "data" / "data-manifest.csv"
    assert manifest.exists()
    content = manifest.read_text()
    assert "original_path" in content  # header present
    assert "rewritten_path" in content


def test_resolve_writes_agent_report(working_copy):
    scan = scan_r_scripts(working_copy)
    result = resolve_paths(working_copy, scan)
    assert result.report_path is not None
    assert result.report_path.exists()
    report_text = result.report_path.read_text()
    assert "DeadReckoning" in report_text
    assert "Path rewrites" in report_text


def test_resolve_agent_report_lists_rewrites(working_copy):
    scan = scan_r_scripts(working_copy)
    result = resolve_paths(working_copy, scan)
    report = result.report_path.read_text()
    for rw in result.rewrites:
        assert rw.original in report


def test_resolve_does_not_touch_original(tmp_path):
    """Original fixture must be unchanged — resolve only on working copy."""
    original_analysis = FIXTURE_NO_LOCKFILE / "code" / "analysis.R"
    before = original_analysis.read_text()

    copy = tmp_path / "project"
    shutil.copytree(FIXTURE_NO_LOCKFILE, copy)
    scan = scan_r_scripts(copy)
    resolve_paths(copy, scan)

    assert original_analysis.read_text() == before


def test_resolve_idempotent(working_copy):
    """Running resolve twice should not double-rewrite or crash."""
    scan1 = scan_r_scripts(working_copy)
    result1 = resolve_paths(working_copy, scan1)

    scan2 = scan_r_scripts(working_copy)
    result2 = resolve_paths(working_copy, scan2)

    # Second pass should find nothing to rewrite (no absolute paths remain)
    assert result2.rewrite_count == 0


# ---------------------------------------------------------------------------
# Secret exclusion
# ---------------------------------------------------------------------------

def test_resolve_excludes_secret_files(tmp_path):
    proj = tmp_path / "project"
    proj.mkdir()
    (proj / ".env").write_text("TOKEN=abc123\n")
    (proj / "run.R").write_text("source('.env')\n")

    scan = scan_r_scripts(proj)
    result = resolve_paths(proj, scan)

    assert not (proj / ".env").exists()
    assert len(result.secrets_excluded) == 1


# ---------------------------------------------------------------------------
# Clean project — no rewrites needed
# ---------------------------------------------------------------------------

def test_resolve_clean_project_no_rewrites(tmp_path):
    (tmp_path / "run.R").write_text('df <- read.csv("data/survey.csv")\n')
    scan = scan_r_scripts(tmp_path)
    result = resolve_paths(tmp_path, scan)
    assert result.rewrite_count == 0
