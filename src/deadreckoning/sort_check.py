"""
SORT-CHECK step: flag a Stata `sort`/`gsort` command, with no `, stable`
option and no `set sortseed` anywhere in the script, immediately feeding a
tie-sensitive operation (`by ... : ... if _n==1` or `_n==_N` — "keep the
first/last observation per group"). Non-blocking — writes SORT-WARNINGS.md,
same posture as RNG-WARNINGS.md / MIXED-LANGUAGE-WARNINGS.md.

Why this exists: unlike R/Python/Julia's `sort()`, which is specified to be
stable (ties keep their input order), Stata's default `sort` breaks ties
among equal key values using an internal random tiebreaker — the observed
order for tied rows is NOT guaranteed to be the same across runs, Stata
editions (SE vs MP), or machine thread counts, unless `set sortseed` is
used (and Stata's own documentation calls that "highly esoteric," reserved
for replication studies, not general use) or the sort is on a variable
combination that already uniquely identifies each observation. A do-file
that sorts on a non-unique key and then picks "the first observation per
group" can silently keep a DIFFERENT observation on a rerun — exit 0, the
exhibit lands on disk, nothing crashes, the number is just quietly
different. See:
  https://www.stata.com/help13.cgi?sortseed=
  https://www.stata.com/manuals/dsort.pdf
  https://www.statalist.org/forums/forum/general-stata-discussion/general/1345163-how-does-stata-randomize-observations-with-the-same-value-when-using-the-command-sort-without-stable

Best-effort regex, like the rest of the static layer — no Stata parser. A
`by`/`bysort ... : ... _n==1` block is only recognized when the by-clause
and the `_n==` test are on the same line (the common one-line idiom); a
split `by var:` / `keep if _n==1` across two lines is not matched. The
check does not attempt to verify whether the sort varlist is actually a
unique key for the data (that would need to run the data) — a sort on a
genuinely unique key is harmless even without `stable`, but flagging it
anyway is a false positive this static layer accepts, same tradeoff as
every other check in this module.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

_SORT_WARNINGS_FILE = "SORT-WARNINGS.md"

_SORT_LINE_RE = re.compile(r"^\s*(?:sort|gsort)\s+(?P<varlist>[^\n,]+)(?P<opts>,.*)?$", re.IGNORECASE)
_STABLE_OPTION_RE = re.compile(r"\bstable\b", re.IGNORECASE)
_SORTSEED_RE = re.compile(r"\bset\s+sortseed\b", re.IGNORECASE)
_TIE_SENSITIVE_RE = re.compile(
    r"\b(?:by|bysort)\b[^\n:]*:\s*[^\n]*\b_n\s*==\s*(?:1|_N)\b", re.IGNORECASE
)

_SKIP_DIRS = frozenset({".git", "_archive", "__pycache__", "node_modules"})


def _rel_parts(p: Path, project_root: Path) -> tuple[str, ...]:
    return p.relative_to(project_root).parts


class SortFinding(BaseModel):
    script: Path
    line: int
    sort_call: str
    tie_sensitive_line: int
    tie_sensitive_call: str


class SortCheckResult(BaseModel):
    findings: list[SortFinding] = Field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0


def _find_do_files(working_copy: Path) -> list[Path]:
    return sorted(
        p for p in working_copy.rglob("*.do")
        if p.is_file() and not any(part in _SKIP_DIRS for part in _rel_parts(p, working_copy))
    )


def check_nondeterministic_sort(working_copy: Path) -> SortCheckResult:
    findings: list[SortFinding] = []

    for script in _find_do_files(working_copy):
        try:
            text = script.read_text(errors="replace")
        except OSError:
            continue
        if _SORTSEED_RE.search(text):
            continue

        lines = text.splitlines()
        rel = script.relative_to(working_copy)

        unstable_sorts: list[tuple[int, str]] = []
        for i, line in enumerate(lines, start=1):
            m = _SORT_LINE_RE.match(line)
            if not m:
                continue
            opts = m.group("opts") or ""
            if _STABLE_OPTION_RE.search(opts):
                continue
            unstable_sorts.append((i, line.strip()))

        if not unstable_sorts:
            continue

        for i, line in enumerate(lines, start=1):
            tie_m = _TIE_SENSITIVE_RE.search(line)
            if not tie_m:
                continue
            # The nearest preceding unstable sort, if any.
            preceding = [s for s in unstable_sorts if s[0] <= i]
            if not preceding:
                continue
            sort_line, sort_call = preceding[-1]
            findings.append(
                SortFinding(
                    script=rel,
                    line=sort_line,
                    sort_call=sort_call,
                    tie_sensitive_line=i,
                    tie_sensitive_call=line.strip(),
                )
            )

    return SortCheckResult(findings=findings)


def write_sort_warnings_file(working_copy: Path, result: SortCheckResult) -> Path:
    lines = [
        "# DeadReckoning — Nondeterministic Sort Warnings\n\n",
        "A `sort`/`gsort` command with no `, stable` option and no "
        "`set sortseed` anywhere in the script was found feeding a "
        "tie-sensitive operation (`by ... : ... if _n==1` or `_n==_N` — "
        "keep the first/last observation per group). Stata's default sort "
        "breaks ties among equal key values with an internal random "
        "tiebreaker that is not guaranteed to be the same across runs, "
        "Stata editions, or machines. The run can succeed and the exhibit "
        "can land on disk with this unchanged — a different observation "
        "may be kept per group on a rerun.\n\n",
        "This is advisory only; the pipeline is not blocked by it. "
        "Fix by sorting on a variable combination that uniquely identifies "
        "each observation, or by adding `, stable`.\n\n",
    ]
    for f in result.findings:
        lines.append(
            f"- `{f.script}:{f.line}` — `{f.sort_call}` feeds "
            f"`{f.script}:{f.tie_sensitive_line}` — `{f.tie_sensitive_call}`\n"
        )
    path = working_copy / _SORT_WARNINGS_FILE
    path.write_text("".join(lines))
    return path


def run_sort_check_step(working_copy: Path) -> SortCheckResult:
    """Full SORT-CHECK step: detect, and if anything was found, write
    SORT-WARNINGS.md. Always non-blocking."""
    result = check_nondeterministic_sort(working_copy)
    if result.has_findings:
        write_sort_warnings_file(working_copy, result)
    return result
