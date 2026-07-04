"""Generate Dockerfile, build image, and validate inside container.

Design invariants (from issue #7):
- Software env only — no COPY of code or data into the image.
- Code + data arrive via volume mount at runtime.
- Data can never leak into the image because there is no COPY.
- .dockerignore suppresses build-context bloat (data dirs, secrets).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import DependencyGraph, EnvSpec, Gap, GapKind
from .runner import RunResult, ValidationResult


# ---------------------------------------------------------------------------
# R base image selection
# ---------------------------------------------------------------------------

# Packages that trigger rocker/geospatial (already bundles GDAL/GEOS/PROJ/sf)
_GEOSPATIAL_PKGS = frozenset({"sf", "terra", "stars", "rgdal", "rgeos", "sp", "mapview",
                               "tmap", "leaflet", "osmdata", "osrm", "tidygeocoder"})

# Packages that trigger rocker/tidyverse
_TIDYVERSE_PKGS = frozenset({"tidyverse", "ggplot2", "dplyr", "tidyr", "readr", "purrr",
                              "tibble", "stringr", "forcats", "lubridate", "hms"})
_TIDYVERSE_THRESHOLD = 3  # ≥3 tidyverse packages → tidyverse image

# Packages that trigger rocker/stan
_STAN_PKGS = frozenset({"rstan", "brms", "cmdstanr", "rstanarm", "bayesplot"})


def _select_r_base_image(packages: list[str], version: str) -> str:
    """
    Choose the most capable rocker base image for a package set.

    Priority (highest first):
      geospatial pkgs present  → rocker/geospatial (bundles GDAL/sf/spatial libs)
      Stan pkgs present        → rocker/stan
      ≥3 tidyverse pkgs        → rocker/tidyverse
      default                  → rocker/r-ver
    """
    pkg_set = set(packages)
    if pkg_set & _GEOSPATIAL_PKGS:
        return f"rocker/geospatial:{version}"
    if pkg_set & _STAN_PKGS:
        return f"rocker/stan:{version}"
    if len(pkg_set & _TIDYVERSE_PKGS) >= _TIDYVERSE_THRESHOLD:
        return f"rocker/tidyverse:{version}"
    return f"rocker/r-ver:{version}"


# ---------------------------------------------------------------------------
# System dependency mapping (packages → apt-get packages)
# ---------------------------------------------------------------------------

# rocker/geospatial already bundles all spatial deps — skip for those packages
_GEOSPATIAL_ALREADY_IN_IMAGE = frozenset({"sf", "terra", "stars", "rgdal", "rgeos",
                                           "sp", "mapview", "tmap", "osmdata"})

# R package → list of apt-get -dev packages required at compile time
_SYSTEM_DEPS: dict[str, list[str]] = {
    "xml2":       ["libxml2-dev"],
    "rvest":      ["libxml2-dev"],
    "curl":       ["libcurl4-openssl-dev", "libssl-dev"],
    "httr":       ["libcurl4-openssl-dev", "libssl-dev"],
    "httr2":      ["libcurl4-openssl-dev", "libssl-dev"],
    "openssl":    ["libssl-dev"],
    "RPostgres":  ["libpq-dev"],
    "RMySQL":     ["libmysqlclient-dev"],
    "arrow":      ["libcurl4-openssl-dev", "libssl-dev"],
    "igraph":     ["libglpk-dev"],
    "sodium":     ["libsodium-dev"],
    "V8":         ["libnode-dev"],
    "rJava":      ["default-jdk"],
    "Rmpfr":      ["libmpfr-dev"],
    "units":      ["libudunits2-dev"],
    "sf":         ["libudunits2-dev", "libgdal-dev", "libgeos-dev", "libproj-dev"],
    "terra":      ["libudunits2-dev", "libgdal-dev", "libgeos-dev", "libproj-dev"],
    # kableExtra pulls in systemfonts/textshaping/svglite transitively —
    # none of those are declared directly, so the C-library needs must be
    # keyed on kableExtra itself (same pattern as sf/terra above).
    "kableExtra": ["libfontconfig1-dev", "libfreetype6-dev", "libharfbuzz-dev",
                   "libfribidi-dev", "libpng-dev", "libtiff5-dev", "libjpeg-dev",
                   "libuv1-dev", "libxml2-dev"],
}


def _system_deps_for_packages(packages: list[str], base_image: str) -> list[str]:
    """
    Return sorted list of apt packages needed for the R package set.
    Skips spatial deps when base_image is rocker/geospatial (already bundled).
    """
    is_geospatial_image = "geospatial" in base_image
    apt_pkgs: set[str] = set()
    for pkg in packages:
        if is_geospatial_image and pkg in _GEOSPATIAL_ALREADY_IN_IMAGE:
            continue
        for apt_pkg in _SYSTEM_DEPS.get(pkg, []):
            apt_pkgs.add(apt_pkg)
    return sorted(apt_pkgs)


# ---------------------------------------------------------------------------
# Base images by language
# ---------------------------------------------------------------------------

_R_BASE = "rocker/r-ver:{version}"
_PYTHON_BASE = "python:{version}-slim"
_JULIA_BASE = "julia:{version}"
_STATA_NOTE = (
    "# Stata is proprietary — no public licensed Docker image.\n"
    "# Build a private image with your licensed stata binary.\n"
    "# See: https://hub.docker.com/r/dataeditors/stata\n"
)
_MATLAB_NOTE = (
    "# MATLAB is proprietary — requires mathworks/matlab with browser login.\n"
    "# See: https://hub.docker.com/r/mathworks/matlab\n"
    "# First run: docker run -it --rm -p 8888:8888 mathworks/matlab -browser\n"
)

# Default versions when not detected
_DEFAULT_R_VERSION = "4.4.0"
_DEFAULT_PYTHON_VERSION = "3.11"
_DEFAULT_JULIA_VERSION = "1.10"

# Platform: proprietary software must be amd64 (license servers + binaries).
# Open-source languages (R/Python/Julia) publish multi-arch images — forcing
# amd64 there just buys pointless QEMU emulation on Apple Silicon. Let Docker
# resolve the host's native platform instead (omit --platform entirely).
_PROPRIETARY_PLATFORM = "linux/amd64"
_DEFAULT_PLATFORM = "linux/amd64"  # kept for callers that pin explicitly


def _platform_for_language(language: str) -> Optional[str]:
    """None means: don't pass --platform at all, let Docker use the host's."""
    if language.upper() in ("STATA", "MATLAB"):
        return _PROPRIETARY_PLATFORM
    return None


# ---------------------------------------------------------------------------
# Dockerfile generation
# ---------------------------------------------------------------------------


def _r_dockerfile(env_spec: EnvSpec) -> str:
    version = env_spec.language_version or _DEFAULT_R_VERSION
    snapshot_url = (
        env_spec.snapshot_url
        or f"https://packagemanager.posit.co/cran/{env_spec.snapshot_date or 'latest'}"
    )
    pkg_names = [p.name for p in env_spec.packages]
    r_vec = "c(" + ", ".join(f'"{n}"' for n in pkg_names) + ")" if pkg_names else "c()"

    base_image = _select_r_base_image(pkg_names, version)
    system_deps = _system_deps_for_packages(pkg_names, base_image)

    lines = [f"FROM {base_image}", ""]

    if system_deps:
        apt_list = " ".join(system_deps)
        lines += [
            "RUN apt-get update && apt-get install -y \\",
            f"    {apt_list} \\",
            "    && rm -rf /var/lib/apt/lists/*",
            "",
        ]

    lines += [
        "ENV RENV_PATHS_CACHE=/renv/cache",
        "",
        f'RUN Rscript -e \'install.packages({r_vec}, repos="{snapshot_url}", Ncpus=4)\'',
        "",
        "WORKDIR /project",
        'CMD ["Rscript", "code/run.R"]',
    ]
    return "\n".join(lines) + "\n"


def _python_dockerfile(env_spec: EnvSpec) -> str:
    version = env_spec.language_version or _DEFAULT_PYTHON_VERSION
    pkg_names = [
        f"{p.name}=={p.version}" if p.version else p.name
        for p in env_spec.packages
    ]

    lines = [
        f"FROM {_PYTHON_BASE.format(version=version)}",
        "",
        "WORKDIR /project",
    ]
    if pkg_names:
        pip_args = " ".join(f'"{n}"' for n in pkg_names)
        lines += [
            "",
            f"RUN pip install --no-cache-dir {pip_args}",
        ]
    lines += [
        "",
        'CMD ["python", "code/analysis.py"]',
    ]
    return "\n".join(lines) + "\n"


def _julia_dockerfile(env_spec: EnvSpec) -> str:
    version = env_spec.language_version or _DEFAULT_JULIA_VERSION
    pkg_names = [p.name for p in env_spec.packages]

    lines = [
        f"FROM {_JULIA_BASE.format(version=version)}",
        "",
        "WORKDIR /project",
    ]
    if pkg_names:
        julia_pkgs = '", "'.join(pkg_names)
        lines += [
            "",
            f'RUN julia -e \'using Pkg; Pkg.add(["{julia_pkgs}"])\'',
        ]
    lines += [
        "",
        'CMD ["julia", "code/analysis.jl"]',
    ]
    return "\n".join(lines) + "\n"


def _unsupported_dockerfile(language: str) -> str:
    note = _STATA_NOTE if language.lower() == "stata" else _MATLAB_NOTE
    return (
        f"# Dockerfile for {language} — manual steps required.\n"
        + note
        + f"\n# FROM your-private-{language.lower()}-image\n"
        + "WORKDIR /project\n"
    )


def _stata_dockerfile(env_spec: EnvSpec) -> str:
    """
    Dockerfile FROM a pre-built private Stata image (env_spec.stata_image).

    Stata binaries are proprietary and license-locked: there is no public
    base image to pull, and DeadReckoning cannot build one (that requires a
    licensed workstation install run through AEADataEditor/docker-stata's
    capture.sh, outside this pipeline's reach). If stata_image is unset,
    fall back to manual-steps guidance.

    The license file itself is never baked into the image — it is bind-
    mounted at container-run time (see run_in_container / _build_run_command).
    """
    if not env_spec.stata_image:
        return _unsupported_dockerfile(env_spec.language)
    return (
        f"FROM --platform={_PROPRIETARY_PLATFORM} {env_spec.stata_image}\n"
        "\n"
        "WORKDIR /project\n"
        "ENTRYPOINT []\n"
        'CMD ["bash"]\n'
    )


def generate_dockerfile(env_spec: EnvSpec) -> str:
    """Return Dockerfile text for env_spec. Never COPYs code or data."""
    lang = env_spec.language.upper()
    if lang == "R":
        return _r_dockerfile(env_spec)
    if lang == "PYTHON":
        return _python_dockerfile(env_spec)
    if lang == "JULIA":
        return _julia_dockerfile(env_spec)
    if lang == "STATA":
        return _stata_dockerfile(env_spec)
    return _unsupported_dockerfile(env_spec.language)


# ---------------------------------------------------------------------------
# .dockerignore generation
# ---------------------------------------------------------------------------

# Patterns that should never enter the build context
_DOCKERIGNORE_BASE = """\
# Data directories — never in image (data attaches via volume)
data/
raw_data/
restricted_data/

# Secrets and credentials
.env
*.key
*.pem
credentials*
secrets*

# Build artifacts and caches
__pycache__/
*.pyc
.Rhistory
.RData
renv/library/
.julia/
node_modules/

# Version control and editor files
.git/
.gitignore
.DS_Store
*.swp
"""


def _secret_patterns_from_scan(scan_result) -> list[str]:
    """Extract secret-file patterns from a scan result, if available."""
    patterns: list[str] = []
    if hasattr(scan_result, "secrets") and scan_result.secrets:
        for s in scan_result.secrets:
            name = Path(s.path).name if hasattr(s, "path") else str(s)
            if name not in patterns:
                patterns.append(name)
    return patterns


def generate_dockerignore(extra_patterns: list[str] | None = None) -> str:
    """Return .dockerignore text."""
    text = _DOCKERIGNORE_BASE
    if extra_patterns:
        text += "\n# Project-specific exclusions\n"
        for p in extra_patterns:
            text += f"{p}\n"
    return text


# ---------------------------------------------------------------------------
# Build result
# ---------------------------------------------------------------------------


@dataclass
class BuildResult:
    success: bool
    image_tag: str
    stdout: str
    stderr: str
    dockerfile_text: str = ""


def write_dockerfile(project_root: Path, dockerfile_text: str) -> Path:
    path = project_root / "Dockerfile"
    path.write_text(dockerfile_text)
    return path


def write_dockerignore(project_root: Path, text: str) -> Path:
    path = project_root / ".dockerignore"
    path.write_text(text)
    return path


def build_image(
    project_root: Path,
    dockerfile_text: str,
    tag: str,
    platform: Optional[str] = None,
) -> BuildResult:
    write_dockerfile(project_root, dockerfile_text)
    cmd = ["docker", "build"]
    if platform:
        cmd.append(f"--platform={platform}")
    cmd += ["-t", tag, "."]
    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    return BuildResult(
        success=result.returncode == 0,
        image_tag=tag,
        stdout=result.stdout,
        stderr=result.stderr,
        dockerfile_text=dockerfile_text,
    )


# ---------------------------------------------------------------------------
# Container run + host-side validation
# ---------------------------------------------------------------------------


@dataclass
class ContainerRunResult:
    run: RunResult
    outputs: ValidationResult


def run_in_container(
    project_root: Path,
    image_tag: str,
    graph: DependencyGraph,
    master_script: Optional[str] = None,
    env_spec: Optional[EnvSpec] = None,
    platform: Optional[str] = None,
    stata_license: Optional[Path] = None,
) -> ContainerRunResult:
    """
    Mount project_root as /project (rw), run master_script.
    Outputs written by the script land back on the host via the volume.
    Validate on host after run.

    stata_license: host path to a Stata license file, bind-mounted read-only
    to /usr/local/stata/stata.lic. Never baked into the image (see
    _stata_dockerfile). Ignored for non-Stata languages.
    """
    cmd = _build_run_command(image_tag, project_root, master_script, env_spec, platform, stata_license)
    result = subprocess.run(cmd, capture_output=True, text=True)
    run_result = RunResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )

    # Validate on host — volume writes are visible immediately
    from .runner import validate_outputs
    outputs = validate_outputs(project_root, graph)

    return ContainerRunResult(run=run_result, outputs=outputs)


def _build_run_command(
    image_tag: str,
    project_root: Path,
    master_script: Optional[str],
    env_spec: Optional[EnvSpec],
    platform: Optional[str],
    stata_license: Optional[Path] = None,
) -> list[str]:
    lang = (env_spec.language.upper() if env_spec else "R")
    if master_script is None:
        master_script = _default_master_script(lang, project_root)

    shell_cmd = _shell_command(lang, master_script)
    cmd = ["docker", "run", "--rm"]
    if platform:
        cmd.append(f"--platform={platform}")
    cmd += [
        "-v", f"{project_root}:/project",
    ]
    if lang == "STATA" and stata_license is not None:
        cmd += ["-v", f"{stata_license}:/usr/local/stata/stata.lic:ro"]
    cmd += [
        "-w", "/project",
        image_tag,
        "bash", "-c", shell_cmd,
    ]
    return cmd


def _default_master_script(language: str, project_root: Path) -> str:
    candidates = {
        "R": ["code/run.R", "code/analysis.R", "run.R"],
        "PYTHON": ["code/run.py", "code/analysis.py", "run.py"],
        "JULIA": ["code/run.jl", "code/analysis.jl", "run.jl"],
        "STATA": ["code/run.do", "code/analysis.do", "run.do"],
        "MATLAB": ["code/run.m", "code/analysis.m", "run.m"],
    }
    for candidate in candidates.get(language, []):
        if (project_root / candidate).exists():
            return candidate
    return "code/run.R"


def _shell_command(language: str, master_script: str) -> str:
    if language == "R":
        return f"Rscript {master_script}"
    if language == "PYTHON":
        return f"python {master_script}"
    if language == "JULIA":
        return f"julia {master_script}"
    if language == "STATA":
        return f"stata-mp -b do {master_script}"
    if language == "MATLAB":
        stem = Path(master_script).stem
        return f"matlab -batch \"{stem}\""
    return f"Rscript {master_script}"


# ---------------------------------------------------------------------------
# Docker FIX loop — mirrors native fix_loop.py dispatcher protocol
# ---------------------------------------------------------------------------


@dataclass
class DockerFixResult:
    build_attempts: int = 0
    run_attempts: int = 0
    dockerfile_fixes: list[str] = field(default_factory=list)
    converged: bool = False
    final_build: Optional[BuildResult] = None
    final_run: Optional[ContainerRunResult] = None
    error: Optional[str] = None


def _parse_missing_r_package(stderr: str) -> Optional[str]:
    """Extract missing R package name from build stderr."""
    m = re.search(r"there is no package called ['\"](\w+)['\"]", stderr, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"package ['\"](\w+)['\"] is not available", stderr, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _add_r_package_to_dockerfile(dockerfile_text: str, package: str) -> str:
    """Splice package into the install.packages() call in a Dockerfile."""
    pattern = re.compile(r'(install\.packages\(c\()([^)]*)\)', re.DOTALL)
    m = pattern.search(dockerfile_text)
    if not m:
        return dockerfile_text
    existing = m.group(2)
    if f'"{package}"' in existing:
        return dockerfile_text
    if existing.strip():
        new_pkgs = existing.rstrip() + f', "{package}"'
    else:
        new_pkgs = f'"{package}"'
    return dockerfile_text[:m.start()] + m.group(1) + new_pkgs + ")" + dockerfile_text[m.end():]


def _parse_missing_python_package(stderr: str) -> Optional[str]:
    """Extract missing Python package name from pip/runtime stderr."""
    m = re.search(r"No module named ['\"]([A-Za-z0-9_\-]+)['\"]", stderr)
    if m:
        return m.group(1)
    m = re.search(r"No matching distribution found for ([A-Za-z0-9_\-]+)", stderr, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"Could not find a version that satisfies the requirement ([A-Za-z0-9_\-]+)", stderr, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _add_python_package_to_dockerfile(dockerfile_text: str, package: str) -> str:
    """Splice package into the pip install line in a Dockerfile."""
    pattern = re.compile(r'(RUN pip install --no-cache-dir)(.*)', re.MULTILINE)
    m = pattern.search(dockerfile_text)
    if not m:
        return dockerfile_text
    existing = m.group(2)
    quoted = f'"{package}"'
    if quoted in existing or f'"{package}==' in existing:
        return dockerfile_text
    new_line = m.group(1) + existing.rstrip() + f" {quoted}"
    return dockerfile_text[:m.start()] + new_line + dockerfile_text[m.end():]


def _parse_missing_julia_package(stderr: str) -> Optional[str]:
    """Extract missing Julia package name from Pkg/runtime stderr."""
    m = re.search(r"Package ([A-Za-z0-9_\-]+) not found in current path", stderr)
    if m:
        return m.group(1)
    m = re.search(r'ArgumentError: Package ([A-Za-z0-9_\-]+) not found', stderr)
    if m:
        return m.group(1)
    m = re.search(r'ERROR: LoadError:.*?([A-Za-z0-9_]+) not installed', stderr, re.DOTALL)
    if m:
        return m.group(1)
    return None


def _add_julia_package_to_dockerfile(dockerfile_text: str, package: str) -> str:
    """Splice package into the Pkg.add([...]) call in a Dockerfile."""
    pattern = re.compile(r'(RUN julia -e \'using Pkg; Pkg\.add\(\[")([^\']*?)("\]\)\')', re.DOTALL)
    m = pattern.search(dockerfile_text)
    if not m:
        return dockerfile_text
    existing = m.group(2)
    if package in existing.split('", "'):
        return dockerfile_text
    if existing.strip():
        new_pkgs = existing.rstrip() + f'", "{package}'
    else:
        new_pkgs = package
    return dockerfile_text[:m.start()] + m.group(1) + new_pkgs + m.group(3) + dockerfile_text[m.end():]


def _parse_missing_package(language: str, stderr: str) -> Optional[str]:
    """Dispatch to language-appropriate package parser."""
    lang = language.upper()
    if lang == "R":
        return _parse_missing_r_package(stderr)
    if lang == "PYTHON":
        return _parse_missing_python_package(stderr)
    if lang == "JULIA":
        return _parse_missing_julia_package(stderr)
    return None


def _add_package_to_dockerfile(language: str, dockerfile_text: str, package: str) -> str:
    """Dispatch to language-appropriate Dockerfile patcher."""
    lang = language.upper()
    if lang == "R":
        return _add_r_package_to_dockerfile(dockerfile_text, package)
    if lang == "PYTHON":
        return _add_python_package_to_dockerfile(dockerfile_text, package)
    if lang == "JULIA":
        return _add_julia_package_to_dockerfile(dockerfile_text, package)
    return dockerfile_text


def run_docker_fix_loop(
    project_root: Path,
    graph: DependencyGraph,
    env_spec: Optional[EnvSpec] = None,
    image_tag: str = "deadreckoning:latest",
    max_iterations: int = 5,
    platform: Optional[str] = None,
    master_script: Optional[str] = None,
    stata_license: Optional[Path] = None,
) -> DockerFixResult:
    """
    Build → run → check → fix → repeat.

    Build failures: missing packages detected deterministically (R/Python/Julia).
    Run failures: LLM fix loop applied to working copy, then rebuild.

    platform: pass explicitly to pin one; otherwise resolved from language
    (amd64 for Stata/MATLAB, host-native for R/Python/Julia).
    """
    if env_spec is None:
        from .capture import capture_env
        env_spec = capture_env(project_root)

    language = env_spec.language if env_spec else "R"
    if platform is None:
        platform = _platform_for_language(language)
    dockerfile_text = generate_dockerfile(env_spec)
    dockerignore_text = generate_dockerignore()
    write_dockerignore(project_root, dockerignore_text)

    result = DockerFixResult()

    for _iteration in range(max_iterations):
        build = build_image(project_root, dockerfile_text, image_tag, platform)
        result.build_attempts += 1
        result.final_build = build

        if not build.success:
            pkg = _parse_missing_package(language, build.stderr)
            if pkg:
                new_df = _add_package_to_dockerfile(language, dockerfile_text, pkg)
                if new_df == dockerfile_text:
                    result.error = f"Cannot fix: package '{pkg}' already in Dockerfile"
                    break
                result.dockerfile_fixes.append(f"add_{language.lower()}_package:{pkg}")
                dockerfile_text = new_df
                continue
            result.error = f"Build failed (no auto-fix): {build.stderr[:400]}"
            break

        run = run_in_container(
            project_root, image_tag, graph,
            master_script=master_script, env_spec=env_spec, platform=platform,
            stata_license=stata_license,
        )
        result.run_attempts += 1
        result.final_run = run

        if run.outputs.success:
            result.converged = True
            break

        # Run succeeded but outputs missing — try LLM fix on working copy then rebuild
        from .fix_loop import run_llm_fix_loop
        from .graph import build_graph
        llm_result, graph = run_llm_fix_loop(
            project_root, graph, env_spec,
            master_script=master_script or _default_master_script(language.upper(), project_root),
        )
        result.dockerfile_fixes.extend(
            f"llm:{f.kind}:{f.script or f.package_name or '—'}"
            for f in llm_result.fixes_applied
        )
        if not llm_result.fixes_applied:
            result.error = (
                f"Outputs missing after run: {[str(p) for p in run.outputs.missing]}\n"
                f"stderr: {run.run.stderr[:300]}"
            )
            break
        # Rebuild with potentially updated scripts
        dockerfile_text = generate_dockerfile(env_spec)

    else:
        if not result.converged:
            result.error = f"Did not converge after {max_iterations} iterations"

    return result


# ---------------------------------------------------------------------------
# AGENT_REPORT.md — Docker section
# ---------------------------------------------------------------------------


def append_docker_report(
    project_root: Path,
    build: BuildResult,
    run: Optional[ContainerRunResult],
    fix_result: Optional[DockerFixResult],
    image_tag: str,
    platform: Optional[str],
) -> None:
    """Append Docker pipeline summary to AGENT_REPORT.md."""
    report = project_root / "AGENT_REPORT.md"
    lines = [
        "\n## Docker pipeline\n",
        f"Image: `{image_tag}`  | Platform: `{platform or 'host default'}`  "
        f"| Build: {'✓' if build.success else '✗'}  "
        f"| Run: {'✓' if (run and run.run.success) else '✗'}\n",
    ]

    if fix_result and fix_result.dockerfile_fixes:
        lines.append("\n### Dockerfile fixes applied\n")
        for fix in fix_result.dockerfile_fixes:
            lines.append(f"- {fix}")

    if run:
        if run.outputs.present:
            lines.append("\n### Outputs regenerated\n")
            for p in run.outputs.present:
                lines.append(f"- `{p}`")
        if run.outputs.missing:
            lines.append("\n### Outputs still missing\n")
            for p in run.outputs.missing:
                lines.append(f"- `{p}`")

    if not build.success:
        lines.append(f"\n**Build error (last 400 chars):**\n```\n{build.stderr[-400:]}\n```")

    with report.open("a") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Registry push guard
# ---------------------------------------------------------------------------


def warn_before_push(image_tag: str, build: BuildResult) -> str:
    """Return a warning string listing Dockerfile contents before any push."""
    dockerfile_lines = [
        ln for ln in build.dockerfile_text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    summary = "\n  ".join(dockerfile_lines)
    return (
        f"WARNING: About to push image '{image_tag}' to registry.\n"
        f"Dockerfile layers:\n  {summary}\n"
        f"Verify no sensitive data is baked in before proceeding."
    )
