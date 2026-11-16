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
from deadreckoning.orchestrator import _detect_master_script, run_pipeline


# ---------------------------------------------------------------------------
# §4.1 — confidentiality gate fires BEFORE working copy is created
# ---------------------------------------------------------------------------


def test_restricted_aborts_before_copy(tmp_path: Path) -> None:
    """Restricted data no longer aborts (#27) — a working copy IS created,
    and the pipeline keeps running (with LLM off for the rest of the run)."""
    # Create a minimal project with a restricted-sounding filename
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "census_pii_microdata.dta").write_bytes(b"")
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")

    snapshot_before = set(Path(tempfile.gettempdir()).glob("dr_*"))

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True)

    snapshot_after = set(Path(tempfile.gettempdir()).glob("dr_*"))
    new_tmpdirs = snapshot_after - snapshot_before

    assert result.restricted.is_restricted, "Should have detected restricted data"
    assert result.error is None
    assert new_tmpdirs != set(), "A dr_* working-copy directory should have been created"
    assert result.working_copy != tmp_path
    assert result.working_copy.exists()


def test_restricted_working_copy_sentinel(tmp_path: Path) -> None:
    """Restricted no longer means working_copy is the sentinel project_root —
    a real copy is made, same as any other run."""
    (tmp_path / "nlsy_confidential.dta").write_bytes(b"")

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True)

    assert result.restricted.is_restricted
    assert result.working_copy != tmp_path
    assert result.working_copy.exists()


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
    """Author says yes; nothing in the filenames would ever catch it. The
    pipeline still proceeds (#27) — restricted just means LLM off."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "wages.csv").write_bytes(b"")  # innocuous name
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")

    intake = questionnaire(answers={"restricted_data": "yes", "data_root": "data"})

    snapshot_before = set(Path(tempfile.gettempdir()).glob("dr_*"))

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True, intake=intake)

    snapshot_after = set(Path(tempfile.gettempdir()).glob("dr_*"))
    new_tmpdirs = snapshot_after - snapshot_before

    assert result.restricted.is_restricted
    assert result.error is None
    assert result.working_copy != tmp_path
    assert new_tmpdirs != set(), "A dr_* working-copy directory should have been created"


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
# §4.2 — a filename-heuristic hit is a lead, not proof: must be re-asked,
# never trusted (or dismissed) on its own.
# ---------------------------------------------------------------------------


def test_filename_hit_without_override_still_aborts(tmp_path: Path) -> None:
    """No re-ask has happened (intake=None) — fail-safe default is to stay
    restricted (LLM off), but the pipeline still proceeds (#27), not aborts."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "census_extract.csv").write_bytes(b"")
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True)

    assert result.restricted.is_restricted
    assert result.working_copy != tmp_path
    assert result.working_copy.exists()


def test_filename_hit_with_override_safe_proceeds(tmp_path: Path) -> None:
    """A filename match alone (e.g. a public-use `psid`-named extract) is not
    proof of restricted data. Once the author is re-asked and confirms this
    specific hit is a false positive, the pipeline must proceed — not abort
    just because the heuristic fired."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "psid_public_use_1997.csv").write_bytes(b"")
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")
    (tmp_path / "run.R").write_text("# script\n")

    intake = questionnaire(answers={"restricted_data": "no"})
    intake.restricted_override_safe = True

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True, intake=intake)

    assert not result.restricted.is_restricted, (
        "Confirmed false positive must clear DETECT, not just skip the abort"
    )
    assert result.working_copy != tmp_path
    assert result.working_copy.exists()


def test_filename_hit_override_unset_still_aborts(tmp_path: Path) -> None:
    """restricted_override_safe defaults to None — a filename hit must still
    be treated as restricted (LLM off) unless the author was actually
    re-asked and said it's safe. The pipeline still proceeds either way (#27)."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "census_extract.csv").write_bytes(b"")
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")

    intake = questionnaire(answers={"restricted_data": "no"})  # no re-ask performed

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True, intake=intake)

    assert result.restricted.is_restricted
    assert result.working_copy != tmp_path
    assert result.working_copy.exists()


# ---------------------------------------------------------------------------
# #27 — restricted runs still produce a working copy and a local-only
# data-structure profile; LLM-FIX stays off, so a fixable-by-LLM native
# failure stays failed instead of being auto-fixed.
# ---------------------------------------------------------------------------


def test_restricted_pipeline_continues_and_profiles_data(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "census_extract.csv").write_text("a,b\n1,2\n3,4\n")
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.R").write_text('read.csv("data/census_extract.csv")\n')
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")

    result = run_pipeline(tmp_path, skip_run=True, skip_docker=True)

    assert result.restricted.is_restricted
    assert result.working_copy != tmp_path
    assert result.working_copy.exists()
    summary = result.working_copy / "DATA-STRUCTURE-SUMMARY.md"
    assert summary.exists()
    assert result.data_profile is not None
    assert any(p.row_count == 2 for p in result.data_profile.profiles)


@pytest.mark.local
def test_restricted_native_failure_is_not_auto_fixed(tmp_path: Path) -> None:
    """A native run failure that LLM-FIX could plausibly patch (a wrong
    hardcoded path) must stay failed for a restricted run — the dispatcher
    is unconditionally refusing, not just skipped because no key is set."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.py").write_text(
        "open('/no/such/path/this_does_not_exist.csv').read()\n"
    )
    (tmp_path / "census_extract.csv").write_bytes(b"")  # filename trigger

    result = run_pipeline(
        tmp_path, master_script="code/run.py", skip_docker=True,
    )

    assert result.restricted.is_restricted
    assert result.error is not None
    assert "Native run failed" in result.error
    assert result.llm_fix_loop is not None
    assert result.llm_fix_loop.fixes_applied == []
    assert result.llm_fix_loop.converged is True  # dispatcher refused -> None -> "converged"


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


# ---------------------------------------------------------------------------
# master_script resolution — explicit flag > intake answer > auto-detect,
# and auto-detect must find a lone .do file even though it matches no
# named convention (run_all.sh / run.R / master.do).
# ---------------------------------------------------------------------------


def test_detect_master_script_finds_lone_do_file(tmp_path: Path) -> None:
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.do").write_text("* stata\n")

    assert _detect_master_script(tmp_path) == "code/analysis.do"


def test_detect_master_script_falls_back_when_ambiguous(tmp_path: Path) -> None:
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.do").write_text("* stata\n")
    (tmp_path / "code" / "cleaning.do").write_text("* stata\n")

    # More than one candidate of the same type — can't guess, keep old default.
    assert _detect_master_script(tmp_path) == "code/run.R"


def test_intake_master_script_used_when_arg_not_given(tmp_path: Path) -> None:
    """
    Entry point named so it matches none of _detect_master_script's known
    conventions (not run_all.sh/run.R/master.do) and isn't a lone .do file
    either — the only way it gets picked up is via intake.master_script.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "tables").mkdir()
    (tmp_path / "paper.tex").write_text(
        r"\documentclass{article}\begin{document}\input{tables/out.tex}\end{document}"
    )
    (tmp_path / "code" / "analysis.py").write_text(
        'open("tables/out.tex", "w").write("1.0")\n'
    )

    intake = questionnaire(answers={"restricted_data": "no", "master_script": "code/analysis.py"})

    result = run_pipeline(tmp_path, skip_docker=True, intake=intake)

    assert result.native_run is not None
    assert result.native_run.success, (
        f"expected intake.master_script to be used; stderr={result.native_run.stderr!r}"
    )
