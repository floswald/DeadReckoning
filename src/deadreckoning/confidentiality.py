"""Confidentiality gate: must run before any file content is read."""

from __future__ import annotations

import re
from pathlib import Path

from .models import RestrictedStatus

# Filename fragments that indicate restricted data
_RESTRICTED_NAME_PATTERNS: list[str] = [
    "restricted", "confidential", "nda", "hipaa", "pii",
    "microdata", "admin", "census", "irs", "hmda",
    "nlsy", "psid", "sipp", "acs_pums",
]

# Filenames that suggest a DUA or ethics document is present
_DUA_NAME_PATTERNS: list[str] = [
    "data_use_agreement", "dua", "irb", "ethics_approval",
    "data_access_agreement", "nda",
]

_RESTRICTED_RE = re.compile(
    "|".join(re.escape(p) for p in _RESTRICTED_NAME_PATTERNS),
    re.IGNORECASE,
)
_DUA_RE = re.compile(
    "|".join(re.escape(p) for p in _DUA_NAME_PATTERNS),
    re.IGNORECASE,
)

# Extensions that are code, documentation, or output — never restricted data.
# Matching on these would produce false positives (e.g. census_*.Rd is R docs).
_SAFE_EXTENSIONS: frozenset[str] = frozenset({
    ".r", ".rmd", ".rd", ".rnw",           # R code/docs
    ".py", ".ipynb",                        # Python
    ".jl",                                  # Julia
    ".do", ".ado",                          # Stata code
    ".m",                                   # MATLAB
    ".tex", ".bib", ".cls", ".sty",        # LaTeX
    ".md", ".rst", ".txt", ".html",        # documentation
    ".toml", ".lock", ".json", ".yaml", ".yml",  # config/lockfiles
    ".log", ".out", ".aux", ".blg", ".bbl",      # build artifacts
    ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".eps",  # figures/output
    ".sh", ".bat",                          # shell scripts
})


def check_restricted(project_root: Path) -> RestrictedStatus:
    """
    Scan filenames and directory names only — no file contents read.
    Returns RestrictedStatus immediately on first match so the caller
    can gate further reads before processing begins.

    Code, documentation, and output file extensions are excluded from
    pattern matching to avoid false positives (e.g. census_add_toutain.Rd).
    """
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() in _SAFE_EXTENSIONS:
            continue

        stem = path.stem.lower()
        name = path.name.lower()

        if _RESTRICTED_RE.search(stem) or _RESTRICTED_RE.search(name):
            return RestrictedStatus(
                is_restricted=True,
                reason=f"Filename matches restricted data pattern: {path.name!r}",
                trigger_path=path,
            )

        if _DUA_RE.search(stem) or _DUA_RE.search(name):
            return RestrictedStatus(
                is_restricted=True,
                reason=f"Filename suggests a data use agreement or IRB document: {path.name!r}",
                trigger_path=path,
            )

    return RestrictedStatus(is_restricted=False)
