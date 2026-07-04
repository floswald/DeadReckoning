"""Smoke test for the LandUse demo script (demo/run_demo_landuse.py).

Fixture sanity checks run everywhere. The full end-to-end run needs a
local Stata install (native RUN step) and ANTHROPIC_API_KEY (LLM fix
loop for the rigged renamed-file bug) — marked local+llm, same as the
Rscript-dependent CLI test in test_cli.py, and excluded from CI by
`-m "not local and not llm"` (see .github/workflows/ci.yml).

Run locally with:
    ANTHROPIC_API_KEY=... pytest tests/test_demo_landuse.py -v -m "local and llm"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FIXTURE = REPO_ROOT / "demo" / "landuse_real"

sys.path.insert(0, str(REPO_ROOT / "demo"))
sys.path.insert(0, str(REPO_ROOT / "src"))


# ---------------------------------------------------------------------------
# Fixture sanity — no Stata/LLM needed
# ---------------------------------------------------------------------------


def test_fixture_script_and_data_present():
    assert (FIXTURE / "code" / "stata" / "figure1.do").exists()
    assert (FIXTURE / "data" / "raw" / "FRA_base_v2.dta").exists()


def test_fixture_excludes_restricted_paths():
    """not-shared/ and data/CASD/ must never be copied into this fixture."""
    assert not (FIXTURE / "not-shared").exists()
    assert not (FIXTURE / "data" / "CASD").exists()


def test_fixture_rigs_exactly_one_bug():
    """Script still references the pre-rename filename; disk has the renamed one."""
    script_text = (FIXTURE / "code" / "stata" / "figure1.do").read_text()
    assert 'use "data/raw/FRA_base.dta"' in script_text
    assert "FRA_base_v2" not in script_text
    assert not (FIXTURE / "data" / "raw" / "FRA_base.dta").exists()


def test_fixture_not_restricted():
    from deadreckoning.confidentiality import check_restricted

    status = check_restricted(FIXTURE)
    assert status.is_restricted is False


def test_scan_finds_no_external_paths():
    """The renamed-file bug is invisible to a static scan — plain relative path."""
    from deadreckoning.scan import scan_scripts

    scan = scan_scripts(FIXTURE)
    assert not scan.has_external_paths


# ---------------------------------------------------------------------------
# Full pipeline — requires local Stata + live Claude API call
# ---------------------------------------------------------------------------


@pytest.mark.local
@pytest.mark.llm
def test_demo_script_runs_end_to_end(capsys):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    import run_demo_landuse

    run_demo_landuse.main(terse=True)

    out = capsys.readouterr().out
    assert "restricted: False" in out
    assert "re-run after LLM fix: OK" in out
    assert "figure1.pdf" in out
