"""
SORT-CHECK step tests — sort_check.py

Stata's default `sort` breaks ties among equal key values with an
internal random tiebreaker, not guaranteed stable across runs/editions —
see module docstring in sort_check.py for primary sources. A sort with no
`, stable` and no `set sortseed`, feeding a tie-sensitive
`by ... : ... _n==1`/`_n==_N` operation, must be flagged.
"""

from __future__ import annotations

from pathlib import Path

from deadreckoning.sort_check import check_nondeterministic_sort


def test_unstable_sort_feeding_first_obs_per_group_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "prep.do").write_text(
        "sort region\n"
        "by region: keep if _n==1\n"
    )
    result = check_nondeterministic_sort(tmp_path)
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.script == Path("code/prep.do")
    assert f.line == 1
    assert f.tie_sensitive_line == 2


def test_bysort_variant_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "prep.do").write_text(
        "sort region\n"
        "bysort region: keep if _n==_N\n"
    )
    result = check_nondeterministic_sort(tmp_path)
    assert len(result.findings) == 1


def test_stable_option_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "prep.do").write_text(
        "sort region, stable\n"
        "by region: keep if _n==1\n"
    )
    result = check_nondeterministic_sort(tmp_path)
    assert result.findings == []


def test_sortseed_set_anywhere_in_script_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "prep.do").write_text(
        "set sortseed 12345\n"
        "sort region\n"
        "by region: keep if _n==1\n"
    )
    result = check_nondeterministic_sort(tmp_path)
    assert result.findings == []


def test_sort_with_no_tie_sensitive_usage_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "prep.do").write_text(
        "sort region\n"
        "save data/prepped.dta, replace\n"
    )
    result = check_nondeterministic_sort(tmp_path)
    assert result.findings == []


def test_tie_sensitive_usage_with_no_preceding_sort_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "prep.do").write_text(
        "by region: keep if _n==1\n"
    )
    result = check_nondeterministic_sort(tmp_path)
    assert result.findings == []
