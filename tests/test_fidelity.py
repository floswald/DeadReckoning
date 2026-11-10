"""
Unit tests for check_exhibit_fidelity() — the "ran clean, exit 0, file
exists, but the numbers no longer match what was published" check.

Synthetic multi-stage fixture (no R/Stata/Julia execution — this tests the
graph-wiring and localizer logic, not native script execution):

    clean.R        -> panel.csv
    export.do      -> input_data_from_2.csv
    combine.jl      reads both -> output/Table3.tex

Mirrors the demo's coauthor-drift scenario: scripts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from deadreckoning.graph import build_graph
from deadreckoning.runner import FidelityResult, SuspectFile, check_exhibit_fidelity, group_fidelity_mismatches


def _write_chain(root: Path) -> None:
    (root / "code").mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)

    (root / "paper.tex").write_text(
        r"""\documentclass{article}
\begin{document}
\input{output/Table3.tex}
\end{document}
"""
    )

    (root / "code" / "clean.R").write_text(
        'write.csv(data.frame(region_id=1:2, revenue=c(100, 200)), "panel.csv", row.names=FALSE)\n'
    )
    (root / "code" / "export.do").write_text(
        'outsheet region_id weight using "input_data_from_2.csv", comma replace\n'
    )
    (root / "code" / "combine.jl").write_text(
        'using CSV\n'
        'panel = CSV.read("panel.csv")\n'
        'weights = CSV.read("input_data_from_2.csv")\n'
        'open("output/Table3.tex", "w") do io\n'
        '    write(io, "placeholder")\n'
        'end\n'
    )

    (root / "panel.csv").write_text("region_id,revenue\n1,100\n2,200\n")
    (root / "input_data_from_2.csv").write_text("region_id,weight\n1,0.34\n2,0.66\n")
    (root / "output" / "Table3.tex").write_text("published: 160.00")


@pytest.fixture
def chain_project(tmp_path):
    _write_chain(tmp_path)
    return tmp_path


def test_matches_reference_when_content_unchanged(chain_project):
    graph = build_graph(chain_project)
    reference = (chain_project / "output" / "Table3.tex").read_bytes()

    result = check_exhibit_fidelity(chain_project, graph, Path("output/Table3.tex"), reference)

    assert result.matches_reference
    assert result.suspects == []


def test_diverges_and_localizes_via_mtime_without_git(chain_project):
    graph = build_graph(chain_project)
    reference = (chain_project / "output" / "Table3.tex").read_bytes()

    # Simulate the coauthor's silent re-export: input_data_from_2.csv changes,
    # Table3.tex is then regenerated with different content.
    (chain_project / "input_data_from_2.csv").write_text(
        "region_id,weight\n1,0.339872451\n2,0.660127549\n"
    )
    (chain_project / "output" / "Table3.tex").write_text("regenerated: 159.87")

    result = check_exhibit_fidelity(chain_project, graph, Path("output/Table3.tex"), reference)

    assert not result.matches_reference
    assert result.reference_hash != result.regenerated_hash
    assert any(s.path == Path("input_data_from_2.csv") for s in result.suspects)
    mtime_suspect = next(s for s in result.suspects if s.path == Path("input_data_from_2.csv"))
    assert mtime_suspect.evidence == "mtime"
    assert mtime_suspect.confidence == "low"
    assert "not reliable provenance" in mtime_suspect.detail

    # panel.csv is also reported (it's upstream too) — the localizer lists
    # every upstream file with its timestamp so the author can eyeball which
    # date looks suspicious; it doesn't claim certainty about which one.
    assert any(s.path == Path("panel.csv") for s in result.suspects)


def test_diverges_and_localizes_via_git_when_repo_present(chain_project):
    subprocess.run(["git", "init", "-q"], cwd=chain_project, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.com"], cwd=chain_project, check=True)
    subprocess.run(["git", "config", "user.name", "Author One"], cwd=chain_project, check=True)
    subprocess.run(["git", "add", "-A"], cwd=chain_project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=chain_project, check=True)

    graph = build_graph(chain_project)
    reference = (chain_project / "output" / "Table3.tex").read_bytes()

    (chain_project / "input_data_from_2.csv").write_text(
        "region_id,weight\n1,0.339872451\n2,0.660127549\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=chain_project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "author2 re-export after Stata upgrade"], cwd=chain_project, check=True)
    (chain_project / "output" / "Table3.tex").write_text("regenerated: 159.87")

    result = check_exhibit_fidelity(chain_project, graph, Path("output/Table3.tex"), reference)

    assert not result.matches_reference
    suspect = next(s for s in result.suspects if s.path == Path("input_data_from_2.csv"))
    assert suspect.evidence == "git"
    assert suspect.confidence == "high"
    assert "author2 re-export after Stata upgrade" not in suspect.detail  # detail is commit metadata, not message
    assert "Author One" in suspect.detail


def test_missing_exhibit_file_reports_mismatch(chain_project):
    graph = build_graph(chain_project)
    reference = b"published: 160.00"
    (chain_project / "output" / "Table3.tex").unlink()

    result = check_exhibit_fidelity(chain_project, graph, Path("output/Table3.tex"), reference)

    assert not result.matches_reference
    assert result.regenerated_hash is None


# ---------------------------------------------------------------------------
# group_fidelity_mismatches — fan-out aggregation over several results
# ---------------------------------------------------------------------------


def _suspect(path: str, evidence: str = "git") -> SuspectFile:
    return SuspectFile(path=Path(path), evidence=evidence, confidence="high", detail="d")


def test_multiple_exhibits_sharing_one_suspect_group_together():
    shared = Path("data/raw/FRA_base.dta")
    results = [
        FidelityResult(exhibit=Path("figure1.pdf"), matches_reference=False, suspects=[_suspect(str(shared))]),
        FidelityResult(exhibit=Path("figureA2a.pdf"), matches_reference=False, suspects=[_suspect(str(shared))]),
        FidelityResult(exhibit=Path("figureA2b.pdf"), matches_reference=False, suspects=[_suspect(str(shared))]),
    ]

    grouped = group_fidelity_mismatches(results)

    assert set(grouped.keys()) == {shared}
    assert set(grouped[shared]) == {Path("figure1.pdf"), Path("figureA2a.pdf"), Path("figureA2b.pdf")}


def test_mismatched_exhibit_with_no_suspects_does_not_appear():
    results = [
        FidelityResult(exhibit=Path("orphan.pdf"), matches_reference=False, suspects=[]),
    ]

    grouped = group_fidelity_mismatches(results)

    assert grouped == {}


def test_clean_matching_exhibit_contributes_nothing():
    results = [
        FidelityResult(exhibit=Path("figureA3.pdf"), matches_reference=True, suspects=[]),
    ]

    grouped = group_fidelity_mismatches(results)

    assert grouped == {}


def test_different_suspects_kept_in_separate_groups():
    results = [
        FidelityResult(exhibit=Path("a.pdf"), matches_reference=False, suspects=[_suspect("input1.csv")]),
        FidelityResult(exhibit=Path("b.pdf"), matches_reference=False, suspects=[_suspect("input2.csv")]),
    ]

    grouped = group_fidelity_mismatches(results)

    assert grouped == {Path("input1.csv"): [Path("a.pdf")], Path("input2.csv"): [Path("b.pdf")]}
