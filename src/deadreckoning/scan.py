"""
SCAN step: read R scripts and extract packages, external paths, secrets,
and download URLs.  Pure reads — zero side effects.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from .models import DataFile


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# library(pkg), require(pkg), pkg::fun() — captures bare name or quoted
_LIBRARY_RE = re.compile(
    r'(?:library|require)\s*\(\s*["\']?([A-Za-z][A-Za-z0-9._]*)["\']?\s*\)',
)
_DOUBLE_COLON_RE = re.compile(r'\b([A-Za-z][A-Za-z0-9._]*)::')

# Absolute paths in strings (Unix + Windows UNC)
_ABS_PATH_RE = re.compile(
    r'"(/[^"\n]{4,})"'          # Unix absolute in double quotes
    r'|'
    r"'(/[^'\n]{4,})'"          # Unix absolute in single quotes
    r'|'
    r'"(//[^"\n]{4,})"'         # UNC share
    r'|'
    r'"([A-Za-z]:\\[^"\n]{3,})"'  # Windows C:\...
)

# Dropbox / OneDrive / Google Drive / iCloud / network / HPC / co-author indicators
_EXTERNAL_KIND_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[/\\]Dropbox[/\\]",        re.IGNORECASE), "dropbox"),
    (re.compile(r"[/\\]OneDrive[/\\]",       re.IGNORECASE), "onedrive"),
    (re.compile(r"[/\\]Google Drive[/\\]",   re.IGNORECASE), "google_drive"),
    (re.compile(r"[/\\]iCloud[/\\]",         re.IGNORECASE), "icloud"),
    (re.compile(r"^//",                       re.IGNORECASE), "network_share"),
    (re.compile(r"/scratch/|/work/|/hpc/|/cluster/", re.IGNORECASE), "hpc"),
    (re.compile(r"^https?://",               re.IGNORECASE), "url"),
    (re.compile(r"^ftp://",                  re.IGNORECASE), "url"),
]

# download.file(url, ...) — capture URL
_DOWNLOAD_RE = re.compile(
    r'download\.file\s*\(\s*["\']([^"\']+)["\']',
)

# Secret / credential file names
_SECRET_NAME_RE = re.compile(
    r'(?:^|[/\\])(?:'
    r'\.env'
    r'|.*\.pem'
    r'|.*\.key'
    r'|.*secret.*'
    r'|.*token.*'
    r'|.*credential.*'
    r'|.*password.*'
    r'|.*api[_-]?key.*'
    r')$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class ExternalPath(BaseModel):
    raw: str                    # literal string found in source
    script: Path
    line: int
    kind: str                   # dropbox / network_share / hpc / url / absolute_local / etc.
    as_data_file: DataFile


class SecretFile(BaseModel):
    path: Path
    reason: str


class DownloadCall(BaseModel):
    url: str
    script: Path
    line: int


class ScanResult(BaseModel):
    used_packages: list[str] = Field(default_factory=list)
    external_paths: list[ExternalPath] = Field(default_factory=list)
    secret_files: list[SecretFile] = Field(default_factory=list)
    download_calls: list[DownloadCall] = Field(default_factory=list)

    @property
    def has_external_paths(self) -> bool:
        return len(self.external_paths) > 0

    @property
    def has_secrets(self) -> bool:
        return len(self.secret_files) > 0


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def _classify_path(raw: str) -> str:
    for pattern, kind in _EXTERNAL_KIND_RULES:
        if pattern.search(raw):
            return kind
    return "absolute_local"


def scan_r_scripts(project_root: Path) -> ScanResult:
    """
    Scan all R scripts under project_root.

    Returns:
        ScanResult with packages, external paths, secret files, download URLs.

    No files are modified.  project_root must already have passed the
    confidentiality gate (check_restricted).
    """
    r_files = list(project_root.rglob("*.R")) + list(project_root.rglob("*.r"))

    packages: set[str] = set()
    external_paths: list[ExternalPath] = []
    download_calls: list[DownloadCall] = []

    for script in sorted(r_files):
        try:
            text = script.read_text(errors="replace")
        except OSError:
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            # Skip comment lines
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue

            # Package extraction
            for m in _LIBRARY_RE.finditer(line):
                packages.add(m.group(1))
            for m in _DOUBLE_COLON_RE.finditer(line):
                packages.add(m.group(1))

            # Absolute / external paths
            for m in _ABS_PATH_RE.finditer(line):
                raw = next(g for g in m.groups() if g is not None)
                kind = _classify_path(raw)
                external_paths.append(ExternalPath(
                    raw=raw,
                    script=script.relative_to(project_root),
                    line=line_no,
                    kind=kind,
                    as_data_file=DataFile(
                        path=Path(raw),
                        exists_on_disk=Path(raw).exists(),
                        referenced_by=[script.relative_to(project_root)],
                        is_external=True,
                        external_kind=kind,
                        url=raw if kind == "url" else None,
                    ),
                ))

            # download.file()
            for m in _DOWNLOAD_RE.finditer(line):
                download_calls.append(DownloadCall(
                    url=m.group(1),
                    script=script.relative_to(project_root),
                    line=line_no,
                ))

    # Secret file scan (filename only — no content read)
    secret_files: list[SecretFile] = []
    for p in project_root.rglob("*"):
        if p.is_file() and _SECRET_NAME_RE.search(p.name):
            secret_files.append(SecretFile(
                path=p.relative_to(project_root),
                reason=f"filename matches credential pattern: {p.name!r}",
            ))

    # Deduplicate packages, exclude base R
    _BASE_R = {"base", "methods", "stats", "utils", "graphics", "grDevices",
                "datasets", "tools", "grid", "splines", "parallel"}
    packages -= _BASE_R

    return ScanResult(
        used_packages=sorted(packages),
        external_paths=external_paths,
        secret_files=secret_files,
        download_calls=download_calls,
    )
