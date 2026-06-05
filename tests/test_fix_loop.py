"""Tests for fix_loop.py — end-state assertions, no R execution needed."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.fix_loop import (
    FixAction,
    FixContext,
    FixLoopResult,
    DeterministicDispatcher,
    append_fix_report,
    apply_fix,
    fix_write_path,
    run_fix_loop,
)
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind, ScriptWritesExhibit, Exhibit, Gap, DependencyGraph
from deadreckoning.scan import scan_r_scripts
from deadreckoning.resolve import resolve_paths

FIXTURE = Path(__file__).parent / "fixtures" / "r_no_lockfile"


# ---------------------------------------------------------------------------
# fix_write_path tool — unit tests
# ---------------------------------------------------------------------------


def test_fix_write_path_rewrites_quoted_string(tmp_path):
    script = tmp_path / "analysis.R"
    script.write_text('ggsave("fig1.pdf", plot = p)\n')

    action = FixAction(
        kind="fix_write_path",
        script=Path("analysis.R"),
        old_path="fig1.pdf",
        new_path="figures/fig1.pdf",
    )
    ok = fix_write_path(tmp_path, action)

    assert ok
    assert 'ggsave("figures/fig1.pdf"' in script.read_text()
    assert '"fig1.pdf"' not in script.read_text()


def test_fix_write_path_single_quotes(tmp_path):
    script = tmp_path / "run.R"
    script.write_text("ggsave('fig1.pdf', plot = p)\n")

    action = FixAction(
        kind="fix_write_path",
        script=Path("run.R"),
        old_path="fig1.pdf",
        new_path="figures/fig1.pdf",
    )
    ok = fix_write_path(tmp_path, action)

    assert ok
    assert "'figures/fig1.pdf'" in script.read_text()


def test_fix_write_path_returns_false_when_not_found(tmp_path):
    script = tmp_path / "run.R"
    script.write_text('ggsave("other_file.pdf")\n')

    action = FixAction(
        kind="fix_write_path",
        script=Path("run.R"),
        old_path="fig1.pdf",
        new_path="figures/fig1.pdf",
    )
    ok = fix_write_path(tmp_path, action)
    assert not ok


def test_fix_write_path_missing_script_returns_false(tmp_path):
    action = FixAction(
        kind="fix_write_path",
        script=Path("nonexistent.R"),
        old_path="fig1.pdf",
        new_path="figures/fig1.pdf",
    )
    assert not fix_write_path(tmp_path, action)


# ---------------------------------------------------------------------------
# DeterministicDispatcher — unit tests
# ---------------------------------------------------------------------------


def _make_graph_with_mismatch(working_copy: Path) -> DependencyGraph:
    """Minimal graph: one script_writes_wrong_path gap."""
    src = ScriptWritesExhibit(
        script=working_copy / "code" / "analysis.R",
        write_call="ggsave",
        line=15,
        written_path=Path("fig1.pdf"),
    )
    exhibit = Exhibit(
        tex_path=Path("figures/fig1.pdf"),
        exists_on_disk=True,
        source=src,
        path_mismatch=True,
    )
    gap = Gap(
        kind=GapKind.script_writes_wrong_path,
        exhibit=Path("figures/fig1.pdf"),
    )
    return DependencyGraph(
        project_root=working_copy,
        exhibits=[exhibit],
        gaps=[gap],
    )


def test_deterministic_dispatcher_emits_fix_for_mismatch(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.R").write_text('ggsave("fig1.pdf")\n')

    graph = _make_graph_with_mismatch(tmp_path)
    dispatcher = DeterministicDispatcher()
    context = FixContext(working_copy=tmp_path, graph=graph)

    action = dispatcher.next_fix(graph.gaps, context)

    assert action is not None
    assert action.kind == "fix_write_path"
    assert action.old_path == "fig1.pdf"
    assert action.new_path == "figures/fig1.pdf"


def test_deterministic_dispatcher_returns_none_after_dispatch(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.R").write_text('ggsave("fig1.pdf")\n')

    graph = _make_graph_with_mismatch(tmp_path)
    dispatcher = DeterministicDispatcher()
    context = FixContext(working_copy=tmp_path, graph=graph)

    dispatcher.next_fix(graph.gaps, context)  # first call dispatches
    action2 = dispatcher.next_fix(graph.gaps, context)  # same gaps, already handled
    assert action2 is None


def test_deterministic_dispatcher_skips_other_gap_kinds(tmp_path):
    graph = DependencyGraph(
        project_root=tmp_path,
        gaps=[
            Gap(kind=GapKind.inline_table, location="paper.tex:10-20"),
            Gap(kind=GapKind.exhibit_missing_from_disk, exhibit=Path("figures/fig3.pdf")),
        ],
    )
    dispatcher = DeterministicDispatcher()
    context = FixContext(working_copy=tmp_path, graph=graph)
    assert dispatcher.next_fix(graph.gaps, context) is None


# ---------------------------------------------------------------------------
# run_fix_loop — integration with r_no_lockfile fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def working_copy(tmp_path):
    copy = tmp_path / "project"
    shutil.copytree(FIXTURE, copy)
    return copy


def test_fix_loop_r_no_lockfile_applies_one_fix(working_copy):
    """After scan+resolve, one script_writes_wrong_path gap remains → one fix."""
    scan = scan_r_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    result, updated_graph = run_fix_loop(working_copy, graph)

    assert result.converged
    assert len(result.fixes_applied) == 1
    assert result.fixes_applied[0].kind == "fix_write_path"
    assert result.fixes_applied[0].old_path == "fig1.pdf"
    assert result.fixes_applied[0].new_path == "figures/fig1.pdf"


def test_fix_loop_removes_script_writes_wrong_path_gap(working_copy):
    scan = scan_r_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    _, updated_graph = run_fix_loop(working_copy, graph)

    remaining_kinds = {g.kind for g in updated_graph.gaps}
    assert GapKind.script_writes_wrong_path not in remaining_kinds


def test_fix_loop_script_updated_on_disk(working_copy):
    scan = scan_r_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    run_fix_loop(working_copy, graph)

    analysis = (working_copy / "code" / "analysis.R").read_text()
    assert '"figures/fig1.pdf"' in analysis
    assert '"fig1.pdf"' not in analysis


def test_fix_loop_original_fixture_untouched(working_copy):
    original = (FIXTURE / "code" / "analysis.R").read_text()

    scan = scan_r_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)

    assert (FIXTURE / "code" / "analysis.R").read_text() == original


# ---------------------------------------------------------------------------
# run_fix_loop — clean project (no gaps to fix)
# ---------------------------------------------------------------------------


def test_fix_loop_clean_project_zero_fixes(tmp_path):
    (tmp_path / "run.R").write_text('df <- read.csv("data/survey.csv")\n')
    graph = build_graph(tmp_path)

    result, _ = run_fix_loop(tmp_path, graph)

    assert result.converged
    assert len(result.fixes_applied) == 0
    assert result.iterations == 1


def test_fix_loop_converged_flag(tmp_path):
    graph = DependencyGraph(project_root=tmp_path, gaps=[])
    result, _ = run_fix_loop(tmp_path, graph)
    assert result.converged is True


# ---------------------------------------------------------------------------
# append_fix_report
# ---------------------------------------------------------------------------


def test_append_fix_report_creates_file(tmp_path):
    fix_result = FixLoopResult(
        iterations=1, converged=True,
        fixes_applied=[
            FixAction(kind="fix_write_path", script=Path("code/analysis.R"),
                      old_path="fig1.pdf", new_path="figures/fig1.pdf"),
        ],
    )
    append_fix_report(tmp_path, fix_result)
    report = tmp_path / "AGENT_REPORT.md"
    assert report.exists()
    text = report.read_text()
    assert "FIX loop" in text
    assert "fix_write_path" in text
    assert "fig1.pdf" in text


def test_append_fix_report_appends_to_existing(tmp_path):
    report = tmp_path / "AGENT_REPORT.md"
    report.write_text("# DeadReckoning — Agent Report\n\n## Path rewrites\n\n_None._\n")

    fix_result = FixLoopResult(iterations=1, converged=True)
    append_fix_report(tmp_path, fix_result)

    text = report.read_text()
    assert "Path rewrites" in text  # original section preserved
    assert "FIX loop" in text       # new section appended


def test_append_fix_report_no_fixes_message(tmp_path):
    fix_result = FixLoopResult(iterations=1, converged=True)
    append_fix_report(tmp_path, fix_result)
    text = (tmp_path / "AGENT_REPORT.md").read_text()
    assert "No fixes needed" in text
