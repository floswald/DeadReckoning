"""
Tests for the `deadreckoning run` CLI's intake wiring (§4.1).

Focus: the CLI must actually collect the intake questionnaire and the
author's restricted_data answer must gate the pipeline — this closes the
gap where IntakeResult.restricted_data was captured but never read anywhere.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from deadreckoning.cli import _cmd_run, _collect_intake


def _make_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        project=None,
        master_script=None,
        skip_docker=True,
        stata_image=None,
        stata_license=None,
        answers_file=None,
        skip_intake=True,
        stop_after=None,
        json=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_collect_intake_skip_returns_none() -> None:
    args = _make_args(skip_intake=True)
    assert _collect_intake(args) is None


def test_collect_intake_answers_file(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps({"restricted_data": "yes"}))

    args = _make_args(skip_intake=False, answers_file=str(answers_path))
    intake = _collect_intake(args)

    assert intake is not None
    assert intake.restricted_data is True


def test_cmd_run_honors_restricted_answer_no_filename_trigger(tmp_path: Path, capsys) -> None:
    """
    Project has no restricted-sounding filenames — only the intake answer
    should trigger the abort. Confirms the real CLI path (not just
    orchestrator.run_pipeline called directly) honors it.
    """
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "wages.csv").write_bytes(b"")
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps({"restricted_data": "yes"}))

    args = _make_args(project=str(tmp_path), skip_intake=False, answers_file=str(answers_path))
    rc = _cmd_run(args)

    out = capsys.readouterr().out
    payload = json.loads(out)

    assert payload["restricted"]["is_restricted"] is True
    assert "restricted" in payload["error"].lower()
    assert payload["working_copy"] == str(tmp_path)  # sentinel — no copy made
    assert rc == 1


@pytest.mark.local
def test_cmd_run_skip_intake_relies_on_filename_only(tmp_path: Path, capsys) -> None:
    """--skip-intake means no questionnaire runs — restricted status comes
    only from the filename heuristic, same as before this change.

    Marked `local`: not restricted → pipeline proceeds to a real native
    Rscript run, which CI's `not local` selection doesn't have installed."""
    (tmp_path / "paper.tex").write_text(r"\documentclass{article}\begin{document}\end{document}")
    (tmp_path / "run.R").write_text("# script\n")

    args = _make_args(project=str(tmp_path), skip_intake=True)
    _cmd_run(args)

    out = capsys.readouterr().out
    payload = json.loads(out)

    assert payload["restricted"]["is_restricted"] is False
    assert payload["intake"] is None
