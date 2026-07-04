"""
Tests for orchestrator.run_pipeline — behavioural contracts.

Focus: things that cross module boundaries and aren't covered by
individual unit tests (graph, capture, fix_loop, etc.).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from deadreckoning.intake import questionnaire
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


# ---------------------------------------------------------------------------
# §4.1 — the author's intake answer must gate, even with no filename trigger
# ---------------------------------------------------------------------------


def test_intake_restricted_yes_aborts_before_copy_no_filename_trigger(tmp_path: Path) -> None:
    """Author says yes; nothing in the filenames would ever catch it."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "wages.csv").write_bytes(b"")  # innocuous name
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")

    intake = questionnaire(answers={"restricted_data": "yes", "data_root": "data"})

    snapshot_before = set(Path(tempfile.gettempdir()).glob("dr_*"))

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True, intake=intake)

    snapshot_after = set(Path(tempfile.gettempdir()).glob("dr_*"))
    new_tmpdirs = snapshot_after - snapshot_before

    assert result.restricted.is_restricted
    assert result.error is not None
    assert "restricted" in result.error.lower()
    assert result.working_copy == tmp_path  # sentinel — no copy made
    assert new_tmpdirs == set(), (
        "No dr_* working-copy directory should have been created — "
        f"found: {new_tmpdirs}"
    )


def test_intake_restricted_no_proceeds_normally(tmp_path: Path) -> None:
    """Author says no, no filename trigger — pipeline proceeds as usual."""
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")
    (tmp_path / "run.R").write_text("# script\n")

    intake = questionnaire(answers={"restricted_data": "no"})

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True, intake=intake)

    assert not result.restricted.is_restricted
    assert result.working_copy != tmp_path
    assert result.working_copy.exists()


# ---------------------------------------------------------------------------
# RESOLVE's here::here() adoption must feed back into env_spec.packages —
# CAPTURE runs before RESOLVE, so it can't see a dependency RESOLVE itself
# introduces by rewriting code.
# ---------------------------------------------------------------------------


def test_here_adoption_adds_here_package(tmp_path: Path) -> None:
    (tmp_path / "code").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "tables").mkdir()
    (tmp_path / "paper.tex").write_text(
        r"\documentclass{article}\begin{document}\input{tables/out.tex}\end{document}"
    )
    (tmp_path / "code" / "run.R").write_text(
        'library(data.table)\n'
        'f <- fread("/Users/someone/Dropbox/project/data/raw.csv")\n'
        'write.csv(f, "data/out.csv")\n'
    )

    result = run_pipeline(tmp_path, master_script="code/run.R", skip_run=True, skip_docker=True)

    assert result.resolve is not None
    assert result.resolve.here_adoptions > 0, "fixture should trigger a here::here() rewrite"
    assert result.env_spec is not None
    assert any(p.name == "here" for p in result.env_spec.packages), (
        "env_spec.packages must include 'here' once RESOLVE adopts here::here() — "
        f"got: {[p.name for p in result.env_spec.packages]}"
    )
