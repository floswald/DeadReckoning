"""
Wall-clock / PID / tempdir-in-output detection — Action Point 3 in compare.md
(ReproAI's C12).

Not a standalone check: this exists to make `check_exhibit_fidelity()` (in
runner.py) more reliable, not to add a new disconnected warning. A script
that writes the current time, a process ID, or a tempdir path into an
exhibit makes every regeneration byte-differ from the reference by
construction — the fidelity check would call that "drift" when it is
actually expected, harmless non-reproducibility. On a mismatch, the
producing script is checked for one of these calls so the report can say
"this may be expected, not drift" instead of pointing the author at the
wrong upstream data file.

Best-effort, script-level, like the rest of the static layer: a match
anywhere in the script that writes a given exhibit is treated as a note
on that exhibit — no attempt to prove the matched call's result actually
reaches the written file's bytes (that would need real parsing).
"""

from __future__ import annotations

import re
from pathlib import Path

# suffix (lowercased) -> regex matching a wall-clock/PID/tempdir call
_NONDETERMINISM_PATTERNS: dict[str, re.Pattern[str]] = {
    ".r": re.compile(
        r"\b(?:Sys\.time|Sys\.Date|Sys\.getpid|tempdir|tempfile|date)\s*\("
    ),
    ".py": re.compile(
        r"\b(?:time\.time|datetime\.now|datetime\.today|os\.getpid"
        r"|tempfile\.mkdtemp|tempfile\.gettempdir|tempfile\.NamedTemporaryFile)\s*\("
    ),
    ".do": re.compile(r"c\(\s*current_date\s*\)|c\(\s*current_time\s*\)", re.IGNORECASE),
    ".jl": re.compile(r"\b(?:now|Dates\.now|getpid|tempdir|tempname)\s*\("),
    ".m": re.compile(r"\b(?:datestr|now|clock|tempdir|tempname)\s*\("),
    ".f90": re.compile(r"\bcall\s+(?:date_and_time|system_clock)\s*\("),
    ".f95": re.compile(r"\bcall\s+(?:date_and_time|system_clock)\s*\("),
    ".f": re.compile(r"\bcall\s+(?:date_and_time|system_clock)\s*\("),
    ".for": re.compile(r"\bcall\s+(?:date_and_time|system_clock)\s*\("),
    ".c": re.compile(r"\b(?:time\s*\(\s*(?:NULL|0)?\s*\)|getpid\s*\(|clock\s*\()"),
    ".h": re.compile(r"\b(?:time\s*\(\s*(?:NULL|0)?\s*\)|getpid\s*\(|clock\s*\()"),
    ".cpp": re.compile(
        r"std::time\s*\(|std::chrono::system_clock::now\s*\(|\bgetpid\s*\("
    ),
    ".cc": re.compile(
        r"std::time\s*\(|std::chrono::system_clock::now\s*\(|\bgetpid\s*\("
    ),
    ".cxx": re.compile(
        r"std::time\s*\(|std::chrono::system_clock::now\s*\(|\bgetpid\s*\("
    ),
    ".hpp": re.compile(
        r"std::time\s*\(|std::chrono::system_clock::now\s*\(|\bgetpid\s*\("
    ),
}


def find_nondeterministic_calls(script: Path) -> list[str]:
    """Distinct wall-clock/PID/tempdir call snippets found in `script`, in
    first-seen order. Empty list if the suffix isn't covered or none found."""
    pattern = _NONDETERMINISM_PATTERNS.get(script.suffix.lower())
    if pattern is None:
        return []
    try:
        text = script.read_text(errors="replace")
    except OSError:
        return []
    seen: list[str] = []
    for m in pattern.finditer(text):
        call = m.group(0)
        if call not in seen:
            seen.append(call)
    return seen
