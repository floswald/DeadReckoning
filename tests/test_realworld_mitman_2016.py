"""Real-world test: Mitman et al. (JPE 2016) replication package.

Mixed Stata + Python package. Tests:
- GRAPH step on a multi-language, multi-script package
- Exhibit extraction from a deeply-structured LaTeX source (code/tex/)
- Stata language detection + low-confidence env capture (no lockfile)
- Python package detection from .py scripts (geopandas, pandas, etc.)
- All exhibits flagged as missing-from-disk (code-only fixture, no outputs)
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from deadreckoning.capture import capture_env
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind
from deadreckoning.scan import scan_scripts

FIXTURE = Path(__file__).parent / "fixtures" / "real-world" / "mitman_2016"

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="Real-world fixture not present — add to tests/fixtures/real-world/mitman_2016/",
)


# ---------------------------------------------------------------------------
# Fixture sanity
# ---------------------------------------------------------------------------


def test_fixture_tex_exists():
    assert (FIXTURE / "code" / "tex" / "MacroElasticity_JPE_Rev3_1_I.tex").exists()


def test_fixture_master_script_exists():
    assert (FIXTURE / "code" / "RunBuild.do").exists()


def test_fixture_config_exists():
    assert (FIXTURE / "code" / "config.do").exists()


def test_fixture_has_stata_scripts():
    do_files = list(FIXTURE.rglob("*.do"))
    assert len(do_files) >= 10


def test_fixture_has_python_scripts():
    py_files = list(FIXTURE.rglob("*.py"))
    assert len(py_files) >= 2


# ---------------------------------------------------------------------------
# GRAPH step
# ---------------------------------------------------------------------------


def test_graph_finds_tex_file():
    g = build_graph(FIXTURE)
    assert len(g.tex_files) >= 1
    tex_names = [t.name for t in g.tex_files]
    assert any("MacroElasticity" in n for n in tex_names)


def test_graph_exhibit_count():
    """43 exhibits referenced in the LaTeX source."""
    g = build_graph(FIXTURE)
    assert len(g.exhibits) == 43


def test_graph_all_exhibits_missing_from_disk():
    """Code-only fixture: no outputs on disk."""
    g = build_graph(FIXTURE)
    assert all(not e.exists_on_disk for e in g.exhibits)


def test_graph_gap_count():
    g = build_graph(FIXTURE)
    assert len(g.gaps) == 46


def test_graph_gap_kinds():
    g = build_graph(FIXTURE)
    kinds = Counter(gap.kind.value for gap in g.gaps)
    assert kinds[GapKind.exhibit_missing_from_disk.value] == 43
    assert kinds[GapKind.inline_table.value] == 2
    assert kinds[GapKind.inline_statistic.value] == 1


def test_graph_detects_figure_exhibits():
    g = build_graph(FIXTURE)
    pdf_exhibits = [e for e in g.exhibits if str(e.tex_path).endswith(".pdf")]
    assert len(pdf_exhibits) >= 5


def test_graph_detects_table_exhibits():
    g = build_graph(FIXTURE)
    tex_exhibits = [e for e in g.exhibits if str(e.tex_path).endswith(".tex")]
    assert len(tex_exhibits) >= 5


def test_graph_specific_figure_present():
    """DiffWks.pdf is referenced in the paper."""
    g = build_graph(FIXTURE)
    paths = [str(e.tex_path) for e in g.exhibits]
    assert any("DiffWks.pdf" in p for p in paths)


def test_graph_specific_table_present():
    """Benefits_on_unemp.tex table is referenced in the paper."""
    g = build_graph(FIXTURE)
    paths = [str(e.tex_path) for e in g.exhibits]
    assert any("Benefits_on_unemp.tex" in p for p in paths)


def test_graph_motight_figures_present():
    """motight_* border figures appear."""
    g = build_graph(FIXTURE)
    paths = [str(e.tex_path) for e in g.exhibits]
    assert any("motight_" in p for p in paths)


# ---------------------------------------------------------------------------
# SCAN step — multi-language package detection
# ---------------------------------------------------------------------------


def test_scan_finds_python_packages():
    scan = scan_scripts(FIXTURE)
    pkgs = set(scan.used_packages)
    assert "pandas" in pkgs


def test_scan_finds_geopandas():
    scan = scan_scripts(FIXTURE)
    pkgs = set(scan.used_packages)
    assert "geopandas" in pkgs


def test_scan_finds_matplotlib():
    scan = scan_scripts(FIXTURE)
    pkgs = set(scan.used_packages)
    assert "matplotlib" in pkgs


def test_scan_no_dangerous_secrets():
    scan = scan_scripts(FIXTURE)
    assert not scan.has_secrets


# ---------------------------------------------------------------------------
# CAPTURE step — Stata language detection, low confidence
# ---------------------------------------------------------------------------


def test_capture_detects_stata():
    spec = capture_env(FIXTURE)
    assert spec.language.upper() == "STATA"


def test_capture_low_confidence_no_lockfile():
    """No Stata lockfile equivalent → low confidence."""
    spec = capture_env(FIXTURE)
    assert spec.confidence < 0.5


def test_capture_returns_env_spec():
    from deadreckoning.models import EnvSpec
    spec = capture_env(FIXTURE)
    assert isinstance(spec, EnvSpec)


# ---------------------------------------------------------------------------
# Multi-language detection
# ---------------------------------------------------------------------------


def test_both_stata_and_python_scripts_present():
    do_files = list(FIXTURE.rglob("*.do"))
    py_files = list(FIXTURE.rglob("*.py"))
    assert len(do_files) > 0
    assert len(py_files) > 0


def test_stata_dominates_language_detection():
    """Primary language should be Stata even though Python scripts exist."""
    spec = capture_env(FIXTURE)
    assert spec.language.upper() == "STATA"
