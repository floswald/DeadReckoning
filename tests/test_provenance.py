"""Unit tests for the exhibit <- data-file provenance tracer."""

from __future__ import annotations

from pathlib import Path

from deadreckoning.graph import build_graph
from deadreckoning.provenance import (
    data_file_exhibits,
    render_data_exhibit_map,
    trace_exhibit_inputs,
)


def test_single_hop_traces_directly_to_root_data(tmp_path):
    """Script reads a CSV and writes the exhibit directly — one hop."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "tables.R").write_text(
        'x <- read.csv("data/survey.csv")\nwriteLines(x, "tables/out.tex")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\input{tables/out.tex}")
    graph = build_graph(tmp_path)
    mapping = trace_exhibit_inputs(graph)
    assert mapping[Path("tables/out.tex")] == [Path("data/survey.csv")]


def test_multi_hop_traces_through_intermediate_file(tmp_path):
    """
    Raw CSV -> intermediate .Rds (written by one script, read by another)
    -> final table. Must report the *raw* CSV as the root input, not the
    intermediate .Rds.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "clean.R").write_text(
        'x <- read.csv("data/raw.csv")\nsaveRDS(x, "data/clean.Rds")\n'
    )
    (tmp_path / "code" / "tables.R").write_text(
        'x <- readRDS("data/clean.Rds")\nwriteLines(x, "tables/out.tex")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\input{tables/out.tex}")
    graph = build_graph(tmp_path)
    mapping = trace_exhibit_inputs(graph)
    assert mapping[Path("tables/out.tex")] == [Path("data/raw.csv")]


def test_missing_root_data_file_still_reported(tmp_path):
    """A root data file that doesn't exist on disk is still reported —
    tracing is about code-declared dependencies, not disk presence."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "tables.R").write_text(
        'x <- read.csv("data/missing.csv")\nwriteLines(x, "tables/out.tex")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\input{tables/out.tex}")
    graph = build_graph(tmp_path)
    mapping = trace_exhibit_inputs(graph)
    assert mapping[Path("tables/out.tex")] == [Path("data/missing.csv")]


def test_cycle_guard_does_not_hang_or_crash(tmp_path):
    """
    Defensive: a (contrived, shouldn't occur in a real pipeline) cycle
    where two scripts each appear to write what the other reads must not
    cause infinite recursion.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "a.R").write_text(
        'x <- readRDS("data/b.Rds")\nsaveRDS(x, "data/a.Rds")\n'
    )
    (tmp_path / "code" / "b.R").write_text(
        'x <- readRDS("data/a.Rds")\nsaveRDS(x, "data/b.Rds")\n'
        'writeLines(x, "tables/out.tex")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\input{tables/out.tex}")
    graph = build_graph(tmp_path)
    mapping = trace_exhibit_inputs(graph)  # must return, not hang
    assert Path("tables/out.tex") in mapping


def test_exhibit_with_no_source_omitted(tmp_path):
    """Exhibits with no known source script have nothing to trace and are
    omitted from the mapping (not present with an empty list)."""
    (tmp_path / "paper.tex").write_text(r"\input{tables/missing.tex}")
    graph = build_graph(tmp_path)
    mapping = trace_exhibit_inputs(graph)
    assert mapping == {}


def test_render_data_exhibit_map_produces_table():
    mapping = {Path("tables/out.tex"): [Path("data/survey.csv")]}
    text = render_data_exhibit_map(mapping)
    assert "tables/out.tex" in text
    assert "data/survey.csv" in text
    assert "| Exhibit | Data input(s) |" in text


def test_render_data_exhibit_map_handles_no_inputs():
    mapping = {Path("tables/out.tex"): []}
    text = render_data_exhibit_map(mapping)
    assert "none found" in text


def test_data_file_exhibits_inverts_mapping():
    """One data file feeding two exhibits must list both when inverted —
    the view deliver.py's Dataset List needs."""
    mapping = {
        Path("tables/t1.tex"): [Path("data/survey.csv")],
        Path("tables/t2.tex"): [Path("data/survey.csv")],
    }
    inverted = data_file_exhibits(mapping)
    assert set(inverted[Path("data/survey.csv")]) == {Path("tables/t1.tex"), Path("tables/t2.tex")}
