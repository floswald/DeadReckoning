"""Unit tests for GRAPH step and confidentiality gate."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from deadreckoning.confidentiality import check_restricted
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fixture_path(name: str) -> Path:
    return FIXTURES / name


# ---------------------------------------------------------------------------
# Working-copy safety
# ---------------------------------------------------------------------------


def test_build_graph_does_not_modify_original(tmp_path):
    """build_graph must be a pure read — original project unchanged after call."""
    src = fixture_path("r_no_lockfile")
    copy = tmp_path / "project"
    shutil.copytree(src, copy)

    # Snapshot checksums before
    before = {p.relative_to(copy): p.read_bytes() for p in copy.rglob("*") if p.is_file()}

    build_graph(copy)

    after = {p.relative_to(copy): p.read_bytes() for p in copy.rglob("*") if p.is_file()}
    assert before == after, "build_graph modified files in the project directory"


# ---------------------------------------------------------------------------
# Exhibit extraction
# ---------------------------------------------------------------------------


def test_exhibit_list_r_no_lockfile():
    """All three \\includegraphics / \\input references extracted from paper.tex."""
    graph = build_graph(fixture_path("r_no_lockfile"))
    names = {e.tex_path.name for e in graph.exhibits}
    assert "fig1.pdf" in names
    assert "fig3b.pdf" in names
    assert "tab1.tex" in names


def test_exhibit_list_already_clean():
    graph = build_graph(fixture_path("already_clean"))
    names = {e.tex_path.name for e in graph.exhibits}
    assert "fig1.pdf" in names
    assert "tab1.tex" in names


# ---------------------------------------------------------------------------
# Script-to-exhibit mapping
# ---------------------------------------------------------------------------


def test_tab1_mapped_to_tables_script():
    """tables.R writes tables/tab1.tex — must be linked as source."""
    graph = build_graph(fixture_path("r_no_lockfile"))
    tab1 = next(e for e in graph.exhibits if e.tex_path.name == "tab1.tex")
    assert tab1.source is not None, "tab1.tex has no source script"
    assert "tables.R" in tab1.source.script.name


def test_already_clean_all_exhibits_sourced():
    """Clean project: every exhibit must have a source script."""
    graph = build_graph(fixture_path("already_clean"))
    for exhibit in graph.exhibits:
        assert exhibit.source is not None, (
            f"{exhibit.tex_path.name} has no source script in already_clean fixture"
        )


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------


def test_fig3b_missing_from_disk_flagged():
    """fig3b.pdf not on disk and no script writes it → exhibit_missing_from_disk gap."""
    graph = build_graph(fixture_path("r_no_lockfile"))
    gap_kinds = {g.kind for g in graph.gaps}
    assert GapKind.exhibit_missing_from_disk in gap_kinds

    missing_gap = next(
        g for g in graph.gaps
        if g.kind == GapKind.exhibit_missing_from_disk
    )
    assert missing_gap.exhibit is not None
    assert missing_gap.exhibit.name == "fig3b.pdf"


def test_fig1_path_mismatch_flagged():
    """analysis.R writes fig1.pdf to cwd, LaTeX expects figures/fig1.pdf → path mismatch."""
    graph = build_graph(fixture_path("r_no_lockfile"))
    fig1 = next(e for e in graph.exhibits if e.tex_path.name == "fig1.pdf")
    # Source found via name-match heuristic, path_mismatch True
    assert fig1.source is not None
    assert fig1.path_mismatch is True

    gap_kinds = {g.kind for g in graph.gaps}
    assert GapKind.script_writes_wrong_path in gap_kinds


def test_inline_table_flagged():
    """Table typed directly into tex (no \\input{}) → inline_table gap."""
    graph = build_graph(fixture_path("r_no_lockfile"))
    gap_kinds = {g.kind for g in graph.gaps}
    assert GapKind.inline_table in gap_kinds


def test_inline_statistic_flagged():
    """'0.047*** (0.012)' in body text → inline_statistic gap."""
    graph = build_graph(fixture_path("r_no_lockfile"))
    gap_kinds = {g.kind for g in graph.gaps}
    assert GapKind.inline_statistic in gap_kinds


def test_already_clean_no_gaps():
    """Clean project must have zero gaps."""
    graph = build_graph(fixture_path("already_clean"))
    assert graph.gaps == [], f"Unexpected gaps in already_clean: {graph.gaps}"
    assert graph.is_complete


# ---------------------------------------------------------------------------
# Confidentiality detection
# ---------------------------------------------------------------------------


def test_restricted_filename_triggers_restricted_mode():
    status = check_restricted(fixture_path("restricted_data"))
    assert status.is_restricted is True
    assert status.trigger_path is not None
    assert "census_microdata_restricted" in status.trigger_path.name


def test_clean_project_not_restricted():
    status = check_restricted(fixture_path("already_clean"))
    assert status.is_restricted is False


def test_restricted_check_runs_before_graph(tmp_path):
    """
    Simulate the required ordering: check_restricted must be called first.
    If restricted, the caller must not proceed to build_graph on data files.
    This test verifies check_restricted returns before any file content is read
    by checking it works on a dir where data files are unreadable.
    """
    src = fixture_path("restricted_data")
    copy = tmp_path / "project"
    shutil.copytree(src, copy)

    # Make the data file unreadable
    dta = copy / "data" / "census_microdata_restricted.dta"
    dta.chmod(0o000)

    try:
        # check_restricted scans names only — must succeed even with unreadable file
        status = check_restricted(copy)
        assert status.is_restricted is True
    finally:
        dta.chmod(0o644)


# ---------------------------------------------------------------------------
# Data file extraction
# ---------------------------------------------------------------------------


def test_external_dropbox_path_detected():
    """Absolute Dropbox path in analysis.R must appear as external data file."""
    graph = build_graph(fixture_path("r_no_lockfile"))
    external = [df for df in graph.data_files if df.is_external]
    assert len(external) > 0, "No external data files detected"
    kinds = {df.external_kind for df in external}
    assert "dropbox" in kinds


def test_piped_write_lines_detected_as_exhibit_source(tmp_path):
    """
    readr::write_lines("out.tex") at the end of a magrittr pipe (data arg
    supplied by %>%, not passed explicitly) must be recognized as the
    script that produces out.tex -- not flagged as exhibit_missing_from_disk.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "tables").mkdir()
    (tmp_path / "code" / "tables.R").write_text(
        'x <- kableExtra::kbl(data.frame(a=1)) %>% readr::write_lines("tables/out.tex")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\input{tables/out.tex}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)
    exhibit = next(e for e in graph.exhibits if e.tex_path == Path("tables/out.tex"))
    assert exhibit.source is not None
    assert exhibit.source.script.name == "tables.R"


def test_modelsummary_detected_via_generic_extension_fallback(tmp_path):
    """
    modelsummary() (and any other unlisted table/figure writer) must be
    caught by the generic *.tex/*.pdf/... fallback, not just the named
    ggsave/write_lines/stargazer patterns.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "tables").mkdir()
    (tmp_path / "code" / "tables.R").write_text(
        'modelsummary(list(m1, m2), output = "tables/reg1.tex")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\input{tables/reg1.tex}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)
    exhibit = next(e for e in graph.exhibits if e.tex_path == Path("tables/reg1.tex"))
    assert exhibit.source is not None


def test_custom_wrapper_caught_by_generic_extension_fallback(tmp_path):
    """
    An unnamed custom table-writing wrapper (not ggsave/stargazer/etc) must
    still be caught via the generic extension fallback, since it's a real
    function call producing a recognized exhibit extension.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "tables").mkdir()
    (tmp_path / "code" / "tables.R").write_text(
        'my_custom_table_writer(results, "tables/custom.tex")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\input{tables/custom.tex}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


def test_file_exists_check_not_treated_as_write_call(tmp_path):
    """
    file.exists("fig1.pdf") is a read/check, not a write — must not be
    mistaken for the script that produces fig1.pdf (would silently hide a
    real reproducibility gap).
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "check.R").write_text(
        'if (!file.exists("figures/fig1.pdf")) stop("missing")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\includegraphics{figures/fig1.pdf}")
    graph = build_graph(tmp_path)
    assert any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


def test_r_fread_detected(tmp_path):
    """data.table::fread(...) must be recognized, not just base-R read.csv."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "tables.R").write_text(
        'library(data.table)\nf <- fread("data/tenders.csv")\n'
    )
    graph = build_graph(tmp_path)
    paths = {str(df.path) for df in graph.data_files}
    assert "data/tenders.csv" in paths


def test_stata_import_delimited_detected(tmp_path):
    """import delimited "path.csv" in a .do file must appear as a data file."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.do").write_text(
        'import delimited "data/survey.csv", clear\n'
        'import delimited using "data/secret_addon.csv", clear\n'
    )
    graph = build_graph(tmp_path)
    paths = {str(df.path) for df in graph.data_files}
    assert "data/survey.csv" in paths
    assert "data/secret_addon.csv" in paths


def test_stata_use_detected(tmp_path):
    """use "path.dta" in a .do file must appear as a data file."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.do").write_text('use "data/panel.dta", clear\n')
    graph = build_graph(tmp_path)
    paths = {str(df.path) for df in graph.data_files}
    assert "data/panel.dta" in paths


def test_python_read_csv_detected(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.py").write_text(
        'import pandas as pd\ndf = pd.read_csv("data/survey.csv")\n'
    )
    graph = build_graph(tmp_path)
    paths = {str(df.path) for df in graph.data_files}
    assert "data/survey.csv" in paths


def test_julia_csv_read_detected(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.jl").write_text(
        'using CSV\ndf = CSV.read("data/survey.csv", DataFrame)\n'
    )
    graph = build_graph(tmp_path)
    paths = {str(df.path) for df in graph.data_files}
    assert "data/survey.csv" in paths


def test_matlab_readtable_detected(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.m").write_text('t = readtable("data/survey.csv");\n')
    graph = build_graph(tmp_path)
    paths = {str(df.path) for df in graph.data_files}
    assert "data/survey.csv" in paths


def test_unknown_extension_yields_no_data_refs(tmp_path):
    """Scripts with unmapped extensions must not silently reuse R's regex."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.sas").write_text('proc import datafile="data/survey.csv";\n')
    graph = build_graph(tmp_path)
    assert graph.data_files == []


# ---------------------------------------------------------------------------
# Command-alias macros (\includetable{x} wrapping \input)
# ---------------------------------------------------------------------------


def test_command_alias_macro_resolves_to_real_exhibit(tmp_path):
    """
    \\newcommand{\\includetable}[1]{\\input{tables/#1.tex}} then
    \\includetable{table1} in the body must resolve to tables/table1.tex —
    a literal \\input{ scan alone would miss this entirely (common AEA/econ
    template idiom).
    """
    (tmp_path / "tables").mkdir()
    (tmp_path / "tables" / "table1.tex").write_text("1 & 2 \\\\")
    (tmp_path / "paper.tex").write_text(
        r"\newcommand{\includetable}[1]{\input{tables/#1.tex}}"
        "\n"
        r"\includetable{table1}"
    )
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)
    assert any(e.tex_path == Path("tables/table1.tex") for e in graph.exhibits)


def test_command_alias_macro_missing_target_flagged(tmp_path):
    """The alias mechanism must still flag genuinely missing exhibits."""
    (tmp_path / "paper.tex").write_text(
        r"\newcommand{\includetable}[1]{\input{tables/#1.tex}}"
        "\n"
        r"\includetable{table_nonexistent}"
    )
    graph = build_graph(tmp_path)
    assert any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


def test_alias_definition_body_not_treated_as_literal_exhibit(tmp_path):
    """
    The macro definition's own template text ("tables/#1.tex", containing a
    literal "#1") must not be scanned as a real \\input{} target — it would
    never exist on disk and would falsely appear as a missing exhibit.
    """
    (tmp_path / "tables").mkdir()
    (tmp_path / "tables" / "table1.tex").write_text("1 & 2 \\\\")
    (tmp_path / "paper.tex").write_text(
        r"\newcommand{\includetable}[1]{\input{tables/#1.tex}}"
        "\n"
        r"\includetable{table1}"
    )
    graph = build_graph(tmp_path)
    assert not any("#1" in str(e.tex_path) for e in graph.exhibits)


# ---------------------------------------------------------------------------
# \includestandalone, \includepdf
# ---------------------------------------------------------------------------


def test_includestandalone_detected(tmp_path):
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "diagram.tex").write_text(r"\tikz \draw (0,0) -- (1,1);")
    (tmp_path / "paper.tex").write_text(r"\includestandalone{figures/diagram}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


def test_includepdf_detected(tmp_path):
    (tmp_path / "appendix.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "paper.tex").write_text(r"\includepdf[pages=-]{appendix.pdf}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)
    assert any(e.tex_path == Path("appendix.pdf") for e in graph.exhibits)


def test_includepdf_missing_flagged(tmp_path):
    (tmp_path / "paper.tex").write_text(r"\includepdf[pages=-]{missing.pdf}")
    graph = build_graph(tmp_path)
    assert any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


# ---------------------------------------------------------------------------
# Direct data-to-table rendering (csvsimple, pgfplotstable, datatool) — the
# data file itself is "the exhibit", no intermediate script-written .tex.
# ---------------------------------------------------------------------------


def test_csvautotabular_present_data_not_flagged(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    (tmp_path / "paper.tex").write_text(r"\csvautotabular{data.csv}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)
    assert any(e.tex_path == Path("data.csv") for e in graph.exhibits)


def test_csvautotabular_missing_data_flagged(tmp_path):
    (tmp_path / "paper.tex").write_text(r"\csvautotabular{missing.csv}")
    graph = build_graph(tmp_path)
    assert any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


def test_csvreader_first_arg_is_file_trailing_args_ignored(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    (tmp_path / "paper.tex").write_text(
        r"\csvreader{data.csv}{a=\colA,b=\colB}{\colA\ \colB}"
    )
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


def test_pgfplotstabletypeset_detected(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    (tmp_path / "paper.tex").write_text(r"\pgfplotstabletypeset{data.csv}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


def test_dtlloaddb_second_arg_is_file(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    (tmp_path / "paper.tex").write_text(r"\DTLloaddb{mydata}{data.csv}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)
    assert any(e.tex_path == Path("data.csv") for e in graph.exhibits)


def test_dtlloaddb_missing_data_flagged(tmp_path):
    (tmp_path / "paper.tex").write_text(r"\DTLloaddb{mydata}{missing.csv}")
    graph = build_graph(tmp_path)
    assert any(g.kind == GapKind.exhibit_missing_from_disk for g in graph.gaps)


def test_csvautotabular_sourced_when_script_writes_same_csv(tmp_path):
    """
    If a script writes the exact CSV that csvautotabular renders, the
    existing exact-path write-call sourcing must pick it up unchanged —
    no new architecture needed for this case.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "make_data.R").write_text(
        'write.csv(df, "data/results.csv")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\csvautotabular{data/results.csv}")
    graph = build_graph(tmp_path)
    assert not any(g.kind == GapKind.exhibit_no_source_script for g in graph.gaps)
    exhibit = next(e for e in graph.exhibits if e.tex_path == Path("data/results.csv"))
    assert exhibit.source is not None


def test_script_writes_exposed_on_graph(tmp_path):
    """
    DependencyGraph.script_writes must expose every write call found, not
    just the ones matched to an exhibit — provenance tracing needs the full
    list (including intermediate-data writes like saveRDS) to walk
    multi-hop chains.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "tables").mkdir()
    (tmp_path / "code" / "clean.R").write_text('saveRDS(x, "data/clean.Rds")\n')
    (tmp_path / "code" / "tables.R").write_text(
        'x <- readRDS("data/clean.Rds")\nwriteLines(x, "tables/out.tex")\n'
    )
    (tmp_path / "paper.tex").write_text(r"\input{tables/out.tex}")
    graph = build_graph(tmp_path)
    written_names = {w.written_path.name for w in graph.script_writes}
    assert "clean.Rds" in written_names
    assert "out.tex" in written_names
