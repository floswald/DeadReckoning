"""Full Stata pipeline tests — scan, capture, _config.do, fix loop."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.capture import capture_env
from deadreckoning.fix_loop import run_fix_loop
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind, PinMethod
from deadreckoning.resolve import resolve_paths
from deadreckoning.scan import scan_scripts, scan_stata_scripts
from deadreckoning.stata import generate_config_do, write_config_do

FIXTURE = Path(__file__).parent / "fixtures" / "stata_project"


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def test_scan_stata_extracts_ssc_packages():
    result = scan_stata_scripts(FIXTURE)
    assert "reghdfe" in result.used_packages
    assert "ftools" in result.used_packages


def test_scan_stata_detects_dropbox_path():
    result = scan_stata_scripts(FIXTURE)
    assert len(result.external_paths) == 1
    assert result.external_paths[0].kind == "dropbox"


def test_scan_stata_in_scan_scripts():
    result = scan_scripts(FIXTURE)
    assert "reghdfe" in result.used_packages
    assert "ftools" in result.used_packages


def test_scan_stata_skips_comment_lines(tmp_path):
    (tmp_path / "analysis.do").write_text(
        "* ssc install notapackage, replace\nssc install mypackage, replace\n"
    )
    result = scan_stata_scripts(tmp_path)
    assert "mypackage" in result.used_packages
    assert "notapackage" not in result.used_packages


def test_scan_stata_net_install(tmp_path):
    (tmp_path / "setup.do").write_text("net install myado, from(https://example.com/)\n")
    result = scan_stata_scripts(tmp_path)
    assert "myado" in result.used_packages


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def test_capture_stata_fixture_language():
    spec = capture_env(FIXTURE)
    assert spec.language == "Stata"
    assert spec.pin_method == PinMethod.unknown


def test_capture_stata_fixture_packages():
    spec = capture_env(FIXTURE)
    names = [p.name for p in spec.packages]
    assert "reghdfe" in names
    assert "ftools" in names


def test_capture_stata_low_confidence():
    spec = capture_env(FIXTURE)
    assert spec.confidence < 0.5


# ---------------------------------------------------------------------------
# _config.do generation
# ---------------------------------------------------------------------------


def test_generate_config_do_sysdir():
    content = generate_config_do([])
    assert 'sysdir set PLUS' in content
    assert 'sysdir set PERSONAL' in content
    assert 'code/ado/' in content


def test_generate_config_do_packages():
    content = generate_config_do(["reghdfe", "ftools"])
    assert "ssc install reghdfe" in content
    assert "ssc install ftools" in content
    assert "replace" in content


def test_generate_config_do_no_packages():
    content = generate_config_do([])
    assert "ssc install" not in content


def test_write_config_do_creates_file(tmp_path):
    (tmp_path / "code").mkdir()
    path = write_config_do(tmp_path, ["reghdfe"])
    assert path.exists()
    assert path == tmp_path / "code" / "_config.do"


def test_write_config_do_creates_code_dir(tmp_path):
    path = write_config_do(tmp_path, [])
    assert (tmp_path / "code").is_dir()


# ---------------------------------------------------------------------------
# Resolve — _config.do written for Stata projects
# ---------------------------------------------------------------------------


def test_resolve_writes_config_do_for_stata(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "project")
    wc = tmp_path / "project"
    scan = scan_scripts(wc)
    result = resolve_paths(wc, scan)

    assert result.config_do_written
    assert (wc / "code" / "_config.do").exists()
    content = (wc / "code" / "_config.do").read_text()
    assert "reghdfe" in content
    assert "ftools" in content


def test_resolve_no_config_do_for_r_project(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "r_no_lockfile"
    wc = tmp_path / "project"
    shutil.copytree(fixture, wc)
    scan = scan_scripts(wc)
    result = resolve_paths(wc, scan)
    assert not result.config_do_written


# ---------------------------------------------------------------------------
# Fix loop — graph export path mismatch
# ---------------------------------------------------------------------------


@pytest.fixture()
def working_copy(tmp_path):
    copy = tmp_path / "project"
    shutil.copytree(FIXTURE, copy)
    return copy


def test_fix_loop_stata_applies_one_fix(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    result, _ = run_fix_loop(working_copy, graph)

    assert result.converged
    assert len(result.fixes_applied) == 1
    assert result.fixes_applied[0].kind == "fix_write_path"
    assert result.fixes_applied[0].old_path == "fig1.pdf"
    assert result.fixes_applied[0].new_path == "figures/fig1.pdf"


def test_fix_loop_stata_removes_mismatch_gap(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    _, updated = run_fix_loop(working_copy, graph)

    kinds = {g.kind for g in updated.gaps}
    assert GapKind.script_writes_wrong_path not in kinds


def test_fix_loop_stata_script_updated(working_copy):
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)

    run_fix_loop(working_copy, graph)

    analysis = (working_copy / "code" / "analysis.do").read_text()
    assert '"figures/fig1.pdf"' in analysis
    assert '"fig1.pdf"' not in analysis


def test_fix_loop_stata_original_untouched(working_copy):
    original = (FIXTURE / "code" / "analysis.do").read_text()
    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)
    assert (FIXTURE / "code" / "analysis.do").read_text() == original
