"""MATLAB scan, capture, and fix loop tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.capture import capture_env
from deadreckoning.fix_loop import run_fix_loop
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind, PinMethod
from deadreckoning.resolve import resolve_paths
from deadreckoning.scan import scan_matlab_scripts, scan_scripts

FIXTURE = Path(__file__).parent / "fixtures" / "matlab_project"


# ---------------------------------------------------------------------------
# Scan — toolbox detection
# ---------------------------------------------------------------------------


def test_scan_matlab_detects_statistics_toolbox(tmp_path):
    (tmp_path / "run.m").write_text("lm = fitlm(T, 'y ~ x');\n")
    result = scan_matlab_scripts(tmp_path)
    assert "Statistics and Machine Learning Toolbox" in result.used_packages


def test_scan_matlab_detects_optimization_toolbox(tmp_path):
    (tmp_path / "run.m").write_text("[x, f] = fmincon(@obj, x0, A, b);\n")
    result = scan_matlab_scripts(tmp_path)
    assert "Optimization Toolbox" in result.used_packages


def test_scan_matlab_skips_comment_lines(tmp_path):
    (tmp_path / "run.m").write_text("% lm = fitlm(T, 'y ~ x');\nlm = 1;\n")
    result = scan_matlab_scripts(tmp_path)
    assert "Statistics and Machine Learning Toolbox" not in result.used_packages


def test_scan_matlab_fixture_toolboxes():
    result = scan_matlab_scripts(FIXTURE)
    assert "Statistics and Machine Learning Toolbox" in result.used_packages
    assert "Optimization Toolbox" in result.used_packages


def test_scan_matlab_detects_addpath(tmp_path):
    (tmp_path / "run.m").write_text("addpath('/Users/jsmith/code/mylib');\n")
    result = scan_matlab_scripts(tmp_path)
    assert any("addpath:" in p for p in result.used_packages)


def test_scan_matlab_fixture_external_paths():
    result = scan_matlab_scripts(FIXTURE)
    assert len(result.external_paths) == 1
    assert result.external_paths[0].kind == "dropbox"
    assert "lfs_2019.csv" in result.external_paths[0].raw


def test_scan_matlab_in_scan_scripts():
    result = scan_scripts(FIXTURE)
    assert "Statistics and Machine Learning Toolbox" in result.used_packages


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def test_capture_matlab_language():
    spec = capture_env(FIXTURE)
    assert spec.language == "MATLAB"
    assert spec.pin_method == PinMethod.inferred_from_date


def test_capture_matlab_low_confidence():
    spec = capture_env(FIXTURE)
    assert spec.confidence < 0.5


def test_capture_matlab_has_date(tmp_path):
    import re
    (tmp_path / "run.m").write_text("x = 1;\n")
    spec = capture_env(tmp_path)
    assert spec.language == "MATLAB"
    assert spec.snapshot_date is not None
    assert re.match(r"\d{4}-\d{2}-\d{2}", spec.snapshot_date)


def test_capture_matlab_note_contains_docker_advice():
    spec = capture_env(FIXTURE)
    assert spec.note is not None
    assert "mathworks/matlab" in spec.note
    assert "interactive" in spec.note.lower() or "browser" in spec.note


def test_capture_matlab_note_mentions_toolboxes():
    spec = capture_env(FIXTURE)
    assert "Toolbox" in spec.note or "toolbox" in spec.note.lower()


# ---------------------------------------------------------------------------
# Graph — write call patterns
# ---------------------------------------------------------------------------


def test_graph_matlab_saveas_detected():
    graph = build_graph(FIXTURE)
    assert len(graph.exhibits) == 1
    assert graph.exhibits[0].path_mismatch


def test_graph_matlab_script_writes_wrong_path():
    graph = build_graph(FIXTURE)
    assert any(g.kind == GapKind.script_writes_wrong_path for g in graph.gaps)


def test_graph_matlab_exportgraphics(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text(
        r"\documentclass{article}\usepackage{graphicx}\begin{document}"
        r"\includegraphics{figures/out}\end{document}"
    )
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "out.pdf").write_text("placeholder")
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.m").write_text(
        "exportgraphics(fig, 'out.pdf');\n"
    )
    graph = build_graph(tmp_path)
    wrong_path_gaps = [g for g in graph.gaps
                       if g.kind == GapKind.script_writes_wrong_path]
    assert len(wrong_path_gaps) == 1


def test_graph_matlab_writetable(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text(
        r"\documentclass{article}\usepackage{graphicx}\begin{document}"
        r"\input{tables/tab1.tex}\end{document}"
    )
    (tmp_path / "tables").mkdir()
    (tmp_path / "tables" / "tab1.tex").write_text("placeholder")
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.m").write_text(
        "writetable(T, 'tab1.tex');\n"
    )
    graph = build_graph(tmp_path)
    wrong_path_gaps = [g for g in graph.gaps
                       if g.kind == GapKind.script_writes_wrong_path]
    assert len(wrong_path_gaps) == 1


# ---------------------------------------------------------------------------
# Fix loop
# ---------------------------------------------------------------------------


@pytest.fixture()
def working_copy(tmp_path):
    copy = tmp_path / "project"
    shutil.copytree(FIXTURE, copy)
    return copy


def test_fix_loop_matlab_applies_one_fix(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    result, _ = run_fix_loop(working_copy, graph)

    assert result.converged
    assert len(result.fixes_applied) == 1
    assert result.fixes_applied[0].kind == "fix_write_path"
    assert result.fixes_applied[0].old_path == "fig1.pdf"
    assert result.fixes_applied[0].new_path == "figures/fig1.pdf"


def test_fix_loop_matlab_removes_mismatch_gap(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    _, updated = run_fix_loop(working_copy, graph)

    kinds = {g.kind for g in updated.gaps}
    assert GapKind.script_writes_wrong_path not in kinds


def test_fix_loop_matlab_script_updated(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    run_fix_loop(working_copy, graph)

    text = (working_copy / "code" / "analysis.m").read_text()
    assert "'figures/fig1.pdf'" in text
    assert "'fig1.pdf'" not in text


def test_fix_loop_matlab_dropbox_path_rewritten(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)

    text = (working_copy / "code" / "analysis.m").read_text()
    assert "/Users/jsmith/Dropbox" not in text


def test_fix_loop_matlab_original_untouched(working_copy):
    original = (FIXTURE / "code" / "analysis.m").read_text()
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)
    assert (FIXTURE / "code" / "analysis.m").read_text() == original
