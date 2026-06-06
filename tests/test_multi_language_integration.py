"""
Integration test: multi_language_full fixture (R + Julia + Stata).

Verifies that scan, graph, resolve, and fix_loop work end-to-end across
all three languages in a single project.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.fix_loop import run_fix_loop
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind
from deadreckoning.resolve import resolve_paths
from deadreckoning.scan import scan_scripts

FIXTURE = Path(__file__).parent / "fixtures" / "multi_language_full"


@pytest.fixture()
def working_copy(tmp_path):
    copy = tmp_path / "project"
    shutil.copytree(FIXTURE, copy)
    return copy


# ---------------------------------------------------------------------------
# SCAN: all languages
# ---------------------------------------------------------------------------


def test_multi_scan_r_packages():
    result = scan_scripts(FIXTURE)
    assert "ggplot2" in result.used_packages
    assert "haven" in result.used_packages


def test_multi_scan_julia_packages():
    result = scan_scripts(FIXTURE)
    assert "DataFrames" in result.used_packages
    assert "CSV" in result.used_packages
    assert "Plots" in result.used_packages


def test_multi_scan_stata_packages():
    result = scan_scripts(FIXTURE)
    assert "reghdfe" in result.used_packages


def test_multi_scan_all_external_paths():
    result = scan_scripts(FIXTURE)
    assert len(result.external_paths) == 3
    assert all(ep.kind == "dropbox" for ep in result.external_paths)


# ---------------------------------------------------------------------------
# GRAPH: 3 exhibits, all path mismatches
# ---------------------------------------------------------------------------


def test_multi_graph_three_exhibits():
    graph = build_graph(FIXTURE)
    assert len(graph.exhibits) == 3


def test_multi_graph_all_script_writes_wrong_path():
    graph = build_graph(FIXTURE)
    wrong_path_gaps = [g for g in graph.gaps
                       if g.kind == GapKind.script_writes_wrong_path]
    assert len(wrong_path_gaps) == 3


def test_multi_graph_covers_all_languages():
    graph = build_graph(FIXTURE)
    source_scripts = {e.source.script.suffix for e in graph.exhibits
                      if e.source is not None}
    assert ".R" in source_scripts
    assert ".jl" in source_scripts
    assert ".do" in source_scripts


# ---------------------------------------------------------------------------
# RESOLVE: absolute paths rewritten in all scripts
# ---------------------------------------------------------------------------


def test_multi_resolve_rewrites_r_paths(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    text = (working_copy / "code" / "analysis.R").read_text()
    assert "/Users/jsmith/Dropbox" not in text


def test_multi_resolve_rewrites_julia_paths(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    text = (working_copy / "code" / "analysis.jl").read_text()
    assert "/Users/jsmith/Dropbox" not in text


def test_multi_resolve_rewrites_stata_paths(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    text = (working_copy / "code" / "analysis.do").read_text()
    assert "/Users/jsmith/Dropbox" not in text


def test_multi_resolve_writes_config_do(working_copy):
    scan = scan_scripts(working_copy)
    result = resolve_paths(working_copy, scan)
    assert result.config_do_written
    assert (working_copy / "code" / "_config.do").exists()


# ---------------------------------------------------------------------------
# FIX LOOP: 3 path mismatches fixed
# ---------------------------------------------------------------------------


def test_multi_fix_loop_applies_three_fixes(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    result, _ = run_fix_loop(working_copy, graph)

    assert result.converged
    assert len(result.fixes_applied) == 3


def test_multi_fix_loop_all_mismatches_resolved(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    _, updated = run_fix_loop(working_copy, graph)

    wrong_path_gaps = [g for g in updated.gaps
                       if g.kind == GapKind.script_writes_wrong_path]
    assert len(wrong_path_gaps) == 0


def test_multi_fix_loop_r_script_updated(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)

    text = (working_copy / "code" / "analysis.R").read_text()
    assert '"figures/fig_r.pdf"' in text


def test_multi_fix_loop_julia_script_updated(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)

    text = (working_copy / "code" / "analysis.jl").read_text()
    assert '"figures/fig_jl.pdf"' in text


def test_multi_fix_loop_stata_script_updated(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)

    text = (working_copy / "code" / "analysis.do").read_text()
    assert '"figures/fig_stata.pdf"' in text


def test_multi_original_fixture_untouched(working_copy):
    originals = {
        "R": (FIXTURE / "code" / "analysis.R").read_text(),
        "jl": (FIXTURE / "code" / "analysis.jl").read_text(),
        "do": (FIXTURE / "code" / "analysis.do").read_text(),
    }
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)

    assert (FIXTURE / "code" / "analysis.R").read_text() == originals["R"]
    assert (FIXTURE / "code" / "analysis.jl").read_text() == originals["jl"]
    assert (FIXTURE / "code" / "analysis.do").read_text() == originals["do"]
