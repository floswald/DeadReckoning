"""MATLAB detection, advice, and native execution."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_CANDIDATES = ["matlab"]

# Glob patterns per platform — newest versions first via sort order
_KNOWN_DIRS: dict[str, list[str]] = {
    "darwin": [
        "/Applications/MATLAB_R2024b.app/bin",
        "/Applications/MATLAB_R2024a.app/bin",
        "/Applications/MATLAB_R2023b.app/bin",
        "/Applications/MATLAB_R2023a.app/bin",
        "/Applications/MATLAB_R2022b.app/bin",
        "/Applications/MATLAB_R2022a.app/bin",
        "/Applications/MATLAB_R2021b.app/bin",
        "/Applications/MATLAB_R2021a.app/bin",
        "/Applications/MATLAB_R2020b.app/bin",
        "/Applications/MATLAB_R2019b.app/bin",
    ],
    "linux": [
        "/usr/local/MATLAB/R2024b/bin",
        "/usr/local/MATLAB/R2024a/bin",
        "/usr/local/MATLAB/R2023b/bin",
        "/usr/local/MATLAB/R2023a/bin",
        "/usr/local/MATLAB/R2022b/bin",
        "/usr/local/MATLAB/R2022a/bin",
        "/usr/local/MATLAB/R2021b/bin",
        "/usr/local/MATLAB/R2021a/bin",
        "/usr/local/MATLAB/R2020b/bin",
        "/usr/local/MATLAB/R2019b/bin",
        "/opt/MATLAB/R2023b/bin",
        "/opt/MATLAB/R2022b/bin",
    ],
    "win32": [
        r"C:\Program Files\MATLAB\R2024b\bin",
        r"C:\Program Files\MATLAB\R2024a\bin",
        r"C:\Program Files\MATLAB\R2023b\bin",
        r"C:\Program Files\MATLAB\R2023a\bin",
        r"C:\Program Files\MATLAB\R2022b\bin",
        r"C:\Program Files\MATLAB\R2022a\bin",
        r"C:\Program Files\MATLAB\R2021b\bin",
        r"C:\Program Files\MATLAB\R2021a\bin",
    ],
}

# R2019b introduced -batch (exits non-zero on error); older needs -r + scanning
_BATCH_MIN_YEAR = 2019
_BATCH_MIN_HALF = "b"  # R2019b


@dataclass
class MatlabInstall:
    found: bool
    binary: str | None        # resolved binary path or name
    release: str | None       # e.g. "R2023b"
    on_path: bool
    hint_path: str | None     # dir found via known-path scan
    supports_batch: bool      # True if release >= R2019b
    advice: str | None


def detect_matlab() -> MatlabInstall:
    """
    Three-state detection:
      1. On PATH      → found=True, on_path=True
      2. Installed but not on PATH → found=True, on_path=False
      3. Not found    → found=False
    """
    # State 1: PATH
    binary = shutil.which("matlab")
    if binary:
        release = _release_from_binary(binary)
        return MatlabInstall(
            found=True, binary=binary, release=release,
            on_path=True, hint_path=None,
            supports_batch=_supports_batch(release),
            advice=None,
        )

    # State 2: known dirs
    platform = sys.platform
    search_dirs = _KNOWN_DIRS.get(platform, []) + _KNOWN_DIRS.get("linux", [])
    for dir_str in search_dirs:
        dir_path = Path(dir_str)
        exe = "matlab.exe" if platform == "win32" else "matlab"
        candidate = dir_path / exe
        if candidate.exists():
            release = _release_from_path(str(dir_path))
            return MatlabInstall(
                found=True, binary=str(candidate), release=release,
                on_path=False, hint_path=dir_str,
                supports_batch=_supports_batch(release),
                advice=_advice_not_on_path(dir_str, platform),
            )

    # State 3: not found
    return MatlabInstall(
        found=False, binary=None, release=None,
        on_path=False, hint_path=None,
        supports_batch=False,
        advice=_advice_not_found(platform),
    )


def _release_from_path(dir_str: str) -> str | None:
    """Extract R20XXx from a directory string."""
    m = re.search(r"(R\d{4}[ab])", dir_str)
    return m.group(1) if m else None


def _release_from_binary(binary: str) -> str | None:
    """Try to extract release from binary path, then from --version output."""
    release = _release_from_path(binary)
    if release:
        return release
    try:
        result = subprocess.run(
            [binary, "-batch", "disp(version('-release'))"],
            capture_output=True, text=True, timeout=30,
        )
        text = (result.stdout + result.stderr).strip()
        m = re.search(r"(R\d{4}[ab])", text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _supports_batch(release: str | None) -> bool:
    """-batch flag available from R2019b onward."""
    if release is None:
        return False
    m = re.match(r"R(\d{4})([ab])", release)
    if not m:
        return False
    year, half = int(m.group(1)), m.group(2)
    if year > _BATCH_MIN_YEAR:
        return True
    if year == _BATCH_MIN_YEAR and half >= _BATCH_MIN_HALF:
        return True
    return False


def _advice_not_on_path(matlab_dir: str, platform: str) -> str:
    if platform == "darwin":
        return (
            f"MATLAB found at {matlab_dir} but not on PATH.\n"
            f"Fix (add to ~/.zshrc or ~/.bashrc):\n"
            f'  export PATH="{matlab_dir}:$PATH"\n'
            f"Then restart your shell or run: source ~/.zshrc"
        )
    if platform == "linux":
        return (
            f"MATLAB found at {matlab_dir} but not on PATH.\n"
            f"Fix:\n"
            f'  export PATH="{matlab_dir}:$PATH"\n'
            f"Or check: module avail matlab"
        )
    return f"MATLAB found at {matlab_dir} but not on PATH. Add that directory to your PATH."


def _advice_not_found(platform: str) -> str:
    base = (
        "MATLAB not found. Checked PATH and common install locations.\n\n"
        "Options:\n"
        "  1. Install MATLAB: https://www.mathworks.com/products/matlab.html\n"
        "  2. On HPC/cluster: run `module load matlab` before executing\n"
        "  3. If installed elsewhere, add its bin/ directory to PATH\n"
        "  4. For Docker: use mathworks/matlab image with -browser flag\n"
        "     (requires MathWorks account + cloud-enabled license)\n"
    )
    if platform == "darwin":
        base += (
            "\nCommon macOS locations:\n"
            "  /Applications/MATLAB_R2023b.app/bin\n"
            "  /Applications/MATLAB_R2024a.app/bin"
        )
    elif platform == "linux":
        base += (
            "\nCommon Linux locations:\n"
            "  /usr/local/MATLAB/R2023b/bin\n"
            "  /opt/MATLAB/R2023b/bin"
        )
    return base


# ---------------------------------------------------------------------------
# Native runner
# ---------------------------------------------------------------------------

@dataclass
class MatlabRunResult:
    returncode: int
    stdout: str
    stderr: str
    log_has_error: bool   # error pattern found in output
    error_snippet: str | None  # first matching error line

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.log_has_error


# Patterns that indicate a MATLAB error in output (used for -r fallback mode)
_ERROR_RE = re.compile(
    r"^(Error |Unrecognized |Undefined |Index exceeds |Cannot |Invalid )",
    re.MULTILINE,
)


def run_matlab(
    project_root: Path,
    master_script: str,
    binary: str,
    supports_batch: bool = True,
) -> MatlabRunResult:
    """
    Run a MATLAB script natively.

    R2019b+: `matlab -batch "run('script.m')"` — exits non-zero on error.
    Older:   `matlab -nosplash -nodesktop -r "run('script.m'); exit"` — always
             exits 0, so we scan stdout/stderr for error patterns.
    """
    if supports_batch:
        cmd = [binary, "-batch", f"run('{master_script}')"]
    else:
        cmd = [
            binary, "-nosplash", "-nodesktop", "-nodisplay",
            "-r", f"run('{master_script}'); exit",
        ]

    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr
    error_match = _ERROR_RE.search(combined)
    log_has_error = error_match is not None
    error_snippet = error_match.group(0).strip() if error_match else None

    # For -batch mode: non-zero return already signals failure, but scan
    # output anyway to surface a readable snippet.
    if not supports_batch and result.returncode != 0:
        log_has_error = True

    return MatlabRunResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        log_has_error=log_has_error,
        error_snippet=error_snippet,
    )
