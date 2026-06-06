"""Real-world test: GarageLocations paper (Bus Location paper, Oswald et al.)

Source: GarageLocations_main.tex
Key features tested:
- Nested macro expansion: \\plots = \\rootdir/\\rootdir/Output/plots
  requires recursive _expand_macros (would silently produce 0 exhibits otherwise)
- 39 exhibits (15 figures + 24 table inputs)
- 2 inline tables (hardcoded tabular environments)
- All exhibits missing from disk (replication data not included)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind

FIXTURE = Path(__file__).parent / "fixtures" / "real-world" / "bus_location"


def test_fixture_tex_exists():
    assert (FIXTURE / "paper.tex").exists()


def test_graph_finds_39_exhibits():
    g = build_graph(FIXTURE)
    assert len(g.exhibits) == 39


def test_graph_all_exhibits_missing_from_disk():
    g = build_graph(FIXTURE)
    assert all(not e.exists_on_disk for e in g.exhibits)


def test_graph_figures_detected():
    g = build_graph(FIXTURE)
    pdfs = [e for e in g.exhibits if str(e.tex_path).endswith(".pdf")]
    assert len(pdfs) == 20


def test_graph_table_inputs_detected():
    g = build_graph(FIXTURE)
    tex_inputs = [e for e in g.exhibits if str(e.tex_path).endswith(".tex")]
    assert len(tex_inputs) == 19


def test_graph_nested_macro_expansion():
    """\\plots = \\rootdir/\\rootdir/Output/plots requires recursive expansion."""
    g = build_graph(FIXTURE)
    paths = [str(e.tex_path) for e in g.exhibits]
    # After expansion, paths should contain Output/plots or Output/tables
    assert any("Output/plots" in p or "Output/tables" in p for p in paths)


def test_graph_no_raw_macro_in_exhibit_paths():
    """No exhibit path should still contain unexpanded \\plots or \\tables."""
    g = build_graph(FIXTURE)
    for e in g.exhibits:
        assert "\\plots" not in str(e.tex_path)
        assert "\\tables" not in str(e.tex_path)


def test_graph_detects_inline_tables():
    g = build_graph(FIXTURE)
    inline = [gap for gap in g.gaps if gap.kind == GapKind.inline_table]
    assert len(inline) == 2


def test_graph_missing_exhibit_gaps():
    g = build_graph(FIXTURE)
    missing = [gap for gap in g.gaps if gap.kind == GapKind.exhibit_missing_from_disk]
    assert len(missing) == 39


def test_graph_specific_figure_present():
    """routes-garages-operators.pdf should be among detected exhibits."""
    g = build_graph(FIXTURE)
    paths = [str(e.tex_path) for e in g.exhibits]
    assert any("routes-garages-operators.pdf" in p for p in paths)


def test_graph_specific_table_present():
    """L-paper-preferred-model.tex should be among detected exhibits."""
    g = build_graph(FIXTURE)
    paths = [str(e.tex_path) for e in g.exhibits]
    assert any("L-paper-preferred-model.tex" in p for p in paths)
