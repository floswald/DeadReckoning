"""Stata detection, advice, native execution, and env capture."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .models import EnvSpec, PackageSpec, PinMethod

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_CANDIDATES = ["stata", "stata-mp", "stata-se", "stata-be", "StataMP", "StataSE", "StataBE"]

_KNOWN_PATHS = {
    "darwin": [
        "/Applications/Stata/StataMP.app/Contents/MacOS",
        "/Applications/Stata/StataSE.app/Contents/MacOS",
        "/Applications/Stata/StataBE.app/Contents/MacOS",
        "/Applications/StataNow/StataMP.app/Contents/MacOS",
        "/Applications/StataNow/StataSE.app/Contents/MacOS",
        "/Applications/StataNow/StataBE.app/Contents/MacOS",
        "/Applications/Stata18/StataMP.app/Contents/MacOS",
        "/Applications/Stata18/StataSE.app/Contents/MacOS",
        "/Applications/Stata17/StataMP.app/Contents/MacOS",
        "/Applications/Stata17/StataSE.app/Contents/MacOS",
    ],
    "linux": [
        "/usr/local/stata",
        "/usr/local/stata18",
        "/usr/local/stata17",
        "/opt/stata",
        "/opt/stata18",
    ],
    "win32": [
        r"C:\Program Files\Stata19",
        r"C:\Program Files\Stata18",
        r"C:\Program Files\Stata17",
    ],
}


@dataclass
class StataInstall:
    found: bool
    binary: str | None          # resolved binary name or path
    flavor: str | None          # "MP", "SE", "BE", "IC", or None
    version: str | None         # e.g. "19.5"
    on_path: bool               # True if found via PATH lookup
    hint_path: str | None       # dir found via known-path scan (not on PATH)
    advice: str | None          # human-readable fix when not usable


def detect_stata() -> StataInstall:
    """
    Three-state detection:
      1. On PATH     → found=True, on_path=True
      2. Installed but not on PATH → found=True, on_path=False, advice has the fix
      3. Not found   → found=False, advice explains options
    """
    # State 1: check PATH candidates
    for name in _CANDIDATES:
        binary = shutil.which(name)
        if binary:
            flavor = _flavor_from_name(name)
            version = _query_version(binary)
            return StataInstall(
                found=True, binary=binary, flavor=flavor,
                version=version, on_path=True,
                hint_path=None, advice=None,
            )

    # State 2: check known install locations
    import sys
    platform = sys.platform
    search_dirs = _KNOWN_PATHS.get(platform, []) + _KNOWN_PATHS.get("linux", [])
    for dir_str in search_dirs:
        dir_path = Path(dir_str)
        if not dir_path.exists():
            continue
        for name in _CANDIDATES:
            candidate = dir_path / name
            if candidate.exists():
                flavor = _flavor_from_name(name)
                version = _query_version(str(candidate))
                advice = _advice_not_on_path(str(dir_path), platform)
                return StataInstall(
                    found=True, binary=str(candidate), flavor=flavor,
                    version=version, on_path=False,
                    hint_path=str(dir_path), advice=advice,
                )

    # State 3: not found
    return StataInstall(
        found=False, binary=None, flavor=None,
        version=None, on_path=False,
        hint_path=None,
        advice=_advice_not_found(platform),
    )


def _flavor_from_name(name: str) -> str | None:
    name_upper = name.upper()
    if "MP" in name_upper:
        return "MP"
    if "SE" in name_upper:
        return "SE"
    if "BE" in name_upper:
        return "BE"
    if "IC" in name_upper:
        return "IC"
    return None


def _query_version(binary: str) -> str | None:
    """Try to extract version string from `stata --version` or log header."""
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        for line in (result.stdout + result.stderr).splitlines():
            m = re.search(r"Stata(?:Now)?\s+(\d+(?:\.\d+)?)", line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def _advice_not_on_path(stata_dir: str, platform: str) -> str:
    if platform == "darwin":
        return (
            f"Stata found at {stata_dir} but not on PATH.\n"
            f"Fix (add to ~/.zshrc or ~/.bashrc):\n"
            f'  export PATH="{stata_dir}:$PATH"\n'
            f"Then restart your shell or run: source ~/.zshrc"
        )
    if platform == "linux":
        return (
            f"Stata found at {stata_dir} but not on PATH.\n"
            f"Fix:\n"
            f'  export PATH="{stata_dir}:$PATH"\n'
            f"Or check if a module is available: module avail stata"
        )
    return f"Stata found at {stata_dir} but not on PATH. Add that directory to your PATH."


def _advice_not_found(platform: str) -> str:
    base = (
        "Stata not found. Checked PATH and common install locations.\n\n"
        "Options:\n"
        "  1. Install Stata: https://www.stata.com/order/\n"
        "  2. On HPC/cluster: run `module load stata` before executing\n"
        "  3. If installed elsewhere, add its directory to PATH\n"
    )
    if platform == "darwin":
        base += (
            "\nCommon macOS locations:\n"
            "  /Applications/Stata/StataMP.app/Contents/MacOS\n"
            "  /Applications/StataNow/StataMP.app/Contents/MacOS"
        )
    elif platform == "linux":
        base += (
            "\nCommon Linux locations:\n"
            "  /usr/local/stata\n"
            "  /usr/local/stata18"
        )
    return base


# ---------------------------------------------------------------------------
# Native runner
# ---------------------------------------------------------------------------

@dataclass
class StataRunResult:
    returncode: int      # always 0 from Stata batch — use log_has_error
    log_path: Path | None
    log_has_error: bool  # True if r(\d+); found in log
    error_code: int | None
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.log_has_error


_R_CODE_RE = re.compile(r"^r\((\d+)\);", re.MULTILINE)


def run_stata(
    project_root: Path,
    master_script: str,
    binary: str,
) -> StataRunResult:
    """
    Run `binary -b do master_script` with cwd=project_root.

    Stata batch always exits 0 — scan the log for r(N); to detect failure.
    Log is written to <project_root>/<basename(master_script)>.log.
    """
    result = subprocess.run(
        [binary, "-b", "do", master_script],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    script_basename = Path(master_script).stem
    log_path = project_root / f"{script_basename}.log"

    log_has_error = False
    error_code = None
    if log_path.exists():
        log_text = log_path.read_text(errors="replace")
        m = _R_CODE_RE.search(log_text)
        if m:
            log_has_error = True
            error_code = int(m.group(1))

    return StataRunResult(
        returncode=result.returncode,
        log_path=log_path,
        log_has_error=log_has_error,
        error_code=error_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


# ---------------------------------------------------------------------------
# Env capture — parse ssc/net install from .do files
# ---------------------------------------------------------------------------

_SSC_RE = re.compile(r"^\s*ssc\s+install\s+(\S+)", re.MULTILINE | re.IGNORECASE)
_NET_RE = re.compile(r"^\s*net\s+install\s+(\S+)", re.MULTILINE | re.IGNORECASE)
_COMMENT_LINE_RE = re.compile(r"^\s*\*.*$", re.MULTILINE)
_INLINE_COMMENT_RE = re.compile(r"//.*$", re.MULTILINE)


def generate_config_do(packages: list[str]) -> str:
    """
    Generate _config.do content.

    Redirects PLUS/PERSONAL sysdir to project-local code/ado/ so that
    user-written ado-files are installed inside the project tree (not the
    system Stata dir). All master scripts should call `do _config.do` first.

    This is safe to run repeatedly — `ssc install X, replace` is idempotent.
    """
    lines = [
        "* _config.do — generated by DeadReckoning",
        "* Run this before any analysis script to install required ado-files.",
        'capture mkdir "code/ado/"',
        'sysdir set PLUS     "code/ado/"',
        'sysdir set PERSONAL "code/ado/"',
        "",
    ]
    if packages:
        lines.append("* Install required user-written packages")
        for pkg in sorted(packages):
            lines.append(f'ssc install {pkg}, replace')
    return "\n".join(lines) + "\n"


def write_config_do(working_copy: Path, packages: list[str]) -> Path:
    """Write _config.do to working_copy/code/_config.do. Returns path."""
    code_dir = working_copy / "code"
    code_dir.mkdir(exist_ok=True)
    config_path = code_dir / "_config.do"
    config_path.write_text(generate_config_do(packages))
    return config_path


def capture_stata_env(project_root: Path) -> EnvSpec:
    """
    Parse Stata env from .do files — no lockfile equivalent exists.

    Collects: Stata version (from binary if available), packages declared via
    `ssc install` or `net install` in any .do file.
    Confidence is low: Stata has no standard lockfile.
    """
    install = detect_stata()
    version = install.version if install.found else None

    do_files = list(project_root.rglob("*.do"))
    packages: list[PackageSpec] = []
    seen: set[str] = set()

    for do_file in do_files:
        try:
            text = do_file.read_text(errors="replace")
        except OSError:
            continue
        # Strip comments before scanning
        text = _COMMENT_LINE_RE.sub("", text)
        text = _INLINE_COMMENT_RE.sub("", text)
        for m in _SSC_RE.finditer(text):
            name = m.group(1).strip(",").strip('"').strip("'")
            if name not in seen:
                seen.add(name)
                packages.append(PackageSpec(name=name, version=None, pin_method=PinMethod.unknown))
        for m in _NET_RE.finditer(text):
            name = m.group(1).strip(",").strip('"').strip("'")
            if name not in seen:
                seen.add(name)
                packages.append(PackageSpec(name=name, version=None, pin_method=PinMethod.unknown))

    return EnvSpec(
        language="Stata",
        language_version=version,
        packages=packages,
        pin_method=PinMethod.unknown,
        confidence=0.3,  # no lockfile → always low confidence
    )
