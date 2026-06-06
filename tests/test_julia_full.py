"""Julia scan, capture, and fix loop tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.capture import capture_env
from deadreckoning.fix_loop import run_fix_loop
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind, PinMethod
from deadreckoning.resolve import resolve_paths
from deadreckoning.scan import scan_julia_scripts, scan_scripts

FIXTURE = Path(__file__).parent / "fixtures" / "julia_project"


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def test_scan_julia_extracts_using(tmp_path):
    (tmp_path / "run.jl").write_text("using DataFrames, CSV\nusing Plots\n")
    result = scan_julia_scripts(tmp_path)
    assert "DataFrames" in result.used_packages
    assert "CSV" in result.used_packages
    assert "Plots" in result.used_packages


def test_scan_julia_import_colon_syntax(tmp_path):
    """import Foo: bar, baz — only Foo is the package, not bar/baz."""
    (tmp_path / "run.jl").write_text(
        "import DataFrames: DataFrame, nrow\nimport CSV: read\n"
    )
    result = scan_julia_scripts(tmp_path)
    assert "DataFrames" in result.used_packages
    assert "CSV" in result.used_packages
    # Imported symbols must NOT appear as packages
    assert "DataFrame" not in result.used_packages
    assert "nrow" not in result.used_packages
    assert "read" not in result.used_packages


def test_scan_julia_excludes_stdlib(tmp_path):
    (tmp_path / "run.jl").write_text(
        "using LinearAlgebra\nusing Statistics\nusing DataFrames\n"
    )
    result = scan_julia_scripts(tmp_path)
    assert "LinearAlgebra" not in result.used_packages
    assert "Statistics" not in result.used_packages
    assert "DataFrames" in result.used_packages


def test_scan_julia_no_spurious_using_package(tmp_path):
    (tmp_path / "run.jl").write_text(
        "using DataFrames, CSV\nusing Plots\nusing Statistics\n"
    )
    result = scan_julia_scripts(tmp_path)
    assert "using" not in result.used_packages


def test_scan_julia_detects_dropbox_path():
    result = scan_julia_scripts(FIXTURE)
    assert any(ep.kind == "dropbox" for ep in result.external_paths)


def test_scan_julia_fixture_packages():
    result = scan_julia_scripts(FIXTURE)
    assert "DataFrames" in result.used_packages
    assert "CSV" in result.used_packages
    assert "Plots" in result.used_packages


def test_scan_scripts_includes_julia(tmp_path):
    (tmp_path / "run.R").write_text("library(ggplot2)\n")
    (tmp_path / "run.jl").write_text("using Plots\n")
    result = scan_scripts(tmp_path)
    assert "ggplot2" in result.used_packages
    assert "Plots" in result.used_packages


# ---------------------------------------------------------------------------
# Capture — Manifest.toml (high confidence)
# ---------------------------------------------------------------------------


def test_capture_julia_manifest_language():
    spec = capture_env(FIXTURE)
    assert spec.language == "Julia"
    assert spec.pin_method == PinMethod.manifest_toml


def test_capture_julia_manifest_packages():
    spec = capture_env(FIXTURE)
    names = [p.name for p in spec.packages]
    assert "CSV" in names
    assert "DataFrames" in names
    assert "Plots" in names


def test_capture_julia_manifest_high_confidence():
    spec = capture_env(FIXTURE)
    assert spec.confidence >= 0.9


def test_capture_julia_manifest_versions():
    spec = capture_env(FIXTURE)
    csv_pkg = next((p for p in spec.packages if p.name == "CSV"), None)
    assert csv_pkg is not None
    assert csv_pkg.version is not None


def test_capture_julia_manifest_takes_priority_over_project_toml(tmp_path):
    (tmp_path / "Manifest.toml").write_text(
        '[[deps.Plots]]\nuuid = "abc"\nversion = "1.39.0"\n'
    )
    (tmp_path / "Project.toml").write_text("[deps]\nPlots = \"abc\"\n")
    spec = capture_env(tmp_path)
    assert spec.pin_method == PinMethod.manifest_toml
    assert spec.confidence >= 0.9


# ---------------------------------------------------------------------------
# Capture — Project.toml only (medium confidence)
# ---------------------------------------------------------------------------


def test_capture_julia_project_toml(tmp_path):
    (tmp_path / "Project.toml").write_text(
        "[deps]\nDataFrames = \"a93c6f00-e57d-5684-b466-afe8fa294f15\"\n"
    )
    spec = capture_env(tmp_path)
    assert spec.language == "Julia"
    names = [p.name for p in spec.packages]
    assert "DataFrames" in names
    assert spec.confidence < 0.9


# ---------------------------------------------------------------------------
# Capture — no lockfile
# ---------------------------------------------------------------------------


def test_capture_julia_no_lockfile_language(tmp_path):
    (tmp_path / "run.jl").write_text("using Plots\n")
    spec = capture_env(tmp_path)
    assert spec.language == "Julia"
    assert spec.pin_method == PinMethod.inferred_from_date


def test_capture_julia_no_lockfile_low_confidence(tmp_path):
    (tmp_path / "run.jl").write_text("using Plots\n")
    spec = capture_env(tmp_path)
    assert spec.confidence < 0.5


# ---------------------------------------------------------------------------
# Fix loop
# ---------------------------------------------------------------------------


@pytest.fixture()
def working_copy(tmp_path):
    copy = tmp_path / "project"
    shutil.copytree(FIXTURE, copy)
    return copy


def test_fix_loop_julia_applies_one_fix(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    result, _ = run_fix_loop(working_copy, graph)

    assert result.converged
    assert len(result.fixes_applied) == 1
    assert result.fixes_applied[0].old_path == "fig1.pdf"
    assert result.fixes_applied[0].new_path == "figures/fig1.pdf"


def test_fix_loop_julia_removes_mismatch_gap(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    _, updated = run_fix_loop(working_copy, graph)

    kinds = {g.kind for g in updated.gaps}
    assert GapKind.script_writes_wrong_path not in kinds


def test_fix_loop_julia_script_updated(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    run_fix_loop(working_copy, graph)

    analysis = (working_copy / "code" / "analysis.jl").read_text()
    assert '"figures/fig1.pdf"' in analysis
    assert '"fig1.pdf"' not in analysis


def test_fix_loop_julia_dropbox_path_rewritten(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)

    analysis = (working_copy / "code" / "analysis.jl").read_text()
    assert "/Users/jsmith/Dropbox" not in analysis


def test_fix_loop_julia_original_untouched(working_copy):
    original = (FIXTURE / "code" / "analysis.jl").read_text()
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)
    assert (FIXTURE / "code" / "analysis.jl").read_text() == original
