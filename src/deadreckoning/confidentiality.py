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


def check_restricted(project_root: Path) -> RestrictedStatus:
    """
    Scan filenames and directory names only — no file contents read.
    Returns RestrictedStatus immediately on first match so the caller
    can gate further reads before processing begins.
    """
    for path in project_root.rglob("*"):
        if not path.is_file():
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
