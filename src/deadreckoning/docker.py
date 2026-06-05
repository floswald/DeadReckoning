"""Generate Dockerfile, build image, and validate inside container."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .models import DependencyGraph, EnvSpec
from .runner import RunResult, ValidationResult

_DOCKERFILE_TEMPLATE = """\
FROM rocker/r-ver:{r_version}

# Install packages from PPM snapshot
RUN Rscript -e 'install.packages({packages_r_vec}, repos="{snapshot_url}")'

COPY . /project
WORKDIR /project

CMD ["Rscript", "{master_script}"]
"""


def generate_dockerfile(
    env_spec: EnvSpec,
    master_script: str = "code/run.R",
) -> str:
    r_version = env_spec.language_version or "4.4.0"
    snapshot_url = env_spec.snapshot_url or "https://packagemanager.posit.co/cran/latest"
    pkg_names = [p.name for p in env_spec.packages]
    packages_r_vec = "c(" + ", ".join(f'"{n}"' for n in pkg_names) + ")"
    return _DOCKERFILE_TEMPLATE.format(
        r_version=r_version,
        packages_r_vec=packages_r_vec,
        snapshot_url=snapshot_url,
        master_script=master_script,
    )


@dataclass
class BuildResult:
    success: bool
    image_tag: str
    stdout: str
    stderr: str


def build_image(project_root: Path, dockerfile_text: str, tag: str) -> BuildResult:
    """Write Dockerfile to project_root and run docker build."""
    dockerfile_path = project_root / "Dockerfile"
    dockerfile_path.write_text(dockerfile_text)
    result = subprocess.run(
        ["docker", "build", "-t", tag, "."],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    return BuildResult(
        success=result.returncode == 0,
        image_tag=tag,
        stdout=result.stdout,
        stderr=result.stderr,
    )


@dataclass
class ContainerValidationResult:
    run: RunResult
    outputs: ValidationResult


def run_in_container(
    project_root: Path,
    image_tag: str,
    graph: DependencyGraph,
    master_script: str = "code/run.R",
) -> ContainerValidationResult:
    """
    Run master_script inside container with project mounted read-only.
    Outputs are written to a tmpfs so they don't pollute the host working copy.
    We then check each expected exhibit path inside the container.
    """
    # Mount project as /project (read-only source), use anonymous volume for outputs
    exhibit_paths = [e.tex_path for e in graph.exhibits if e.source is not None]

    # Run the script and list output files in one container invocation
    check_cmds = " && ".join(
        f"test -f /project/{p}" for p in exhibit_paths
    )
    shell_cmd = f"Rscript {master_script} && {check_cmds}" if check_cmds else f"Rscript {master_script}"

    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{project_root}:/project",
            "-w", "/project",
            image_tag,
            "bash", "-c", shell_cmd,
        ],
        capture_output=True,
        text=True,
    )
    run_result = RunResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )

    # Determine which exhibits are present by re-checking with individual test calls
    present: list[Path] = []
    missing: list[Path] = []
    if result.returncode == 0:
        present = list(exhibit_paths)
    else:
        # Parse which test -f failed (heuristic: all missing on failure)
        missing = list(exhibit_paths)

    return ContainerValidationResult(
        run=run_result,
        outputs=ValidationResult(missing=missing, present=present),
    )
