"""
MATLAB detection and runner tests.

Fast tests: detect_matlab() behavior, runner dispatch, MatlabRunResult logic.
Local tests: real execution (requires MATLAB license + binary).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deadreckoning.matlab import (
    MatlabInstall,
    MatlabRunResult,
    _release_from_path,
    _supports_batch,
    detect_matlab,
    run_matlab,
)
from deadreckoning.runner import run_natively

FIXTURE = Path(__file__).parent / "fixtures" / "matlab_project"


# ---------------------------------------------------------------------------
# _release_from_path
# ---------------------------------------------------------------------------


def test_release_from_path_darwin():
    assert _release_from_path("/Applications/MATLAB_R2023b.app/bin") == "R2023b"


def test_release_from_path_linux():
    assert _release_from_path("/usr/local/MATLAB/R2022a/bin") == "R2022a"


def test_release_from_path_windows():
    assert _release_from_path(r"C:\Program Files\MATLAB\R2024a\bin") == "R2024a"


def test_release_from_path_no_match():
    assert _release_from_path("/usr/local/bin") is None


# ---------------------------------------------------------------------------
# _supports_batch
# ---------------------------------------------------------------------------


def test_supports_batch_r2019b():
    assert _supports_batch("R2019b") is True


def test_supports_batch_r2020a():
    assert _supports_batch("R2020a") is True


def test_supports_batch_r2024b():
    assert _supports_batch("R2024b") is True


def test_supports_batch_r2019a():
    assert _supports_batch("R2019a") is False


def test_supports_batch_r2018b():
    assert _supports_batch("R2018b") is False


def test_supports_batch_none():
    assert _supports_batch(None) is False


def test_supports_batch_unparseable():
    assert _supports_batch("unknown") is False


# ---------------------------------------------------------------------------
# detect_matlab — not-found path (CI / machines without MATLAB)
# ---------------------------------------------------------------------------


def test_detect_matlab_returns_install_object():
    result = detect_matlab()
    assert isinstance(result, MatlabInstall)


def test_detect_matlab_not_found_has_advice():
    with patch("deadreckoning.matlab.shutil.which", return_value=None), \
         patch("deadreckoning.matlab.Path.exists", return_value=False):
        result = detect_matlab()
    assert not result.found
    assert result.advice is not None
    assert "MATLAB" in result.advice


def test_detect_matlab_not_found_binary_none():
    with patch("deadreckoning.matlab.shutil.which", return_value=None), \
         patch("deadreckoning.matlab.Path.exists", return_value=False):
        result = detect_matlab()
    assert result.binary is None
    assert result.release is None


def test_detect_matlab_on_path_found():
    with patch("deadreckoning.matlab.shutil.which", return_value="/usr/bin/matlab"), \
         patch("deadreckoning.matlab._release_from_binary", return_value="R2023b"):
        result = detect_matlab()
    assert result.found
    assert result.on_path
    assert result.binary == "/usr/bin/matlab"
    assert result.release == "R2023b"


def test_detect_matlab_on_path_supports_batch():
    with patch("deadreckoning.matlab.shutil.which", return_value="/usr/bin/matlab"), \
         patch("deadreckoning.matlab._release_from_binary", return_value="R2023b"):
        result = detect_matlab()
    assert result.supports_batch is True


def test_detect_matlab_old_release_no_batch():
    with patch("deadreckoning.matlab.shutil.which", return_value="/usr/bin/matlab"), \
         patch("deadreckoning.matlab._release_from_binary", return_value="R2018a"):
        result = detect_matlab()
    assert result.supports_batch is False


# ---------------------------------------------------------------------------
# MatlabRunResult.success logic
# ---------------------------------------------------------------------------


def test_matlab_run_result_success():
    r = MatlabRunResult(returncode=0, stdout="", stderr="", log_has_error=False, error_snippet=None)
    assert r.success is True


def test_matlab_run_result_nonzero_returncode():
    r = MatlabRunResult(returncode=1, stdout="", stderr="", log_has_error=False, error_snippet=None)
    assert r.success is False


def test_matlab_run_result_zero_but_log_error():
    r = MatlabRunResult(returncode=0, stdout="Error in script", stderr="", log_has_error=True, error_snippet="Error in script")
    assert r.success is False


# ---------------------------------------------------------------------------
# run_matlab — mocked subprocess
# ---------------------------------------------------------------------------


def test_run_matlab_batch_command(tmp_path):
    with patch("deadreckoning.matlab.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_matlab(tmp_path, "code/run.m", binary="matlab", supports_batch=True)
        cmd = mock_run.call_args[0][0]
    assert "-batch" in cmd
    assert "run('code/run.m')" in cmd[-1]


def test_run_matlab_legacy_command(tmp_path):
    with patch("deadreckoning.matlab.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_matlab(tmp_path, "code/run.m", binary="matlab", supports_batch=False)
        cmd = mock_run.call_args[0][0]
    assert "-r" in cmd
    assert "-batch" not in cmd
    assert "exit" in cmd[-1]


def test_run_matlab_detects_error_in_stdout(tmp_path):
    with patch("deadreckoning.matlab.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Error in analysis (line 12): Undefined function 'foo'",
            stderr="",
        )
        result = run_matlab(tmp_path, "code/run.m", binary="matlab", supports_batch=False)
    assert result.log_has_error is True
    assert result.success is False


def test_run_matlab_clean_run(tmp_path):
    with patch("deadreckoning.matlab.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="All done.", stderr="")
        result = run_matlab(tmp_path, "code/run.m", binary="matlab", supports_batch=True)
    assert result.log_has_error is False
    assert result.success is True


# ---------------------------------------------------------------------------
# Runner dispatch for .m
# ---------------------------------------------------------------------------


def test_runner_dispatches_m_extension_not_r(tmp_path):
    result = run_natively(tmp_path, master_script="code/run.m")
    # MATLAB not installed in CI — must get MATLAB error, not Rscript error
    assert "Rscript" not in result.stderr
    assert result.returncode != 0  # MATLAB not found


def test_runner_m_missing_matlab_has_advice(tmp_path):
    with patch("deadreckoning.matlab.shutil.which", return_value=None), \
         patch("deadreckoning.matlab.Path.exists", return_value=False):
        result = run_natively(tmp_path, master_script="code/run.m")
    assert "MATLAB" in result.stderr
    assert result.returncode == 1


def test_runner_m_appends_error_snippet(tmp_path):
    with patch("deadreckoning.matlab.detect_matlab") as mock_detect, \
         patch("deadreckoning.matlab.run_matlab") as mock_run:
        mock_detect.return_value = MatlabInstall(
            found=True, binary="matlab", release="R2023b",
            on_path=True, hint_path=None, supports_batch=True, advice=None,
        )
        mock_run.return_value = MatlabRunResult(
            returncode=1, stdout="", stderr="matlab crashed",
            log_has_error=True, error_snippet="Error in run",
        )
        result = run_natively(tmp_path, master_script="code/run.m")
    assert "Error in run" in result.stderr
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Local — real MATLAB execution (requires license)
# ---------------------------------------------------------------------------


@pytest.mark.local
@pytest.mark.skipif(not shutil.which("matlab"), reason="matlab not on PATH")
def test_matlab_detect_finds_binary():
    result = detect_matlab()
    assert result.found
    assert result.binary is not None


@pytest.mark.local
@pytest.mark.skipif(not shutil.which("matlab"), reason="matlab not on PATH")
def test_matlab_detect_release_set():
    result = detect_matlab()
    assert result.release is not None
    import re
    assert re.match(r"R\d{4}[ab]", result.release)


@pytest.mark.local
@pytest.mark.skipif(not shutil.which("matlab"), reason="matlab not on PATH")
def test_matlab_native_run_succeeds(tmp_path):
    # Use 'master.m' to avoid shadowing MATLAB's built-in run() function.
    # Write output via absolute path derived from mfilename to avoid CWD
    # ambiguity in MATLAB -batch mode.
    (tmp_path / "code").mkdir()
    out_file = str(tmp_path / "out.txt").replace("\\", "/")
    (tmp_path / "code" / "master.m").write_text(
        f"disp('hello from matlab');\n"
        f"x = 1 + 1;\n"
        f"fid = fopen('{out_file}', 'w');\n"
        f"fprintf(fid, 'done');\n"
        f"fclose(fid);\n"
    )
    result = run_natively(tmp_path, master_script="code/master.m")
    assert result.success, f"MATLAB failed:\n{result.stderr}"
    assert (tmp_path / "out.txt").exists()


@pytest.mark.local
@pytest.mark.skipif(not shutil.which("matlab"), reason="matlab not on PATH")
def test_matlab_broken_script_returns_nonzero(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "master.m").write_text("error('intentional failure');\n")
    result = run_natively(tmp_path, master_script="code/master.m")
    assert result.returncode != 0
