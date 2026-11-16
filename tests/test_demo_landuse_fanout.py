"""Smoke test for the landuse fan-out demo script (demo/run_demo_landuse_fanout.py).

Fixture sanity checks run everywhere. The full end-to-end run needs a
local Stata install (two native RUN steps) — no LLM involved, nothing in
this demo crashes — marked `local`, excluded from CI by
`-m "not local and not llm"` (see .github/workflows/ci.yml).

Run locally with:
    pytest tests/test_demo_landuse_fanout.py -v -m local
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FIXTURE = REPO_ROOT / "demo" / "landuse_fanout"

sys.path.insert(0, str(REPO_ROOT / "demo"))
sys.path.insert(0, str(REPO_ROOT / "src"))


# ---------------------------------------------------------------------------
# Fixture sanity — no Stata needed
# ---------------------------------------------------------------------------


def test_fixture_scripts_and_data_present():
    assert (FIXTURE / "code" / "stata" / "figure1.do").exists()
    assert (FIXTURE / "code" / "stata" / "generatethetas.do").exists()
    assert (FIXTURE / "data" / "raw" / "FRA_base.dta").exists()


def test_fixture_reference_has_all_six_exhibits():
    for name in (
        "figure1.pdf", "figureA2a.pdf", "figureA2b.pdf",
        "figureA3.pdf", "figure7.pdf", "figureA4.pdf",
    ):
        assert (FIXTURE / "reference" / name).exists(), name


def test_fixture_both_scripts_read_the_same_input():
    fig1_text = (FIXTURE / "code" / "stata" / "figure1.do").read_text()
    thetas_text = (FIXTURE / "code" / "stata" / "generatethetas.do").read_text()
    assert 'use "data/raw/FRA_base.dta"' in fig1_text
    assert 'use "data/raw/FRA_base.dta"' in thetas_text


def test_fixture_not_restricted():
    from deadreckoning.confidentiality import check_restricted

    status = check_restricted(FIXTURE)
    assert status.is_restricted is False


def test_graph_sees_one_shared_data_file_referenced_by_both_scripts():
    from deadreckoning.graph import build_graph

    graph = build_graph(FIXTURE)
    fra_base = next(df for df in graph.data_files if df.path == Path("data/raw/FRA_base.dta"))
    referenced = {s.name for s in fra_base.referenced_by}
    assert referenced == {"figure1.do", "generatethetas.do"}


# ---------------------------------------------------------------------------
# Full pipeline — requires local Stata
# ---------------------------------------------------------------------------


@pytest.mark.local
@pytest.mark.stata
def test_demo_script_runs_end_to_end_and_discriminates_3_3(capsys):
    import run_demo_landuse_fanout

    run_demo_landuse_fanout.main(terse=True)

    out = capsys.readouterr().out
    assert "restricted: False" in out
    assert "3/6 match reference" in out
    assert "3/6 MISMATCH" in out

    # figure1.do's three exhibits are the stale ones; generatethetas.do's
    # three are current — this is the discrimination the demo exists to show.
    assert "figure1.pdf" in out and "figureA2a.pdf" in out and "figureA2b.pdf" in out
    assert "figureA3.pdf" in out and "figure7.pdf" in out and "figureA4.pdf" in out

    # all three mismatches converge on the same upstream suspect
    assert "data/raw/FRA_base.dta" in out
    assert out.count("data/raw/FRA_base.dta") >= 1
