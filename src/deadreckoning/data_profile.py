"""
Local-only data-structure profiling for restricted-data runs.

Reports row counts and column names so a restricted-data author gets some
visibility into their own data without the pipeline opening files on their
behalf in a way that could leak cell values. Never reads/reports a cell
value, and the result is never transmitted anywhere — see issue #27.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .models import DataFileProfile, DataProfileResult, DependencyGraph

_STRUCTURED_TEXT_SUFFIXES = {".csv", ".tsv"}

_UNSUPPORTED_NOTE = (
    "structure not introspectable without an additional dependency "
    "(pandas/pyreadstat/etc.) — not added in this pass"
)


def _profile_csv(display_path: Path, actual_path: Path, delimiter: str) -> DataFileProfile:
    with actual_path.open(newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            return DataFileProfile(path=display_path, exists_on_disk=True, row_count=0, columns=[])
        row_count = sum(1 for _ in reader)
    return DataFileProfile(path=display_path, exists_on_disk=True, row_count=row_count, columns=header)


def profile_data_files(working_copy: Path, graph: DependencyGraph) -> DataProfileResult:
    """Structure-only summary of every data file in `graph.data_files`."""
    profiles: list[DataFileProfile] = []
    for df in graph.data_files:
        if df.is_external:
            continue
        actual_path = working_copy / df.path
        if not df.exists_on_disk:
            profiles.append(DataFileProfile(path=df.path, exists_on_disk=False))
            continue

        suffix = actual_path.suffix.lower()
        if suffix == ".csv":
            profiles.append(_profile_csv(df.path, actual_path, delimiter=","))
        elif suffix == ".tsv":
            profiles.append(_profile_csv(df.path, actual_path, delimiter="\t"))
        else:
            profiles.append(DataFileProfile(path=df.path, exists_on_disk=True, note=_UNSUPPORTED_NOTE))

    return DataProfileResult(profiles=profiles)


def render_data_structure_summary(result: DataProfileResult) -> str:
    """Render a Markdown summary — row counts and column names only."""
    lines = [
        "# Data Structure Summary",
        "",
        "Structure only — row counts and column names. No cell values are",
        "read or reported here, and this file is never transmitted anywhere.",
        "",
        "| Data file | Rows | Columns | Note |",
        "|---|---|---|---|",
    ]
    for p in sorted(result.profiles, key=lambda p: str(p.path)):
        rows = str(p.row_count) if p.row_count is not None else "—"
        cols = ", ".join(f"`{c}`" for c in p.columns) if p.columns else "—"
        note = p.note or ("not found on disk" if not p.exists_on_disk else "—")
        lines.append(f"| `{p.path}` | {rows} | {cols} | {note} |")
    return "\n".join(lines) + "\n"


def write_data_structure_summary(working_copy: Path, text: str) -> Path:
    path = working_copy / "DATA-STRUCTURE-SUMMARY.md"
    path.write_text(text)
    return path
