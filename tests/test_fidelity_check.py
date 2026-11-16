"""
FIDELITY step tests — fidelity_check.py

Orchestrator-facing wiring on top of the already-tested
check_exhibit_fidelity() (see test_fidelity.py): matches exhibits to an
author-supplied reference directory by basename, across one or more
directories, and reports what it found (or couldn't find).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.fidelity_check import run_fidelity_check_step
from deadreckoning.models import IntakeResult
from deadreckoning.orchestrator import run_pipeline

PYTHON_FIXTURE = Path(__file__).parent / "fixtures" / "runnable_python_minimal"


def _write_project(root: Path, table_content: str = "regenerated content") -> None:
    (root / "code").mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)
    (root / "paper.tex").write_text(
        r"""\documentclass{article}
\begin{document}
\input{output/Table1.tex}
\end{document}
"""
    )
    (root / "code" / "make_table.R").write_text(
        'writeLines("placeholder", "output/Table1.tex")\n'
    )
    (root / "output" / "Table1.tex").write_text(table_content)


def test_no_reference_dirs_given_not_attempted(tmp_path):
    _write_project(tmp_path)
    result = run_fidelity_check_step(tmp_path, IntakeResult())
    assert result.attempted is False
    assert not (tmp_path / "FIDELITY-REPORT.md").exists()


def test_none_intake_not_attempted(tmp_path):
    _write_project(tmp_path)
    result = run_fidelity_check_step(tmp_path, None)
    assert result.attempted is False


def test_matching_reference_identical_content_no_mismatch(tmp_path):
    _write_project(tmp_path, table_content="same content")
    ref_dir = tmp_path.parent / "reference_1"
    ref_dir.mkdir()
    (ref_dir / "Table1.tex").write_text("same content")

    intake = IntakeResult(reference_exhibit_dirs=[str(ref_dir)])
    result = run_fidelity_check_step(tmp_path, intake)

    assert result.attempted is True
    assert result.exhibits_checked == 1
    assert result.mismatches == []
    assert (tmp_path / "FIDELITY-REPORT.md").exists()


def test_matching_reference_different_content_is_mismatch(tmp_path):
    _write_project(tmp_path, table_content="regenerated content")
    ref_dir = tmp_path.parent / "reference_2"
    ref_dir.mkdir()
    (ref_dir / "Table1.tex").write_text("published content")

    intake = IntakeResult(reference_exhibit_dirs=[str(ref_dir)])
    result = run_fidelity_check_step(tmp_path, intake)

    assert result.exhibits_checked == 1
    assert len(result.mismatches) == 1
    assert result.mismatches[0].exhibit == Path("output/Table1.tex")
    assert result.has_findings is True


def test_missing_reference_dir_reported(tmp_path):
    _write_project(tmp_path)
    nonexistent = tmp_path.parent / "does_not_exist"

    intake = IntakeResult(reference_exhibit_dirs=[str(nonexistent)])
    result = run_fidelity_check_step(tmp_path, intake)

    assert result.attempted is True
    assert nonexistent in result.missing_reference_dirs
    assert result.exhibits_checked == 0
    assert result.has_findings is True


def test_exhibit_with_no_reference_anywhere_reported(tmp_path):
    _write_project(tmp_path)
    ref_dir = tmp_path.parent / "reference_3"
    ref_dir.mkdir()
    # Reference dir exists but has no file named Table1.tex in it.

    intake = IntakeResult(reference_exhibit_dirs=[str(ref_dir)])
    result = run_fidelity_check_step(tmp_path, intake)

    assert result.exhibits_checked == 0
    assert Path("output/Table1.tex") in result.exhibits_without_reference


def test_basename_found_in_two_dirs_is_collision_but_first_wins(tmp_path):
    _write_project(tmp_path, table_content="regenerated content")
    ref_dir_a = tmp_path.parent / "reference_a"
    ref_dir_b = tmp_path.parent / "reference_b"
    ref_dir_a.mkdir()
    ref_dir_b.mkdir()
    (ref_dir_a / "Table1.tex").write_text("regenerated content")  # matches -> no mismatch
    (ref_dir_b / "Table1.tex").write_text("a completely different table")

    intake = IntakeResult(reference_exhibit_dirs=[str(ref_dir_a), str(ref_dir_b)])
    result = run_fidelity_check_step(tmp_path, intake)

    assert "Table1.tex" in result.basename_collisions
    assert len(result.basename_collisions["Table1.tex"]) == 2
    # First dir (ref_dir_a) wins the actual comparison -> content matches, no mismatch.
    assert result.mismatches == []


def test_multiple_dirs_second_one_has_the_file(tmp_path):
    _write_project(tmp_path, table_content="same content")
    ref_dir_a = tmp_path.parent / "reference_only_other_files"
    ref_dir_b = tmp_path.parent / "reference_has_table1"
    ref_dir_a.mkdir()
    ref_dir_b.mkdir()
    (ref_dir_a / "SomeOtherFile.tex").write_text("irrelevant")
    (ref_dir_b / "Table1.tex").write_text("same content")

    intake = IntakeResult(reference_exhibit_dirs=[str(ref_dir_a), str(ref_dir_b)])
    result = run_fidelity_check_step(tmp_path, intake)

    assert result.exhibits_checked == 1
    assert result.mismatches == []
    assert "Table1.tex" not in result.basename_collisions


def test_relative_reference_dir_resolved_against_working_copy(tmp_path):
    _write_project(tmp_path, table_content="same content")
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "Table1.tex").write_text("same content")

    intake = IntakeResult(reference_exhibit_dirs=["reference"])
    result = run_fidelity_check_step(tmp_path, intake)

    assert result.attempted is True
    assert result.exhibits_checked == 1
    assert result.mismatches == []


# ---------------------------------------------------------------------------
# Orchestrator-level: run_pipeline() must actually reach and populate
# fidelity_check on a real native run, not just as a standalone function.
# ---------------------------------------------------------------------------


@pytest.mark.local
@pytest.mark.skipif(not PYTHON_FIXTURE.exists(), reason="python fixture missing")
def test_orchestrator_populates_fidelity_check_on_real_run(tmp_path):
    ref_dir = tmp_path / "accepted_submission"
    ref_dir.mkdir()
    # tables.py's output is deterministic (fixed input list) — the fixture's
    # own checked-in tables/summary.tex is already the correct regenerated
    # content, so copying it as the "reference" gives a real clean match.
    shutil.copy(
        PYTHON_FIXTURE / "tables" / "summary.tex", ref_dir / "summary.tex"
    )

    intake = IntakeResult(reference_exhibit_dirs=[str(ref_dir)])
    result = run_pipeline(
        PYTHON_FIXTURE, master_script="code/run.py", skip_docker=True, intake=intake
    )

    assert result.error is None, f"pipeline error: {result.error}"
    assert result.fidelity_check is not None
    assert result.fidelity_check.attempted is True
    assert result.fidelity_check.exhibits_checked >= 1
    assert (result.working_copy / "FIDELITY-REPORT.md").exists()
