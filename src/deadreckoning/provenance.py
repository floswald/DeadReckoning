"""
Trace which root data file(s) feed each paper exhibit (table/figure).

Answers the data-availability-statement question authors find tedious to
write by hand: "which input dataset produces this table?" Walks the
existing GRAPH structures backward from each exhibit through however many
intermediate scripts/files stand between a raw input and the final output —
no new parsing needed, DependencyGraph.script_writes and .data_files
already have everything required.
"""

from __future__ import annotations

from pathlib import Path

from .models import DataFile, DependencyGraph


def _resolves_to(written_path: Path, writer_script: Path, target_abs: Path, project_root: Path) -> bool:
    """Same two-pass resolution used for exhibit-sourcing in graph.py: try
    script-relative, then project-root-relative — authors often write
    relative paths meant to be relative to the project root, not the
    writing script's own location."""
    written_abs_script = (writer_script.parent / written_path).resolve()
    written_abs_root = (project_root / written_path).resolve()
    return written_abs_script == target_abs or written_abs_root == target_abs


def _resolve_data_file_path(df_path: Path, reader_script: Path, project_root: Path) -> Path:
    """Resolve a DataFile.path (as literally written in the reading script)
    to an absolute path, for matching against write-call targets."""
    if df_path.is_absolute():
        return df_path.resolve()
    root_candidate = (project_root / df_path).resolve()
    if root_candidate.exists():
        return root_candidate
    return (reader_script.parent / df_path).resolve()


def _reads_of(script: Path, data_files: list[DataFile]) -> list[DataFile]:
    return [df for df in data_files if script in df.referenced_by]


def _find_writer(target_abs: Path, graph: DependencyGraph) -> Path | None:
    for w in graph.script_writes:
        if _resolves_to(w.written_path, w.script, target_abs, graph.project_root):
            return w.script
    return None


def _root_inputs_for_script(script: Path, graph: DependencyGraph, visited: frozenset[Path]) -> list[Path]:
    """Backward-BFS (recursive): a script's root inputs are its own reads,
    except any read that is itself written by another script in the
    project — in that case, recurse into the writer's reads instead."""
    if script in visited:
        return []  # cycle guard — shouldn't occur in a correct pipeline
    visited = visited | {script}

    roots: list[Path] = []
    for df in _reads_of(script, graph.data_files):
        target_abs = _resolve_data_file_path(df.path, script, graph.project_root)
        writer = _find_writer(target_abs, graph)
        if writer is not None and writer != script:
            roots.extend(_root_inputs_for_script(writer, graph, visited))
        else:
            roots.append(df.path)
    return roots


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def trace_exhibit_inputs(graph: DependencyGraph) -> dict[Path, list[Path]]:
    """
    For each sourced exhibit, return the root data file(s) that feed it —
    walking through any intermediate scripts (raw CSV -> cleaned .Rds ->
    final table) rather than stopping at the first hop.

    Exhibits with no known source script are omitted (nothing to trace).
    """
    mapping: dict[Path, list[Path]] = {}
    for exhibit in graph.exhibits:
        if exhibit.source is None:
            continue
        roots = _root_inputs_for_script(exhibit.source.script, graph, frozenset())
        mapping[exhibit.tex_path] = _dedupe(roots)
    return mapping


def render_data_exhibit_map(mapping: dict[Path, list[Path]]) -> str:
    """Render the exhibit -> root-data-input mapping as a Markdown table."""
    lines = [
        "# Data → Exhibit Map",
        "",
        "Which input data file(s) feed each paper exhibit, traced through",
        "any intermediate processing scripts.",
        "",
        "| Exhibit | Data input(s) |",
        "|---|---|",
    ]
    for exhibit in sorted(mapping, key=str):
        inputs = mapping[exhibit]
        input_str = ", ".join(f"`{i}`" for i in inputs) if inputs else "_(none found)_"
        lines.append(f"| `{exhibit}` | {input_str} |")
    return "\n".join(lines) + "\n"


def write_data_exhibit_map(working_copy: Path, text: str) -> Path:
    path = working_copy / "DATA-EXHIBIT-MAP.md"
    path.write_text(text)
    return path


def data_file_exhibits(mapping: dict[Path, list[Path]]) -> dict[Path, list[Path]]:
    """Invert trace_exhibit_inputs(): for each root data file, which exhibit(s) it feeds."""
    inverted: dict[Path, list[Path]] = {}
    for exhibit, inputs in mapping.items():
        for data_path in inputs:
            inverted.setdefault(data_path, []).append(exhibit)
    return inverted
