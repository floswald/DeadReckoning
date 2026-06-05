"""
SCAN step: extract packages, external paths, secrets, and download URLs
from all scripts. Pure reads — zero side effects.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from .models import DataFile


# ---------------------------------------------------------------------------
# Shared patterns
# ---------------------------------------------------------------------------

# Absolute paths in strings (Unix + Windows UNC)
_ABS_PATH_RE = re.compile(
    r'"(/[^"\n]{4,})"'               # Unix absolute in double quotes
    r'|'
    r"'(/[^'\n]{4,})'"               # Unix absolute in single quotes
    r'|'
    r'"(//[^"\n]{4,})"'              # UNC share
    r'|'
    r'"([A-Za-z]:\\[^"\n]{3,})"'    # Windows C:\...
)

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
# R patterns
# ---------------------------------------------------------------------------

_LIBRARY_RE = re.compile(
    r'(?:library|require)\s*\(\s*["\']?([A-Za-z][A-Za-z0-9._]*)["\']?\s*\)',
)
_DOUBLE_COLON_RE = re.compile(r'\b([A-Za-z][A-Za-z0-9._]*)::')
_DOWNLOAD_RE = re.compile(
    r'download\.file\s*\(\s*["\']([^"\']+)["\']',
)

_BASE_R = {
    "base", "methods", "stats", "utils", "graphics", "grDevices",
    "datasets", "tools", "grid", "splines", "parallel",
}


# ---------------------------------------------------------------------------
# Python patterns
# ---------------------------------------------------------------------------

_PY_IMPORT_RE = re.compile(
    r'^[ \t]*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)',
    re.MULTILINE,
)

_PY_DOWNLOAD_RE = re.compile(
    r'(?:urlretrieve|requests\.(?:get|post)|urlopen)\s*\(\s*["\']([^"\']+)["\']',
)

_PYTHON_STDLIB = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio", "asyncore",
    "atexit", "audioop", "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
    "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs",
    "codeop", "collections", "colorsys", "compileall", "concurrent", "configparser",
    "contextlib", "contextvars", "copy", "copyreg", "csv", "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis", "distutils",
    "doctest", "email", "encodings", "enum", "errno", "faulthandler", "fcntl",
    "filecmp", "fileinput", "fnmatch", "fractions", "ftplib", "functools", "gc",
    "getopt", "getpass", "gettext", "glob", "grp", "gzip", "hashlib", "heapq",
    "hmac", "html", "http", "idlelib", "imaplib", "importlib", "inspect", "io",
    "ipaddress", "itertools", "json", "keyword", "linecache", "locale", "logging",
    "lzma", "mailbox", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
    "netrc", "numbers", "operator", "optparse", "os", "pathlib", "pdb", "pickle",
    "pickletools", "pipes", "pkgutil", "platform", "plistlib", "poplib", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue",
    "quopri", "random", "re", "readline", "reprlib", "resource", "runpy", "sched",
    "secrets", "select", "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtplib", "socket", "socketserver", "sqlite3", "ssl", "stat", "statistics",
    "string", "stringprep", "struct", "subprocess", "sys", "sysconfig", "tarfile",
    "tempfile", "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "types", "typing",
    "unicodedata", "unittest", "urllib", "uuid", "venv", "warnings", "wave",
    "weakref", "webbrowser", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport",
    "zlib", "zoneinfo", "__future__", "_thread",
}


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class ExternalPath(BaseModel):
    raw: str
    script: Path
    line: int
    kind: str
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
# Shared helpers
# ---------------------------------------------------------------------------


def _classify_path(raw: str) -> str:
    for pattern, kind in _EXTERNAL_KIND_RULES:
        if pattern.search(raw):
            return kind
    return "absolute_local"


def _scan_secrets(project_root: Path) -> list[SecretFile]:
    """Filename-only scan — no file content read."""
    result: list[SecretFile] = []
    for p in project_root.rglob("*"):
        if p.is_file() and _SECRET_NAME_RE.search(p.name):
            result.append(SecretFile(
                path=p.relative_to(project_root),
                reason=f"filename matches credential pattern: {p.name!r}",
            ))
    return result


def _extract_external_paths(
    text: str,
    script: Path,
    project_root: Path,
) -> list[ExternalPath]:
    results: list[ExternalPath] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
            continue
        for m in _ABS_PATH_RE.finditer(line):
            raw = next(g for g in m.groups() if g is not None)
            kind = _classify_path(raw)
            results.append(ExternalPath(
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
    return results


# ---------------------------------------------------------------------------
# R scanner
# ---------------------------------------------------------------------------


def _scan_r_internals(
    project_root: Path,
) -> tuple[set[str], list[ExternalPath], list[DownloadCall]]:
    r_files = list(project_root.rglob("*.R")) + list(project_root.rglob("*.r"))
    packages: set[str] = set()
    external_paths: list[ExternalPath] = []
    download_calls: list[DownloadCall] = []

    for script in sorted(r_files):
        try:
            text = script.read_text(errors="replace")
        except OSError:
            continue

        external_paths.extend(_extract_external_paths(text, script, project_root))

        for line_no, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for m in _LIBRARY_RE.finditer(line):
                packages.add(m.group(1))
            for m in _DOUBLE_COLON_RE.finditer(line):
                packages.add(m.group(1))
            for m in _DOWNLOAD_RE.finditer(line):
                download_calls.append(DownloadCall(
                    url=m.group(1),
                    script=script.relative_to(project_root),
                    line=line_no,
                ))

    packages -= _BASE_R
    return packages, external_paths, download_calls


def scan_r_scripts(project_root: Path) -> ScanResult:
    """Scan all R scripts. Backward-compatible entry point."""
    packages, external_paths, download_calls = _scan_r_internals(project_root)
    return ScanResult(
        used_packages=sorted(packages),
        external_paths=external_paths,
        secret_files=_scan_secrets(project_root),
        download_calls=download_calls,
    )


# ---------------------------------------------------------------------------
# Python scanner
# ---------------------------------------------------------------------------


def _scan_python_internals(
    project_root: Path,
) -> tuple[set[str], list[ExternalPath], list[DownloadCall]]:
    py_files = list(project_root.rglob("*.py"))
    packages: set[str] = set()
    external_paths: list[ExternalPath] = []
    download_calls: list[DownloadCall] = []

    for script in sorted(py_files):
        try:
            text = script.read_text(errors="replace")
        except OSError:
            continue

        external_paths.extend(_extract_external_paths(text, script, project_root))

        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for m in _PY_IMPORT_RE.finditer(line):
                raw = m.group(1) or m.group(2)
                if raw:
                    pkg = raw.split(".")[0]
                    packages.add(pkg)
            for m in _PY_DOWNLOAD_RE.finditer(line):
                download_calls.append(DownloadCall(
                    url=m.group(1),
                    script=script.relative_to(project_root),
                    line=line_no,
                ))

    packages -= _PYTHON_STDLIB
    return packages, external_paths, download_calls


def scan_python_scripts(project_root: Path) -> ScanResult:
    """Scan all Python scripts."""
    packages, external_paths, download_calls = _scan_python_internals(project_root)
    return ScanResult(
        used_packages=sorted(packages),
        external_paths=external_paths,
        secret_files=_scan_secrets(project_root),
        download_calls=download_calls,
    )


# ---------------------------------------------------------------------------
# Stata scanner
# ---------------------------------------------------------------------------


def _scan_stata_internals(
    project_root: Path,
) -> tuple[set[str], list[ExternalPath]]:
    """Extract packages (from ssc/net install) and external paths from .do files."""
    do_files = list(project_root.rglob("*.do"))
    packages: set[str] = set()
    external_paths: list[ExternalPath] = []

    _SSC_RE = re.compile(r"^\s*ssc\s+install\s+(\S+)", re.MULTILINE | re.IGNORECASE)
    _NET_RE = re.compile(r"^\s*net\s+install\s+(\S+)", re.MULTILINE | re.IGNORECASE)

    for script in sorted(do_files):
        try:
            text = script.read_text(errors="replace")
        except OSError:
            continue
        external_paths.extend(_extract_external_paths(text, script, project_root))
        for m in _SSC_RE.finditer(text):
            packages.add(m.group(1).strip(",").strip('"').strip("'"))
        for m in _NET_RE.finditer(text):
            packages.add(m.group(1).strip(",").strip('"').strip("'"))

    return packages, external_paths


def scan_stata_scripts(project_root: Path) -> ScanResult:
    """Scan all Stata .do scripts."""
    pkgs, paths = _scan_stata_internals(project_root)
    return ScanResult(
        used_packages=sorted(pkgs),
        external_paths=paths,
        secret_files=_scan_secrets(project_root),
    )


# ---------------------------------------------------------------------------
# Combined multi-language scanner
# ---------------------------------------------------------------------------


def scan_scripts(project_root: Path) -> ScanResult:
    """
    Scan all scripts across supported languages (R, Python, Stata).
    Returns a single merged ScanResult. Secret scan runs once.
    """
    r_pkgs, r_paths, r_dl = _scan_r_internals(project_root)
    py_pkgs, py_paths, py_dl = _scan_python_internals(project_root)
    stata_pkgs, stata_paths = _scan_stata_internals(project_root)

    all_packages = sorted(r_pkgs | py_pkgs | stata_pkgs)
    all_paths = r_paths + py_paths + stata_paths
    all_downloads = r_dl + py_dl

    return ScanResult(
        used_packages=all_packages,
        external_paths=all_paths,
        secret_files=_scan_secrets(project_root),
        download_calls=all_downloads,
    )
