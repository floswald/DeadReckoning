"""
ASK step tests — ask.py

All fast (no R/Stata/Docker). Uses tmp_path fixtures and minimal
DependencyGraph / EnvSpec objects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.ask import (
    _extract_path,
    _parse_date,
    all_blocking_answered,
    apply_responses,
    identify_questions,
    parse_author_responses,
    run_ask_step,
    write_questions_file,
)
from deadreckoning.models import (
    AuthorQuestion,
    AuthorResponse,
    DependencyGraph,
    EnvSpec,
    Exhibit,
    Gap,
    GapKind,
    PinMethod,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_ROOT = Path("/tmp/test_project")


def _empty_graph() -> DependencyGraph:
    return DependencyGraph(project_root=_ROOT)


def _graph_with_gap(kind: GapKind, exhibit: str = "figures/fig1.pdf") -> DependencyGraph:
    gap = Gap(kind=kind, exhibit=Path(exhibit))
    ex = Exhibit(tex_path=Path(exhibit), exists_on_disk=False, source=None)
    return DependencyGraph(project_root=_ROOT, exhibits=[ex], gaps=[gap])


def _low_conf_env(language: str = "R") -> EnvSpec:
    return EnvSpec(language=language, confidence=0.2, snapshot_date=None)


def _high_conf_env() -> EnvSpec:
    return EnvSpec(
        language="R", confidence=0.95,
        language_version="4.4.0",
        pin_method=PinMethod.lockfile,
        snapshot_date="2024-01-01",
    )


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


def test_parse_date_iso():
    assert _parse_date("2023-03") == "2023-03-01"


def test_parse_date_iso_full():
    assert _parse_date("2023-03-15") == "2023-03-15"


def test_parse_date_month_year():
    assert _parse_date("March 2023") == "2023-03-01"


def test_parse_date_month_abbr():
    assert _parse_date("ran it in Mar 2022") == "2022-03-01"


def test_parse_date_mm_yyyy():
    assert _parse_date("03/2023") == "2023-03-01"


def test_parse_date_bare_year():
    assert _parse_date("sometime in 2021") == "2021-01-01"


def test_parse_date_none():
    assert _parse_date("I don't remember") is None


# ---------------------------------------------------------------------------
# _extract_path
# ---------------------------------------------------------------------------


def test_extract_path_backtick():
    assert _extract_path("see `code/figures.R` for details") == "code/figures.R"


def test_extract_path_bare():
    assert _extract_path("the script is code/figures.R I think") == "code/figures.R"


def test_extract_path_none():
    assert _extract_path("I have no idea") is None


# ---------------------------------------------------------------------------
# identify_questions
# ---------------------------------------------------------------------------


def test_no_questions_for_clean_graph():
    qs = identify_questions(_empty_graph())
    assert qs == []


def test_question_for_no_source_script():
    graph = _graph_with_gap(GapKind.exhibit_no_source_script)
    qs = identify_questions(graph)
    assert any(q.gap_kind == GapKind.exhibit_no_source_script.value for q in qs)


def test_question_for_missing_from_disk():
    graph = _graph_with_gap(GapKind.exhibit_missing_from_disk)
    qs = identify_questions(graph)
    assert any(q.gap_kind == GapKind.exhibit_missing_from_disk.value for q in qs)


def test_question_for_missing_input():
    graph = _graph_with_gap(GapKind.input_missing_from_disk, exhibit="data/ghost.csv")
    qs = identify_questions(graph)
    assert any(q.gap_kind == GapKind.input_missing_from_disk.value for q in qs)


def test_missing_input_is_blocking():
    graph = _graph_with_gap(GapKind.input_missing_from_disk, exhibit="data/ghost.csv")
    qs = identify_questions(graph)
    responses = [AuthorResponse(exhibit=q.exhibit, answer="") for q in qs]
    assert not all_blocking_answered(qs, responses)
    answered = [AuthorResponse(exhibit=q.exhibit, answer="restricted, author has it") for q in qs]
    assert all_blocking_answered(qs, answered)


def test_apply_responses_records_missing_input_answer():
    graph = _graph_with_gap(GapKind.input_missing_from_disk, exhibit="data/ghost.csv")
    qs = identify_questions(graph)
    responses = [AuthorResponse(exhibit=q.exhibit, answer="Restricted — contact author.") for q in qs]
    updated_graph, _ = apply_responses(graph, _high_conf_env(), qs, responses)
    gap = next(g for g in updated_graph.gaps if g.kind == GapKind.input_missing_from_disk)
    assert "Restricted" in (gap.note or "")


def test_question_for_compiled_language_no_build_script():
    gap = Gap(kind=GapKind.compiled_language_no_build_script, exhibit=None,
              location="compiled_language_build", note="found code/sim.f90")
    graph = DependencyGraph(project_root=_ROOT, gaps=[gap])
    qs = identify_questions(graph)
    assert any(q.gap_kind == GapKind.compiled_language_no_build_script.value for q in qs)


def test_compiled_language_question_is_blocking():
    gap = Gap(kind=GapKind.compiled_language_no_build_script, exhibit=None,
              location="compiled_language_build", note="found code/sim.f90")
    graph = DependencyGraph(project_root=_ROOT, gaps=[gap])
    qs = identify_questions(graph)
    unanswered = [AuthorResponse(exhibit=q.exhibit, answer="") for q in qs]
    assert not all_blocking_answered(qs, unanswered)
    answered = [
        AuthorResponse(exhibit=q.exhibit, answer="gfortran code/sim.f90 -o code/sim && ./code/sim")
        for q in qs
    ]
    assert all_blocking_answered(qs, answered)


def test_apply_responses_sets_compile_command_on_env_spec():
    gap = Gap(kind=GapKind.compiled_language_no_build_script, exhibit=None,
              location="compiled_language_build", note="found code/sim.f90")
    graph = DependencyGraph(project_root=_ROOT, gaps=[gap])
    qs = identify_questions(graph)
    command = "gfortran code/sim.f90 -o code/sim && ./code/sim"
    responses = [AuthorResponse(exhibit=q.exhibit, answer=command) for q in qs]
    _, updated_env = apply_responses(graph, _high_conf_env(), qs, responses)
    assert updated_env.compile_command == command


def test_no_duplicate_for_same_exhibit():
    gap1 = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("figures/fig1.pdf"))
    gap2 = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("figures/fig1.pdf"))
    graph = DependencyGraph(project_root=_ROOT, exhibits=[], gaps=[gap1, gap2])
    qs = identify_questions(graph)
    exhibit_qs = [q for q in qs if q.gap_kind == GapKind.exhibit_no_source_script.value]
    assert len(exhibit_qs) == 1


def test_question_for_low_conf_env():
    qs = identify_questions(_empty_graph(), env_spec=_low_conf_env())
    assert any(q.gap_kind == "env_last_run_date" for q in qs)


def test_no_env_question_for_high_conf():
    qs = identify_questions(_empty_graph(), env_spec=_high_conf_env())
    assert not any(q.gap_kind == "env_last_run_date" for q in qs)


def test_stata_license_question():
    env = EnvSpec(language="Stata", confidence=0.3)
    qs = identify_questions(_empty_graph(), env_spec=env)
    assert any(q.gap_kind == "proprietary_license" for q in qs)


def test_matlab_license_question():
    env = EnvSpec(language="MATLAB", confidence=0.25)
    qs = identify_questions(_empty_graph(), env_spec=env)
    assert any(q.gap_kind == "proprietary_license" for q in qs)


def test_r_no_license_question():
    qs = identify_questions(_empty_graph(), env_spec=_high_conf_env())
    assert not any(q.gap_kind == "proprietary_license" for q in qs)


def test_question_contains_exhibit_name():
    graph = _graph_with_gap(GapKind.exhibit_no_source_script, "figures/fig3b.pdf")
    qs = identify_questions(graph)
    script_qs = [q for q in qs if q.gap_kind == GapKind.exhibit_no_source_script.value]
    assert any("fig3b.pdf" in q.question for q in script_qs)


# ---------------------------------------------------------------------------
# write_questions_file / parse_author_responses
# ---------------------------------------------------------------------------


def test_write_creates_file(tmp_path):
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When did you last run?")]
    path = write_questions_file(tmp_path, qs)
    assert path.exists()
    assert "QUESTIONS.md" in str(path)


def test_write_contains_answer_prompt(tmp_path):
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    write_questions_file(tmp_path, qs)
    text = (tmp_path / "QUESTIONS.md").read_text()
    assert "> Answer:" in text


def test_write_contains_question_text(tmp_path):
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When did you last run?")]
    write_questions_file(tmp_path, qs)
    text = (tmp_path / "QUESTIONS.md").read_text()
    assert "When did you last run?" in text


def test_write_multiple_questions(tmp_path):
    qs = [
        AuthorQuestion(gap_kind="env_last_run_date", question="When?"),
        AuthorQuestion(gap_kind="proprietary_license", question="Stata license?"),
    ]
    write_questions_file(tmp_path, qs)
    text = (tmp_path / "QUESTIONS.md").read_text()
    # Each question gets exactly one "> Answer:" line
    assert text.count("> Answer: ") == 2


def test_parse_empty_answers(tmp_path):
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    write_questions_file(tmp_path, qs)
    responses = parse_author_responses(tmp_path, qs)
    assert len(responses) == 1
    assert responses[0].answer == ""


def test_parse_filled_answer(tmp_path):
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    write_questions_file(tmp_path, qs)
    text = (tmp_path / "QUESTIONS.md").read_text()
    text = text.replace("> Answer: ", "> Answer: March 2023")
    (tmp_path / "QUESTIONS.md").write_text(text)
    responses = parse_author_responses(tmp_path, qs)
    assert responses[0].answer == "March 2023"


def test_parse_positional_matching(tmp_path):
    qs = [
        AuthorQuestion(gap_kind="env_last_run_date", question="When?"),
        AuthorQuestion(gap_kind="proprietary_license", question="License?"),
    ]
    write_questions_file(tmp_path, qs)
    text = (tmp_path / "QUESTIONS.md").read_text()
    # Answer second question only
    lines = text.splitlines()
    answer_lines = [i for i, l in enumerate(lines) if l.startswith("> Answer:")]
    lines[answer_lines[1]] = "> Answer: yes SE edition"
    (tmp_path / "QUESTIONS.md").write_text("\n".join(lines))
    responses = parse_author_responses(tmp_path, qs)
    assert responses[0].answer == ""
    assert "SE edition" in responses[1].answer


def test_parse_extracts_data_path(tmp_path):
    qs = [AuthorQuestion(
        gap_kind=GapKind.exhibit_no_source_script.value,
        exhibit="figures/fig1.pdf",
        question="Which script?",
    )]
    write_questions_file(tmp_path, qs)
    text = (tmp_path / "QUESTIONS.md").read_text()
    text = text.replace("> Answer: ", "> Answer: `code/figures.R`")
    (tmp_path / "QUESTIONS.md").write_text(text)
    responses = parse_author_responses(tmp_path, qs)
    assert responses[0].data_path == "code/figures.R"


def test_parse_no_file_returns_empty(tmp_path):
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    responses = parse_author_responses(tmp_path, qs)
    assert responses == []


# ---------------------------------------------------------------------------
# all_blocking_answered
# ---------------------------------------------------------------------------


def test_blocking_answered_no_questions():
    assert all_blocking_answered([], []) is True


def test_blocking_answered_non_blocking_only():
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    resps = [AuthorResponse(answer="")]
    assert all_blocking_answered(qs, resps) is True


def test_blocking_not_answered():
    qs = [AuthorQuestion(
        gap_kind=GapKind.exhibit_no_source_script.value,
        exhibit="fig1.pdf",
        question="Which script?",
    )]
    resps = [AuthorResponse(answer="")]
    assert all_blocking_answered(qs, resps) is False


def test_blocking_answered():
    qs = [AuthorQuestion(
        gap_kind=GapKind.exhibit_no_source_script.value,
        exhibit="fig1.pdf",
        question="Which script?",
    )]
    resps = [AuthorResponse(answer="code/figures.R")]
    assert all_blocking_answered(qs, resps) is True


# ---------------------------------------------------------------------------
# apply_responses
# ---------------------------------------------------------------------------


def test_apply_env_date_from_answer():
    env = _low_conf_env()
    graph = _empty_graph()
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    resps = [AuthorResponse(answer="March 2023")]
    _, updated_env = apply_responses(graph, env, qs, resps)
    assert updated_env.snapshot_date == "2023-03-01"


def test_apply_does_not_overwrite_existing_date():
    env = EnvSpec(language="R", confidence=0.2, snapshot_date="2022-06-01")
    graph = _empty_graph()
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    resps = [AuthorResponse(answer="March 2023")]
    _, updated_env = apply_responses(graph, env, qs, resps)
    assert updated_env.snapshot_date == "2022-06-01"


def test_apply_records_script_in_gap_note():
    graph = _graph_with_gap(GapKind.exhibit_no_source_script, "figures/fig1.pdf")
    env = _high_conf_env()
    qs = [AuthorQuestion(
        gap_kind=GapKind.exhibit_no_source_script.value,
        exhibit="figures/fig1.pdf",
        question="Which script?",
    )]
    resps = [AuthorResponse(answer="code/figures.R", exhibit="figures/fig1.pdf")]
    updated_graph, _ = apply_responses(graph, env, qs, resps)
    gap = updated_graph.gaps[0]
    assert "code/figures.R" in (gap.note or "")


def test_apply_ignores_empty_answers():
    env = _low_conf_env()
    graph = _empty_graph()
    qs = [AuthorQuestion(gap_kind="env_last_run_date", question="When?")]
    resps = [AuthorResponse(answer="")]
    _, updated_env = apply_responses(graph, env, qs, resps)
    assert updated_env.snapshot_date is None


# ---------------------------------------------------------------------------
# run_ask_step
# ---------------------------------------------------------------------------


def test_run_ask_no_questions_no_halt(tmp_path):
    graph = _empty_graph()
    env = _high_conf_env()
    qa, needs_input, _, _ = run_ask_step(tmp_path, graph, env)
    assert needs_input is False
    assert qa.questions == []


def test_run_ask_blocking_gap_halts(tmp_path):
    graph = _graph_with_gap(GapKind.exhibit_no_source_script)
    env = _high_conf_env()
    qa, needs_input, _, _ = run_ask_step(tmp_path, graph, env)
    assert needs_input is True
    assert (tmp_path / "QUESTIONS.md").exists()


def test_run_ask_writes_questions_file(tmp_path):
    graph = _graph_with_gap(GapKind.exhibit_no_source_script)
    env = _high_conf_env()
    run_ask_step(tmp_path, graph, env)
    assert (tmp_path / "QUESTIONS.md").exists()


def test_run_ask_second_run_reads_responses(tmp_path):
    graph = _graph_with_gap(GapKind.exhibit_no_source_script, "figures/fig1.pdf")
    env = _high_conf_env()
    # First run — writes file
    run_ask_step(tmp_path, graph, env)
    # Author fills in answer
    text = (tmp_path / "QUESTIONS.md").read_text()
    text = text.replace("> Answer: ", "> Answer: code/figures.R")
    (tmp_path / "QUESTIONS.md").write_text(text)
    # Second run — reads answer, no longer blocks
    qa, needs_input, _, _ = run_ask_step(tmp_path, graph, env)
    assert needs_input is False
    assert qa.responses[0].answer == "code/figures.R"


def test_run_ask_unanswered_blocking_still_halts(tmp_path):
    graph = _graph_with_gap(GapKind.exhibit_no_source_script)
    env = _high_conf_env()
    run_ask_step(tmp_path, graph, env)
    # Second run without filling in answer
    qa, needs_input, _, _ = run_ask_step(tmp_path, graph, env)
    assert needs_input is True


def test_run_ask_low_conf_env_question_nonblocking(tmp_path):
    graph = _empty_graph()
    env = _low_conf_env()
    # Low-confidence env triggers question but should NOT block (non-blocking kind)
    qa, needs_input, _, _ = run_ask_step(tmp_path, graph, env)
    assert needs_input is False  # env_last_run_date is advisory, not blocking
    assert (tmp_path / "QUESTIONS.md").exists()


def test_run_ask_env_date_applied_on_second_run(tmp_path):
    graph = _empty_graph()
    env = _low_conf_env()
    run_ask_step(tmp_path, graph, env)
    text = (tmp_path / "QUESTIONS.md").read_text()
    text = text.replace("> Answer: ", "> Answer: March 2023")
    (tmp_path / "QUESTIONS.md").write_text(text)
    _, _, _, updated_env = run_ask_step(tmp_path, graph, env)
    assert updated_env.snapshot_date == "2023-03-01"


# ---------------------------------------------------------------------------
# exhibit_copied_but_no_source_script — a copy/rename edge was found, but
# its original is unexplained (see graph.py's copy/rename provenance work)
# ---------------------------------------------------------------------------


def test_question_for_copied_but_no_source():
    graph = _graph_with_gap(GapKind.exhibit_copied_but_no_source_script)
    qs = identify_questions(graph)
    assert any(q.gap_kind == GapKind.exhibit_copied_but_no_source_script.value for q in qs)


def test_copied_but_no_source_is_blocking(tmp_path):
    graph = _graph_with_gap(GapKind.exhibit_copied_but_no_source_script)
    env = _high_conf_env()
    qa, needs_input, _, _ = run_ask_step(tmp_path, graph, env)
    assert needs_input is True


def test_copied_but_no_source_answer_unblocks(tmp_path):
    graph = _graph_with_gap(GapKind.exhibit_copied_but_no_source_script, "figures/fig1.pdf")
    env = _high_conf_env()
    run_ask_step(tmp_path, graph, env)
    text = (tmp_path / "QUESTIONS.md").read_text()
    text = text.replace("> Answer: ", "> Answer: code/plotter.jl line 42")
    (tmp_path / "QUESTIONS.md").write_text(text)
    qa, needs_input, updated_graph, _ = run_ask_step(tmp_path, graph, env)
    assert needs_input is False
    gap = next(g for g in updated_graph.gaps if g.kind == GapKind.exhibit_copied_but_no_source_script)
    assert "code/plotter.jl line 42" in (gap.note or "")


# ---------------------------------------------------------------------------
# LLM gap hints — mocked dispatcher, no network. Confirms the hint is
# clearly labeled and additive, never replacing the deterministic question.
# ---------------------------------------------------------------------------


class _StubHintDispatcher:
    """Duck-typed GapHintDispatcher — avoids needing a real Anthropic mock
    client for pure ask.py-wiring tests."""
    def __init__(self, hint: str | None) -> None:
        self._hint = hint
        self.calls: list[GapKind] = []

    def propose_hint(self, gap, graph, project_root):
        self.calls.append(gap.kind)
        return self._hint


def test_hint_appended_to_context_when_available():
    graph = _graph_with_gap(GapKind.exhibit_no_source_script)
    dispatcher = _StubHintDispatcher("Probably code/plot.R line 12 (medium confidence).")
    qs = identify_questions(graph, hint_dispatcher=dispatcher)
    q = next(q for q in qs if q.gap_kind == GapKind.exhibit_no_source_script.value)
    assert "Probably code/plot.R line 12" in (q.context or "")
    assert "unverified" in (q.context or "").lower()
    assert "proposed by Claude" in (q.context or "")


def test_no_hint_appended_when_dispatcher_returns_none():
    graph = _graph_with_gap(GapKind.exhibit_no_source_script)
    dispatcher = _StubHintDispatcher(None)
    qs = identify_questions(graph, hint_dispatcher=dispatcher)
    q = next(q for q in qs if q.gap_kind == GapKind.exhibit_no_source_script.value)
    assert q.context is None  # unchanged from the no-dispatcher baseline


def test_no_hint_appended_without_dispatcher():
    """Baseline: hint_dispatcher=None (default) must behave exactly as
    before this feature existed — no hint text, no dispatcher call."""
    graph = _graph_with_gap(GapKind.exhibit_no_source_script)
    qs = identify_questions(graph)
    q = next(q for q in qs if q.gap_kind == GapKind.exhibit_no_source_script.value)
    assert q.context is None


def test_hint_dispatcher_called_once_per_blocking_gap():
    gap1 = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"))
    gap2 = Gap(kind=GapKind.exhibit_copied_but_no_source_script, exhibit=Path("fig2.pdf"))
    ex1 = Exhibit(tex_path=Path("fig1.pdf"), exists_on_disk=False, source=None)
    ex2 = Exhibit(tex_path=Path("fig2.pdf"), exists_on_disk=False, source=None)
    graph = DependencyGraph(project_root=_ROOT, exhibits=[ex1, ex2], gaps=[gap1, gap2])

    dispatcher = _StubHintDispatcher("a lead")
    identify_questions(graph, hint_dispatcher=dispatcher)
    assert dispatcher.calls == [GapKind.exhibit_no_source_script, GapKind.exhibit_copied_but_no_source_script]


def test_run_ask_step_default_dispatcher_is_noop_without_api_key(tmp_path, monkeypatch):
    """run_ask_step's default (no hint_dispatcher passed) must not crash and
    must not change behavior when there's no ANTHROPIC_API_KEY — the exact
    environment every other test in this file already runs under."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    graph = _graph_with_gap(GapKind.exhibit_no_source_script)
    env = _high_conf_env()
    qa, needs_input, _, _ = run_ask_step(tmp_path, graph, env)
    assert needs_input is True
    assert qa.questions[0].context is None
