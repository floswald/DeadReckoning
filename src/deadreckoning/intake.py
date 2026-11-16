"""
Pre-pipeline intake questionnaire.

Collects author context before any file is opened. Runs interactively
(stdin prompts) or non-interactively (pre-supplied answers dict).

Usage:
    from deadreckoning.intake import questionnaire
    intake = questionnaire()                        # interactive
    intake = questionnaire(answers={"restricted_data": "no", ...})  # tests / CI
"""

from __future__ import annotations

import re
import sys
from typing import Optional

from .models import IntakeResult


# ---------------------------------------------------------------------------
# ANSI helpers — self-contained (questionnaire() is also called directly by
# demo/run_demo.py, bypassing cli.py's own color state).
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()
_DR_TAG = "\033[1;36m[dr]\033[0m" if _USE_COLOR else "[dr]"


# ---------------------------------------------------------------------------
# Question definitions
# ---------------------------------------------------------------------------

_QUESTIONS: list[dict] = [
    {
        "key": "restricted_data",
        "prompt": (
            "Does this project use data that is confidential, restricted, or covered "
            "by a data use agreement, IRB protocol, or NDA?\n"
            "  (I ask this first because I run on remote servers — "
            "restricted data must not be sent over the internet.)\n"
            "  Answer yes/no: "
        ),
        "kind": "bool",
        "mandatory": True,
    },
    {
        "key": "paper_tex_path",
        "prompt": (
            "Where is your paper.tex (or main LaTeX file)? "
            "Enter a path relative to the project root, or press Enter to auto-detect: "
        ),
        "kind": "str_optional",
    },
    {
        "key": "code_root",
        "prompt": (
            "Where is your code? "
            "(e.g. `code/`, or press Enter if code is in the project root): "
        ),
        "kind": "str_optional",
    },
    {
        "key": "master_script",
        "prompt": (
            "What is the master/entry script that runs the full analysis end to end? "
            "(e.g. `code/run_all.sh`, `code/master.do`, or press Enter to auto-detect): "
        ),
        "kind": "str_optional",
    },
    {
        "key": "data_root",
        "prompt": (
            "Where is your data? "
            "(e.g. `data/`, or an absolute path like `/Users/you/Dropbox/data/`, "
            "or press Enter if data is inside the project): "
        ),
        "kind": "str_optional",
    },
    {
        "key": "reference_exhibit_dirs",
        "prompt": (
            "Where are your output files stored -- i.e. where are the figures and "
            "tables that appear in your conditionally accepted paper PDF, on your "
            "computer right now? Please give the absolute path to the relevant "
            "directory, or several separated by commas if they're not all in one "
            "place. Press Enter if you don't have these preserved separately from "
            "your working project: "
        ),
        "kind": "path_list_optional",
    },
    {
        "key": "last_run_date",
        "prompt": (
            "When did you last run this project successfully? "
            "(e.g. 'March 2023' or '2023-03', or press Enter if unsure): "
        ),
        "kind": "str_optional",
    },
    {
        "key": "languages_claimed",
        "prompt": (
            "Which languages does this project use? "
            "(e.g. 'R', 'R and Stata', 'Python', or press Enter to auto-detect): "
        ),
        "kind": "list_optional",
    },
    {
        "key": "has_stata_license",
        "prompt": "Is a Stata license available on this machine? (y/n, or Enter to skip): ",
        "kind": "bool_optional",
        "show_if": lambda r: _claimed_language(r, "stata"),
    },
    {
        "key": "has_matlab_license",
        "prompt": (
            "Is a MathWorks cloud-enabled license available? "
            "(Required for Docker image; y/n, or Enter to skip): "
        ),
        "kind": "bool_optional",
        "show_if": lambda r: _claimed_language(r, "matlab"),
    },
    {
        "key": "runtime_estimate",
        "prompt": (
            "Roughly how long does a full run take? "
            "('minutes', 'hours', 'days', or press Enter if unsure): "
        ),
        "kind": "str_optional",
    },
    {
        "key": "target_journal",
        "prompt": (
            "Target journal or submission standard? "
            "(e.g. 'AEA', 'JPE', 'ReStud', or press Enter to use AEA defaults): "
        ),
        "kind": "str_optional",
    },
]


def _claimed_language(partial: dict, lang: str) -> bool:
    claimed = partial.get("languages_claimed") or []
    return any(lang in c.lower() for c in claimed)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_bool(raw: str) -> Optional[bool]:
    r = raw.strip().lower()
    if r in ("y", "yes", "true", "1"):
        return True
    if r in ("n", "no", "false", "0"):
        return False
    return None


def _parse_list(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [token.strip() for token in raw.replace(",", " ").replace("/", " ").split() if token.strip()]


def _parse_path_list(raw: str) -> list[str]:
    """Like _parse_list, but for path-shaped answers: splits only on commas
    and newlines, never on '/' or plain whitespace, since a path legitimately
    contains both (an absolute path, or a directory name with a space in it)."""
    if not raw.strip():
        return []
    return [token.strip() for token in re.split(r"[,\n]", raw) if token.strip()]


# ---------------------------------------------------------------------------
# Main questionnaire function
# ---------------------------------------------------------------------------


def questionnaire(
    answers: Optional[dict[str, str]] = None,
    _input_fn=input,
) -> IntakeResult:
    """
    Collect pre-pipeline author context.

    Parameters
    ----------
    answers : dict[str, str] | None
        Pre-supplied answers keyed by question ``key``. If None, prompts
        interactively via stdin. Partial dicts are fine — missing keys are
        prompted interactively.
    _input_fn : callable
        Override for ``input()``; used in tests to avoid stdin.

    Returns
    -------
    IntakeResult
    """
    raw: dict = {}

    for q in _QUESTIONS:
        key = q["key"]
        kind = q["kind"]
        show_if = q.get("show_if")

        if show_if is not None and not show_if(raw):
            continue

        if answers is not None:
            raw_value = answers.get(key, "")
        else:
            raw_value = _input_fn(f"{_DR_TAG} {q['prompt']}").strip()
            print()  # blank line between questions — easier to read at the terminal

        if kind == "bool":
            parsed: object = _parse_bool(raw_value)
            if parsed is None and q.get("mandatory"):
                parsed = False
            raw[key] = parsed
        elif kind == "bool_optional":
            raw[key] = _parse_bool(raw_value)
        elif kind == "list_optional":
            raw[key] = _parse_list(raw_value)
        elif kind == "path_list_optional":
            raw[key] = _parse_path_list(raw_value)
        else:
            raw[key] = raw_value if raw_value else None

    return IntakeResult(
        paper_tex_path=raw.get("paper_tex_path"),
        code_root=raw.get("code_root"),
        master_script=raw.get("master_script"),
        data_root=raw.get("data_root"),
        reference_exhibit_dirs=raw.get("reference_exhibit_dirs") or [],
        last_run_date=raw.get("last_run_date"),
        languages_claimed=raw.get("languages_claimed") or [],
        has_stata_license=raw.get("has_stata_license"),
        has_matlab_license=raw.get("has_matlab_license"),
        restricted_data=raw.get("restricted_data"),
        runtime_estimate=raw.get("runtime_estimate"),
        target_journal=raw.get("target_journal"),
    )
