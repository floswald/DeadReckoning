"""
Walking skeleton tests — Phase 2.

These tests execute real R scripts and (optionally) build Docker images.
They are gated behind markers so they don't run on every CI push:

  pytest -m "not local"        ← fast CI (GitHub Actions, no R/Docker)
  pytest -m local              ← full local run
  pytest -m "local and not docker"  ← local, skip Docker
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from deadreckoning.capture import capture_env
from deadreckoning.graph import build_graph
from deadreckoning.models import PinMethod
from deadreckoning.orchestrator import run_pipeline
from deadreckoning.runner import RunResult, run_natively, validate_outputs

FIXTURE = Path(__file__).parent / "fixtures" / "runnable_minimal"

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="runnable_minimal fixture not found",
)


# ---------------------------------------------------------------------------
# capture.py unit tests  (no R execution, pure file parsing)
# ---------------------------------------------------------------------------


def test_capture_reads_renv_lock():
    spec = capture_env(FIXTURE)
    assert spec.language == "R"
    assert spec.language_version == "4.5.1"


def test_capture_snapshot_url():
    spec = capture_env(FIXTURE)
    assert spec.snapshot_url == "https://packagemanager.posit.co/cran/2025-01-15"


def test_capture_snapshot_date():
    spec = capture_env(FIXTURE)
    assert spec.snapshot_date == "2025-01-15"


def test_capture_packages():
    spec = capture_env(FIXTURE)
    names = {p.name for p in spec.packages}
    assert "ggplot2" in names


def test_capture_pin_method():
    spec = capture_env(FIXTURE)
    assert spec.pin_method == PinMethod.lockfile
    assert spec.confidence >= 0.9


def test_capture_no_lockfile(tmp_path):
    (tmp_path / "paper.tex").write_text("")
    spec = capture_env(tmp_path)
    assert spec.language == "unknown"
    assert spec.confidence == 0.0


# ---------------------------------------------------------------------------
# graph.py sanity on runnable_minimal
# ---------------------------------------------------------------------------


def test_graph_finds_exhibits():
    graph = build_graph(FIXTURE)
    names = {e.tex_path.name for e in graph.exhibits}
    assert "fig1.pdf" in names
    assert "summary.tex" in names


def test_graph_sourced():
    graph = build_graph(FIXTURE)
    sourced = {e.tex_path.name for e in graph.exhibits if e.source is not None}
    assert "fig1.pdf" in sourced


# ---------------------------------------------------------------------------
# Native run  (requires Rscript + ggplot2 installed)
# ---------------------------------------------------------------------------


@pytest.mark.local
def test_native_run_in_working_copy(tmp_path):
    """Delete outputs from a copy, run scripts, verify regenerated."""
    working = tmp_path / "project"
    shutil.copytree(FIXTURE, working)

    # Delete generated outputs
    (working / "figures" / "fig1.pdf").unlink(missing_ok=True)
    (working / "tables" / "summary.tex").unlink(missing_ok=True)

    result = run_natively(working, master_script="code/run.R")
    assert result.success, f"Rscript failed:\n{result.stderr}"

    graph = build_graph(working)
    validation = validate_outputs(working, graph)
    assert validation.success, f"Missing after run: {validation.missing}"


@pytest.mark.local
def test_native_run_does_not_touch_original():
    """Original fixture is unchanged after native run (working-copy safety)."""
    orig_fig = FIXTURE / "figures" / "fig1.pdf"
    if not orig_fig.exists():
        pytest.skip("fig1.pdf not pre-generated in fixture")

    orig_mtime = orig_fig.stat().st_mtime

    with tempfile.TemporaryDirectory() as tmpdir:
        working = Path(tmpdir) / "project"
        shutil.copytree(FIXTURE, working)
        run_natively(working, master_script="code/run.R")

    assert orig_fig.stat().st_mtime == orig_mtime, "Original fixture was modified"


# ---------------------------------------------------------------------------
# Full pipeline  (native only, no Docker)
# ---------------------------------------------------------------------------


@pytest.mark.local
def test_pipeline_native_succeeds():
    result = run_pipeline(FIXTURE, skip_docker=True)
    assert result.error is None, f"Pipeline error: {result.error}"
    assert result.native_ok, f"Native run failed:\n{result.native_run.stderr if result.native_run else 'no run'}"
    assert result.native_validation is not None
    assert result.native_validation.success, f"Missing: {result.native_validation.missing}"


@pytest.mark.local
def test_pipeline_original_untouched():
    """Pipeline must never modify files in project_root."""
    orig_fig = FIXTURE / "figures" / "fig1.pdf"
    if not orig_fig.exists():
        pytest.skip("fig1.pdf not pre-generated in fixture")
    orig_size = orig_fig.stat().st_size

    run_pipeline(FIXTURE, skip_docker=True)

    assert orig_fig.stat().st_size == orig_size


# ---------------------------------------------------------------------------
# Docker pipeline  (requires docker daemon)
# ---------------------------------------------------------------------------


@pytest.mark.local
@pytest.mark.docker
def test_pipeline_docker_succeeds():
    result = run_pipeline(FIXTURE, docker_tag="dr-test-runnable-minimal:latest")
    assert result.error is None, f"Pipeline error: {result.error}"
    assert result.native_ok
    assert result.docker_build is not None and result.docker_build.success, (
        f"Docker build failed:\n{result.docker_build.stderr if result.docker_build else 'no build'}"
    )
    assert result.container_ok, (
        f"Container validation failed:\n"
        f"{result.container_validation.run.stderr if result.container_validation else 'no run'}"
    )
