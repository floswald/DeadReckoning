"""
Real-world test: LandUse paper (paper_production folder).

Loose oracle — no manifest required. Checks structural properties of the
dependency graph rather than asserting exact exhibit lists or script sources.

Skipped automatically when the fixture isn't present (real data, not in repo).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.confidentiality import check_restricted
from deadreckoning.graph import build_graph, _collect_tex_macros
from deadreckoning.models import GapKind

FIXTURE = Path(__file__).parent / "real_world" / "landuse"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_world: mark test as requiring real-world fixture data"
    )


@pytest.fixture(scope="module")
def landuse_graph():
    graph = build_graph(FIXTURE)
    return graph


# Skip entire module if fixture not present
pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="Real-world landuse fixture not present (local only)",
)


# ---------------------------------------------------------------------------
# Confidentiality
# ---------------------------------------------------------------------------


def test_landuse_not_restricted():
    status = check_restricted(FIXTURE)
    assert status.is_restricted is False


# ---------------------------------------------------------------------------
# LaTeX macro resolution
# ---------------------------------------------------------------------------


def test_latex_path_macros_resolved():
    """\\dataplots, \\modplots etc. must be expanded to real paths."""
    tex_files = sorted(FIXTURE.rglob("*.tex"))
    macros = _collect_tex_macros(tex_files)
    assert "dataplots" in macros
    assert "modplots" in macros
    assert "modtables" in macros
    assert "datatables" in macros
    assert "images" in macros


def test_all_exhibits_exist_on_disk(landuse_graph):
    """After macro resolution, every referenced exhibit must exist on disk."""
    missing = [e for e in landuse_graph.exhibits if not e.exists_on_disk]
    assert missing == [], (
        f"{len(missing)} exhibits referenced in .tex but missing from disk:\n"
        + "\n".join(f"  {e.tex_path}" for e in missing[:10])
    )


# ---------------------------------------------------------------------------
# Exhibit count sanity
# ---------------------------------------------------------------------------


def test_exhibit_count_plausible(landuse_graph):
    """Paper has many figures and tables — expect at least 30 exhibits."""
    assert len(landuse_graph.exhibits) >= 30, (
        f"Only {len(landuse_graph.exhibits)} exhibits found — macro resolution likely broken"
    )


# ---------------------------------------------------------------------------
# Gap classification
# ---------------------------------------------------------------------------


def test_no_inline_statistics_in_prose(landuse_graph):
    """Output table tex files must be excluded — no false inline_statistic hits."""
    stat_gaps = [g for g in landuse_graph.gaps if g.kind == GapKind.inline_statistic]
    assert stat_gaps == [], (
        f"{len(stat_gaps)} inline_statistic gaps — likely false positives from output tables:\n"
        + "\n".join(f"  {g.location}: {g.snippet!r}" for g in stat_gaps[:5])
    )


def test_all_gaps_are_no_source_script(landuse_graph):
    """
    This folder contains paper + outputs but NO code scripts.
    All exhibit gaps should be exhibit_no_source_script (expected),
    not exhibit_missing_from_disk (would mean macro resolution broke).
    """
    wrong = [
        g for g in landuse_graph.gaps
        if g.kind == GapKind.exhibit_missing_from_disk
    ]
    assert wrong == [], (
        f"{len(wrong)} exhibits missing from disk — macro resolution may be broken:\n"
        + "\n".join(f"  {g.exhibit}" for g in wrong[:10])
    )


def test_no_scripts_found(landuse_graph):
    """paper_production has no code scripts — script_order must be empty."""
    assert landuse_graph.script_order == []
