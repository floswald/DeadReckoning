"""
Runner dispatch tests for Julia and Python.

Fast tests: dispatch routing (no execution).
Local tests: real execution against runnable fixtures.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.graph import build_graph
from deadreckoning.runner import RunResult, run_natively, validate_outputs

JULIA_FIXTURE = Path(__file__).parent / "fixtures" / "runnable_julia_minimal"
PYTHON_FIXTURE = Path(__file__).parent / "fixtures" / "runnable_python_minimal"


# ---------------------------------------------------------------------------
# Dispatch routing (no execution required)
# ---------------------------------------------------------------------------


def test_unsupported_extension_returns_error(tmp_path):
    result = run_natively(tmp_path, master_script="code/run.nb")
    assert result.returncode == 1
    assert "Unsupported" in result.stderr


def test_julia_extension_does_not_fall_through_to_r(tmp_path):
    # .jl script that does not exist → julia error, not Rscript error
    result = run_natively(tmp_path, master_script="code/run.jl")
    assert result.returncode != 0
    assert "Rscript" not in result.stderr


def test_python_extension_does_not_fall_through_to_r(tmp_path):
    result = run_natively(tmp_path, master_script="code/run.py")
    assert result.returncode != 0
    assert "Rscript" not in result.stderr


# ---------------------------------------------------------------------------
# Julia — real execution (requires julia in PATH)
# ---------------------------------------------------------------------------


@pytest.mark.local
@pytest.mark.skipif(not JULIA_FIXTURE.exists(), reason="julia fixture missing")
def test_julia_native_run_succeeds(tmp_path):
    working = tmp_path / "julia_project"
    shutil.copytree(JULIA_FIXTURE, working)
    (working / "figures" / "fig1.pdf").unlink(missing_ok=True)
    (working / "tables" / "summary.tex").unlink(missing_ok=True)

    result = run_natively(working, master_script="code/run.jl")
    assert result.success, f"julia failed:\n{result.stderr}"


@pytest.mark.local
@pytest.mark.skipif(not JULIA_FIXTURE.exists(), reason="julia fixture missing")
def test_julia_outputs_regenerated(tmp_path):
    working = tmp_path / "julia_project"
    shutil.copytree(JULIA_FIXTURE, working)
    (working / "figures" / "fig1.pdf").unlink(missing_ok=True)
    (working / "tables" / "summary.tex").unlink(missing_ok=True)

    run_natively(working, master_script="code/run.jl")

    graph = build_graph(working)
    validation = validate_outputs(working, graph)
    assert validation.success, f"Missing after julia run: {validation.missing}"


@pytest.mark.local
@pytest.mark.skipif(not JULIA_FIXTURE.exists(), reason="julia fixture missing")
def test_julia_original_fixture_untouched():
    orig = JULIA_FIXTURE / "figures" / "fig1.pdf"
    if not orig.exists():
        pytest.skip("fig1.pdf not pre-generated in julia fixture")
    mtime_before = orig.stat().st_mtime

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp) / "project"
        shutil.copytree(JULIA_FIXTURE, working)
        run_natively(working, master_script="code/run.jl")

    assert orig.stat().st_mtime == mtime_before, "Julia fixture was modified"


@pytest.mark.local
@pytest.mark.skipif(not JULIA_FIXTURE.exists(), reason="julia fixture missing")
def test_julia_run_result_has_returncode_zero(tmp_path):
    working = tmp_path / "julia_project"
    shutil.copytree(JULIA_FIXTURE, working)
    result = run_natively(working, master_script="code/run.jl")
    assert isinstance(result, RunResult)
    assert result.returncode == 0


@pytest.mark.local
@pytest.mark.skipif(not JULIA_FIXTURE.exists(), reason="julia fixture missing")
def test_julia_broken_script_returns_nonzero(tmp_path):
    working = tmp_path / "julia_broken"
    shutil.copytree(JULIA_FIXTURE, working)
    (working / "code" / "run.jl").write_text("error(\"intentional failure\")\n")
    result = run_natively(working, master_script="code/run.jl")
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Python — real execution (requires python in PATH)
# ---------------------------------------------------------------------------


@pytest.mark.local
@pytest.mark.skipif(not PYTHON_FIXTURE.exists(), reason="python fixture missing")
def test_python_native_run_succeeds(tmp_path):
    working = tmp_path / "python_project"
    shutil.copytree(PYTHON_FIXTURE, working)
    (working / "figures" / "fig1.pdf").unlink(missing_ok=True)
    (working / "tables" / "summary.tex").unlink(missing_ok=True)

    result = run_natively(working, master_script="code/run.py")
    assert result.success, f"python failed:\n{result.stderr}"


@pytest.mark.local
@pytest.mark.skipif(not PYTHON_FIXTURE.exists(), reason="python fixture missing")
def test_python_outputs_regenerated(tmp_path):
    working = tmp_path / "python_project"
    shutil.copytree(PYTHON_FIXTURE, working)
    (working / "figures" / "fig1.pdf").unlink(missing_ok=True)
    (working / "tables" / "summary.tex").unlink(missing_ok=True)

    run_natively(working, master_script="code/run.py")

    graph = build_graph(working)
    validation = validate_outputs(working, graph)
    assert validation.success, f"Missing after python run: {validation.missing}"


@pytest.mark.local
@pytest.mark.skipif(not PYTHON_FIXTURE.exists(), reason="python fixture missing")
def test_python_original_fixture_untouched():
    orig = PYTHON_FIXTURE / "figures" / "fig1.pdf"
    if not orig.exists():
        pytest.skip("fig1.pdf not pre-generated in python fixture")
    mtime_before = orig.stat().st_mtime

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp) / "project"
        shutil.copytree(PYTHON_FIXTURE, working)
        run_natively(working, master_script="code/run.py")

    assert orig.stat().st_mtime == mtime_before, "Python fixture was modified"


@pytest.mark.local
@pytest.mark.skipif(not PYTHON_FIXTURE.exists(), reason="python fixture missing")
def test_python_run_result_has_returncode_zero(tmp_path):
    working = tmp_path / "python_project"
    shutil.copytree(PYTHON_FIXTURE, working)
    result = run_natively(working, master_script="code/run.py")
    assert isinstance(result, RunResult)
    assert result.returncode == 0


@pytest.mark.local
@pytest.mark.skipif(not PYTHON_FIXTURE.exists(), reason="python fixture missing")
def test_python_broken_script_returns_nonzero(tmp_path):
    working = tmp_path / "python_broken"
    shutil.copytree(PYTHON_FIXTURE, working)
    (working / "code" / "run.py").write_text("raise RuntimeError('intentional failure')\n")
    result = run_natively(working, master_script="code/run.py")
    assert result.returncode != 0
