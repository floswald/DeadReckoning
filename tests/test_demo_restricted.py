"""Smoke test for the restricted-data demo script (demo/run_demo_restricted.py).

Pure Python standard library end to end — no interpreter dependency, no
API key, no Docker — so unlike the other demo smoke tests, this one runs
in regular CI, not just `-m local`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FIXTURE = REPO_ROOT / "demo" / "restricted_data"

sys.path.insert(0, str(REPO_ROOT / "src"))


def _load_demo_module():
    spec = importlib.util.spec_from_file_location(
        "run_demo_restricted", REPO_ROOT / "demo" / "run_demo_restricted.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_present():
    assert (FIXTURE / "code" / "analysis.py").exists()
    assert (FIXTURE / "data" / "survey_confidential.csv").exists()
    assert (FIXTURE / "paper.tex").exists()


def test_fixture_filename_trips_restricted_heuristic():
    from deadreckoning.confidentiality import check_restricted

    restricted = check_restricted(FIXTURE)
    assert restricted.is_restricted
    assert "survey_confidential.csv" in restricted.reason


def test_demo_runs_end_to_end_restricted_and_llm_fix_never_touches_client(capsys):
    module = _load_demo_module()
    module.main(terse=True)

    out = capsys.readouterr().out

    assert "restricted: True" in out
    assert "FAILED" in out  # the renamed-column bug
    assert "household_income" in out  # the bug surfaces in the traceback
    # DATA-STRUCTURE-SUMMARY must show the real column name, never cell values.
    assert "`income`" in out
    assert "54230" not in out  # a real cell value from the fixture CSV
    # The landmine client must never have been touched.
    assert "No AssertionError raised" in out
    assert "still failing" in out  # LLM-FIX did nothing, bug stays unfixed
