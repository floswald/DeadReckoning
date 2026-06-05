"""
Tests for real-world LaTeX structural patterns beyond the basic r_no_lockfile case.
Each test covers one common pattern that breaks naive exhibit extraction.
"""

from __future__ import annotations

from pathlib import Path

from deadreckoning.graph import build_graph, _collect_tex_macros, _collect_graphicspath

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# \def\macro{path} and \renewcommand  (latex_def_macro fixture)
# ---------------------------------------------------------------------------


def test_def_macro_collected():
    """\def\figs{figures} must be collected as a path macro."""
    tex_files = sorted((FIXTURES / "latex_def_macro").rglob("*.tex"))
    macros = _collect_tex_macros(tex_files)
    assert "figs" in macros, f"\\def\\figs not collected. Got: {macros}"
    assert macros["figs"] == "figures"


def test_def_macro_exhibit_resolved():
    """\\includegraphics{\\figs/fig1.pdf} must resolve to figures/fig1.pdf on disk."""
    graph = build_graph(FIXTURES / "latex_def_macro")
    names = {e.tex_path.name for e in graph.exhibits}
    assert "fig1.pdf" in names
    assert "tab1.tex" in names


def test_def_macro_exhibits_exist_on_disk():
    graph = build_graph(FIXTURES / "latex_def_macro")
    missing = [e for e in graph.exhibits if not e.exists_on_disk]
    assert missing == [], f"Missing: {[str(e.tex_path) for e in missing]}"


def test_def_macro_fig1_sourced():
    """fig1.pdf written by analysis.R via ggsave — must be linked."""
    graph = build_graph(FIXTURES / "latex_def_macro")
    fig1 = next(e for e in graph.exhibits if e.tex_path.name == "fig1.pdf")
    assert fig1.source is not None, "fig1.pdf has no source script"
    assert "analysis.R" in fig1.source.script.name


# ---------------------------------------------------------------------------
# \graphicspath{{figures/}{tables/}}  (latex_graphicspath fixture)
# ---------------------------------------------------------------------------


def test_graphicspath_collected():
    """\graphicspath entries must be collected."""
    tex_files = sorted((FIXTURES / "latex_graphicspath").rglob("*.tex"))
    gp = _collect_graphicspath(tex_files)
    entries = [entry for _, entry in gp]
    assert "figures/" in entries, f"figures/ not in graphicspath entries: {entries}"


def test_graphicspath_bare_ref_resolved():
    """\\includegraphics{{fig1.pdf}} with no path prefix resolved via graphicspath."""
    graph = build_graph(FIXTURES / "latex_graphicspath")
    names = {e.tex_path.name for e in graph.exhibits}
    assert "fig1.pdf" in names


def test_graphicspath_exhibits_exist_on_disk():
    graph = build_graph(FIXTURES / "latex_graphicspath")
    missing = [e for e in graph.exhibits if not e.exists_on_disk]
    assert missing == [], f"Missing after graphicspath resolution: {[str(e.tex_path) for e in missing]}"


def test_graphicspath_fig1_sourced():
    graph = build_graph(FIXTURES / "latex_graphicspath")
    fig1 = next(e for e in graph.exhibits if e.tex_path.name == "fig1.pdf")
    assert fig1.source is not None, "fig1.pdf has no source script"


# ---------------------------------------------------------------------------
# Extension-less refs  (latex_no_extension fixture)
# ---------------------------------------------------------------------------


def test_no_extension_pdf_found():
    """\\includegraphics{figures/fig1} — no suffix — must find figures/fig1.pdf."""
    graph = build_graph(FIXTURES / "latex_no_extension")
    fig1 = next(
        (e for e in graph.exhibits if "fig1" in e.tex_path.stem), None
    )
    assert fig1 is not None, "fig1 exhibit not found at all"
    assert fig1.exists_on_disk, "fig1.pdf not found on disk via extension search"


def test_no_extension_png_found():
    """\\includegraphics{figures/fig2} — no suffix — must find figures/fig2.png."""
    graph = build_graph(FIXTURES / "latex_no_extension")
    fig2 = next(
        (e for e in graph.exhibits if "fig2" in e.tex_path.stem), None
    )
    assert fig2 is not None, "fig2 exhibit not found at all"
    assert fig2.exists_on_disk, "fig2.png not found on disk via extension search"


def test_no_extension_no_false_missing():
    """No exhibit should show as missing — both figures exist with different extensions."""
    graph = build_graph(FIXTURES / "latex_no_extension")
    missing = [e for e in graph.exhibits if not e.exists_on_disk]
    assert missing == [], f"Exhibits falsely missing: {[str(e.tex_path) for e in missing]}"


def test_no_extension_sourced():
    """Both extension-less figures must be traced to analysis.R."""
    graph = build_graph(FIXTURES / "latex_no_extension")
    for exhibit in graph.exhibits:
        assert exhibit.source is not None, (
            f"{exhibit.tex_path.name} not traced to a script"
        )
