"""Capture environment specification from project lockfiles."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .models import EnvSpec, PackageSpec, PinMethod


def capture_env(project_root: Path) -> EnvSpec:
    """
    Detect and parse the environment spec from a project directory.

    Priority order:
      renv.lock        → R (high confidence)
      requirements.txt → Python (medium confidence)
      *.do files exist → Stata (low confidence — no lockfile standard)
      fallback         → unknown
    """
    renv_lock = project_root / "renv.lock"
    if renv_lock.exists():
        return _from_renv_lock(renv_lock)

    requirements = project_root / "requirements.txt"
    if requirements.exists():
        return _from_requirements_txt(requirements)

    do_files = list(project_root.rglob("*.do"))
    if do_files:
        from .stata import capture_stata_env
        return capture_stata_env(project_root)

    # R project without renv.lock — infer snapshot date from file mtimes / git
    r_files = list(project_root.rglob("*.R")) + list(project_root.rglob("*.r"))
    if r_files:
        return _r_inferred_from_date(project_root, r_files)

    return EnvSpec(language="unknown", confidence=0.0)


def _from_renv_lock(lockfile: Path) -> EnvSpec:
    data = json.loads(lockfile.read_text())

    r_section = data.get("R", {})
    r_version = r_section.get("Version")

    repos = r_section.get("Repositories", [])
    snapshot_url = next(
        (r["URL"] for r in repos if "packagemanager" in r.get("URL", "")),
        None,
    )
    snapshot_date = _extract_date_from_ppm_url(snapshot_url) if snapshot_url else None

    packages = [
        PackageSpec(
            name=pkg["Package"],
            version=pkg.get("Version"),
            pin_method=PinMethod.lockfile,
        )
        for pkg in data.get("Packages", {}).values()
    ]

    return EnvSpec(
        language="R",
        language_version=r_version,
        packages=packages,
        pin_method=PinMethod.lockfile,
        snapshot_date=snapshot_date,
        snapshot_url=snapshot_url,
        confidence=0.95,
    )


def _from_requirements_txt(requirements: Path) -> EnvSpec:
    packages = []
    for line in requirements.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Parse name==version or name>=version etc.
        m = re.match(r"^([A-Za-z0-9_.\-]+)(?:[>=<!]=?(.+))?$", line)
        if m:
            packages.append(
                PackageSpec(
                    name=m.group(1),
                    version=m.group(2),
                    pin_method=PinMethod.pip_freeze,
                )
            )
    return EnvSpec(
        language="Python",
        packages=packages,
        pin_method=PinMethod.pip_freeze,
        confidence=0.8,
    )


def _extract_date_from_ppm_url(url: str) -> str | None:
    """Extract ISO date from a PPM snapshot URL like .../cran/2025-01-15."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Date inference for R projects without renv.lock
# ---------------------------------------------------------------------------

_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _infer_date_from_rhistory(project_root: Path) -> str | None:
    """Parse the most recent date from .Rhistory timestamp lines."""
    rhistory = project_root / ".Rhistory"
    if not rhistory.exists():
        return None
    try:
        text = rhistory.read_text(errors="replace")
        dates = _ISO_DATE_RE.findall(text)
        return max(dates) if dates else None
    except OSError:
        return None


def _infer_date_from_git_log(project_root: Path) -> str | None:
    """Return date of the most recent commit in the project's own git repo."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            m = _ISO_DATE_RE.search(result.stdout)
            return m.group(0) if m else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _infer_date_from_file_mtimes(r_files: list[Path]) -> str | None:
    """Return ISO date of the most recently modified R script."""
    try:
        latest_ts = max(f.stat().st_mtime for f in r_files if f.exists())
        return datetime.fromtimestamp(latest_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OSError, ValueError):
        return None


def _r_inferred_from_date(project_root: Path, r_files: list[Path]) -> EnvSpec:
    """
    Build an EnvSpec for an R project with no renv.lock.

    Inference order (best to worst):
      1. .Rhistory timestamp
      2. git log of project's own repo
      3. latest R script mtime
    """
    snapshot_date = (
        _infer_date_from_rhistory(project_root)
        or _infer_date_from_git_log(project_root)
        or _infer_date_from_file_mtimes(r_files)
    )

    snapshot_url: str | None = None
    if snapshot_date:
        snapshot_url = f"https://packagemanager.posit.co/cran/{snapshot_date}"

    return EnvSpec(
        language="R",
        pin_method=PinMethod.inferred_from_date,
        snapshot_date=snapshot_date,
        snapshot_url=snapshot_url,
        confidence=0.4,
    )
