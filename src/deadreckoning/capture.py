"""Capture environment specification from project lockfiles."""

from __future__ import annotations

import json
import re
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
