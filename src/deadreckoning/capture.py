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
      renv.lock          → R (high confidence)
      environment.yml    → Python conda
      requirements.txt   → Python pip_freeze
      pyproject.toml     → Python pyproject
      *.do files exist   → Stata (low confidence — no lockfile standard)
      *.R files, no lock → R inferred from date
      *.py files, no env → Python inferred from date
      fallback           → unknown
    """
    renv_lock = project_root / "renv.lock"
    if renv_lock.exists():
        return _from_renv_lock(renv_lock)

    manifest_toml = project_root / "Manifest.toml"
    if manifest_toml.exists():
        return _from_manifest_toml(manifest_toml)

    project_toml = project_root / "Project.toml"
    if project_toml.exists():
        return _from_project_toml(project_toml)

    env_yml = project_root / "environment.yml"
    if env_yml.exists():
        return _from_environment_yml(env_yml)

    requirements = project_root / "requirements.txt"
    if requirements.exists():
        return _from_requirements_txt(requirements)

    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        return _from_pyproject_toml(pyproject)

    do_files = list(project_root.rglob("*.do"))
    if do_files:
        from .stata import capture_stata_env
        return capture_stata_env(project_root)

    # R package with DESCRIPTION — extract declared Imports
    description = project_root / "DESCRIPTION"
    if description.exists():
        r_files = list(project_root.rglob("*.R")) + list(project_root.rglob("*.r"))
        return _from_description(description, project_root, r_files)

    # R project without renv.lock — infer snapshot date from file mtimes / git
    r_files = list(project_root.rglob("*.R")) + list(project_root.rglob("*.r"))
    if r_files:
        return _r_inferred_from_date(project_root, r_files)

    # Julia project without Manifest.toml
    jl_files = list(project_root.rglob("*.jl"))
    if jl_files:
        return _julia_inferred_from_date(project_root, jl_files)

    # Python project without any env file
    py_files = list(project_root.rglob("*.py"))
    if py_files:
        return _python_inferred_from_date(project_root, py_files)

    # MATLAB project — no lockfile standard; infer from mtime/git
    m_files = list(project_root.rglob("*.m"))
    if m_files:
        return _matlab_inferred_from_date(project_root, m_files)

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


def _from_environment_yml(env_yml: Path) -> EnvSpec:
    """Parse conda environment.yml — no PyYAML needed."""
    packages: list[PackageSpec] = []
    in_deps = False
    in_pip = False

    for raw_line in env_yml.read_text(errors="replace").splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("#"):
            continue

        if line.lstrip().startswith("dependencies:"):
            in_deps = True
            in_pip = False
            continue

        if in_deps:
            stripped = line.lstrip()
            # Top-level list item under dependencies
            if re.match(r"^- ", stripped):
                entry = stripped[2:].strip()
                if entry == "pip:":
                    in_pip = True
                    continue
                in_pip = False
                # Skip python itself
                if re.match(r"^python[=<>!]", entry, re.IGNORECASE):
                    continue
                m = re.match(r"^([A-Za-z0-9_.\-]+)(?:[=<>!].+)?$", entry)
                if m:
                    name = m.group(1)
                    ver_m = re.search(r"[=<>!]+\s*([^\s,]+)", entry)
                    packages.append(PackageSpec(
                        name=name,
                        version=ver_m.group(1) if ver_m else None,
                        pin_method=PinMethod.conda_export,
                    ))
            elif in_pip and re.match(r"^- ", stripped):
                entry = stripped[2:].strip()
                m = re.match(r"^([A-Za-z0-9_.\-]+)(?:[=<>!].+)?$", entry)
                if m:
                    ver_m = re.search(r"[=<>!]+\s*([^\s,]+)", entry)
                    packages.append(PackageSpec(
                        name=m.group(1),
                        version=ver_m.group(1) if ver_m else None,
                        pin_method=PinMethod.pip_freeze,
                    ))
            elif not stripped.startswith("-") and ":" in line and not in_pip:
                # New top-level key — exit deps
                if not line.startswith(" ") and not line.startswith("\t"):
                    in_deps = False

    return EnvSpec(
        language="Python",
        packages=packages,
        pin_method=PinMethod.conda_export,
        confidence=0.85,
    )


def _from_pyproject_toml(pyproject: Path) -> EnvSpec:
    """Parse pyproject.toml — handles [project] and [tool.poetry.dependencies]."""
    text = pyproject.read_text(errors="replace")
    packages: list[PackageSpec] = []

    try:
        import tomllib  # type: ignore[import]
        data = tomllib.loads(text)
    except ImportError:
        data = _parse_toml_simple(text)

    # [project] dependencies (PEP 621)
    project = data.get("project", {})
    for dep in project.get("dependencies", []):
        m = re.match(r"^([A-Za-z0-9_.\-]+)(?:[=<>!;].+)?$", dep.strip())
        if m:
            name = m.group(1)
            ver_m = re.search(r"[=<>!]=?\s*([0-9][^\s,;]*)", dep)
            packages.append(PackageSpec(
                name=name,
                version=ver_m.group(1) if ver_m else None,
                pin_method=PinMethod.pyproject,
            ))

    # [tool.poetry.dependencies]
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for name, val in poetry_deps.items():
        if name.lower() == "python":
            continue
        ver = val if isinstance(val, str) else (val.get("version") if isinstance(val, dict) else None)
        packages.append(PackageSpec(
            name=name,
            version=ver,
            pin_method=PinMethod.pyproject,
        ))

    return EnvSpec(
        language="Python",
        packages=packages,
        pin_method=PinMethod.pyproject,
        confidence=0.85,
    )


def _parse_toml_simple(text: str) -> dict:
    """
    Minimal TOML parser — handles string values and array-of-strings only.
    Falls back for pyproject.toml when tomllib is unavailable (Python < 3.11).
    """
    data: dict = {}
    current_table: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Table header: [foo.bar]
        m = re.match(r"^\[([^\[\]]+)\]$", line)
        if m:
            current_table = [part.strip() for part in m.group(1).split(".")]
            _nested_set(data, current_table, {})
            continue
        # Array of strings: key = ["a", "b"]
        m = re.match(r'^(\w+)\s*=\s*\[([^\]]*)\]', line)
        if m:
            key = m.group(1)
            items = re.findall(r'"([^"]*)"', m.group(2))
            _nested_setkey(data, current_table, key, items)
            continue
        # String value: key = "value"
        m = re.match(r'^(\w+)\s*=\s*"([^"]*)"', line)
        if m:
            _nested_setkey(data, current_table, m.group(1), m.group(2))

    return data


def _nested_set(d: dict, keys: list[str], val) -> None:
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d.setdefault(keys[-1], val)


def _nested_setkey(d: dict, table: list[str], key: str, val) -> None:
    node = d
    for k in table:
        node = node.setdefault(k, {})
    node[key] = val


def _from_manifest_toml(manifest: Path) -> EnvSpec:
    """Parse Julia Manifest.toml (lockfile — high confidence)."""
    text = manifest.read_text(errors="replace")
    try:
        import tomllib  # type: ignore[import]
        data = tomllib.loads(text)
    except ImportError:
        data = _parse_toml_simple(text)

    packages: list[PackageSpec] = []
    # Julia 1.7+ format: [[deps.PackageName]] sections
    # Simple approach: extract all package names from [[deps.X]] headers
    # and version = "X.Y.Z" lines
    seen: set[str] = set()

    # Try structured parse first
    deps = data.get("deps", {})
    for name, entries in deps.items():
        if name in seen:
            continue
        seen.add(name)
        version = None
        if isinstance(entries, list) and entries:
            version = entries[0].get("version") if isinstance(entries[0], dict) else None
        elif isinstance(entries, dict):
            version = entries.get("version")
        packages.append(PackageSpec(
            name=name,
            version=version,
            pin_method=PinMethod.manifest_toml,
        ))

    # Fallback: regex parse for [[deps.X]] + version = "..."
    if not packages:
        current_pkg: str | None = None
        for line in text.splitlines():
            m = re.match(r'^\[\[deps\.([^\]]+)\]\]', line)
            if m:
                current_pkg = m.group(1)
                if current_pkg not in seen:
                    seen.add(current_pkg)
                    packages.append(PackageSpec(
                        name=current_pkg,
                        pin_method=PinMethod.manifest_toml,
                    ))
            elif current_pkg:
                vm = re.match(r'^version\s*=\s*"([^"]+)"', line)
                if vm:
                    for p in packages:
                        if p.name == current_pkg and p.version is None:
                            p.version = vm.group(1)

    return EnvSpec(
        language="Julia",
        packages=packages,
        pin_method=PinMethod.manifest_toml,
        confidence=0.95,
    )


def _from_project_toml(project_toml: Path) -> EnvSpec:
    """Parse Julia Project.toml (no exact versions, but lists direct deps)."""
    text = project_toml.read_text(errors="replace")
    try:
        import tomllib  # type: ignore[import]
        data = tomllib.loads(text)
    except ImportError:
        data = _parse_toml_simple(text)

    packages: list[PackageSpec] = []
    deps = data.get("deps", {})
    for name in deps:
        packages.append(PackageSpec(
            name=name,
            version=None,
            pin_method=PinMethod.manifest_toml,
        ))

    return EnvSpec(
        language="Julia",
        packages=packages,
        pin_method=PinMethod.manifest_toml,
        confidence=0.7,  # Project.toml has deps but no exact versions
    )


def _julia_inferred_from_date(project_root: Path, jl_files: list[Path]) -> EnvSpec:
    """EnvSpec for Julia project with no Manifest.toml."""
    snapshot_date = (
        _infer_date_from_git_log(project_root)
        or _infer_date_from_file_mtimes(jl_files)
    )
    return EnvSpec(
        language="Julia",
        pin_method=PinMethod.inferred_from_date,
        snapshot_date=snapshot_date,
        confidence=0.3,
    )


_MATLAB_DOCKER_ADVICE = (
    "MATLAB requires a MathWorks account and interactive login on first container run. "
    "Use the mathworks/matlab Docker image with the -browser flag:\n"
    "  docker run --rm -it -p 8888:8888 mathworks/matlab -browser\n"
    "After first-run authentication the license is cached. "
    "Subsequent non-interactive runs work with:\n"
    "  docker run --rm mathworks/matlab -batch \"run('code/run.m')\"\n"
    "Toolboxes must be licensed and declared in the project README."
)


def _matlab_inferred_from_date(project_root: Path, m_files: list[Path]) -> EnvSpec:
    """EnvSpec for MATLAB project — no lockfile, infer date from git/mtime."""
    snapshot_date = (
        _infer_date_from_git_log(project_root)
        or _infer_date_from_file_mtimes(m_files)
    )
    return EnvSpec(
        language="MATLAB",
        pin_method=PinMethod.inferred_from_date,
        snapshot_date=snapshot_date,
        confidence=0.25,  # lowest: no lockfile, no standard package manager
        note=_MATLAB_DOCKER_ADVICE,
    )


def _python_inferred_from_date(project_root: Path, py_files: list[Path]) -> EnvSpec:
    """EnvSpec for Python project with no env file — infer from mtime/git."""
    snapshot_date = (
        _infer_date_from_git_log(project_root)
        or _infer_date_from_file_mtimes(py_files)
    )
    return EnvSpec(
        language="Python",
        pin_method=PinMethod.inferred_from_date,
        snapshot_date=snapshot_date,
        confidence=0.3,
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


# ---------------------------------------------------------------------------
# DESCRIPTION parsing (R package projects)
# ---------------------------------------------------------------------------

_DESCRIPTION_FIELD_RE = re.compile(r"^(\w[\w.]+)\s*:\s*(.+?)(?=\n\w|\Z)", re.DOTALL | re.MULTILINE)
_DESCRIPTION_PKG_RE = re.compile(r"([A-Za-z][A-Za-z0-9._]*)")


def _parse_description_imports(text: str) -> list[str]:
    """Extract package names from Imports:, Depends:, Suggests: fields."""
    packages: list[str] = []
    for m in _DESCRIPTION_FIELD_RE.finditer(text):
        field = m.group(1).strip()
        if field not in ("Imports", "Depends", "Suggests", "LinkingTo"):
            continue
        value = m.group(2)
        for pkg_match in _DESCRIPTION_PKG_RE.finditer(value):
            name = pkg_match.group(1)
            if name not in ("R", "base", "methods", "stats", "utils", "grDevices",
                            "graphics", "datasets", "tools", "compiler"):
                packages.append(name)
    return list(dict.fromkeys(packages))  # deduplicate, preserve order


def _from_description(
    description: Path,
    project_root: Path,
    r_files: list[Path],
) -> EnvSpec:
    """Build EnvSpec from DESCRIPTION file (R package project)."""
    text = description.read_text(errors="replace")
    packages = _parse_description_imports(text)
    pkg_specs = [PackageSpec(name=p, pin_method=PinMethod.inferred_from_date) for p in packages]

    snapshot_date = (
        _infer_date_from_rhistory(project_root)
        or _infer_date_from_git_log(project_root)
        or _infer_date_from_file_mtimes(r_files)
    )
    snapshot_url = (
        f"https://packagemanager.posit.co/cran/{snapshot_date}" if snapshot_date else None
    )

    return EnvSpec(
        language="R",
        packages=pkg_specs,
        pin_method=PinMethod.inferred_from_date,
        snapshot_date=snapshot_date,
        snapshot_url=snapshot_url,
        confidence=0.55,
    )
