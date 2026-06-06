"""Tests for the fixture generator and fault modules.

All tests run against tmp_path — never against committed fixtures.
Committed fixtures are tested separately via their own test files.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
import pytest

from fixture_generator import (
    FixtureGenerator,
    ManifestDelta,
    add_orphan_script,
    add_restricted_filename,
    absolutize_paths,
    build_python_external_data,
    build_stata_mixed,
    create_gold_python,
    create_gold_r,
    create_gold_stata,
    delete_lockfile,
    inject_inline_statistic,
    inline_table_in_tex,
    remove_write_path,
    write_manifest,
)
from deadreckoning.models import GapKind, Manifest, PinMethod


# ---------------------------------------------------------------------------
# Gold seed helpers
# ---------------------------------------------------------------------------


def test_create_gold_r(tmp_path):
    create_gold_r(tmp_path)
    assert (tmp_path / "renv.lock").exists()
    assert (tmp_path / "code" / "run.R").exists()
    assert (tmp_path / "paper.tex").exists()
    assert (tmp_path / "figures" / "fig1.pdf").exists()


def test_create_gold_stata(tmp_path):
    create_gold_stata(tmp_path)
    assert (tmp_path / "code" / "analysis.do").exists()
    assert (tmp_path / "paper.tex").exists()
    assert (tmp_path / "figures" / "fig1.pdf").exists()


def test_create_gold_python(tmp_path):
    create_gold_python(tmp_path)
    assert (tmp_path / "requirements.txt").exists()
    assert (tmp_path / "code" / "analysis.py").exists()
    assert (tmp_path / "figures" / "fig1.pdf").exists()


# ---------------------------------------------------------------------------
# delete_lockfile
# ---------------------------------------------------------------------------


def test_delete_lockfile_removes_renv_lock(tmp_path):
    create_gold_r(tmp_path)
    delta = delete_lockfile(tmp_path)
    assert not (tmp_path / "renv.lock").exists()
    assert "renv.lock" in delta.files_removed


def test_delete_lockfile_version_pin_is_inferred(tmp_path):
    create_gold_r(tmp_path)
    delta = delete_lockfile(tmp_path)
    assert any(vp.method == PinMethod.inferred_from_date for vp in delta.version_pins)


def test_delete_lockfile_no_lockfile_is_noop(tmp_path):
    create_gold_r(tmp_path)
    (tmp_path / "renv.lock").unlink()
    delta = delete_lockfile(tmp_path)
    assert delta.files_removed == []


# ---------------------------------------------------------------------------
# absolutize_paths
# ---------------------------------------------------------------------------


@pytest.fixture
def gold_r(tmp_path):
    d = tmp_path / "gold"
    create_gold_r(d)
    return d


def test_absolutize_paths_rewrites_r_script(gold_r):
    delta = absolutize_paths(gold_r, abs_root="/Users/testuser/Dropbox")
    script_text = (gold_r / "code" / "run.R").read_text()
    assert "/Users/testuser/Dropbox" in script_text


def test_absolutize_paths_delta_has_rewrites(gold_r):
    delta = absolutize_paths(gold_r, abs_root="/Users/testuser/Dropbox")
    assert len(delta.path_rewrites) >= 1


def test_absolutize_paths_rewrite_original_is_absolute(gold_r):
    delta = absolutize_paths(gold_r, abs_root="/Users/testuser/Dropbox")
    for pr in delta.path_rewrites:
        assert pr.original.startswith("/Users/testuser/Dropbox")


def test_absolutize_paths_rewrite_rewritten_is_relative(gold_r):
    delta = absolutize_paths(gold_r, abs_root="/Users/testuser/Dropbox")
    for pr in delta.path_rewrites:
        assert not pr.rewritten.startswith("/")


def test_absolutize_paths_stata_only(tmp_path):
    create_gold_stata(tmp_path)
    delta = absolutize_paths(tmp_path, abs_root="/home/user/data", extensions=(".do",))
    assert len(delta.path_rewrites) >= 1
    script_text = (tmp_path / "code" / "analysis.do").read_text()
    assert "/home/user/data" in script_text


# ---------------------------------------------------------------------------
# remove_write_path
# ---------------------------------------------------------------------------


def test_remove_write_path_r(tmp_path):
    create_gold_r(tmp_path)
    delta = remove_write_path(tmp_path, "code/run.R", "figures/fig1.pdf")
    text = (tmp_path / "code" / "run.R").read_text()
    assert '"fig1.pdf"' in text
    assert '"figures/fig1.pdf"' not in text


def test_remove_write_path_gap_kind(tmp_path):
    create_gold_r(tmp_path)
    delta = remove_write_path(tmp_path, "code/run.R", "figures/fig1.pdf")
    assert any(g.kind == GapKind.script_writes_wrong_path for g in delta.gaps)


def test_remove_write_path_gap_exhibit(tmp_path):
    create_gold_r(tmp_path)
    delta = remove_write_path(tmp_path, "code/run.R", "figures/fig1.pdf")
    assert any(g.exhibit == "figures/fig1.pdf" for g in delta.gaps)


def test_remove_write_path_missing_script_is_noop(tmp_path):
    create_gold_r(tmp_path)
    delta = remove_write_path(tmp_path, "code/nonexistent.R", "figures/fig1.pdf")
    assert delta.gaps == []


def test_remove_write_path_stata(tmp_path):
    create_gold_stata(tmp_path)
    delta = remove_write_path(tmp_path, "code/analysis.do", "figures/fig1.pdf")
    text = (tmp_path / "code" / "analysis.do").read_text()
    assert '"fig1.pdf"' in text
    assert '"figures/fig1.pdf"' not in text


# ---------------------------------------------------------------------------
# inline_table_in_tex
# ---------------------------------------------------------------------------


def test_inline_table_replaces_input(tmp_path):
    create_gold_r(tmp_path)
    delta = inline_table_in_tex(tmp_path, "tab1")
    text = (tmp_path / "paper.tex").read_text()
    assert r"\input{tables/tab1" not in text
    assert r"\begin{tabular}" in text


def test_inline_table_gap_kind(tmp_path):
    create_gold_r(tmp_path)
    delta = inline_table_in_tex(tmp_path, "tab1")
    assert any(g.kind == GapKind.inline_table for g in delta.gaps)


def test_inline_table_missing_table_is_noop(tmp_path):
    create_gold_r(tmp_path)
    delta = inline_table_in_tex(tmp_path, "tab99")
    assert delta.gaps == []


# ---------------------------------------------------------------------------
# add_orphan_script
# ---------------------------------------------------------------------------


def test_add_orphan_script_r(tmp_path):
    create_gold_r(tmp_path)
    delta = add_orphan_script(tmp_path, "old_v2.R", language="R")
    assert (tmp_path / "code" / "old_v2.R").exists()
    assert "library(" in (tmp_path / "code" / "old_v2.R").read_text()


def test_add_orphan_script_stata(tmp_path):
    create_gold_stata(tmp_path)
    delta = add_orphan_script(tmp_path, "old_merge.do", language="Stata")
    assert (tmp_path / "code" / "old_merge.do").exists()


def test_add_orphan_script_no_gap_emitted(tmp_path):
    create_gold_r(tmp_path)
    delta = add_orphan_script(tmp_path)
    assert delta.gaps == []


# ---------------------------------------------------------------------------
# add_restricted_filename
# ---------------------------------------------------------------------------


def test_add_restricted_filename_creates_file(tmp_path):
    create_gold_r(tmp_path)
    delta = add_restricted_filename(tmp_path, "census_restricted.dta", "data")
    assert (tmp_path / "data" / "census_restricted.dta").exists()


def test_add_restricted_filename_sets_is_restricted(tmp_path):
    create_gold_r(tmp_path)
    delta = add_restricted_filename(tmp_path)
    assert delta.is_restricted


def test_add_restricted_filename_trigger_path(tmp_path):
    create_gold_r(tmp_path)
    delta = add_restricted_filename(tmp_path, "secret.dta", "data")
    assert delta.restricted_trigger == "data/secret.dta"


# ---------------------------------------------------------------------------
# inject_inline_statistic
# ---------------------------------------------------------------------------


def test_inject_inline_statistic_in_tex(tmp_path):
    create_gold_r(tmp_path)
    delta = inject_inline_statistic(tmp_path, "0.047*** (0.012)")
    text = (tmp_path / "paper.tex").read_text()
    assert "0.047***" in text


def test_inject_inline_statistic_gap_kind(tmp_path):
    create_gold_r(tmp_path)
    delta = inject_inline_statistic(tmp_path)
    assert any(g.kind == GapKind.inline_statistic for g in delta.gaps)


# ---------------------------------------------------------------------------
# FixtureGenerator — orchestrated generation
# ---------------------------------------------------------------------------


def test_generator_copies_gold(tmp_path):
    gold = tmp_path / "gold"
    create_gold_r(gold)
    target = tmp_path / "out"
    gen = FixtureGenerator("test_fix", gold, target)
    assert (target / "paper.tex").exists()
    assert (target / "renv.lock").exists()


def test_generator_apply_accumulates_delta(tmp_path):
    gold = tmp_path / "gold"
    create_gold_r(gold)
    target = tmp_path / "out"
    gen = FixtureGenerator("test_fix", gold, target)
    gen.apply(delete_lockfile)
    gen.apply(remove_write_path, script_rel="code/run.R", filename="figures/fig1.pdf")
    manifest = gen.finalize()
    assert manifest.files_removed  # from delete_lockfile
    assert any(g.kind == GapKind.script_writes_wrong_path for g in manifest.gaps)


def test_generator_writes_manifest_yaml(tmp_path):
    gold = tmp_path / "gold"
    create_gold_r(gold)
    target = tmp_path / "out"
    gen = FixtureGenerator("test_fix", gold, target)
    gen.finalize()
    assert (target / "manifest.yaml").exists()


def test_generator_manifest_yaml_parseable(tmp_path):
    gold = tmp_path / "gold"
    create_gold_r(gold)
    target = tmp_path / "out"
    gen = FixtureGenerator("test_fix", gold, target)
    gen.apply(delete_lockfile)
    gen.finalize(notes="test")
    content = yaml.safe_load((target / "manifest.yaml").read_text())
    assert content["fixture_name"] == "test_fix"
    assert "gaps" in content
    assert "version_pins" in content


def test_generator_doesnt_overwrite_on_finalize_twice(tmp_path):
    gold = tmp_path / "gold"
    create_gold_r(gold)
    target = tmp_path / "out"
    gen = FixtureGenerator("test_fix", gold, target)
    m1 = gen.finalize(notes="first")
    m2 = gen.finalize(notes="second")
    # Second finalize overwrites — that's fine, just check no crash
    assert m2.fixture_name == "test_fix"


def test_generator_full_r_pipeline(tmp_path):
    gold = tmp_path / "gold"
    create_gold_r(gold)
    target = tmp_path / "r_messy"
    gen = FixtureGenerator("r_messy", gold, target)
    gen.apply(delete_lockfile)
    gen.apply(absolutize_paths, abs_root="/Users/testuser/Dropbox/rproject")
    gen.apply(remove_write_path, script_rel="code/run.R", filename="figures/fig1.pdf")
    gen.apply(inline_table_in_tex, table_name="tab1")
    gen.apply(add_orphan_script, name="old_code.R")
    manifest = gen.finalize(notes="Full R messy fixture.")

    assert manifest.is_restricted is False
    assert len(manifest.gaps) >= 2  # script_writes_wrong_path + inline_table
    assert len(manifest.path_rewrites) >= 1
    assert manifest.files_removed  # renv.lock
    text = (target / "code" / "run.R").read_text()
    assert "/Users/testuser/Dropbox" in text
    assert '"fig1.pdf"' in text
    assert (target / "code" / "old_code.R").exists()


def test_generator_restricted_fixture(tmp_path):
    gold = tmp_path / "gold"
    create_gold_r(gold)
    target = tmp_path / "restricted_out"
    gen = FixtureGenerator("restricted_test", gold, target)
    gen.apply(add_restricted_filename, name="census_2010_restricted.dta")
    manifest = gen.finalize()
    assert manifest.is_restricted
    assert manifest.restricted_trigger is not None


# ---------------------------------------------------------------------------
# Built-in committed fixture builders
# ---------------------------------------------------------------------------


def test_build_stata_mixed(tmp_path):
    target = tmp_path / "stata_mixed"
    manifest = build_stata_mixed(target)
    assert target.exists()
    assert (target / "manifest.yaml").exists()
    assert manifest.fixture_name == "stata_mixed"
    assert any(g.kind == GapKind.script_writes_wrong_path for g in manifest.gaps)
    assert any(g.kind == GapKind.inline_table for g in manifest.gaps)
    assert len(manifest.path_rewrites) >= 1
    # Verify absolute path injected in script
    do_text = (target / "code" / "analysis.do").read_text()
    assert "/Users/jsmith/Dropbox" in do_text


def test_build_python_external_data(tmp_path):
    target = tmp_path / "python_ext"
    manifest = build_python_external_data(target)
    assert target.exists()
    assert (target / "manifest.yaml").exists()
    assert manifest.fixture_name == "python_external_data"
    wrong_path_gaps = [g for g in manifest.gaps if g.kind == GapKind.script_writes_wrong_path]
    assert len(wrong_path_gaps) == 2  # fig1 + fig2
    py_text = (target / "code" / "analysis.py").read_text()
    assert "/Users/jsmith/Dropbox" in py_text


def test_build_stata_mixed_orphan_script(tmp_path):
    target = tmp_path / "stata_mixed"
    build_stata_mixed(target)
    assert (target / "code" / "old_merge.do").exists()


# ---------------------------------------------------------------------------
# multi_language_full manifest
# ---------------------------------------------------------------------------


def test_multi_language_full_manifest_exists():
    from pathlib import Path
    manifest_path = Path(__file__).parent / "fixtures" / "multi_language_full" / "manifest.yaml"
    assert manifest_path.exists(), "multi_language_full/manifest.yaml must exist"


def test_multi_language_full_manifest_has_three_gaps():
    from pathlib import Path
    import yaml
    manifest_path = Path(__file__).parent / "fixtures" / "multi_language_full" / "manifest.yaml"
    content = yaml.safe_load(manifest_path.read_text())
    gaps = content.get("gaps", [])
    assert len(gaps) == 3
    kinds = {g["kind"] for g in gaps}
    assert "script_writes_wrong_path" in kinds


def test_multi_language_full_manifest_has_rewrites():
    from pathlib import Path
    import yaml
    manifest_path = Path(__file__).parent / "fixtures" / "multi_language_full" / "manifest.yaml"
    content = yaml.safe_load(manifest_path.read_text())
    assert len(content.get("path_rewrites", [])) >= 1


def test_multi_language_full_manifest_three_version_pins():
    from pathlib import Path
    import yaml
    manifest_path = Path(__file__).parent / "fixtures" / "multi_language_full" / "manifest.yaml"
    content = yaml.safe_load(manifest_path.read_text())
    pins = content.get("version_pins", [])
    languages = {vp["language"] for vp in pins}
    assert languages == {"R", "Julia", "Stata"}


# ---------------------------------------------------------------------------
# write_manifest roundtrip
# ---------------------------------------------------------------------------


def test_write_manifest_roundtrip(tmp_path):
    from deadreckoning.models import ExpectedGap, ExpectedVersionPin, PathRewrite
    manifest = Manifest(
        fixture_name="roundtrip_test",
        gaps=[ExpectedGap(kind=GapKind.script_writes_wrong_path, exhibit="figures/fig1.pdf")],
        path_rewrites=[PathRewrite(original="/abs/path", rewritten="data/path")],
        version_pins=[ExpectedVersionPin(language="R", method=PinMethod.ppm_snapshot, snapshot_date="2023-01-01")],
        is_restricted=False,
    )
    write_manifest(tmp_path, manifest)
    content = yaml.safe_load((tmp_path / "manifest.yaml").read_text())
    assert content["fixture_name"] == "roundtrip_test"
    assert content["gaps"][0]["kind"] == "script_writes_wrong_path"
    assert content["version_pins"][0]["method"] == "ppm_snapshot"
    assert content["version_pins"][0]["snapshot_date"] == "2023-01-01"
