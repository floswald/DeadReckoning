"""Docker pipeline tests.

Unit tests (generation): always run, no Docker required.
Integration tests (real build+run): skipped unless DEADRECKONING_DOCKER_TESTS=1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from deadreckoning.capture import capture_env
from deadreckoning.docker import (
    DockerFixResult,
    _add_julia_package_to_dockerfile,
    _add_python_package_to_dockerfile,
    _add_r_package_to_dockerfile,
    _parse_missing_julia_package,
    _parse_missing_python_package,
    _parse_missing_r_package,
    _shell_command,
    generate_dockerfile,
    generate_dockerignore,
    run_docker_fix_loop,
    warn_before_push,
)
from deadreckoning.models import EnvSpec, PackageSpec, PinMethod

FIXTURE = Path(__file__).parent / "fixtures" / "r_no_lockfile"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOCKER_AVAILABLE = shutil.which("docker") is not None
_DOCKER_TESTS = os.environ.get("DEADRECKONING_DOCKER_TESTS", "0") == "1"

requires_docker = pytest.mark.skipif(
    not (_DOCKER_AVAILABLE and _DOCKER_TESTS),
    reason="Docker integration tests require DEADRECKONING_DOCKER_TESTS=1 and docker on PATH",
)


def _r_spec(version="4.4.0", packages=None, snapshot_date="2024-01-01") -> EnvSpec:
    pkgs = [PackageSpec(name=n, pin_method=PinMethod.ppm_snapshot) for n in (packages or [])]
    return EnvSpec(
        language="R",
        language_version=version,
        packages=pkgs,
        pin_method=PinMethod.ppm_snapshot,
        snapshot_date=snapshot_date,
        snapshot_url=f"https://packagemanager.posit.co/cran/{snapshot_date}",
        confidence=0.9,
    )


def _python_spec(version="3.11", packages=None) -> EnvSpec:
    pkgs = [PackageSpec(name=n, pin_method=PinMethod.pip_freeze) for n in (packages or [])]
    return EnvSpec(language="Python", language_version=version, packages=pkgs, confidence=0.8)


def _julia_spec(version="1.10", packages=None) -> EnvSpec:
    pkgs = [PackageSpec(name=n) for n in (packages or [])]
    return EnvSpec(language="Julia", language_version=version, packages=pkgs, confidence=0.8)


# ---------------------------------------------------------------------------
# Dockerfile generation — R
# ---------------------------------------------------------------------------


def test_r_dockerfile_base_image():
    df = generate_dockerfile(_r_spec(version="4.3.2"))
    assert "rocker/r-ver:4.3.2" in df


def test_r_dockerfile_no_copy():
    df = generate_dockerfile(_r_spec(packages=["ggplot2"]))
    assert "COPY" not in df


def test_r_dockerfile_packages_in_install():
    df = generate_dockerfile(_r_spec(packages=["ggplot2", "dplyr"]))
    assert '"ggplot2"' in df
    assert '"dplyr"' in df
    assert "install.packages" in df


def test_r_dockerfile_snapshot_url():
    df = generate_dockerfile(_r_spec(snapshot_date="2023-06-15"))
    assert "2023-06-15" in df


def test_r_dockerfile_workdir():
    df = generate_dockerfile(_r_spec())
    assert "WORKDIR /project" in df


def test_r_dockerfile_platform():
    df = generate_dockerfile(_r_spec())
    assert "linux/amd64" in df


def test_r_dockerfile_no_packages():
    df = generate_dockerfile(_r_spec(packages=[]))
    assert "install.packages(c()" in df or "install.packages(c(" in df


# ---------------------------------------------------------------------------
# Dockerfile generation — Python
# ---------------------------------------------------------------------------


def test_python_dockerfile_base_image():
    df = generate_dockerfile(_python_spec(version="3.12"))
    assert "python:3.12-slim" in df


def test_python_dockerfile_no_copy():
    df = generate_dockerfile(_python_spec(packages=["pandas"]))
    assert "COPY" not in df


def test_python_dockerfile_pip_install():
    df = generate_dockerfile(_python_spec(packages=["pandas", "matplotlib"]))
    assert "pip install" in df
    assert "pandas" in df
    assert "matplotlib" in df


def test_python_dockerfile_workdir():
    df = generate_dockerfile(_python_spec())
    assert "WORKDIR /project" in df


# ---------------------------------------------------------------------------
# Dockerfile generation — Julia
# ---------------------------------------------------------------------------


def test_julia_dockerfile_base_image():
    df = generate_dockerfile(_julia_spec(version="1.9"))
    assert "julia:1.9" in df


def test_julia_dockerfile_no_copy():
    df = generate_dockerfile(_julia_spec(packages=["DataFrames"]))
    assert "COPY" not in df


def test_julia_dockerfile_pkg_add():
    df = generate_dockerfile(_julia_spec(packages=["DataFrames", "CSV"]))
    assert "Pkg.add" in df
    assert "DataFrames" in df
    assert "CSV" in df


# ---------------------------------------------------------------------------
# Dockerfile generation — unsupported (Stata, MATLAB)
# ---------------------------------------------------------------------------


def test_stata_dockerfile_is_unsupported():
    spec = EnvSpec(language="Stata", confidence=0.4)
    df = generate_dockerfile(spec)
    assert "proprietary" in df.lower() or "#" in df
    assert "COPY" not in df


def test_matlab_dockerfile_is_unsupported():
    spec = EnvSpec(language="MATLAB", confidence=0.25)
    df = generate_dockerfile(spec)
    assert "mathworks" in df.lower() or "proprietary" in df.lower()
    assert "COPY" not in df


# ---------------------------------------------------------------------------
# .dockerignore generation
# ---------------------------------------------------------------------------


def test_dockerignore_excludes_data():
    di = generate_dockerignore()
    assert "data/" in di


def test_dockerignore_excludes_secrets():
    di = generate_dockerignore()
    assert ".env" in di


def test_dockerignore_excludes_git():
    di = generate_dockerignore()
    assert ".git/" in di


def test_dockerignore_extra_patterns():
    di = generate_dockerignore(extra_patterns=["mydata/", "credentials.json"])
    assert "mydata/" in di
    assert "credentials.json" in di


# ---------------------------------------------------------------------------
# Shell command helper
# ---------------------------------------------------------------------------


def test_shell_command_r():
    assert _shell_command("R", "code/run.R") == "Rscript code/run.R"


def test_shell_command_python():
    assert _shell_command("PYTHON", "code/analysis.py") == "python code/analysis.py"


def test_shell_command_julia():
    assert _shell_command("JULIA", "code/analysis.jl") == "julia code/analysis.jl"


def test_shell_command_matlab():
    assert _shell_command("MATLAB", "code/analysis.m") == 'matlab -batch "analysis"'


def test_shell_command_stata():
    assert "stata" in _shell_command("STATA", "code/run.do")


# ---------------------------------------------------------------------------
# Dockerfile FIX helpers
# ---------------------------------------------------------------------------


def test_parse_missing_r_package_no_package_called():
    stderr = "Error in library(haven) : there is no package called 'haven'"
    assert _parse_missing_r_package(stderr) == "haven"


def test_parse_missing_r_package_not_available():
    stderr = "package 'fixest' is not available for this version of R"
    assert _parse_missing_r_package(stderr) == "fixest"


def test_parse_missing_r_package_none():
    assert _parse_missing_r_package("syntax error in line 42") is None


def test_add_r_package_to_dockerfile():
    df = generate_dockerfile(_r_spec(packages=["ggplot2"]))
    new_df = _add_r_package_to_dockerfile(df, "haven")
    assert '"haven"' in new_df
    assert '"ggplot2"' in new_df


def test_add_r_package_idempotent():
    df = generate_dockerfile(_r_spec(packages=["ggplot2"]))
    df2 = _add_r_package_to_dockerfile(df, "ggplot2")
    assert df2.count('"ggplot2"') == df.count('"ggplot2"')


# ---------------------------------------------------------------------------
# Python package parser / patcher
# ---------------------------------------------------------------------------


def test_parse_missing_python_package_module_not_found():
    stderr = "ModuleNotFoundError: No module named 'pandas'"
    assert _parse_missing_python_package(stderr) == "pandas"


def test_parse_missing_python_package_no_distribution():
    stderr = "ERROR: No matching distribution found for scikit-learn"
    assert _parse_missing_python_package(stderr) == "scikit-learn"


def test_parse_missing_python_package_satisfies():
    stderr = "ERROR: Could not find a version that satisfies the requirement numpy (from versions: none)"
    assert _parse_missing_python_package(stderr) == "numpy"


def test_parse_missing_python_package_none():
    assert _parse_missing_python_package("SyntaxError: invalid syntax") is None


def test_add_python_package_to_dockerfile():
    df = generate_dockerfile(_python_spec(packages=["pandas"]))
    new_df = _add_python_package_to_dockerfile(df, "numpy")
    assert '"numpy"' in new_df
    assert '"pandas"' in new_df


def test_add_python_package_idempotent():
    df = generate_dockerfile(_python_spec(packages=["pandas"]))
    df2 = _add_python_package_to_dockerfile(df, "pandas")
    assert df2.count('"pandas"') == df.count('"pandas"')


# ---------------------------------------------------------------------------
# Julia package parser / patcher
# ---------------------------------------------------------------------------


def test_parse_missing_julia_package_not_found():
    stderr = "Package DataFrames not found in current path"
    assert _parse_missing_julia_package(stderr) == "DataFrames"


def test_parse_missing_julia_package_argument_error():
    stderr = "ArgumentError: Package CSV not found"
    assert _parse_missing_julia_package(stderr) == "CSV"


def test_parse_missing_julia_package_none():
    assert _parse_missing_julia_package("syntax: unexpected token") is None


def test_add_julia_package_to_dockerfile():
    df = generate_dockerfile(_julia_spec(packages=["DataFrames"]))
    new_df = _add_julia_package_to_dockerfile(df, "CSV")
    assert "CSV" in new_df
    assert "DataFrames" in new_df


def test_add_julia_package_idempotent():
    df = generate_dockerfile(_julia_spec(packages=["DataFrames"]))
    df2 = _add_julia_package_to_dockerfile(df, "DataFrames")
    assert df2.count("DataFrames") == df.count("DataFrames")


# ---------------------------------------------------------------------------
# run_docker_fix_loop — unit tests (mock subprocess)
# ---------------------------------------------------------------------------


def _make_build_result(success: bool, stderr: str = "") -> "BuildResult":
    from deadreckoning.docker import BuildResult
    return BuildResult(
        success=success,
        image_tag="dr:test",
        stdout="",
        stderr=stderr,
        dockerfile_text="FROM python:3.11-slim\nRUN pip install --no-cache-dir \"pandas\"\nWORKDIR /project\n",
    )


def _make_run_result(outputs_ok: bool) -> "ContainerRunResult":
    from deadreckoning.docker import ContainerRunResult
    from deadreckoning.runner import RunResult, ValidationResult
    return ContainerRunResult(
        run=RunResult(returncode=0 if outputs_ok else 1, stdout="", stderr=""),
        outputs=ValidationResult(
            present=[Path("figures/fig1.pdf")] if outputs_ok else [],
            missing=[] if outputs_ok else [Path("figures/fig1.pdf")],
        ),
    )


def test_run_docker_fix_loop_converges_immediately(tmp_path, monkeypatch):
    """Build succeeds, run succeeds → converged=True in 1 iteration."""
    from deadreckoning.docker import ContainerRunResult
    from deadreckoning.runner import ValidationResult, RunResult
    from deadreckoning.models import DependencyGraph

    monkeypatch.setattr(
        "deadreckoning.docker.build_image",
        lambda *a, **kw: _make_build_result(True),
    )
    monkeypatch.setattr(
        "deadreckoning.docker.run_in_container",
        lambda *a, **kw: _make_run_result(True),
    )
    monkeypatch.setattr("deadreckoning.docker.write_dockerignore", lambda *a, **kw: None)

    graph = DependencyGraph(project_root=tmp_path)
    spec = _python_spec(packages=["pandas"])
    result = run_docker_fix_loop(tmp_path, graph, spec, image_tag="dr:test")
    assert result.converged
    assert result.build_attempts == 1
    assert result.run_attempts == 1


def test_run_docker_fix_loop_python_build_fail_adds_package(tmp_path, monkeypatch):
    """Build fails with missing Python package → package added to Dockerfile → converges."""
    from deadreckoning.models import DependencyGraph

    calls = {"n": 0}

    def fake_build(project_root, dockerfile_text, tag, platform=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _make_build_result(False, "No matching distribution found for numpy")
        # Second call: build succeeds (numpy was added)
        result = _make_build_result(True)
        result.dockerfile_text = dockerfile_text
        return result

    monkeypatch.setattr("deadreckoning.docker.build_image", fake_build)
    monkeypatch.setattr(
        "deadreckoning.docker.run_in_container",
        lambda *a, **kw: _make_run_result(True),
    )
    monkeypatch.setattr("deadreckoning.docker.write_dockerignore", lambda *a, **kw: None)

    graph = DependencyGraph(project_root=tmp_path)
    spec = _python_spec(packages=["pandas"])
    result = run_docker_fix_loop(tmp_path, graph, spec, image_tag="dr:test")
    assert result.converged
    assert result.build_attempts == 2
    assert any("numpy" in f for f in result.dockerfile_fixes)


def test_run_docker_fix_loop_build_fail_no_fix(tmp_path, monkeypatch):
    """Build fails with unfixable error → error set, not converged."""
    from deadreckoning.models import DependencyGraph

    monkeypatch.setattr(
        "deadreckoning.docker.build_image",
        lambda *a, **kw: _make_build_result(False, "COPY failed: file not found"),
    )
    monkeypatch.setattr("deadreckoning.docker.write_dockerignore", lambda *a, **kw: None)

    graph = DependencyGraph(project_root=tmp_path)
    spec = _python_spec(packages=["pandas"])
    result = run_docker_fix_loop(tmp_path, graph, spec, image_tag="dr:test")
    assert not result.converged
    assert result.error is not None
    assert "no auto-fix" in result.error


# ---------------------------------------------------------------------------
# warn_before_push
# ---------------------------------------------------------------------------


def test_warn_before_push_contains_tag():
    from deadreckoning.docker import BuildResult
    br = BuildResult(
        success=True,
        image_tag="myrepo/paper:latest",
        stdout="",
        stderr="",
        dockerfile_text=generate_dockerfile(_r_spec(packages=["ggplot2"])),
    )
    warning = warn_before_push("myrepo/paper:latest", br)
    assert "myrepo/paper:latest" in warning
    assert "WARNING" in warning


def test_warn_before_push_lists_layers():
    from deadreckoning.docker import BuildResult
    br = BuildResult(
        success=True,
        image_tag="x",
        stdout="",
        stderr="",
        dockerfile_text="FROM rocker/r-ver:4.4.0\nRUN echo hi\n",
    )
    warning = warn_before_push("x", br)
    assert "FROM" in warning or "RUN" in warning


# ---------------------------------------------------------------------------
# append_docker_report
# ---------------------------------------------------------------------------


def test_append_docker_report_creates_section(tmp_path):
    from deadreckoning.docker import BuildResult, append_docker_report
    br = BuildResult(
        success=True,
        image_tag="dr:test",
        stdout="",
        stderr="",
        dockerfile_text="FROM rocker/r-ver:4.4.0\n",
    )
    from deadreckoning.runner import ValidationResult
    from deadreckoning.docker import ContainerRunResult

    cr = ContainerRunResult(
        run=RunResult(returncode=0, stdout="", stderr=""),
        outputs=ValidationResult(present=[Path("figures/fig1.pdf")], missing=[]),
    )
    append_docker_report(tmp_path, br, cr, None, "dr:test", "linux/amd64")
    text = (tmp_path / "AGENT_REPORT.md").read_text()
    assert "Docker pipeline" in text
    assert "dr:test" in text
    assert "linux/amd64" in text


def test_append_docker_report_missing_outputs(tmp_path):
    from deadreckoning.docker import BuildResult, append_docker_report
    from deadreckoning.runner import ValidationResult
    from deadreckoning.docker import ContainerRunResult

    br = BuildResult(success=False, image_tag="dr:fail", stdout="", stderr="Build error", dockerfile_text="")
    append_docker_report(tmp_path, br, None, None, "dr:fail", "linux/amd64")
    text = (tmp_path / "AGENT_REPORT.md").read_text()
    assert "Build error" in text


# ---------------------------------------------------------------------------
# Integration — real Docker (opt-in only)
# ---------------------------------------------------------------------------


@requires_docker
def test_docker_integration_r_no_lockfile(tmp_path):
    """End-to-end: build R image → run with volume → validate outputs on host."""
    import shutil
    from deadreckoning.docker import (
        build_image,
        generate_dockerignore,
        run_in_container,
        write_dockerignore,
    )
    from deadreckoning.fix_loop import run_fix_loop
    from deadreckoning.graph import build_graph
    from deadreckoning.resolve import resolve_paths
    from deadreckoning.scan import scan_scripts

    working_copy = tmp_path / "project"
    shutil.copytree(FIXTURE, working_copy)

    scan = scan_scripts(working_copy)
    resolve_paths(working_copy, scan)
    graph = build_graph(working_copy)
    run_fix_loop(working_copy, graph)
    graph = build_graph(working_copy)

    env_spec = capture_env(working_copy)
    df_text = generate_dockerfile(env_spec)
    assert "COPY" not in df_text

    write_dockerignore(working_copy, generate_dockerignore())

    build = build_image(working_copy, df_text, "deadreckoning-test:r_no_lockfile")
    assert build.success, f"Build failed:\n{build.stderr}"

    # Delete existing exhibits so we can verify container regenerated them
    for exhibit in graph.exhibits:
        p = working_copy / exhibit.tex_path
        if p.exists():
            p.unlink()

    run_result = run_in_container(working_copy, "deadreckoning-test:r_no_lockfile", graph, env_spec=env_spec)
    assert run_result.outputs.success, f"Missing: {run_result.outputs.missing}"


# Expose RunResult for import convenience in report test
from deadreckoning.runner import RunResult  # noqa: E402
