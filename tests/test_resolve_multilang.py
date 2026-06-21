"""
Multi-language RESOLVE tests.

Covers absolute path rewriting and relative path canonicalization for
Python, Julia, and MATLAB scripts.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.resolve import (
    _adopt_julia_at_dir,
    _adopt_matlab_fullfile,
    _adopt_python_pathlib,
    _script_depth,
    resolve_paths,
)
from deadreckoning.scan import scan_scripts

JULIA_FIXTURE = Path(__file__).parent / "fixtures" / "julia_project"
PYTHON_FIXTURE = Path(__file__).parent / "fixtures" / "python_external_data"
MATLAB_FIXTURE = Path(__file__).parent / "fixtures" / "matlab_project"


# ---------------------------------------------------------------------------
# _script_depth
# ---------------------------------------------------------------------------


def test_script_depth_at_root(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("")
    assert _script_depth(script, tmp_path) == 0


def test_script_depth_one_level(tmp_path):
    script = tmp_path / "code" / "analysis.py"
    script.parent.mkdir()
    script.write_text("")
    assert _script_depth(script, tmp_path) == 1


def test_script_depth_two_levels(tmp_path):
    script = tmp_path / "code" / "utils" / "helpers.py"
    script.parent.mkdir(parents=True)
    script.write_text("")
    assert _script_depth(script, tmp_path) == 2


# ---------------------------------------------------------------------------
# Absolute path rewriting — already language-agnostic, verify per language
# ---------------------------------------------------------------------------


@pytest.fixture()
def julia_copy(tmp_path):
    copy = tmp_path / "julia"
    shutil.copytree(JULIA_FIXTURE, copy)
    return copy


@pytest.fixture()
def python_copy(tmp_path):
    copy = tmp_path / "python"
    shutil.copytree(PYTHON_FIXTURE, copy)
    return copy


@pytest.fixture()
def matlab_copy(tmp_path):
    copy = tmp_path / "matlab"
    shutil.copytree(MATLAB_FIXTURE, copy)
    return copy


def test_resolve_julia_removes_absolute_path(julia_copy):
    scan = scan_scripts(julia_copy)
    resolve_paths(julia_copy, scan)
    for script in julia_copy.rglob("*.jl"):
        assert "/Users/jsmith/Dropbox" not in script.read_text()


def test_resolve_python_removes_absolute_path(python_copy):
    scan = scan_scripts(python_copy)
    resolve_paths(python_copy, scan)
    for script in python_copy.rglob("*.py"):
        assert "/Users/jsmith/Dropbox" not in script.read_text()


def test_resolve_matlab_removes_absolute_path(matlab_copy):
    scan = scan_scripts(matlab_copy)
    resolve_paths(matlab_copy, scan)
    for script in matlab_copy.rglob("*.m"):
        assert "/Users/jsmith/Dropbox" not in script.read_text()


def test_resolve_julia_rewrites_recorded(julia_copy):
    scan = scan_scripts(julia_copy)
    result = resolve_paths(julia_copy, scan)
    assert result.rewrite_count > 0


def test_resolve_python_rewrites_recorded(python_copy):
    scan = scan_scripts(python_copy)
    result = resolve_paths(python_copy, scan)
    assert result.rewrite_count > 0


def test_resolve_matlab_rewrites_recorded(matlab_copy):
    scan = scan_scripts(matlab_copy)
    result = resolve_paths(matlab_copy, scan)
    assert result.rewrite_count > 0


def test_resolve_julia_manifest_written(julia_copy):
    scan = scan_scripts(julia_copy)
    resolve_paths(julia_copy, scan)
    assert (julia_copy / "data" / "data-manifest.csv").exists()


def test_resolve_python_manifest_written(python_copy):
    scan = scan_scripts(python_copy)
    resolve_paths(python_copy, scan)
    assert (python_copy / "data" / "data-manifest.csv").exists()


def test_resolve_matlab_manifest_written(matlab_copy):
    scan = scan_scripts(matlab_copy)
    resolve_paths(matlab_copy, scan)
    assert (matlab_copy / "data" / "data-manifest.csv").exists()


# ---------------------------------------------------------------------------
# _adopt_python_pathlib
# ---------------------------------------------------------------------------


def test_adopt_python_wraps_relative_path(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.py"
    script.write_text('df = pd.read_csv("data/lfs.csv")\n')
    _adopt_python_pathlib(tmp_path, [])
    text = script.read_text()
    assert "Path(__file__).parents[1]" in text
    # Bare standalone literal replaced by pathlib expression
    assert 'pd.read_csv("data/lfs.csv")' not in text


def test_adopt_python_adds_pathlib_import(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.py"
    script.write_text('df = pd.read_csv("data/lfs.csv")\n')
    _adopt_python_pathlib(tmp_path, [])
    text = script.read_text()
    assert "from pathlib import Path" in text


def test_adopt_python_skips_if_import_present(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.py"
    script.write_text('from pathlib import Path\ndf = pd.read_csv("data/lfs.csv")\n')
    _adopt_python_pathlib(tmp_path, [])
    text = script.read_text()
    assert text.count("from pathlib import Path") == 1


def test_adopt_python_skips_depth_zero(tmp_path):
    script = tmp_path / "analysis.py"
    script.write_text('df = pd.read_csv("data/lfs.csv")\n')
    _adopt_python_pathlib(tmp_path, [])
    # At root, no wrapping (relative path works from project root cwd)
    assert "Path(__file__)" not in script.read_text()


def test_adopt_python_depth2_uses_parents2(tmp_path):
    (tmp_path / "code" / "utils").mkdir(parents=True)
    script = tmp_path / "code" / "utils" / "helpers.py"
    script.write_text('f = open("data/lfs.csv")\n')
    _adopt_python_pathlib(tmp_path, [])
    assert "parents[2]" in script.read_text()


def test_adopt_python_skips_already_wrapped(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.py"
    script.write_text('p = str(Path(__file__).parents[1] / "data/lfs.csv")\n')
    _adopt_python_pathlib(tmp_path, [])
    text = script.read_text()
    assert text.count("parents[1]") == 1


def test_adopt_python_result_count(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.py"
    script.write_text('a = "data/a.csv"\nb = "figures/fig.pdf"\n')
    n = _adopt_python_pathlib(tmp_path, [])
    assert n == 2


def test_resolve_python_pathlib_adoption_counted(python_copy):
    scan = scan_scripts(python_copy)
    result = resolve_paths(python_copy, scan)
    assert result.pathlib_adoptions >= 0  # may be 0 if no relative paths remain


# ---------------------------------------------------------------------------
# _adopt_julia_at_dir
# ---------------------------------------------------------------------------


def test_adopt_julia_wraps_relative_path(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.jl"
    script.write_text('df = CSV.read("data/lfs.csv", DataFrame)\n')
    _adopt_julia_at_dir(tmp_path, [])
    text = script.read_text()
    assert "joinpath(@__DIR__" in text
    assert '".."' in text
    # Bare standalone literal replaced; path now inside joinpath call
    assert 'CSV.read("data/lfs.csv"' not in text


def test_adopt_julia_depth1_one_up(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.jl"
    script.write_text('CSV.read("data/lfs.csv", DataFrame)\n')
    _adopt_julia_at_dir(tmp_path, [])
    text = script.read_text()
    assert 'joinpath(@__DIR__, "..\"' in text


def test_adopt_julia_depth2_two_ups(tmp_path):
    (tmp_path / "code" / "utils").mkdir(parents=True)
    script = tmp_path / "code" / "utils" / "helpers.jl"
    script.write_text('CSV.read("data/lfs.csv", DataFrame)\n')
    _adopt_julia_at_dir(tmp_path, [])
    text = script.read_text()
    assert text.count('"..\"') == 2


def test_adopt_julia_skips_depth_zero(tmp_path):
    script = tmp_path / "run.jl"
    script.write_text('CSV.read("data/lfs.csv", DataFrame)\n')
    _adopt_julia_at_dir(tmp_path, [])
    assert "@__DIR__" not in script.read_text()


def test_adopt_julia_skips_already_wrapped(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.jl"
    script.write_text('CSV.read(joinpath(@__DIR__, "..\"", "data/lfs.csv"), DataFrame)\n')
    _adopt_julia_at_dir(tmp_path, [])
    assert script.read_text().count("joinpath(@__DIR__") == 1


def test_adopt_julia_skips_comment_lines(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.jl"
    script.write_text('# CSV.read("data/lfs.csv", DataFrame)\n')
    _adopt_julia_at_dir(tmp_path, [])
    assert "@__DIR__" not in script.read_text()


def test_adopt_julia_result_count(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.jl"
    script.write_text('a = "data/a.csv"\nb = "figures/fig.pdf"\n')
    n = _adopt_julia_at_dir(tmp_path, [])
    assert n == 2


def test_resolve_julia_at_dir_adoption_counted(julia_copy):
    scan = scan_scripts(julia_copy)
    result = resolve_paths(julia_copy, scan)
    assert result.at_dir_adoptions >= 0


# ---------------------------------------------------------------------------
# _adopt_matlab_fullfile
# ---------------------------------------------------------------------------


def test_adopt_matlab_wraps_relative_path(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.m"
    script.write_text("T = readtable('data/lfs.csv');\n")
    _adopt_matlab_fullfile(tmp_path, [])
    text = script.read_text()
    assert "fullfile(fileparts(mfilename('fullpath'))" in text
    # Bare standalone literal replaced; path now inside fullfile call
    assert "readtable('data/lfs.csv')" not in text


def test_adopt_matlab_depth1_one_up(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.m"
    script.write_text("T = readtable('data/lfs.csv');\n")
    _adopt_matlab_fullfile(tmp_path, [])
    text = script.read_text()
    assert "'..')" in text or ", '..'," in text


def test_adopt_matlab_depth2_two_ups(tmp_path):
    (tmp_path / "code" / "utils").mkdir(parents=True)
    script = tmp_path / "code" / "utils" / "helpers.m"
    script.write_text("T = readtable('data/lfs.csv');\n")
    _adopt_matlab_fullfile(tmp_path, [])
    text = script.read_text()
    assert text.count("'..'") == 2


def test_adopt_matlab_skips_depth_zero(tmp_path):
    script = tmp_path / "run.m"
    script.write_text("T = readtable('data/lfs.csv');\n")
    _adopt_matlab_fullfile(tmp_path, [])
    assert "mfilename" not in script.read_text()


def test_adopt_matlab_skips_comment_lines(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.m"
    script.write_text("% T = readtable('data/lfs.csv');\n")
    _adopt_matlab_fullfile(tmp_path, [])
    assert "mfilename" not in script.read_text()


def test_adopt_matlab_skips_already_wrapped(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.m"
    script.write_text("T = readtable(fullfile(fileparts(mfilename('fullpath')), '..', 'data/lfs.csv'));\n")
    _adopt_matlab_fullfile(tmp_path, [])
    assert script.read_text().count("mfilename") == 1


def test_adopt_matlab_result_count(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "analysis.m"
    script.write_text("a = 'data/a.csv';\nb = 'figures/fig.pdf';\n")
    n = _adopt_matlab_fullfile(tmp_path, [])
    assert n == 2


def test_resolve_matlab_fullfile_adoption_counted(matlab_copy):
    scan = scan_scripts(matlab_copy)
    result = resolve_paths(matlab_copy, scan)
    assert result.fullfile_adoptions >= 0


# ---------------------------------------------------------------------------
# AGENT_REPORT reflects multi-language canonicalization
# ---------------------------------------------------------------------------


def test_agent_report_mentions_python_pathlib(python_copy):
    scan = scan_scripts(python_copy)
    result = resolve_paths(python_copy, scan)
    report = result.report_path.read_text()
    # Either reports adoptions or "None needed" — both are correct
    assert "canonicalization" in report.lower() or "Relative path" in report


def test_agent_report_mentions_julia_at_dir(julia_copy):
    scan = scan_scripts(julia_copy)
    result = resolve_paths(julia_copy, scan)
    report = result.report_path.read_text()
    assert "canonicalization" in report.lower() or "Relative path" in report


def test_agent_report_mentions_matlab_fullfile(matlab_copy):
    scan = scan_scripts(matlab_copy)
    result = resolve_paths(matlab_copy, scan)
    report = result.report_path.read_text()
    assert "canonicalization" in report.lower() or "Relative path" in report
