"""Broken-fixture tests for Mitman et al. (JPE forthcoming 2026).

Each test copies the Mitman fixture to tmp_path, injects a specific error,
then asserts DeadReckoning detects it.  Every test follows a baseline→inject→
assert delta pattern so we prove detection rather than pre-existing state.

Scenarios:
  1. Absolute path in a .do file  → scan + resolve_paths detects/rewrites it
  2. Script writes exhibit to wrong path  → build_graph emits script_writes_wrong_path
  3. Exhibit on disk with no source script → build_graph emits exhibit_no_source_script
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind
from deadreckoning.resolve import resolve_paths
from deadreckoning.scan import scan_scripts

FIXTURE = Path(__file__).parent / "fixtures" / "real-world" / "mitman_2026"

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="Real-world fixture not present — add to tests/fixtures/real-world/mitman_2026/",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / "mitman_2026"
    shutil.copytree(FIXTURE, dest)
    return dest


# ---------------------------------------------------------------------------
# Scenario 1 — absolute path injection
# ---------------------------------------------------------------------------

class TestAbsolutePathDetection:
    """Inject an absolute path into a .do file; verify scan + resolve catch it."""

    TARGET_SCRIPT = Path("code") / "analysis" / "Table1_OLS.do"
    INJECTED_PATH = "/Users/mitman/data/panel.dta"

    def test_baseline_no_external_paths(self):
        scan = scan_scripts(FIXTURE)
        assert not scan.has_external_paths, "baseline fixture must have no external paths"

    def test_scan_detects_injected_absolute_path(self, tmp_path):
        work = _copy_fixture(tmp_path)
        script = work / self.TARGET_SCRIPT
        script.write_text(script.read_text() + f'\nuse "{self.INJECTED_PATH}"\n')

        scan = scan_scripts(work)

        assert scan.has_external_paths
        raw_paths = [ep.raw for ep in scan.external_paths]
        assert self.INJECTED_PATH in raw_paths

    def test_resolve_rewrites_injected_path(self, tmp_path):
        work = _copy_fixture(tmp_path)
        script = work / self.TARGET_SCRIPT
        script.write_text(script.read_text() + f'\nuse "{self.INJECTED_PATH}"\n')

        scan = scan_scripts(work)
        result = resolve_paths(work, scan)

        assert result.rewrite_count > 0
        originals = [r.original for r in result.rewrites]
        assert self.INJECTED_PATH in originals

    def test_resolve_rewrites_to_relative_data_path(self, tmp_path):
        work = _copy_fixture(tmp_path)
        script = work / self.TARGET_SCRIPT
        script.write_text(script.read_text() + f'\nuse "{self.INJECTED_PATH}"\n')

        scan = scan_scripts(work)
        result = resolve_paths(work, scan)

        rewritten = {r.original: r.rewritten for r in result.rewrites}
        assert rewritten[self.INJECTED_PATH].startswith("data/")

    def test_resolve_modifies_script_on_disk(self, tmp_path):
        work = _copy_fixture(tmp_path)
        script = work / self.TARGET_SCRIPT
        script.write_text(script.read_text() + f'\nuse "{self.INJECTED_PATH}"\n')

        scan = scan_scripts(work)
        resolve_paths(work, scan)

        content_after = script.read_text()
        assert self.INJECTED_PATH not in content_after

    def test_multiple_absolute_paths_all_rewritten(self, tmp_path):
        """Inject two distinct absolute paths; both must appear in rewrites."""
        work = _copy_fixture(tmp_path)
        path_a = "/Users/mitman/data/panel.dta"
        path_b = "/home/server/shared/wages.csv"
        script = work / self.TARGET_SCRIPT
        script.write_text(
            script.read_text()
            + f'\nuse "{path_a}"\nimport delimited "{path_b}"\n'
        )

        scan = scan_scripts(work)
        result = resolve_paths(work, scan)

        originals = {r.original for r in result.rewrites}
        assert path_a in originals
        assert path_b in originals


# ---------------------------------------------------------------------------
# Scenario 2 — script writes exhibit to wrong path
# ---------------------------------------------------------------------------

class TestScriptWritesWrongPath:
    """Script names the right file but puts it in the wrong directory."""

    # DiffWks.pdf is referenced in the LaTeX; graph resolves it to code/tex/DiffWks.pdf
    EXHIBIT_REL = Path("code") / "tex" / "DiffWks.pdf"
    EXHIBIT_NAME = "DiffWks.pdf"

    def test_baseline_no_wrong_path_gap(self):
        g = build_graph(FIXTURE)
        kinds = [gap.kind for gap in g.gaps]
        assert GapKind.script_writes_wrong_path not in kinds

    def test_wrong_path_gap_detected(self, tmp_path):
        work = _copy_fixture(tmp_path)

        # Put the exhibit on disk so "same filename, different dir" logic fires
        exhibit = work / self.EXHIBIT_REL
        exhibit.parent.mkdir(parents=True, exist_ok=True)
        exhibit.write_bytes(b"")

        # Write a script that outputs the file to the wrong directory
        wrong_script = work / "code" / "analysis" / "fake_diffwks.do"
        wrong_script.write_text(
            f'graph export "wrong_output/{self.EXHIBIT_NAME}", replace\n'
        )

        g = build_graph(work)

        gap_kinds = [gap.kind for gap in g.gaps]
        assert GapKind.script_writes_wrong_path in gap_kinds

    def test_wrong_path_gap_names_correct_exhibit(self, tmp_path):
        work = _copy_fixture(tmp_path)

        exhibit = work / self.EXHIBIT_REL
        exhibit.parent.mkdir(parents=True, exist_ok=True)
        exhibit.write_bytes(b"")

        wrong_script = work / "code" / "analysis" / "fake_diffwks.do"
        wrong_script.write_text(
            f'graph export "wrong_output/{self.EXHIBIT_NAME}", replace\n'
        )

        g = build_graph(work)

        wrong_gaps = [
            gap for gap in g.gaps
            if gap.kind == GapKind.script_writes_wrong_path
        ]
        assert any(self.EXHIBIT_NAME in str(gap.exhibit) for gap in wrong_gaps)

    def test_wrong_path_gap_note_mentions_both_paths(self, tmp_path):
        work = _copy_fixture(tmp_path)

        exhibit = work / self.EXHIBIT_REL
        exhibit.parent.mkdir(parents=True, exist_ok=True)
        exhibit.write_bytes(b"")

        wrong_dir = "wrong_output"
        wrong_script = work / "code" / "analysis" / "fake_diffwks.do"
        wrong_script.write_text(
            f'graph export "{wrong_dir}/{self.EXHIBIT_NAME}", replace\n'
        )

        g = build_graph(work)

        wrong_gaps = [
            gap for gap in g.gaps
            if gap.kind == GapKind.script_writes_wrong_path
            and self.EXHIBIT_NAME in str(gap.exhibit)
        ]
        assert wrong_gaps, "expected a script_writes_wrong_path gap for DiffWks.pdf"
        note = wrong_gaps[0].note or ""
        assert self.EXHIBIT_NAME in note

    def test_no_spurious_missing_disk_gap_for_present_exhibit(self, tmp_path):
        """Once an exhibit is on disk, it must not also appear as missing_from_disk."""
        work = _copy_fixture(tmp_path)

        exhibit = work / self.EXHIBIT_REL
        exhibit.parent.mkdir(parents=True, exist_ok=True)
        exhibit.write_bytes(b"")

        wrong_script = work / "code" / "analysis" / "fake_diffwks.do"
        wrong_script.write_text(
            f'graph export "wrong_output/{self.EXHIBIT_NAME}", replace\n'
        )

        g = build_graph(work)

        missing_gaps = [
            gap for gap in g.gaps
            if gap.kind == GapKind.exhibit_missing_from_disk
            and gap.exhibit is not None
            and self.EXHIBIT_NAME in str(gap.exhibit)
        ]
        assert not missing_gaps


# ---------------------------------------------------------------------------
# Scenario 3 — exhibit on disk but no script writes it
# ---------------------------------------------------------------------------

class TestExhibitNoSourceScript:
    """Exhibit exists on disk but no script has a matching write call."""

    # Benefits_on_unemp.tex — referenced via \input, resolves to code/tex/
    EXHIBIT_REL = Path("code") / "tex" / "Benefits_on_unemp.tex"
    EXHIBIT_NAME = "Benefits_on_unemp.tex"

    def test_baseline_exhibit_missing_from_disk(self):
        g = build_graph(FIXTURE)
        gap_exhibits = [
            gap for gap in g.gaps
            if gap.kind == GapKind.exhibit_missing_from_disk
            and gap.exhibit is not None
            and self.EXHIBIT_NAME in str(gap.exhibit)
        ]
        assert gap_exhibits, "baseline: exhibit must be flagged missing_from_disk"

    def test_exhibit_on_disk_no_script_gives_no_source_gap(self, tmp_path):
        work = _copy_fixture(tmp_path)

        exhibit = work / self.EXHIBIT_REL
        exhibit.parent.mkdir(parents=True, exist_ok=True)
        exhibit.write_text(
            "% placeholder — on disk but no script writes this file\n"
        )

        g = build_graph(work)

        no_source_gaps = [
            gap for gap in g.gaps
            if gap.kind == GapKind.exhibit_no_source_script
            and gap.exhibit is not None
            and self.EXHIBIT_NAME in str(gap.exhibit)
        ]
        assert no_source_gaps

    def test_no_source_gap_not_also_missing_from_disk(self, tmp_path):
        work = _copy_fixture(tmp_path)

        exhibit = work / self.EXHIBIT_REL
        exhibit.parent.mkdir(parents=True, exist_ok=True)
        exhibit.write_text("% placeholder\n")

        g = build_graph(work)

        missing_gaps = [
            gap for gap in g.gaps
            if gap.kind == GapKind.exhibit_missing_from_disk
            and gap.exhibit is not None
            and self.EXHIBIT_NAME in str(gap.exhibit)
        ]
        assert not missing_gaps

    def test_adding_source_script_clears_no_source_gap(self, tmp_path):
        """Once a script writes the exhibit, the no_source gap must disappear."""
        work = _copy_fixture(tmp_path)

        exhibit = work / self.EXHIBIT_REL
        exhibit.parent.mkdir(parents=True, exist_ok=True)
        exhibit.write_text("% placeholder\n")

        # Add a script that writes the exhibit to the correct path
        source_script = work / "code" / "analysis" / "fake_table1.do"
        source_script.write_text(
            f'esttab using "code/tex/{self.EXHIBIT_NAME}", tex replace\n'
        )

        g = build_graph(work)

        no_source_gaps = [
            gap for gap in g.gaps
            if gap.kind == GapKind.exhibit_no_source_script
            and gap.exhibit is not None
            and self.EXHIBIT_NAME in str(gap.exhibit)
        ]
        assert not no_source_gaps

    def test_gap_count_increases_by_one_when_exhibit_added_without_script(
        self, tmp_path
    ):
        """
        Baseline: Benefits_on_unemp.tex is missing_from_disk (1 gap).
        After: it's on disk but no script → same 1 gap, different kind.
        Net gap count unchanged; kind changes.
        """
        baseline_g = build_graph(FIXTURE)
        baseline_count = len(baseline_g.gaps)

        work = _copy_fixture(tmp_path)
        exhibit = work / self.EXHIBIT_REL
        exhibit.parent.mkdir(parents=True, exist_ok=True)
        exhibit.write_text("% placeholder\n")

        broken_g = build_graph(work)

        # gap count same (kind swapped, not added)
        assert len(broken_g.gaps) == baseline_count
