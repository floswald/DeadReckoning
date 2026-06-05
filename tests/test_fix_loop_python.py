"""FIX loop end-to-end tests for Python fixture."""

from __future__ import annotations

import shutil
from pathlib import Path

from deadreckoning.fix_loop import run_fix_loop
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind
from deadreckoning.resolve import resolve_paths
from deadreckoning.scan import scan_scripts

FIXTURE = Path(__file__).parent / "fixtures" / "python_project"


def _working_copy(tmp_path):
    copy = tmp_path / "project"
    shutil.copytree(FIXTURE, copy)
    return copy


def test_fix_loop_python_applies_one_fix(tmp_path):
    wc = _working_copy(tmp_path)
    scan = scan_scripts(wc)
    resolve_paths(wc, scan)
    graph = build_graph(wc)

    result, _ = run_fix_loop(wc, graph)

    assert result.converged
    assert len(result.fixes_applied) == 1
    assert result.fixes_applied[0].kind == "fix_write_path"
    assert result.fixes_applied[0].old_path == "fig1.pdf"
    assert result.fixes_applied[0].new_path == "figures/fig1.pdf"


def test_fix_loop_python_removes_mismatch_gap(tmp_path):
    wc = _working_copy(tmp_path)
    scan = scan_scripts(wc)
    resolve_paths(wc, scan)
    graph = build_graph(wc)

    _, updated = run_fix_loop(wc, graph)

    kinds = {g.kind for g in updated.gaps}
    assert GapKind.script_writes_wrong_path not in kinds


def test_fix_loop_python_script_updated(tmp_path):
    wc = _working_copy(tmp_path)
    scan = scan_scripts(wc)
    resolve_paths(wc, scan)
    graph = build_graph(wc)

    run_fix_loop(wc, graph)

    analysis = (wc / "code" / "analysis.py").read_text()
    assert '"figures/fig1.pdf"' in analysis
    assert '"fig1.pdf"' not in analysis


def test_fix_loop_python_dropbox_path_rewritten(tmp_path):
    wc = _working_copy(tmp_path)
    scan = scan_scripts(wc)
    resolve_paths(wc, scan)

    analysis = (wc / "code" / "analysis.py").read_text()
    assert "/Users/jsmith/Dropbox" not in analysis


def test_fix_loop_python_original_untouched(tmp_path):
    original = (FIXTURE / "code" / "analysis.py").read_text()
    wc = _working_copy(tmp_path)
    scan = scan_scripts(wc)
    resolve_paths(wc, scan)
    graph = build_graph(wc)
    run_fix_loop(wc, graph)

    assert (FIXTURE / "code" / "analysis.py").read_text() == original
