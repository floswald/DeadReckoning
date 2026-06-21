"""
CLEAN step tests — clean.py

All fast (no R/Stata/Docker). Uses tmp_path fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.clean import (
    _file_kind,
    _reachable_data,
    _reachable_scripts,
    apply_cleanup_choices,
    find_orphans,
    parse_cleanup_choices,
    run_clean_step,
    write_cleanup_file,
)
from deadreckoning.models import (
    CleanChoice,
    DataFile,
    DependencyGraph,
    Exhibit,
    OrphanFile,
    ScriptWritesExhibit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a project directory with the given file paths and contents."""
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _empty_graph(root: Path) -> DependencyGraph:
    return DependencyGraph(project_root=root)


def _graph_with_exhibit(root: Path, script: Path, exhibit: Path) -> DependencyGraph:
    src = ScriptWritesExhibit(
        script=script,
        write_call="ggsave",
        line=5,
        written_path=exhibit,
    )
    ex = Exhibit(tex_path=exhibit, exists_on_disk=True, source=src)
    return DependencyGraph(project_root=root, exhibits=[ex])


# ---------------------------------------------------------------------------
# _file_kind
# ---------------------------------------------------------------------------


def test_file_kind_script():
    assert _file_kind(Path("code/analysis.R")) == "script"


def test_file_kind_script_py():
    assert _file_kind(Path("code/analysis.py")) == "script"


def test_file_kind_data_csv():
    assert _file_kind(Path("data/raw.csv")) == "data"


def test_file_kind_data_dta():
    assert _file_kind(Path("data/raw.dta")) == "data"


def test_file_kind_output_pdf():
    assert _file_kind(Path("figures/fig1.pdf")) == "output"


def test_file_kind_output_png():
    assert _file_kind(Path("figures/fig1.png")) == "output"


def test_file_kind_other():
    assert _file_kind(Path("code/utils.c")) == "other"


# ---------------------------------------------------------------------------
# _reachable_scripts
# ---------------------------------------------------------------------------


def test_reachable_includes_exhibit_source(tmp_path):
    root = _make_project(tmp_path, {
        "code/run.R": 'source("code/analysis.R")\n',
        "code/analysis.R": "ggsave('figures/fig1.pdf')\n",
        "figures/fig1.pdf": "",
    })
    analysis = root / "code" / "analysis.R"
    graph = _graph_with_exhibit(root, analysis, root / "figures" / "fig1.pdf")
    reachable = _reachable_scripts(root, graph)
    assert analysis.resolve() in reachable


def test_reachable_expands_to_caller(tmp_path):
    root = _make_project(tmp_path, {
        "code/run.R": 'source("code/analysis.R")\n',
        "code/analysis.R": "ggsave('figures/fig1.pdf')\n",
        "figures/fig1.pdf": "",
    })
    analysis = root / "code" / "analysis.R"
    run = root / "code" / "run.R"
    graph = _graph_with_exhibit(root, analysis, root / "figures" / "fig1.pdf")
    reachable = _reachable_scripts(root, graph)
    # "analysis" appears in run.R → run.R is reachable
    assert run.resolve() in reachable


def test_reachable_excludes_unreferenced_script(tmp_path):
    root = _make_project(tmp_path, {
        "code/run.R": 'source("code/analysis.R")\n',
        "code/analysis.R": "ggsave('figures/fig1.pdf')\n",
        "code/scratch.R": "x <- 1\n",   # not mentioned anywhere
        "figures/fig1.pdf": "",
    })
    analysis = root / "code" / "analysis.R"
    scratch = root / "code" / "scratch.R"
    graph = _graph_with_exhibit(root, analysis, root / "figures" / "fig1.pdf")
    reachable = _reachable_scripts(root, graph)
    assert scratch.resolve() not in reachable


# ---------------------------------------------------------------------------
# _reachable_data
# ---------------------------------------------------------------------------


def test_reachable_data_local(tmp_path):
    (tmp_path / "data").mkdir()
    df = DataFile(path=tmp_path / "data" / "raw.csv", exists_on_disk=True)
    graph = DependencyGraph(project_root=tmp_path, data_files=[df])
    rd = _reachable_data(tmp_path, graph)
    assert (tmp_path / "data" / "raw.csv").resolve() in rd


def test_reachable_data_excludes_external(tmp_path):
    df = DataFile(path=Path("/Users/jsmith/Dropbox/raw.csv"), exists_on_disk=False, is_external=True)
    graph = DependencyGraph(project_root=tmp_path, data_files=[df])
    rd = _reachable_data(tmp_path, graph)
    assert Path("/Users/jsmith/Dropbox/raw.csv").resolve() not in rd


# ---------------------------------------------------------------------------
# find_orphans
# ---------------------------------------------------------------------------


def test_find_orphans_empty_project(tmp_path):
    graph = _empty_graph(tmp_path)
    orphans = find_orphans(tmp_path, graph)
    assert orphans == []


def test_find_orphans_no_orphans_when_all_reachable(tmp_path):
    root = _make_project(tmp_path, {
        "code/analysis.R": "ggsave('figures/fig1.pdf')\n",
        "data/raw.csv": "a,b\n1,2\n",
        "figures/fig1.pdf": "%PDF",
    })
    analysis = root / "code" / "analysis.R"
    data_csv = root / "data" / "raw.csv"
    fig = root / "figures" / "fig1.pdf"
    df = DataFile(path=data_csv, exists_on_disk=True)
    graph = DependencyGraph(
        project_root=root,
        exhibits=[Exhibit(tex_path=fig, exists_on_disk=True,
                          source=ScriptWritesExhibit(script=analysis, write_call="ggsave", line=1, written_path=fig))],
        data_files=[df],
    )
    orphans = find_orphans(root, graph)
    # data/raw.csv is reachable; figures/fig1.pdf is output so could be orphan
    # but analysis.R sources it — no orphan scripts
    script_orphans = [o for o in orphans if o.kind == "script"]
    assert script_orphans == []


def test_find_orphans_flags_unreferenced_script(tmp_path):
    root = _make_project(tmp_path, {
        "code/analysis.R": "ggsave('figures/fig1.pdf')\n",
        "code/scratch.R": "# old code\n",
        "figures/fig1.pdf": "%PDF",
    })
    analysis = root / "code" / "analysis.R"
    fig = root / "figures" / "fig1.pdf"
    graph = DependencyGraph(
        project_root=root,
        exhibits=[Exhibit(tex_path=fig, exists_on_disk=True,
                          source=ScriptWritesExhibit(script=analysis, write_call="ggsave", line=1, written_path=fig))],
    )
    orphans = find_orphans(root, graph)
    paths = [str(o.path) for o in orphans]
    assert any("scratch.R" in p for p in paths)


def test_find_orphans_flags_unreferenced_data(tmp_path):
    root = _make_project(tmp_path, {
        "code/analysis.R": "ggsave('figures/fig1.pdf')\n",
        "data/needed.csv": "a,b\n",
        "data/stale.csv": "x,y\n",
        "figures/fig1.pdf": "%PDF",
    })
    analysis = root / "code" / "analysis.R"
    fig = root / "figures" / "fig1.pdf"
    needed = root / "data" / "needed.csv"
    df = DataFile(path=needed, exists_on_disk=True)
    graph = DependencyGraph(
        project_root=root,
        exhibits=[Exhibit(tex_path=fig, exists_on_disk=True,
                          source=ScriptWritesExhibit(script=analysis, write_call="ggsave", line=1, written_path=fig))],
        data_files=[df],
    )
    orphans = find_orphans(root, graph)
    paths = [str(o.path) for o in orphans]
    assert any("stale.csv" in p for p in paths)
    assert not any("needed.csv" in p for p in paths)


def test_find_orphans_skips_tex_files(tmp_path):
    root = _make_project(tmp_path, {
        "paper.tex": "\\documentclass{article}\n",
        "appendix.tex": "Appendix text.\n",
    })
    graph = _empty_graph(root)
    orphans = find_orphans(root, graph)
    assert not any(".tex" in str(o.path) for o in orphans)


def test_find_orphans_skips_readme(tmp_path):
    root = _make_project(tmp_path, {"README.md": "# Project\n"})
    graph = _empty_graph(root)
    assert find_orphans(root, graph) == []


def test_find_orphans_skips_hidden_dirs(tmp_path):
    root = _make_project(tmp_path, {".git/config": "[core]\n", "data/raw.csv": "a,b\n"})
    graph = _empty_graph(root)
    orphans = find_orphans(root, graph)
    assert not any(".git" in str(o.path) for o in orphans)


def test_find_orphans_orphan_kind_correct(tmp_path):
    root = _make_project(tmp_path, {
        "code/scratch.R": "x <- 1\n",
        "data/old.csv": "a,b\n",
        "figures/old.pdf": "%PDF",
    })
    graph = _empty_graph(root)
    orphans = find_orphans(root, graph)
    kinds = {o.kind for o in orphans}
    assert "script" in kinds
    assert "data" in kinds
    assert "output" in kinds


# ---------------------------------------------------------------------------
# write_cleanup_file / parse_cleanup_choices
# ---------------------------------------------------------------------------


def test_write_cleanup_creates_file(tmp_path):
    orphans = [OrphanFile(path=Path("code/scratch.R"), kind="script")]
    path = write_cleanup_file(tmp_path, orphans)
    assert path.exists()
    assert path.name == "CLEANUP.md"


def test_write_cleanup_contains_action_prompt(tmp_path):
    orphans = [OrphanFile(path=Path("code/scratch.R"), kind="script")]
    write_cleanup_file(tmp_path, orphans)
    text = (tmp_path / "CLEANUP.md").read_text()
    assert "> Action:" in text


def test_write_cleanup_default_action_keep(tmp_path):
    orphans = [OrphanFile(path=Path("code/scratch.R"), kind="script")]
    write_cleanup_file(tmp_path, orphans)
    text = (tmp_path / "CLEANUP.md").read_text()
    assert "> Action: keep" in text


def test_write_cleanup_one_action_per_orphan(tmp_path):
    orphans = [
        OrphanFile(path=Path("code/scratch.R"), kind="script"),
        OrphanFile(path=Path("data/old.csv"), kind="data"),
    ]
    write_cleanup_file(tmp_path, orphans)
    text = (tmp_path / "CLEANUP.md").read_text()
    # Count lines that START with "> Action:" (not the intro sentence)
    action_lines = [l for l in text.splitlines() if l.startswith("> Action:")]
    assert len(action_lines) == 2


def test_parse_default_is_keep(tmp_path):
    orphans = [OrphanFile(path=Path("code/scratch.R"), kind="script")]
    write_cleanup_file(tmp_path, orphans)
    choices = parse_cleanup_choices(tmp_path, orphans)
    assert choices[0].action == "keep"


def test_parse_delete_choice(tmp_path):
    orphans = [OrphanFile(path=Path("code/scratch.R"), kind="script")]
    write_cleanup_file(tmp_path, orphans)
    text = (tmp_path / "CLEANUP.md").read_text()
    text = text.replace("> Action: keep", "> Action: delete")
    (tmp_path / "CLEANUP.md").write_text(text)
    choices = parse_cleanup_choices(tmp_path, orphans)
    assert choices[0].action == "delete"


def test_parse_archive_choice(tmp_path):
    orphans = [OrphanFile(path=Path("code/scratch.R"), kind="script")]
    write_cleanup_file(tmp_path, orphans)
    text = (tmp_path / "CLEANUP.md").read_text()
    text = text.replace("> Action: keep", "> Action: archive")
    (tmp_path / "CLEANUP.md").write_text(text)
    choices = parse_cleanup_choices(tmp_path, orphans)
    assert choices[0].action == "archive"


def test_parse_positional_matching(tmp_path):
    orphans = [
        OrphanFile(path=Path("code/scratch.R"), kind="script"),
        OrphanFile(path=Path("data/old.csv"), kind="data"),
    ]
    write_cleanup_file(tmp_path, orphans)
    text = (tmp_path / "CLEANUP.md").read_text()
    # Only change second action
    lines = text.splitlines()
    action_lines = [i for i, l in enumerate(lines) if l.startswith("> Action:")]
    lines[action_lines[1]] = "> Action: delete"
    (tmp_path / "CLEANUP.md").write_text("\n".join(lines))
    choices = parse_cleanup_choices(tmp_path, orphans)
    assert choices[0].action == "keep"
    assert choices[1].action == "delete"


def test_parse_no_file_defaults_to_keep(tmp_path):
    orphans = [OrphanFile(path=Path("code/scratch.R"), kind="script")]
    choices = parse_cleanup_choices(tmp_path, orphans)
    assert choices[0].action == "keep"


# ---------------------------------------------------------------------------
# apply_cleanup_choices
# ---------------------------------------------------------------------------


def test_apply_delete_removes_file(tmp_path):
    script = tmp_path / "code" / "scratch.R"
    script.parent.mkdir()
    script.write_text("x <- 1\n")
    choices = [CleanChoice(path=Path("code/scratch.R"), kind="script", action="delete")]
    apply_cleanup_choices(tmp_path, choices)
    assert not script.exists()


def test_apply_archive_moves_file(tmp_path):
    script = tmp_path / "code" / "scratch.R"
    script.parent.mkdir()
    script.write_text("x <- 1\n")
    choices = [CleanChoice(path=Path("code/scratch.R"), kind="script", action="archive")]
    apply_cleanup_choices(tmp_path, choices)
    assert not script.exists()
    assert (tmp_path / "_archive" / "code" / "scratch.R").exists()


def test_apply_keep_leaves_file(tmp_path):
    script = tmp_path / "code" / "scratch.R"
    script.parent.mkdir()
    script.write_text("x <- 1\n")
    choices = [CleanChoice(path=Path("code/scratch.R"), kind="script", action="keep")]
    apply_cleanup_choices(tmp_path, choices)
    assert script.exists()


def test_apply_result_counts(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "a.R").write_text("x\n")
    (tmp_path / "code" / "b.R").write_text("y\n")
    (tmp_path / "code" / "c.R").write_text("z\n")
    choices = [
        CleanChoice(path=Path("code/a.R"), kind="script", action="delete"),
        CleanChoice(path=Path("code/b.R"), kind="script", action="archive"),
        CleanChoice(path=Path("code/c.R"), kind="script", action="keep"),
    ]
    result = apply_cleanup_choices(tmp_path, choices)
    assert len(result.deleted) == 1
    assert len(result.archived) == 1
    assert len(result.kept) == 1
    assert result.total_cleaned == 2


def test_apply_skips_missing_file(tmp_path):
    choices = [CleanChoice(path=Path("code/gone.R"), kind="script", action="delete")]
    result = apply_cleanup_choices(tmp_path, choices)
    assert result.deleted == []


# ---------------------------------------------------------------------------
# run_clean_step
# ---------------------------------------------------------------------------


def test_run_clean_no_orphans(tmp_path):
    graph = _empty_graph(tmp_path)
    result, needs_review = run_clean_step(tmp_path, graph)
    assert result.orphans == []
    assert needs_review is False


def test_run_clean_writes_cleanup_md_first_run(tmp_path):
    root = _make_project(tmp_path, {"code/scratch.R": "x <- 1\n"})
    graph = _empty_graph(root)
    result, needs_review = run_clean_step(root, graph)
    assert (root / "CLEANUP.md").exists()
    assert needs_review is True


def test_run_clean_applies_choices_second_run(tmp_path):
    root = _make_project(tmp_path, {"code/scratch.R": "x <- 1\n"})
    graph = _empty_graph(root)
    # First run — writes CLEANUP.md with default "keep"
    run_clean_step(root, graph)
    # Author changes to delete
    text = (root / "CLEANUP.md").read_text()
    text = text.replace("> Action: keep", "> Action: delete")
    (root / "CLEANUP.md").write_text(text)
    # Second run — applies
    result, needs_review = run_clean_step(root, graph)
    assert needs_review is False
    assert result.apply is not None
    assert len(result.apply.deleted) == 1
    assert not (root / "code" / "scratch.R").exists()


def test_run_clean_pipeline_nonblocking(tmp_path):
    """CLEAN never halts the pipeline — needs_review is advisory only."""
    root = _make_project(tmp_path, {"code/scratch.R": "x <- 1\n"})
    graph = _empty_graph(root)
    # Even first run (needs_review=True) is non-blocking at pipeline level
    result, needs_review = run_clean_step(root, graph)
    # needs_review is True but this is advisory — orchestrator does NOT halt
    assert result.orphans  # found something
    assert needs_review is True  # advisory flag set


def test_run_clean_archive_preserves_structure(tmp_path):
    root = _make_project(tmp_path, {"code/utils/scratch.R": "x <- 1\n"})
    graph = _empty_graph(root)
    run_clean_step(root, graph)
    text = (root / "CLEANUP.md").read_text()
    text = text.replace("> Action: keep", "> Action: archive")
    (root / "CLEANUP.md").write_text(text)
    run_clean_step(root, graph)
    assert (root / "_archive" / "code" / "utils" / "scratch.R").exists()
