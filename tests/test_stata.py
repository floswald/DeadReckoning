"""
Stata support tests.

Markers:
  (none)        — pure unit tests, no Stata needed
  @pytest.mark.local — requires Stata on PATH or installed
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.capture import capture_env
from deadreckoning.graph import build_graph
from deadreckoning.models import PinMethod
from deadreckoning.orchestrator import run_pipeline
from deadreckoning.runner import run_natively, validate_outputs
from deadreckoning.stata import (
    StataInstall,
    _advice_not_found,
    _advice_not_on_path,
    capture_stata_env,
    detect_stata,
)

FIXTURE = Path(__file__).parent / "fixtures" / "runnable_stata_minimal"

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="runnable_stata_minimal fixture not found",
)


# ---------------------------------------------------------------------------
# Detection unit tests — no Stata required
# ---------------------------------------------------------------------------


def test_advice_not_found_contains_url():
    advice = _advice_not_found("darwin")
    assert "stata.com" in advice.lower()


def test_advice_not_found_linux_mentions_module():
    advice = _advice_not_found("linux")
    assert "module" in advice


def test_advice_not_on_path_contains_path():
    advice = _advice_not_on_path("/usr/local/stata18", "linux")
    assert "/usr/local/stata18" in advice
    assert "PATH" in advice


def test_advice_not_on_path_macos():
    advice = _advice_not_on_path("/Applications/Stata/StataMP.app/Contents/MacOS", "darwin")
    assert "export PATH" in advice
    assert "zshrc" in advice


# ---------------------------------------------------------------------------
# Detection — requires Stata present (local)
# ---------------------------------------------------------------------------


@pytest.mark.local
def test_detect_stata_finds_binary():
    install = detect_stata()
    assert install.found, f"Stata not found. Advice:\n{install.advice}"
    assert install.binary is not None


@pytest.mark.local
def test_detect_stata_has_version():
    install = detect_stata()
    if install.found:
        # version may be None if --version flag not supported, so just check type
        assert install.version is None or isinstance(install.version, str)


# ---------------------------------------------------------------------------
# capture_stata_env — parse ssc/net install from .do files
# ---------------------------------------------------------------------------


def test_capture_stata_language(tmp_path):
    (tmp_path / "analysis.do").write_text("sysuse auto, clear\n")
    spec = capture_stata_env(tmp_path)
    assert spec.language == "Stata"


def test_capture_stata_ssc_install(tmp_path):
    (tmp_path / "setup.do").write_text(
        "ssc install estout\nssc install reghdfe\n"
    )
    spec = capture_stata_env(tmp_path)
    names = {p.name for p in spec.packages}
    assert "estout" in names
    assert "reghdfe" in names


def test_capture_stata_net_install(tmp_path):
    (tmp_path / "setup.do").write_text(
        'net install ftools, from("https://raw.github.com/sergiocorreia/ftools/master/src/")\n'
    )
    spec = capture_stata_env(tmp_path)
    names = {p.name for p in spec.packages}
    assert "ftools" in names


def test_capture_stata_ignores_commented_ssc(tmp_path):
    (tmp_path / "setup.do").write_text(
        "* ssc install estout\n"
        "ssc install reghdfe\n"
    )
    spec = capture_stata_env(tmp_path)
    names = {p.name for p in spec.packages}
    assert "estout" not in names
    assert "reghdfe" in names


def test_capture_stata_low_confidence(tmp_path):
    (tmp_path / "analysis.do").write_text("sysuse auto, clear\n")
    spec = capture_stata_env(tmp_path)
    assert spec.confidence < 0.5


def test_capture_env_dispatches_to_stata():
    """capture_env detects Stata project from .do files when no renv.lock."""
    spec = capture_env(FIXTURE)
    assert spec.language == "Stata"


# ---------------------------------------------------------------------------
# Graph on Stata fixture
# ---------------------------------------------------------------------------


def test_graph_stata_finds_exhibits():
    graph = build_graph(FIXTURE)
    names = {e.tex_path.name for e in graph.exhibits}
    assert "fig1.pdf" in names
    assert "summary.tex" in names


def test_graph_stata_fig1_sourced():
    graph = build_graph(FIXTURE)
    fig1 = next((e for e in graph.exhibits if e.tex_path.name == "fig1.pdf"), None)
    assert fig1 is not None
    assert fig1.source is not None, "fig1.pdf not traced to a script"
    assert fig1.source.script.suffix == ".do"


# ---------------------------------------------------------------------------
# Native run — requires Stata (local)
# ---------------------------------------------------------------------------


@pytest.mark.local
def test_stata_run_in_working_copy(tmp_path):
    working = tmp_path / "project"
    shutil.copytree(FIXTURE, working)

    (working / "figures" / "fig1.pdf").unlink(missing_ok=True)
    (working / "tables" / "summary.tex").unlink(missing_ok=True)

    result = run_natively(working, master_script="code/master.do")
    assert result.success, f"Stata run failed:\n{result.stderr}"

    graph = build_graph(working)
    validation = validate_outputs(working, graph)
    assert validation.success, f"Missing after run: {validation.missing}"


@pytest.mark.local
def test_stata_run_does_not_touch_original():
    orig = FIXTURE / "figures" / "fig1.pdf"
    if not orig.exists():
        pytest.skip("fig1.pdf not pre-generated in fixture")
    orig_mtime = orig.stat().st_mtime

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        working = Path(tmpdir) / "project"
        shutil.copytree(FIXTURE, working)
        run_natively(working, master_script="code/master.do")

    assert orig.stat().st_mtime == orig_mtime, "Original fixture was modified"


@pytest.mark.local
def test_stata_log_error_detection(tmp_path):
    """A .do file with an error must produce success=False even though exit code is 0."""
    (tmp_path / "bad.do").write_text("sysuse auto, clear\nthis_command_does_not_exist\n")
    result = run_natively(tmp_path, master_script="bad.do")
    assert not result.success, "Failed Stata run should report success=False"


# ---------------------------------------------------------------------------
# Pipeline (native only) — requires Stata (local)
# ---------------------------------------------------------------------------


@pytest.mark.local
def test_stata_pipeline_native_succeeds():
    result = run_pipeline(FIXTURE, skip_docker=True)
    assert result.error is None, f"Pipeline error: {result.error}"
    assert result.native_ok, (
        f"Native run failed:\n{result.native_run.stderr if result.native_run else 'no run'}"
    )
    assert result.native_validation is not None
    assert result.native_validation.success, f"Missing: {result.native_validation.missing}"


@pytest.mark.local
def test_stata_pipeline_auto_detects_master():
    """Pipeline with master_script=None must auto-detect code/master.do."""
    result = run_pipeline(FIXTURE, master_script=None, skip_docker=True)
    assert result.error is None, f"Pipeline error: {result.error}"
    assert result.native_ok
