"""
Loose oracle for the LandUse replication package (Coeurdacier, Oswald, Teignier — REStud 2025).

Usage (from repo root):
    R_LANDUSE=~/Dropbox/research/LandUse/ReplicationPackage-submit \
    pytest tests/real_world/landuse/oracle.py -v

Checks every code-generated exhibit from README.qmd exists on disk under output/.
Exhibits marked "no code" in README (Figures 2, A.1, A.6–A.9, A.17) are excluded.
Does NOT check file contents — presence only (loose oracle per issue #9 spec).

Paths verified against actual output/ tree of a completed run.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_LANDUSE_PATH = os.environ.get("R_LANDUSE", "")
_PKG_ROOT = Path(_LANDUSE_PATH).expanduser() if _LANDUSE_PATH else None

pytestmark = pytest.mark.skipif(
    not _LANDUSE_PATH or not (_PKG_ROOT and _PKG_ROOT.exists()),
    reason="R_LANDUSE not set or path does not exist",
)


def root() -> Path:
    assert _PKG_ROOT is not None
    return _PKG_ROOT


def out(rel: str) -> Path:
    return root() / "output" / rel


def _panels(stem: str, letters: str) -> list[str]:
    return [f"{stem}{c}.pdf" for c in letters]


# ---------------------------------------------------------------------------
# Main text — data plots  (output/data/plots/)
# Figure 2 excluded — README: "no data/code used"
# Figure 5 uses hyphen separator: figure5-a.pdf, figure5-b.pdf
# ---------------------------------------------------------------------------

MAIN_DATA_PLOTS = [
    "data/plots/figure1.pdf",
    "data/plots/figure3.pdf",
    "data/plots/figure4a.pdf",
    "data/plots/figure4b.pdf",
    "data/plots/figure5-a.pdf",
    "data/plots/figure5-b.pdf",
    "data/plots/figure6a.pdf",
    "data/plots/figure6b.pdf",
    "data/plots/figure7.pdf",
]


@pytest.mark.parametrize("rel", MAIN_DATA_PLOTS)
def test_main_data_plot_exists(rel: str) -> None:
    assert out(rel).exists(), f"Missing main text data plot: output/{rel}"


# ---------------------------------------------------------------------------
# Main text — tables
# ---------------------------------------------------------------------------

MAIN_TABLES = [
    "model/tables/table1.tex",
    "data/tables/table2.tex",
]


@pytest.mark.parametrize("rel", MAIN_TABLES)
def test_main_table_exists(rel: str) -> None:
    assert out(rel).exists(), f"Missing main text table: output/{rel}"


# ---------------------------------------------------------------------------
# Main text — model plots  (output/model/plots/)
# ---------------------------------------------------------------------------

_MODEL_PLOTS: list[str] = []
for _fig, _letters in [
    ("figure8",  "abc"),
    ("figure9",  "ab"),
    ("figure10", "ab"),
    ("figure11", "ab"),
    ("figure12", "ab"),
    ("figure13", "abc"),
    ("figure14", "ab"),
    ("figure15", "abc"),
    ("figure16", "abc"),
    ("figure17", "abc"),
]:
    _MODEL_PLOTS.extend(f"model/plots/{p}" for p in _panels(_fig, _letters))


@pytest.mark.parametrize("rel", _MODEL_PLOTS)
def test_main_model_plot_exists(rel: str) -> None:
    assert out(rel).exists(), f"Missing main text model plot: output/{rel}"


# ---------------------------------------------------------------------------
# Appendix A — plots  (output/data/plots/)
# Excluded (no code): A.1, A.6, A.7, A.8, A.9, A.17
# FigureA5.pdf has capital F (actual filename on disk)
# A.10, A.11 are single-panel despite "tableAxx" label in README
# ---------------------------------------------------------------------------

APP_A_PLOTS = [
    "data/plots/figureA2a.pdf",
    "data/plots/figureA2b.pdf",
    "data/plots/figureA3.pdf",
    "data/plots/figureA4.pdf",
    "data/plots/FigureA5.pdf",       # capital F — actual filename
    "data/plots/figureA10.pdf",
    "data/plots/figureA11.pdf",
    "data/plots/figureA12.pdf",
    "data/plots/figureA13.pdf",
    "data/plots/figureA14a.pdf",
    "data/plots/figureA14b.pdf",
    "data/plots/figureA15.pdf",
    "data/plots/figureA16.pdf",
    "data/plots/figureA18.pdf",
    "data/plots/figureA19.pdf",
    "data/plots/figureA20.pdf",
    "data/plots/figureA21a.pdf",
    "data/plots/figureA21b.pdf",
    "data/plots/figureA22.pdf",
    "data/plots/figureA23.pdf",
]


@pytest.mark.parametrize("rel", APP_A_PLOTS)
def test_appendix_a_plot_exists(rel: str) -> None:
    assert out(rel).exists(), f"Missing Appendix A plot: output/{rel}"


# ---------------------------------------------------------------------------
# Appendix A — tables  (output/data/tables/)
# ---------------------------------------------------------------------------

APP_A_TABLES = [
    "data/tables/tableA1.tex",
    "data/tables/tableA2.tex",
    "data/tables/tableA3.tex",
    "data/tables/tableA4.tex",
    "data/tables/tableA5.tex",
    "data/tables/tableA6.tex",
]


@pytest.mark.parametrize("rel", APP_A_TABLES)
def test_appendix_a_table_exists(rel: str) -> None:
    assert out(rel).exists(), f"Missing Appendix A table: output/{rel}"


# ---------------------------------------------------------------------------
# Appendix B — plots  (output/model/plots/)
# figureB14 is listed as "identical to figure 13" in README but has its own
# panel files on disk (a/b/c) — included.
# ---------------------------------------------------------------------------

_APP_B_PLOTS: list[str] = []
for _fig, _letters in [
    ("figureB1",  "abcdef"),
    ("figureB2",  "abcd"),
    ("figureB3",  "abc"),
    ("figureB4",  ""),
    ("figureB5",  ""),
    ("figureB6",  ""),
    ("figureB7",  "abc"),
    ("figureB8",  "abc"),
    ("figureB9",  "abc"),
    ("figureB10", "abcdef"),
    ("figureB11", "abcdef"),
    ("figureB12", "abcdef"),
    ("figureB13", "abc"),
    ("figureB14", "abc"),
]:
    if _letters:
        _APP_B_PLOTS.extend(f"model/plots/{p}" for p in _panels(_fig, _letters))
    else:
        _APP_B_PLOTS.append(f"model/plots/{_fig}.pdf")


@pytest.mark.parametrize("rel", _APP_B_PLOTS)
def test_appendix_b_plot_exists(rel: str) -> None:
    assert out(rel).exists(), f"Missing Appendix B plot: output/{rel}"


# ---------------------------------------------------------------------------
# Appendix B — tables  (output/model/tables/, .tex extension)
# ---------------------------------------------------------------------------

APP_B_TABLES = [
    "model/tables/tableB1.tex",
    "model/tables/tableB2.tex",
    "model/tables/tableB3.tex",
    "model/tables/tableB4.tex",
    "model/tables/tableB5.tex",
]


@pytest.mark.parametrize("rel", APP_B_TABLES)
def test_appendix_b_table_exists(rel: str) -> None:
    assert out(rel).exists(), f"Missing Appendix B table: output/{rel}"


# ---------------------------------------------------------------------------
# Inventory sanity check
# ---------------------------------------------------------------------------

def test_oracle_exhibit_inventory() -> None:
    total = (
        len(MAIN_DATA_PLOTS)
        + len(MAIN_TABLES)
        + len(_MODEL_PLOTS)
        + len(APP_A_PLOTS)
        + len(APP_A_TABLES)
        + len(_APP_B_PLOTS)
        + len(APP_B_TABLES)
    )
    assert total >= 80, f"Oracle covers only {total} exhibits — likely incomplete"
