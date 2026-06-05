"""Tests for Python environment capture."""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.capture import (
    _from_environment_yml,
    _from_pyproject_toml,
    _python_inferred_from_date,
    capture_env,
)
from deadreckoning.models import PinMethod

FIXTURE = Path(__file__).parent / "fixtures" / "python_project"


# ---------------------------------------------------------------------------
# requirements.txt (existing path, just verify still works)
# ---------------------------------------------------------------------------


def test_capture_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "pandas==2.0.3\nmatplotlib==3.7.2\n"
    )
    spec = capture_env(tmp_path)
    assert spec.language == "Python"
    assert spec.pin_method == PinMethod.pip_freeze
    names = [p.name for p in spec.packages]
    assert "pandas" in names
    assert "matplotlib" in names


# ---------------------------------------------------------------------------
# environment.yml
# ---------------------------------------------------------------------------


def test_capture_environment_yml_language(tmp_path):
    (tmp_path / "environment.yml").write_text(
        "name: myenv\ndependencies:\n  - python=3.10\n  - pandas=2.0.0\n"
    )
    spec = capture_env(tmp_path)
    assert spec.language == "Python"
    assert spec.pin_method == PinMethod.conda_export


def test_capture_environment_yml_packages(tmp_path):
    yml = "name: myenv\ndependencies:\n  - pandas=2.0.0\n  - matplotlib>=3.7\n  - numpy\n"
    (tmp_path / "environment.yml").write_text(yml)
    spec = _from_environment_yml(tmp_path / "environment.yml")
    names = [p.name for p in spec.packages]
    assert "pandas" in names
    assert "matplotlib" in names
    assert "numpy" in names
    assert "python" not in names


def test_capture_environment_yml_version_parsed(tmp_path):
    (tmp_path / "environment.yml").write_text(
        "name: e\ndependencies:\n  - pandas=2.0.3\n"
    )
    spec = _from_environment_yml(tmp_path / "environment.yml")
    pkg = next(p for p in spec.packages if p.name == "pandas")
    assert pkg.version == "2.0.3"


def test_capture_environment_yml_pip_section(tmp_path):
    yml = (
        "name: e\ndependencies:\n"
        "  - pandas=2.0\n"
        "  - pip:\n"
        "    - some-pip-pkg==1.0\n"
    )
    (tmp_path / "environment.yml").write_text(yml)
    spec = _from_environment_yml(tmp_path / "environment.yml")
    names = [p.name for p in spec.packages]
    assert "pandas" in names
    assert "some-pip-pkg" in names


def test_capture_environment_yml_takes_priority_over_requirements(tmp_path):
    (tmp_path / "environment.yml").write_text(
        "name: e\ndependencies:\n  - pandas=2.0\n"
    )
    (tmp_path / "requirements.txt").write_text("pandas==1.0\n")
    spec = capture_env(tmp_path)
    assert spec.pin_method == PinMethod.conda_export


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


def test_capture_pyproject_pep621(tmp_path):
    toml = (
        '[project]\nname = "myproject"\n'
        'dependencies = [\n  "pandas>=2.0",\n  "matplotlib",\n]\n'
    )
    (tmp_path / "pyproject.toml").write_text(toml)
    spec = _from_pyproject_toml(tmp_path / "pyproject.toml")
    names = [p.name for p in spec.packages]
    assert "pandas" in names
    assert "matplotlib" in names
    assert spec.pin_method == PinMethod.pyproject


def test_capture_pyproject_poetry(tmp_path):
    toml = (
        "[tool.poetry.dependencies]\n"
        'python = "^3.10"\n'
        'pandas = "^2.0"\n'
        'numpy = ">=1.24"\n'
    )
    (tmp_path / "pyproject.toml").write_text(toml)
    spec = _from_pyproject_toml(tmp_path / "pyproject.toml")
    names = [p.name for p in spec.packages]
    assert "pandas" in names
    assert "numpy" in names
    assert "python" not in names


def test_capture_pyproject_language(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    spec = capture_env(tmp_path)
    assert spec.language == "Python"


# ---------------------------------------------------------------------------
# Python date inference (no env file)
# ---------------------------------------------------------------------------


def test_capture_python_no_env_file_language(tmp_path):
    (tmp_path / "run.py").write_text("import pandas\n")
    spec = capture_env(tmp_path)
    assert spec.language == "Python"
    assert spec.pin_method == PinMethod.inferred_from_date


def test_capture_python_no_env_file_has_date(tmp_path):
    (tmp_path / "run.py").write_text("import pandas\n")
    spec = capture_env(tmp_path)
    import re
    assert spec.snapshot_date is not None
    assert re.match(r"\d{4}-\d{2}-\d{2}", spec.snapshot_date)


def test_capture_python_no_env_file_low_confidence(tmp_path):
    (tmp_path / "run.py").write_text("import pandas\n")
    spec = capture_env(tmp_path)
    assert spec.confidence < 0.5


# ---------------------------------------------------------------------------
# Fixture: requirements.txt present
# ---------------------------------------------------------------------------


def test_capture_fixture_python_project():
    spec = capture_env(FIXTURE)
    assert spec.language == "Python"
    assert spec.pin_method == PinMethod.pip_freeze
    names = [p.name for p in spec.packages]
    assert "pandas" in names
    assert "matplotlib" in names
