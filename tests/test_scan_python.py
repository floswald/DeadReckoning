"""Tests for Python scanning in scan.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.scan import scan_python_scripts, scan_scripts

FIXTURE = Path(__file__).parent / "fixtures" / "python_project"


# ---------------------------------------------------------------------------
# Package extraction
# ---------------------------------------------------------------------------


def test_scan_python_extracts_imports(tmp_path):
    (tmp_path / "run.py").write_text("import pandas as pd\nimport numpy\n")
    result = scan_python_scripts(tmp_path)
    assert "pandas" in result.used_packages
    assert "numpy" in result.used_packages


def test_scan_python_from_import(tmp_path):
    (tmp_path / "run.py").write_text("from sklearn.linear_model import LinearRegression\n")
    result = scan_python_scripts(tmp_path)
    assert "sklearn" in result.used_packages


def test_scan_python_excludes_stdlib(tmp_path):
    (tmp_path / "run.py").write_text(
        "import os\nimport sys\nfrom pathlib import Path\nimport pandas\n"
    )
    result = scan_python_scripts(tmp_path)
    assert "os" not in result.used_packages
    assert "sys" not in result.used_packages
    assert "pathlib" not in result.used_packages
    assert "pandas" in result.used_packages


def test_scan_python_skips_comment_lines(tmp_path):
    (tmp_path / "run.py").write_text("# import pandas\nimport numpy\n")
    result = scan_python_scripts(tmp_path)
    assert "pandas" not in result.used_packages
    assert "numpy" in result.used_packages


def test_scan_python_fixture_packages():
    result = scan_python_scripts(FIXTURE)
    assert "pandas" in result.used_packages
    assert "matplotlib" in result.used_packages
    assert "sklearn" in result.used_packages


# ---------------------------------------------------------------------------
# External path detection
# ---------------------------------------------------------------------------


def test_scan_python_detects_dropbox_path(tmp_path):
    (tmp_path / "run.py").write_text(
        'df = pd.read_csv("/Users/jsmith/Dropbox/data/file.csv")\n'
    )
    result = scan_python_scripts(tmp_path)
    assert len(result.external_paths) == 1
    assert result.external_paths[0].kind == "dropbox"


def test_scan_python_fixture_external_paths():
    result = scan_python_scripts(FIXTURE)
    assert len(result.external_paths) == 1
    assert result.external_paths[0].kind == "dropbox"
    assert "lfs_2019.csv" in result.external_paths[0].raw


def test_scan_python_no_external_paths_for_relative(tmp_path):
    (tmp_path / "run.py").write_text('df = pd.read_csv("data/survey.csv")\n')
    result = scan_python_scripts(tmp_path)
    assert len(result.external_paths) == 0


# ---------------------------------------------------------------------------
# Download detection
# ---------------------------------------------------------------------------


def test_scan_python_detects_requests_get(tmp_path):
    (tmp_path / "run.py").write_text(
        'resp = requests.get("https://example.com/data.zip")\n'
    )
    result = scan_python_scripts(tmp_path)
    assert len(result.download_calls) == 1
    assert "example.com" in result.download_calls[0].url


def test_scan_python_detects_urlretrieve(tmp_path):
    (tmp_path / "run.py").write_text(
        'urllib.request.urlretrieve("https://data.gov/file.csv", "file.csv")\n'
    )
    result = scan_python_scripts(tmp_path)
    assert len(result.download_calls) == 1


# ---------------------------------------------------------------------------
# Combined scan_scripts
# ---------------------------------------------------------------------------


def test_scan_scripts_combines_r_and_python(tmp_path):
    (tmp_path / "analysis.R").write_text("library(ggplot2)\n")
    (tmp_path / "analysis.py").write_text("import pandas\n")
    result = scan_scripts(tmp_path)
    assert "ggplot2" in result.used_packages
    assert "pandas" in result.used_packages


def test_scan_scripts_secrets_deduped(tmp_path):
    (tmp_path / ".env").write_text("TOKEN=abc\n")
    (tmp_path / "run.R").write_text("library(dplyr)\n")
    (tmp_path / "run.py").write_text("import pandas\n")
    result = scan_scripts(tmp_path)
    # Secret scan runs once — only one entry for .env
    secret_paths = [str(s.path) for s in result.secret_files]
    assert secret_paths.count(".env") == 1
