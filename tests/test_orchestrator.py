"""
Tests for orchestrator.run_pipeline — behavioural contracts.

Focus: things that cross module boundaries and aren't covered by
individual unit tests (graph, capture, fix_loop, etc.).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from deadreckoning.orchestrator import run_pipeline


# ---------------------------------------------------------------------------
# §4.1 — confidentiality gate fires BEFORE working copy is created
# ---------------------------------------------------------------------------


def test_restricted_aborts_before_copy(tmp_path: Path) -> None:
    """No working copy must be created when restricted data is detected."""
    # Create a minimal project with a restricted-sounding filename
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "census_pii_microdata.dta").write_bytes(b"")
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")

    snapshot_before = set(Path(tempfile.gettempdir()).glob("dr_*"))

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True)

    snapshot_after = set(Path(tempfile.gettempdir()).glob("dr_*"))
    new_tmpdirs = snapshot_after - snapshot_before

    assert result.restricted.is_restricted, "Should have detected restricted data"
    assert result.error is not None
    assert "restricted" in result.error.lower()
    assert new_tmpdirs == set(), (
        "No dr_* working-copy directory should have been created — "
        f"found: {new_tmpdirs}"
    )


def test_restricted_working_copy_sentinel(tmp_path: Path) -> None:
    """When aborted early, working_copy is set to project_root (sentinel)."""
    (tmp_path / "nlsy_confidential.dta").write_bytes(b"")

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True)

    assert result.restricted.is_restricted
    assert result.working_copy == tmp_path


def test_non_restricted_creates_working_copy(tmp_path: Path) -> None:
    """Clean project must get a working copy in a temp dir."""
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")
    (tmp_path / "run.R").write_text("# script\n")

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True)

    assert not result.restricted.is_restricted
    assert result.working_copy != tmp_path
    assert result.working_copy.exists()


def test_restricted_original_untouched(tmp_path: Path) -> None:
    """Original project_root must be untouched after restricted abort."""
    restricted_file = tmp_path / "hmda_restricted.csv"
    restricted_file.write_bytes(b"fake,data\n")

    run_pipeline(tmp_path, skip_run=True, skip_docker=True)

    # File still present, unmodified
    assert restricted_file.exists()
    assert restricted_file.read_bytes() == b"fake,data\n"
