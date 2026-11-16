"""
ASK step: surface gaps that cannot be resolved from disk alone, collect
author responses, and apply them to the graph and env spec.

Design rule (spec §3, §5):
  Ask only what the disk could not answer.
  Never ask for information already found.
  Every question is grounded in a specific gap or low-confidence signal.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional



from .models import AuthorQA, AuthorQuestion, AuthorResponse, DependencyGraph, EnvSpec, GapKind, IntakeResult

# ---------------------------------------------------------------------------
# Question categories
# ---------------------------------------------------------------------------

# Gaps that block the pipeline and require author input before proceeding
_BLOCKING_GAP_KINDS = {
    GapKind.exhibit_no_source_script,
    GapKind.exhibit_missing_from_disk,
    GapKind.exhibit_copied_but_no_source_script,
    GapKind.input_missing_from_disk,
    GapKind.compiled_language_no_build_script,
}

# gap_kind values (as stored on AuthorQuestion, which uses .value strings)
# that expect a script-path answer and should block the pipeline — kept as
# one tuple so parse_author_responses / all_blocking_answered stay in sync.
_PATH_ANSWER_GAP_KIND_VALUES = (
    GapKind.exhibit_no_source_script.value,
    GapKind.exhibit_missing_from_disk.value,
    GapKind.exhibit_copied_but_no_source_script.value,
    GapKind.input_missing_from_disk.value,
    GapKind.compiled_language_no_build_script.value,
)

# Env confidence below this threshold triggers a "when did you last run this?" question
_LOW_CONFIDENCE_THRESHOLD = 0.5

_QUESTIONS_FILE = "QUESTIONS.md"


def _with_hint(
    note: Optional[str],
    gap,  # Gap
    graph: DependencyGraph,
    hint_dispatcher: Any,
) -> Optional[str]:
    """
    Append an unverified LLM-proposed lead to `note`, if a dispatcher was
    supplied and it has anything to say. No dispatcher, no API key, or
    nothing useful found → returns `note` unchanged, same as before this
    existed. The label is deliberate and non-negotiable: this is a
    suggestion for the author to confirm, never a resolved fact — nothing
    downstream (the graph, the gap, the pipeline's pass/fail) is allowed to
    treat it as one.
    """
    if hint_dispatcher is None:
        return note
    hint = hint_dispatcher.propose_hint(gap, graph, graph.project_root)
    if not hint:
        return note
    labeled = f"**Possible lead (unverified — proposed by Claude, confirm before relying on it):** {hint}"
    return f"{note}\n\n{labeled}" if note else labeled


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------


def identify_questions(
    graph: DependencyGraph,
    env_spec: Optional[EnvSpec] = None,
    scan=None,  # ScanResult | None — checked for external data paths
    intake: Optional[IntakeResult] = None,
    hint_dispatcher: Any = None,
) -> list[AuthorQuestion]:
    """
    Build the list of questions for the author.

    Order:
      0. Intake contradictions (intake claim vs. disk evidence)
      1. Blocking graph gaps (no source script, missing exhibit, copied-but-
         unexplained) — optionally augmented with an unverified LLM-proposed
         lead via `hint_dispatcher` (a GapHintDispatcher; see
         llm_gap_hints.py). None/no API key → behaves exactly as before,
         zero network dependency.
      2. External data locations not found on disk
      3. License availability for proprietary software (suppressed if intake answered)
      4. Environment confidence / last-run date (suppressed if intake answered)
    """
    questions: list[AuthorQuestion] = []
    seen_exhibits: set[str] = set()

    # 0. Intake contradictions — surface mismatches between what author claimed and disk shows
    if intake is not None:
        questions.extend(_contradiction_questions(intake, graph, env_spec, scan))

    # 1. Blocking graph gaps
    for gap in graph.gaps:
        if gap.kind not in _BLOCKING_GAP_KINDS:
            continue
        exhibit = str(gap.exhibit) if gap.exhibit else (gap.location or "unknown")
        if exhibit in seen_exhibits:
            continue
        seen_exhibits.add(exhibit)

        if gap.kind == GapKind.exhibit_no_source_script:
            questions.append(AuthorQuestion(
                gap_kind=gap.kind.value,
                exhibit=exhibit,
                question=(
                    f"No script was found that produces `{exhibit}`. "
                    "Which script creates this file? "
                    "Please enter the path relative to the project root "
                    "(e.g. `code/figures.R`) or describe how it was produced."
                ),
                context=_with_hint(gap.note, gap, graph, hint_dispatcher),
            ))
        elif gap.kind == GapKind.exhibit_missing_from_disk:
            questions.append(AuthorQuestion(
                gap_kind=gap.kind.value,
                exhibit=exhibit,
                question=(
                    f"`{exhibit}` is referenced in the paper but not present on disk "
                    "and no script appears to produce it. "
                    "Is this file restricted/confidential data? "
                    "If so, where can a replicator obtain it? "
                    "If it was generated by code, which script produced it?"
                ),
                context=gap.note,
            ))
        elif gap.kind == GapKind.input_missing_from_disk:
            questions.append(AuthorQuestion(
                gap_kind=gap.kind.value,
                exhibit=exhibit,
                question=(
                    f"A script reads `{exhibit}` but it is not present on disk "
                    "and no script produces it. "
                    "Is this a restricted/confidential input? If so, where can "
                    "a replicator obtain it? "
                    "If it's a typo or was moved, what is the correct path "
                    "relative to the project root?"
                ),
                context=gap.note,
            ))
        elif gap.kind == GapKind.compiled_language_no_build_script:
            questions.append(AuthorQuestion(
                gap_kind=gap.kind.value,
                exhibit=None,
                question=(
                    "This project contains Fortran/C/C++ source but no "
                    "Makefile, CMakeLists.txt, or build/compile script was "
                    "found anywhere in it. What is the exact command (or "
                    "sequence of commands) you run to compile AND execute "
                    "this code — compiler, flags, output binary name, and "
                    "how you run the resulting binary? For example: "
                    "`gfortran code/simulate.f90 -o code/simulate "
                    "&& ./code/simulate`"
                ),
                context=gap.note,
            ))
        elif gap.kind == GapKind.exhibit_copied_but_no_source_script:
            # We know one hop of provenance (a copy/rename edge reaches this
            # exhibit) — gap.note already names it. What's missing is the
            # script that wrote the ORIGINAL (pre-rename) file.
            questions.append(AuthorQuestion(
                gap_kind=gap.kind.value,
                exhibit=exhibit,
                question=(
                    f"`{exhibit}` is produced by copying/renaming another file "
                    "(see context below) — but nothing writes that original "
                    "file under its exact name, likely because the filename "
                    "is built dynamically in code (a loop variable, a lookup "
                    "key, string interpolation). Which script/function "
                    "actually generates it?"
                ),
                context=_with_hint(gap.note, gap, graph, hint_dispatcher),
            ))

    # 2. External data not found on disk
    if scan is not None and hasattr(scan, "external_paths"):
        for ep in scan.external_paths:
            if ep.kind in ("dropbox", "absolute", "network", "unc"):
                # Suppress if intake already told us where data is and path matches
                if intake is not None and intake.data_root and ep.raw.startswith(intake.data_root):
                    continue
                questions.append(AuthorQuestion(
                    gap_kind="external_data_missing",
                    exhibit=None,
                    question=(
                        f"The script `{ep.script}` references data at `{ep.raw}` "
                        "which is outside the project directory. "
                        "Is this file available on this machine at that path, "
                        "or does it need to be copied into the project? "
                        "If restricted, describe how a replicator can obtain it."
                    ),
                    context=f"Referenced in {ep.script} (line {ep.line})" if hasattr(ep, "line") else None,
                ))

    # 3. Proprietary software license — suppressed if intake already answered
    if env_spec is not None:
        lang = env_spec.language.upper()
        if lang == "STATA" and (intake is None or intake.has_stata_license is None):
            questions.append(AuthorQuestion(
                gap_kind="proprietary_license",
                exhibit=None,
                question=(
                    "This project uses Stata. "
                    "Is a Stata license available on this machine? "
                    "If yes, which edition (MP/SE/BE) and version? "
                    "If no, can replication be done on a different machine?"
                ),
                context=None,
            ))
        elif lang == "MATLAB" and (intake is None or intake.has_matlab_license is None):
            questions.append(AuthorQuestion(
                gap_kind="proprietary_license",
                exhibit=None,
                question=(
                    "This project uses MATLAB. "
                    "Is a MathWorks account with a cloud-enabled license available? "
                    "(Required for `mathworks/matlab` Docker image with `-browser` flag.) "
                    "Which release was used (e.g. R2023b)?"
                ),
                context=env_spec.note,
            ))

    # 4. Low-confidence environment — suppressed if intake supplied last_run_date
    if env_spec is not None and env_spec.confidence < _LOW_CONFIDENCE_THRESHOLD:
        if intake is None or not intake.last_run_date:
            questions.append(AuthorQuestion(
                gap_kind="env_last_run_date",
                exhibit=None,
                question=(
                    f"No lockfile was found for {env_spec.language}. "
                    "When did you last run this project successfully? "
                    "An approximate date (e.g. 'March 2023' or '2023-03') "
                    "helps reconstruct which package versions were installed."
                ),
                context=(
                    f"Current best guess: {env_spec.snapshot_date or 'unknown'}. "
                    f"Confidence: {env_spec.confidence:.0%}."
                ),
            ))

    return questions


# ---------------------------------------------------------------------------
# Intake contradiction detection
# ---------------------------------------------------------------------------


def _contradiction_questions(
    intake: IntakeResult,
    graph: DependencyGraph,
    env_spec: Optional[EnvSpec],
    scan,
) -> list[AuthorQuestion]:
    """
    Compare intake claims against disk evidence. Return contradiction questions.
    These are informational (gap_kind='intake_contradiction') — not blocking.
    """
    contradictions: list[AuthorQuestion] = []

    # Language claimed ≠ script extensions found
    if intake.languages_claimed:
        claimed_lower = {c.lower() for c in intake.languages_claimed}
        claimed_stata = any("stata" in c for c in claimed_lower)
        claimed_matlab = any("matlab" in c for c in claimed_lower)

        if scan is not None and hasattr(scan, "scripts"):
            extensions = {Path(s).suffix.lower() for s in (scan.scripts or [])}
            if not claimed_stata and ".do" in extensions:
                contradictions.append(AuthorQuestion(
                    gap_kind="intake_contradiction",
                    question=(
                        "You said this project does not use Stata, "
                        "but I found `.do` files on disk. "
                        "Is Stata required to reproduce any of the paper's outputs?"
                    ),
                    context=f"Claimed languages: {', '.join(intake.languages_claimed)}",
                ))
            if not claimed_matlab and ".m" in extensions:
                contradictions.append(AuthorQuestion(
                    gap_kind="intake_contradiction",
                    question=(
                        "You said this project does not use MATLAB, "
                        "but I found `.m` files on disk. "
                        "Is MATLAB required to reproduce any of the paper's outputs?"
                    ),
                    context=f"Claimed languages: {', '.join(intake.languages_claimed)}",
                ))

    # last_run_date vs env_spec.snapshot_date — flag if they differ by > 1 year
    if intake.last_run_date and env_spec is not None and env_spec.snapshot_date:
        intake_year = _extract_year(intake.last_run_date)
        snap_year = _extract_year(env_spec.snapshot_date)
        if intake_year and snap_year and abs(intake_year - snap_year) > 1:
            contradictions.append(AuthorQuestion(
                gap_kind="intake_contradiction",
                question=(
                    f"You said this was last run around {intake.last_run_date}, "
                    f"but the lockfile or environment suggests {env_spec.snapshot_date}. "
                    "Which date should be used to reconstruct package versions?"
                ),
                context=(
                    f"Intake date: {intake.last_run_date}  |  "
                    f"Disk date: {env_spec.snapshot_date}"
                ),
            ))

    # data_root given but path doesn't exist on disk
    if intake.data_root:
        data_path = Path(intake.data_root)
        if not data_path.is_absolute():
            data_path = graph.project_root / intake.data_root
        if not data_path.exists():
            contradictions.append(AuthorQuestion(
                gap_kind="intake_contradiction",
                question=(
                    f"You said data is at `{intake.data_root}`, "
                    "but that path does not exist on this machine. "
                    "Has the data been moved, or is it on a different drive or machine?"
                ),
                context=f"Checked: {data_path}",
            ))

    return contradictions


def _extract_year(date_str: str) -> Optional[int]:
    """Pull a 4-digit year from a date string."""
    m = re.search(r"\b(20\d{2})\b", date_str)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Write / read QUESTIONS.md
# ---------------------------------------------------------------------------


def write_questions_file(working_copy: Path, questions: list[AuthorQuestion]) -> Path:
    """Write QUESTIONS.md to working_copy. Returns path."""
    lines = [
        "# DeadReckoning — Author Questions\n\n",
        "Please answer the questions below, then re-run `deadreckoning run`.\n",
        "Fill in each `> Answer:` line. Leave blank if not applicable.\n\n",
    ]
    for i, q in enumerate(questions, 1):
        label = q.exhibit or q.gap_kind
        lines.append(f"## Q{i}: {label}\n\n")
        lines.append(f"**Type:** `{q.gap_kind}`\n\n")
        if q.context:
            lines.append(f"**Context:** {q.context}\n\n")
        lines.append(f"{q.question}\n\n")
        lines.append(f"> Answer: \n\n")
        lines.append("---\n\n")
    path = working_copy / _QUESTIONS_FILE
    path.write_text("".join(lines))
    return path


def read_questions_file(working_copy: Path) -> Path | None:
    path = working_copy / _QUESTIONS_FILE
    return path if path.exists() else None


def parse_author_responses(
    working_copy: Path,
    questions: list[AuthorQuestion],
) -> list[AuthorResponse]:
    """
    Read QUESTIONS.md and pair each answer with its question.

    Answers are matched positionally (Q1 → questions[0], etc.).
    Empty answers are represented as AuthorResponse(answer="").
    """
    path = working_copy / _QUESTIONS_FILE
    if not path.exists():
        return []

    text = path.read_text()
    raw_answers: list[str] = []
    for line in text.splitlines():
        if line.startswith("> Answer:"):
            raw_answers.append(line[len("> Answer:"):].strip())

    responses: list[AuthorResponse] = []
    for i, q in enumerate(questions):
        answer = raw_answers[i] if i < len(raw_answers) else ""
        data_path = _extract_path(answer) if q.gap_kind in (
            ("external_data_missing",) + _PATH_ANSWER_GAP_KIND_VALUES
        ) else None
        responses.append(AuthorResponse(
            exhibit=q.exhibit,
            answer=answer,
            data_path=data_path,
        ))
    return responses


def _extract_path(text: str) -> Optional[str]:
    """
    Pull the first path-like token from an answer string.

    Recognises:
      - backtick-quoted: `code/run.R`
      - bare tokens containing / or \
    """
    # Backtick-quoted path
    m = re.search(r"`([^`]+)`", text)
    if m:
        return m.group(1)
    # Bare path token (contains slash or backslash)
    m = re.search(r"\b([\w./\\-]+[/\\][\w./\\-]+)\b", text)
    if m:
        return m.group(1)
    return None


def all_blocking_answered(
    questions: list[AuthorQuestion],
    responses: list[AuthorResponse],
) -> bool:
    """Return True if every blocking question has a non-empty answer."""
    for i, q in enumerate(questions):
        if q.gap_kind not in _PATH_ANSWER_GAP_KIND_VALUES:
            continue
        ans = responses[i].answer if i < len(responses) else ""
        if not ans:
            return False
    return True


# ---------------------------------------------------------------------------
# Apply responses to graph / env_spec
# ---------------------------------------------------------------------------


def apply_responses(
    graph: DependencyGraph,
    env_spec: EnvSpec,
    questions: list[AuthorQuestion],
    responses: list[AuthorResponse],
) -> tuple[DependencyGraph, EnvSpec]:
    """
    Patch graph and env_spec with author-supplied information.

    Currently handles:
      - env_last_run_date → update env_spec.snapshot_date if empty
      - exhibit_no_source_script + path answer → record in gap note
        (full graph patching needs LLM; record as note for now)

    Returns (updated_graph, updated_env_spec).
    """
    env_spec = env_spec.model_copy(deep=True)

    for i, q in enumerate(questions):
        if i >= len(responses):
            break
        resp = responses[i]
        answer = resp.answer.strip()
        if not answer:
            continue

        if q.gap_kind == "env_last_run_date":
            if env_spec.snapshot_date is None:
                # Parse year-month from free-text answer
                date = _parse_date(answer)
                if date:
                    env_spec.snapshot_date = date

        elif q.gap_kind == GapKind.compiled_language_no_build_script.value:
            env_spec.compile_command = answer

        elif q.gap_kind in (
            GapKind.exhibit_no_source_script.value,
            GapKind.exhibit_copied_but_no_source_script.value,
            GapKind.input_missing_from_disk.value,
        ):
            # Record the author-supplied script path in the gap note
            for gap in graph.gaps:
                if gap.kind.value == q.gap_kind:
                    exhibit_str = str(gap.exhibit) if gap.exhibit else ""
                    if exhibit_str == (q.exhibit or ""):
                        gap.note = (gap.note or "") + f" [Author: {answer}]"

    return graph, env_spec


def _parse_date(text: str) -> Optional[str]:
    """
    Extract an ISO-ish date from free text.

    Handles: "March 2023", "2023-03", "2023-03-15", "03/2023".
    Returns "YYYY-MM-01" or "YYYY-MM-DD" or None.
    """
    _MONTHS = {
        "january": "01", "february": "02", "march": "03",
        "april": "04", "may": "05", "june": "06",
        "july": "07", "august": "08", "september": "09",
        "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    # ISO: 2023-03 or 2023-03-15
    m = re.search(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b", text)
    if m:
        day = m.group(3) or "01"
        return f"{m.group(1)}-{m.group(2)}-{day}"
    # MM/YYYY or MM/YY
    m = re.search(r"\b(\d{1,2})/(\d{4})\b", text)
    if m:
        return f"{m.group(2)}-{m.group(1).zfill(2)}-01"
    # Month YYYY
    lower = text.lower()
    for name, num in _MONTHS.items():
        m = re.search(rf"\b{name}\b.*?\b(\d{{4}})\b", lower)
        if m:
            return f"{m.group(1)}-{num}-01"
    # Bare YYYY
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        return f"{m.group(1)}-01-01"
    return None


# ---------------------------------------------------------------------------
# High-level entry point (called by orchestrator)
# ---------------------------------------------------------------------------


def run_ask_step(
    working_copy: Path,
    graph: DependencyGraph,
    env_spec: EnvSpec,
    scan=None,
    intake: Optional[IntakeResult] = None,
    hint_dispatcher: Any = None,
) -> tuple[AuthorQA, bool, DependencyGraph, EnvSpec]:
    """
    Full ASK step.

    Returns (qa, needs_input, updated_graph, updated_env_spec).
    needs_input=True  → pipeline should halt; author must answer QUESTIONS.md
    needs_input=False → all blocking questions answered (or none); proceed

    hint_dispatcher: a GapHintDispatcher (llm_gap_hints.py), or None to
    build the real one. Same fallback contract as LLM-FIX's dispatcher: no
    ANTHROPIC_API_KEY → every hint call is a no-op, ASK behaves exactly as
    it did before this existed. Pass an explicit instance (e.g. a test
    double, or `False`-ish sentinel is not supported — pass a dispatcher
    whose propose_hint always returns None) to disable or mock it.
    """
    if hint_dispatcher is None:
        from .llm_gap_hints import GapHintDispatcher
        hint_dispatcher = GapHintDispatcher()

    # Apply intake-supplied last_run_date to env_spec before anything else
    if intake is not None and intake.last_run_date and env_spec.snapshot_date is None:
        date = _parse_date(intake.last_run_date)
        if date:
            env_spec = env_spec.model_copy(update={"snapshot_date": date})

    questions = identify_questions(graph, env_spec, scan, intake=intake, hint_dispatcher=hint_dispatcher)
    questions_path = working_copy / _QUESTIONS_FILE

    if not questions:
        return AuthorQA(questions=[], responses=[]), False, graph, env_spec

    has_blocking = any(q.gap_kind in _PATH_ANSWER_GAP_KIND_VALUES for q in questions)

    if not questions_path.exists():
        # First encounter — always write the file
        write_questions_file(working_copy, questions)
        qa = AuthorQA(questions=questions, responses=[])
        # Only halt if there are blocking questions the author must answer
        return qa, has_blocking, graph, env_spec

    # File exists — author may have answered
    responses = parse_author_responses(working_copy, questions)
    qa = AuthorQA(questions=questions, responses=responses)

    if has_blocking and not all_blocking_answered(questions, responses):
        return qa, True, graph, env_spec

    # All blocking answered (or none) — apply what we can
    graph, env_spec = apply_responses(graph, env_spec, questions, responses)
    return qa, False, graph, env_spec
