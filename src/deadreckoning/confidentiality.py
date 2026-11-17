"""Confidentiality gate: must run before any file content is read."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .models import RestrictedStatus

# Filename fragments that indicate restricted data
_RESTRICTED_NAME_PATTERNS: list[str] = [
    "restricted", "confidential", "nda", "hipaa", "pii",
    "microdata", "census", "irs", "hmda",
    "nlsy", "psid", "sipp", "acs_pums",
]

# "admin" alone is too broad a substring — it also matches public reference
# datasets whose names merely contain it (e.g. IGN's AdminExpress French
# administrative-boundary files: ign_metropole_adminexpress_chefs_lieux_z.prj).
# Only treat it as a restricted-data signal when adjacent to an actual
# data/records marker, which is how real admin-microdata files are named
# (admin_data.dta, SSA_admin_records.csv, administrative_microdata.dta).
_RESTRICTED_CONTEXTUAL_PATTERNS: list[str] = [
    r"admin(?:istrative)?[_-]?(?:data|records?|microdata|panel)",
]

# Filenames that suggest a DUA or ethics document is present
_DUA_NAME_PATTERNS: list[str] = [
    "data_use_agreement", "dua", "irb", "ethics_approval",
    "data_access_agreement", "nda",
]

_RESTRICTED_RE = re.compile(
    "|".join(re.escape(p) for p in _RESTRICTED_NAME_PATTERNS)
    + "|" + "|".join(_RESTRICTED_CONTEXTUAL_PATTERNS),
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


def parse_yes_no(raw: str) -> bool:
    """Shared yes/no parsing for interactive author prompts (restricted-hit
    re-ask, per-fix approval, ...). Keeps the accepted spellings in one place."""
    return raw.strip().lower() in ("y", "yes", "true", "1")


def confirm_restricted_hit(
    restricted: RestrictedStatus,
    *,
    answer: Optional[bool] = None,
    _input_fn=input,
) -> bool:
    """
    §4.2 — re-ask the author about a filename-heuristic hit; never trust
    the heuristic on its own.

    A filename match (``census``, ``psid``, ``nda``, ...) is a *lead*,
    not proof — plenty of legitimate public-use extracts are named this
    way. So when the author already said "no" to the up-front question
    but the scan later finds something suspicious, this asks again,
    specifically, rather than silently flipping into restricted mode.

    Parameters
    ----------
    restricted : RestrictedStatus
        Result of `check_restricted`. If not `is_restricted`, this is a
        no-op — there's nothing to confirm.
    answer : bool | None
        Pre-supplied answer (CI / `--restricted-override`): True = author
        confirms this really is restricted; False = confirmed false
        positive. None = prompt interactively.
    _input_fn : callable
        Override for `input()`; used in tests to avoid stdin.

    Returns
    -------
    bool
        True if the data should be treated as restricted (abort), False
        if the author confirmed this specific hit is not restricted data
        and the pipeline may proceed.
    """
    if not restricted.is_restricted:
        return False

    if answer is not None:
        return answer

    prompt = (
        f"\n[dr] I found something that may indicate restricted data: {restricted.reason}\n"
        "  This alone isn't proof — plenty of legitimate public-use data is named this way.\n"
        "  Before I read any data files, please confirm: is this covered by a data use\n"
        "  agreement, IRB protocol, or NDA? Answer yes/no: "
    )
    raw = _input_fn(prompt)
    return parse_yes_no(raw)
