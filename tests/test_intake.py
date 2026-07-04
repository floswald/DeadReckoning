"""Tests for the pre-pipeline intake questionnaire and confrontation logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.ask import _contradiction_questions, identify_questions
from deadreckoning.intake import _parse_bool, _parse_list, questionnaire
from deadreckoning.models import (
    DependencyGraph,
    EnvSpec,
    Gap,
    GapKind,
    IntakeResult,
    PinMethod,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(gaps=None, project_root=None) -> DependencyGraph:
    return DependencyGraph(
        project_root=Path(project_root or "/tmp/proj"),
        gaps=gaps or [],
    )


def _make_env(language="R", confidence=0.3, snapshot_date=None) -> EnvSpec:
    return EnvSpec(
        language=language,
        confidence=confidence,
        snapshot_date=snapshot_date,
        pin_method=PinMethod.unknown,
    )


def _make_intake(**kwargs) -> IntakeResult:
    return IntakeResult(**kwargs)


# ---------------------------------------------------------------------------
# IntakeResult model
# ---------------------------------------------------------------------------


class TestIntakeResultModel:
    def test_defaults_all_none(self):
        i = IntakeResult()
        assert i.paper_tex_path is None
        assert i.last_run_date is None
        assert i.languages_claimed == []
        assert i.restricted_data is None

    def test_fields_round_trip(self):
        i = IntakeResult(
            last_run_date="March 2023",
            languages_claimed=["R", "Stata"],
            has_stata_license=True,
            restricted_data=False,
            target_journal="AEA",
        )
        assert i.last_run_date == "March 2023"
        assert "Stata" in i.languages_claimed
        assert i.has_stata_license is True
        assert i.target_journal == "AEA"


# ---------------------------------------------------------------------------
# questionnaire() — non-interactive
# ---------------------------------------------------------------------------


class TestQuestionnaire:
    def test_non_interactive_restricted_yes(self):
        result = questionnaire(answers={"restricted_data": "yes"})
        assert result.restricted_data is True

    def test_non_interactive_restricted_no(self):
        result = questionnaire(answers={"restricted_data": "no"})
        assert result.restricted_data is False

    def test_non_interactive_full(self):
        answers = {
            "restricted_data": "no",
            "paper_tex_path": "paper/main.tex",
            "code_root": "code/",
            "data_root": "data/",
            "last_run_date": "March 2023",
            "languages_claimed": "R, Stata",
            "has_stata_license": "yes",
            "runtime_estimate": "hours",
            "target_journal": "JPE",
        }
        result = questionnaire(answers=answers)
        assert result.restricted_data is False
        assert result.paper_tex_path == "paper/main.tex"
        assert result.code_root == "code/"
        assert result.data_root == "data/"
        assert result.last_run_date == "March 2023"
        assert "R" in result.languages_claimed
        assert "Stata" in result.languages_claimed
        assert result.has_stata_license is True
        assert result.runtime_estimate == "hours"
        assert result.target_journal == "JPE"

    def test_empty_optional_fields_are_none(self):
        result = questionnaire(answers={"restricted_data": "no"})
        assert result.paper_tex_path is None
        assert result.last_run_date is None
        assert result.data_root is None

    def test_languages_parsed_from_comma_separated(self):
        result = questionnaire(answers={"restricted_data": "no", "languages_claimed": "R, Python, Julia"})
        assert set(result.languages_claimed) == {"R", "Python", "Julia"}

    def test_stata_license_only_asked_if_stata_claimed(self):
        # Stata not claimed → has_stata_license never set → remains None
        result = questionnaire(answers={
            "restricted_data": "no",
            "languages_claimed": "R",
            "has_stata_license": "yes",  # provided but should be skipped
        })
        assert result.has_stata_license is None

    def test_stata_license_asked_if_stata_claimed(self):
        result = questionnaire(answers={
            "restricted_data": "no",
            "languages_claimed": "Stata",
            "has_stata_license": "yes",
        })
        assert result.has_stata_license is True

    def test_matlab_license_only_asked_if_matlab_claimed(self):
        result = questionnaire(answers={
            "restricted_data": "no",
            "languages_claimed": "R",
            "has_matlab_license": "yes",
        })
        assert result.has_matlab_license is None

    def test_mandatory_restricted_defaults_false_on_empty(self):
        # Empty answer for mandatory bool → False (safe default)
        result = questionnaire(answers={"restricted_data": ""})
        assert result.restricted_data is False


# ---------------------------------------------------------------------------
# _parse_bool / _parse_list helpers
# ---------------------------------------------------------------------------


class TestParseHelpers:
    @pytest.mark.parametrize("raw,expected", [
        ("yes", True), ("y", True), ("YES", True), ("true", True),
        ("no", False), ("n", False), ("NO", False), ("false", False),
        ("", None), ("maybe", None),
    ])
    def test_parse_bool(self, raw, expected):
        assert _parse_bool(raw) == expected

    def test_parse_list_comma(self):
        assert _parse_list("R, Stata") == ["R", "Stata"]

    def test_parse_list_space(self):
        assert _parse_list("R Stata Julia") == ["R", "Stata", "Julia"]

    def test_parse_list_empty(self):
        assert _parse_list("") == []

    def test_parse_list_slash(self):
        assert _parse_list("R/Stata") == ["R", "Stata"]


# ---------------------------------------------------------------------------
# identify_questions — suppression via intake
# ---------------------------------------------------------------------------


class TestSuppressionViaIntake:
    def test_last_run_date_suppresses_env_question(self):
        intake = _make_intake(last_run_date="March 2023")
        env = _make_env(confidence=0.1)   # low confidence → would normally ask
        qs = identify_questions(_make_graph(), env, intake=intake)
        kinds = [q.gap_kind for q in qs]
        assert "env_last_run_date" not in kinds

    def test_no_intake_still_asks_env_question(self):
        env = _make_env(confidence=0.1)
        qs = identify_questions(_make_graph(), env, intake=None)
        kinds = [q.gap_kind for q in qs]
        assert "env_last_run_date" in kinds

    def test_stata_license_suppressed_when_intake_answered(self):
        intake = _make_intake(has_stata_license=True)
        env = _make_env(language="Stata", confidence=0.9)
        qs = identify_questions(_make_graph(), env, intake=intake)
        kinds = [q.gap_kind for q in qs]
        assert "proprietary_license" not in kinds

    def test_stata_license_asked_when_intake_not_answered(self):
        intake = _make_intake(has_stata_license=None)
        env = _make_env(language="Stata", confidence=0.9)
        qs = identify_questions(_make_graph(), env, intake=intake)
        kinds = [q.gap_kind for q in qs]
        assert "proprietary_license" in kinds

    def test_matlab_license_suppressed_when_intake_answered(self):
        intake = _make_intake(has_matlab_license=False)
        env = _make_env(language="MATLAB", confidence=0.9)
        qs = identify_questions(_make_graph(), env, intake=intake)
        kinds = [q.gap_kind for q in qs]
        assert "proprietary_license" not in kinds

    def test_no_intake_asks_matlab_license(self):
        env = _make_env(language="MATLAB", confidence=0.9)
        qs = identify_questions(_make_graph(), env, intake=None)
        kinds = [q.gap_kind for q in qs]
        assert "proprietary_license" in kinds


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------


class TestContradictionDetection:
    def _fake_scan(self, suffixes: list[str]):
        """Minimal scan-like object with a scripts attribute."""
        from types import SimpleNamespace
        return SimpleNamespace(scripts=[f"code/script{s}" for s in suffixes])

    def test_stata_dot_files_found_but_not_claimed(self):
        intake = _make_intake(languages_claimed=["R"])
        scan = self._fake_scan([".R", ".do"])
        contradictions = _contradiction_questions(intake, _make_graph(), None, scan)
        assert any("Stata" in q.question for q in contradictions)

    def test_no_contradiction_when_stata_claimed(self):
        intake = _make_intake(languages_claimed=["R", "Stata"])
        scan = self._fake_scan([".R", ".do"])
        contradictions = _contradiction_questions(intake, _make_graph(), None, scan)
        assert not any("Stata" in q.question for q in contradictions)

    def test_matlab_dot_m_found_but_not_claimed(self):
        intake = _make_intake(languages_claimed=["R"])
        scan = self._fake_scan([".R", ".m"])
        contradictions = _contradiction_questions(intake, _make_graph(), None, scan)
        assert any("MATLAB" in q.question for q in contradictions)

    def test_real_scan_result_triggers_stata_contradiction(self, tmp_path):
        """
        Regression: ScanResult (the real production type from scan_scripts())
        must satisfy the same `.scripts` shape the mock in _fake_scan assumes.
        Previously ScanResult had no `scripts` field, so hasattr(scan, "scripts")
        was always False in the real pipeline and this check never fired.
        """
        from deadreckoning.scan import scan_scripts

        (tmp_path / "code").mkdir()
        (tmp_path / "code" / "analysis.do").write_text('display "hi"\n')
        scan = scan_scripts(tmp_path)
        assert scan.scripts, "scan_scripts() must populate .scripts"

        intake = _make_intake(languages_claimed=["R"])
        contradictions = _contradiction_questions(intake, _make_graph(), None, scan)
        assert any("Stata" in q.question for q in contradictions)

    def test_date_discrepancy_flagged(self):
        intake = _make_intake(last_run_date="2020")
        env = _make_env(snapshot_date="2023-06-01")
        contradictions = _contradiction_questions(intake, _make_graph(), env, None)
        assert any("intake_contradiction" == q.gap_kind for q in contradictions)

    def test_date_close_not_flagged(self):
        intake = _make_intake(last_run_date="2023")
        env = _make_env(snapshot_date="2023-06-01")
        contradictions = _contradiction_questions(intake, _make_graph(), env, None)
        date_contradictions = [q for q in contradictions if "date" in q.question.lower() or "2023" in q.question]
        assert not date_contradictions

    def test_data_root_missing_on_disk(self, tmp_path):
        intake = _make_intake(data_root="nonexistent_data_dir")
        graph = _make_graph(project_root=str(tmp_path))
        contradictions = _contradiction_questions(intake, graph, None, None)
        assert any("does not exist" in q.question for q in contradictions)

    def test_data_root_present_on_disk_no_contradiction(self, tmp_path):
        (tmp_path / "data").mkdir()
        intake = _make_intake(data_root="data")
        graph = _make_graph(project_root=str(tmp_path))
        contradictions = _contradiction_questions(intake, graph, None, None)
        assert not any("does not exist" in q.question for q in contradictions)

    def test_no_intake_no_contradictions(self):
        qs = identify_questions(_make_graph(), _make_env(), intake=None)
        assert not any(q.gap_kind == "intake_contradiction" for q in qs)

    def test_contradictions_appear_first_in_question_list(self):
        """Contradiction questions precede blocking gap questions."""
        intake = _make_intake(languages_claimed=["R"])
        scan = self._fake_scan([".do"])
        gap = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"))
        graph = _make_graph(gaps=[gap])
        qs = identify_questions(graph, None, scan=scan, intake=intake)
        kinds = [q.gap_kind for q in qs]
        contradiction_idx = kinds.index("intake_contradiction")
        blocking_idx = kinds.index(GapKind.exhibit_no_source_script.value)
        assert contradiction_idx < blocking_idx


# ---------------------------------------------------------------------------
# intake feeds into run_ask_step (snapshot_date seeded)
# ---------------------------------------------------------------------------


class TestIntakeAppliedInAskStep:
    def test_last_run_date_seeds_snapshot_date(self, tmp_path):
        from deadreckoning.ask import run_ask_step

        intake = _make_intake(last_run_date="March 2023")
        env = _make_env(confidence=0.1, snapshot_date=None)
        graph = _make_graph(project_root=str(tmp_path))

        _qa, _needs, _g, updated_env = run_ask_step(
            tmp_path, graph, env, intake=intake
        )
        assert updated_env.snapshot_date == "2023-03-01"

    def test_existing_snapshot_not_overwritten(self, tmp_path):
        from deadreckoning.ask import run_ask_step

        intake = _make_intake(last_run_date="March 2023")
        env = _make_env(confidence=0.1, snapshot_date="2021-01-01")
        graph = _make_graph(project_root=str(tmp_path))

        _qa, _needs, _g, updated_env = run_ask_step(
            tmp_path, graph, env, intake=intake
        )
        assert updated_env.snapshot_date == "2021-01-01"
