"""
DELIVER step tests — deliver.py

All fast (no R/Stata/Docker). Uses tmp_path fixtures.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from deadreckoning.deliver import (
    _iso_to_human,
    assemble_package,
    generate_delivery_report,
    generate_readme,
    run_deliver_step,
    write_delivery_report,
    write_readme,
)
from deadreckoning.models import (
    AuthorQA,
    AuthorQuestion,
    AuthorResponse,
    CleanApplyResult,
    CleanResult,
    DataFile,
    DeliverResult,
    DependencyGraph,
    EnvSpec,
    Exhibit,
    GapKind,
    OrphanFile,
    PackageSpec,
    PinMethod,
    ScriptWritesExhibit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROOT = Path("/tmp/test_deliver_project")


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _simple_graph(root: Path) -> DependencyGraph:
    script = root / "code" / "analysis.R"
    exhibit = root / "figures" / "fig1.pdf"
    src = ScriptWritesExhibit(script=script, write_call="ggsave", line=5, written_path=exhibit)
    ex = Exhibit(tex_path=exhibit, exists_on_disk=True, source=src)
    return DependencyGraph(project_root=root, exhibits=[ex], script_order=[script])


def _r_env(ver: str = "4.4.0") -> EnvSpec:
    return EnvSpec(
        language="R",
        language_version=ver,
        packages=[PackageSpec(name="ggplot2", version="3.5.0"),
                  PackageSpec(name="renv", version="1.0.3")],
        pin_method=PinMethod.lockfile,
        snapshot_date="2024-03-01",
        confidence=0.95,
    )


def _empty_graph(root: Path = _ROOT) -> DependencyGraph:
    return DependencyGraph(project_root=root)


# ---------------------------------------------------------------------------
# _iso_to_human
# ---------------------------------------------------------------------------


def test_iso_to_human_march():
    assert _iso_to_human("2023-03-01") == "March 2023"


def test_iso_to_human_december():
    assert _iso_to_human("2023-12-01") == "December 2023"


def test_iso_to_human_invalid():
    # Shouldn't crash on bad input — returns input unchanged
    result = _iso_to_human("not-a-date")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_readme
# ---------------------------------------------------------------------------


def test_readme_contains_language(tmp_path):
    graph = _simple_graph(tmp_path)
    env = _r_env()
    text = generate_readme(graph, env)
    assert "R" in text
    assert "4.4.0" in text


def test_readme_contains_packages(tmp_path):
    graph = _simple_graph(tmp_path)
    env = _r_env()
    text = generate_readme(graph, env)
    assert "ggplot2" in text
    assert "3.5.0" in text


def test_readme_contains_exhibit(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_readme(graph, _r_env())
    assert "fig1.pdf" in text


def test_readme_contains_script(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_readme(graph, _r_env())
    assert "analysis.R" in text


def test_readme_has_instructions_section(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_readme(graph, _r_env())
    assert "Instructions" in text


def test_readme_has_data_availability_section(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_readme(graph, _r_env())
    assert "Data Availability" in text


def test_readme_has_computational_requirements(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_readme(graph, _r_env())
    assert "Computational Requirements" in text


def test_readme_external_data_listed(tmp_path):
    df = DataFile(
        path=Path("/Users/jsmith/Dropbox/raw.csv"),
        exists_on_disk=False,
        is_external=True,
        external_kind="dropbox",
    )
    graph = DependencyGraph(project_root=tmp_path, data_files=[df])
    text = generate_readme(graph, _r_env())
    assert "raw.csv" in text
    assert "dropbox" in text


def test_readme_no_external_data_note(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_readme(graph, _r_env())
    assert "included in the `data/` directory" in text


def test_readme_rscript_command_for_r(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_readme(graph, _r_env())
    assert "Rscript" in text


def test_readme_python_command_for_python(tmp_path):
    script = tmp_path / "code" / "run.py"
    exhibit = tmp_path / "figures" / "fig1.pdf"
    src = ScriptWritesExhibit(script=script, write_call="savefig", line=1, written_path=exhibit)
    ex = Exhibit(tex_path=exhibit, exists_on_disk=True, source=src)
    graph = DependencyGraph(project_root=tmp_path, exhibits=[ex], script_order=[script])
    env = EnvSpec(language="Python", language_version="3.11", confidence=0.8)
    text = generate_readme(graph, env)
    assert "python" in text.lower()


def test_readme_snapshot_date_shown(tmp_path):
    graph = _simple_graph(tmp_path)
    env = _r_env()
    text = generate_readme(graph, env)
    assert "March 2024" in text


def test_readme_truncates_long_package_list(tmp_path):
    pkgs = [PackageSpec(name=f"pkg{i}", version="1.0") for i in range(40)]
    env = EnvSpec(language="R", packages=pkgs, confidence=0.8)
    graph = _empty_graph(tmp_path)
    text = generate_readme(graph, env)
    assert "more" in text  # truncation notice


def test_readme_open_questions_mentioned(tmp_path):
    graph = _simple_graph(tmp_path)
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    resps: list[AuthorResponse] = []  # unanswered
    qa = AuthorQA(questions=qs, responses=resps)
    text = generate_readme(graph, _r_env(), qa=qa)
    assert "Open Questions" in text or "question" in text.lower()


def test_readme_no_open_questions_section_when_all_answered(tmp_path):
    graph = _simple_graph(tmp_path)
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    resps = [AuthorResponse(answer="March 2023")]
    qa = AuthorQA(questions=qs, responses=resps)
    text = generate_readme(graph, _r_env(), qa=qa)
    assert "Open Questions" not in text


# ---------------------------------------------------------------------------
# write_readme
# ---------------------------------------------------------------------------


def test_write_readme_creates_file(tmp_path):
    graph = _simple_graph(tmp_path)
    path = write_readme(tmp_path, graph, _r_env())
    assert path.exists()
    assert path.name == "README.md"


def test_write_readme_skips_if_exists(tmp_path):
    existing = tmp_path / "README.md"
    existing.write_text("# My existing README\n")
    graph = _simple_graph(tmp_path)
    write_readme(tmp_path, graph, _r_env(), overwrite=False)
    assert existing.read_text() == "# My existing README\n"


def test_write_readme_overwrites_when_flag_set(tmp_path):
    existing = tmp_path / "README.md"
    existing.write_text("# My existing README\n")
    graph = _simple_graph(tmp_path)
    write_readme(tmp_path, graph, _r_env(), overwrite=True)
    assert "# My existing README" not in existing.read_text()


# ---------------------------------------------------------------------------
# generate_delivery_report
# ---------------------------------------------------------------------------


def test_report_contains_exhibit_count(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_delivery_report(graph, _r_env())
    assert "1 exhibit" in text


def test_report_native_ok(tmp_path):
    graph = _empty_graph(tmp_path)
    text = generate_delivery_report(graph, _r_env(), native_ok=True)
    assert "✓" in text


def test_report_native_fail(tmp_path):
    graph = _empty_graph(tmp_path)
    text = generate_delivery_report(graph, _r_env(), native_ok=False)
    assert "✗" in text


def test_report_no_issues_when_clean(tmp_path):
    graph = _simple_graph(tmp_path)
    text = generate_delivery_report(graph, _r_env(), native_ok=True, container_ok=True)
    assert "None." in text


def test_report_lists_graph_gap(tmp_path):
    from deadreckoning.models import Gap
    gap = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("figures/fig2.pdf"))
    graph = DependencyGraph(project_root=tmp_path, gaps=[gap])
    text = generate_delivery_report(graph, _r_env())
    assert "fig2.pdf" in text


def test_report_contains_env_confidence(tmp_path):
    graph = _empty_graph(tmp_path)
    text = generate_delivery_report(graph, _r_env())
    assert "95%" in text


def test_report_clean_result_shown(tmp_path):
    graph = _empty_graph(tmp_path)
    clean = CleanResult(
        orphans=[OrphanFile(path=Path("code/scratch.R"), kind="script")],
        apply=CleanApplyResult(deleted=[Path("code/scratch.R")]),
    )
    text = generate_delivery_report(graph, _r_env(), clean=clean)
    assert "orphan" in text.lower()


def test_report_env_note_shown(tmp_path):
    graph = _empty_graph(tmp_path)
    env = EnvSpec(language="MATLAB", confidence=0.3, note="Requires MathWorks license")
    text = generate_delivery_report(graph, env)
    assert "Requires MathWorks license" in text


def test_report_unanswered_question_flagged(tmp_path):
    graph = _empty_graph(tmp_path)
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    qa = AuthorQA(questions=qs, responses=[])
    text = generate_delivery_report(graph, _r_env(), qa=qa)
    assert "Unanswered" in text or "unanswered" in text.lower()


# ---------------------------------------------------------------------------
# write_delivery_report
# ---------------------------------------------------------------------------


def test_write_report_creates_file(tmp_path):
    graph = _simple_graph(tmp_path)
    path = write_delivery_report(tmp_path, graph, _r_env())
    assert path.exists()
    assert path.name == "DELIVERY_REPORT.md"


# ---------------------------------------------------------------------------
# assemble_package
# ---------------------------------------------------------------------------


def test_assemble_creates_zip(tmp_path):
    proj = _make_project(tmp_path / "project", {
        "code/analysis.R": "x <- 1\n",
        "data/raw.csv": "a,b\n",
        "README.md": "# Hello\n",
    })
    dest, inc, exc = assemble_package(proj)
    assert dest.exists()
    assert dest.suffix == ".zip"


def test_assemble_includes_code_and_data(tmp_path):
    proj = _make_project(tmp_path / "project", {
        "code/analysis.R": "x <- 1\n",
        "data/raw.csv": "a,b\n",
    })
    dest, inc, exc = assemble_package(proj)
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
    assert any("analysis.R" in n for n in names)
    assert any("raw.csv" in n for n in names)


def test_assemble_excludes_git(tmp_path):
    proj = _make_project(tmp_path / "project", {
        "code/analysis.R": "x\n",
        ".git/config": "[core]\n",
    })
    dest, inc, exc = assemble_package(proj)
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
    assert not any(".git" in n for n in names)
    assert exc >= 1


def test_assemble_excludes_cleanup_md(tmp_path):
    proj = _make_project(tmp_path / "project", {
        "code/analysis.R": "x\n",
        "CLEANUP.md": "# cleanup\n",
        "QUESTIONS.md": "# qs\n",
        "AGENT_REPORT.md": "# report\n",
    })
    dest, inc, exc = assemble_package(proj)
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
    assert "CLEANUP.md" not in names
    assert "QUESTIONS.md" not in names
    assert "AGENT_REPORT.md" not in names


def test_assemble_excludes_pycache(tmp_path):
    proj = _make_project(tmp_path / "project", {
        "code/analysis.py": "x=1\n",
        "__pycache__/analysis.cpython-311.pyc": "\x00",
    })
    dest, inc, exc = assemble_package(proj)
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
    assert not any("__pycache__" in n for n in names)


def test_assemble_custom_dest(tmp_path):
    proj = _make_project(tmp_path / "project", {"code/run.R": "x\n"})
    custom = tmp_path / "output.zip"
    dest, inc, exc = assemble_package(proj, custom)
    assert dest == custom
    assert dest.exists()


# ---------------------------------------------------------------------------
# run_deliver_step
# ---------------------------------------------------------------------------


def test_run_deliver_writes_readme(tmp_path):
    graph = _simple_graph(tmp_path)
    result = run_deliver_step(tmp_path, graph, _r_env())
    assert result.readme_path is not None
    assert result.readme_path.exists()


def test_run_deliver_writes_report(tmp_path):
    graph = _simple_graph(tmp_path)
    result = run_deliver_step(tmp_path, graph, _r_env())
    assert result.report_path is not None
    assert result.report_path.exists()


def test_run_deliver_no_zip_by_default(tmp_path):
    graph = _simple_graph(tmp_path)
    result = run_deliver_step(tmp_path, graph, _r_env())
    assert result.package_path is None


def test_run_deliver_zip_when_flag_set(tmp_path):
    graph = _simple_graph(tmp_path)
    result = run_deliver_step(tmp_path, graph, _r_env(), assemble_zip=True)
    assert result.package_path is not None
    assert result.package_path.exists()
    assert result.included_count > 0


def test_run_deliver_skips_existing_readme(tmp_path):
    existing = tmp_path / "README.md"
    existing.write_text("# Author's own README\n")
    graph = _simple_graph(tmp_path)
    run_deliver_step(tmp_path, graph, _r_env())
    assert existing.read_text() == "# Author's own README\n"
