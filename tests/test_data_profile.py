"""
Tests for data_profile.py — local-only, structure-only data profiling.

Row counts and column names only; must never surface a cell value,
in the result or in the rendered Markdown. See issue #27.
"""

from __future__ import annotations

from pathlib import Path

from deadreckoning.data_profile import (
    profile_data_files,
    render_data_structure_summary,
    write_data_structure_summary,
)
from deadreckoning.models import DataFile, DependencyGraph

_SECRET_CELL = "ZZQX-SECRET-1"


def _make_graph(project_root: Path, data_files: list[DataFile]) -> DependencyGraph:
    return DependencyGraph(project_root=project_root, data_files=data_files)


def test_profile_csv_row_count_and_columns(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    csv_path = tmp_path / "data" / "census_extract.csv"
    csv_path.write_text(f"name,value\nalice,{_SECRET_CELL}\nbob,other\n")

    df = DataFile(path=Path("data/census_extract.csv"), exists_on_disk=True)
    graph = _make_graph(tmp_path, [df])

    result = profile_data_files(tmp_path, graph)

    assert len(result.profiles) == 1
    profile = result.profiles[0]
    assert profile.row_count == 2
    assert profile.columns == ["name", "value"]
    assert profile.note is None


def test_rendered_summary_never_contains_cell_values(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    csv_path = tmp_path / "data" / "census_extract.csv"
    csv_path.write_text(f"name,value\nalice,{_SECRET_CELL}\nbob,other\n")

    df = DataFile(path=Path("data/census_extract.csv"), exists_on_disk=True)
    graph = _make_graph(tmp_path, [df])

    result = profile_data_files(tmp_path, graph)
    text = render_data_structure_summary(result)

    assert _SECRET_CELL not in text
    assert "other" not in text
    assert "alice" not in text
    assert "bob" not in text
    # Structure metadata must still be present.
    assert "name" in text
    assert "2" in text


def test_unsupported_suffix_gets_note_not_row_count(tmp_path: Path) -> None:
    dta_path = tmp_path / "survey.dta"
    dta_path.write_bytes(b"\x00\x01")

    df = DataFile(path=Path("survey.dta"), exists_on_disk=True)
    graph = _make_graph(tmp_path, [df])

    result = profile_data_files(tmp_path, graph)

    assert len(result.profiles) == 1
    profile = result.profiles[0]
    assert profile.row_count is None
    assert profile.columns is None
    assert profile.note is not None
    assert "pandas" in profile.note


def test_external_data_files_are_skipped(tmp_path: Path) -> None:
    df = DataFile(path=Path("/some/dropbox/mount/file.csv"), exists_on_disk=False, is_external=True)
    graph = _make_graph(tmp_path, [df])

    result = profile_data_files(tmp_path, graph)

    assert result.profiles == []


def test_write_data_structure_summary(tmp_path: Path) -> None:
    graph = _make_graph(tmp_path, [])
    result = profile_data_files(tmp_path, graph)
    text = render_data_structure_summary(result)

    path = write_data_structure_summary(tmp_path, text)

    assert path == tmp_path / "DATA-STRUCTURE-SUMMARY.md"
    assert path.read_text() == text
