"""CAPTURE enhancements — date inference for R without renv.lock."""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.capture import (
    _infer_date_from_file_mtimes,
    _infer_date_from_rhistory,
    _r_inferred_from_date,
    capture_env,
)
from deadreckoning.models import PinMethod

FIXTURE_NO_LOCKFILE = Path(__file__).parent / "fixtures" / "r_no_lockfile"


def test_capture_r_no_lockfile_returns_r():
    spec = capture_env(FIXTURE_NO_LOCKFILE)
    assert spec.language == "R"


def test_capture_r_no_lockfile_method_inferred():
    spec = capture_env(FIXTURE_NO_LOCKFILE)
    assert spec.pin_method == PinMethod.inferred_from_date


def test_capture_r_no_lockfile_has_date():
    spec = capture_env(FIXTURE_NO_LOCKFILE)
    assert spec.snapshot_date is not None
    # Must be ISO date format
    import re
    assert re.match(r"\d{4}-\d{2}-\d{2}", spec.snapshot_date)


def test_capture_r_no_lockfile_has_snapshot_url():
    spec = capture_env(FIXTURE_NO_LOCKFILE)
    assert spec.snapshot_url is not None
    assert "packagemanager.posit.co/cran/" in spec.snapshot_url


def test_capture_r_no_lockfile_lower_confidence():
    spec = capture_env(FIXTURE_NO_LOCKFILE)
    assert spec.confidence < 0.9  # inferred, not pinned


def test_infer_date_from_rhistory(tmp_path):
    (tmp_path / ".Rhistory").write_text(
        "# 2024-03-15 some session\nlibrary(ggplot2)\n"
    )
    r_files = [tmp_path / "run.R"]
    (tmp_path / "run.R").write_text("library(ggplot2)\n")
    date = _infer_date_from_rhistory(tmp_path)
    assert date == "2024-03-15"


def test_infer_date_from_rhistory_missing(tmp_path):
    date = _infer_date_from_rhistory(tmp_path)
    assert date is None


def test_infer_date_from_file_mtimes(tmp_path):
    r_file = tmp_path / "run.R"
    r_file.write_text("library(ggplot2)\n")
    date = _infer_date_from_file_mtimes([r_file])
    assert date is not None
    import re
    assert re.match(r"\d{4}-\d{2}-\d{2}", date)


def test_r_inferred_builds_ppm_url(tmp_path):
    (tmp_path / ".Rhistory").write_text("# 2023-11-01\n")
    r_files = [tmp_path / "run.R"]
    (tmp_path / "run.R").write_text("")
    spec = _r_inferred_from_date(tmp_path, r_files)
    assert spec.snapshot_url == "https://packagemanager.posit.co/cran/2023-11-01"
    assert spec.pin_method == PinMethod.inferred_from_date
