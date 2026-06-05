"""Tests for scan.py — pure reads, no local R required."""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.scan import scan_r_scripts

FIXTURE_NO_LOCKFILE = Path(__file__).parent / "fixtures" / "r_no_lockfile"
FIXTURE_MINIMAL     = Path(__file__).parent / "fixtures" / "runnable_minimal"


# ---------------------------------------------------------------------------
# Package extraction
# ---------------------------------------------------------------------------

def test_scan_extracts_library_calls():
    result = scan_r_scripts(FIXTURE_NO_LOCKFILE)
    assert "ggplot2" in result.used_packages
    assert "dplyr" in result.used_packages
    assert "stargazer" in result.used_packages
    assert "haven" in result.used_packages


def test_scan_excludes_base_r_packages():
    result = scan_r_scripts(FIXTURE_NO_LOCKFILE)
    assert "base" not in result.used_packages
    assert "stats" not in result.used_packages


def test_scan_double_colon_packages(tmp_path):
    (tmp_path / "script.R").write_text("x <- dplyr::filter(df, age > 30)\n")
    result = scan_r_scripts(tmp_path)
    assert "dplyr" in result.used_packages


def test_scan_no_packages_in_comment(tmp_path):
    (tmp_path / "script.R").write_text("# library(ggplot2) — old code\n")
    result = scan_r_scripts(tmp_path)
    assert "ggplot2" not in result.used_packages


# ---------------------------------------------------------------------------
# External path detection
# ---------------------------------------------------------------------------

def test_scan_detects_dropbox_paths():
    result = scan_r_scripts(FIXTURE_NO_LOCKFILE)
    kinds = {ep.kind for ep in result.external_paths}
    assert "dropbox" in kinds


def test_scan_external_paths_have_correct_script():
    result = scan_r_scripts(FIXTURE_NO_LOCKFILE)
    dropbox_paths = [ep for ep in result.external_paths if ep.kind == "dropbox"]
    scripts = {str(ep.script) for ep in dropbox_paths}
    assert any("analysis.R" in s or "tables.R" in s for s in scripts)


def test_scan_detects_network_share(tmp_path):
    (tmp_path / "script.R").write_text('df <- read.csv("//server/share/data.csv")\n')
    result = scan_r_scripts(tmp_path)
    assert any(ep.kind == "network_share" for ep in result.external_paths)


def test_scan_clean_project_no_external_paths():
    result = scan_r_scripts(FIXTURE_MINIMAL)
    assert not result.has_external_paths


# ---------------------------------------------------------------------------
# Secret file detection
# ---------------------------------------------------------------------------

def test_scan_detects_env_file(tmp_path):
    (tmp_path / ".env").write_text("API_KEY=secret123\n")
    (tmp_path / "script.R").write_text("library(httr)\n")
    result = scan_r_scripts(tmp_path)
    assert result.has_secrets
    assert any(".env" in str(sf.path) for sf in result.secret_files)


def test_scan_no_secrets_in_clean_project():
    result = scan_r_scripts(FIXTURE_MINIMAL)
    assert not result.has_secrets


# ---------------------------------------------------------------------------
# Download URL detection
# ---------------------------------------------------------------------------

def test_scan_detects_download_file(tmp_path):
    (tmp_path / "script.R").write_text(
        'download.file("https://example.com/data.zip", "data/data.zip")\n'
    )
    result = scan_r_scripts(tmp_path)
    assert len(result.download_calls) == 1
    assert result.download_calls[0].url == "https://example.com/data.zip"


def test_scan_no_downloads_in_minimal():
    result = scan_r_scripts(FIXTURE_MINIMAL)
    assert len(result.download_calls) == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_scan_empty_project(tmp_path):
    result = scan_r_scripts(tmp_path)
    assert result.used_packages == []
    assert result.external_paths == []
    assert result.secret_files == []
    assert result.download_calls == []
