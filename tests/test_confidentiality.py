"""Tests for the filename-only confidentiality gate (deadreckoning.confidentiality).

Focus: the 'admin' fragment must only fire on genuine admin-microdata
naming (admin_data.dta, admin_records.csv, ...), not on public reference
datasets that merely contain the substring — e.g. IGN's AdminExpress
French administrative-boundary files
(ign_metropole_adminexpress_chefs_lieux_z.prj), which triggered a false
positive in the wild (see tests/test_realworld_landuse_full.py).
"""

from __future__ import annotations

from pathlib import Path

from deadreckoning.confidentiality import check_restricted


def _touch(root: Path, relpath: str) -> Path:
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


# ---------------------------------------------------------------------------
# 'admin' false positives — must NOT trigger
# ---------------------------------------------------------------------------


def test_adminexpress_filename_not_restricted(tmp_path: Path) -> None:
    _touch(tmp_path, "data/IGN-chef-lieux/ign_metropole_adminexpress_chefs_lieux_z.prj")
    status = check_restricted(tmp_path)
    assert not status.is_restricted


def test_administrator_filename_not_restricted(tmp_path: Path) -> None:
    _touch(tmp_path, "docs/administrator_notes.txt")
    status = check_restricted(tmp_path)
    assert not status.is_restricted


def test_bare_admin_filename_not_restricted(tmp_path: Path) -> None:
    """Bare 'admin' with no data/records marker is too generic to flag alone."""
    _touch(tmp_path, "data/admin.dta")
    status = check_restricted(tmp_path)
    assert not status.is_restricted


# ---------------------------------------------------------------------------
# genuine admin-microdata naming — must still trigger
# ---------------------------------------------------------------------------


def test_admin_data_filename_is_restricted(tmp_path: Path) -> None:
    _touch(tmp_path, "data/admin_data.dta")
    status = check_restricted(tmp_path)
    assert status.is_restricted
    assert "admin_data.dta" in status.reason


def test_administrative_records_filename_is_restricted(tmp_path: Path) -> None:
    _touch(tmp_path, "data/administrative_records.csv")
    status = check_restricted(tmp_path)
    assert status.is_restricted


def test_admin_microdata_filename_is_restricted(tmp_path: Path) -> None:
    _touch(tmp_path, "data/SSA_admin_microdata.dta")
    status = check_restricted(tmp_path)
    assert status.is_restricted


# ---------------------------------------------------------------------------
# other existing patterns unaffected
# ---------------------------------------------------------------------------


def test_census_microdata_still_restricted(tmp_path: Path) -> None:
    _touch(tmp_path, "data/census_micro.dta")
    status = check_restricted(tmp_path)
    assert status.is_restricted


def test_clean_project_not_restricted(tmp_path: Path) -> None:
    _touch(tmp_path, "data/survey.csv")
    _touch(tmp_path, "code/analysis.R")
    status = check_restricted(tmp_path)
    assert not status.is_restricted
