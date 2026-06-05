"""Run research scripts natively and validate that expected outputs exist."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .models import DependencyGraph


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


@dataclass
class ValidationResult:
    missing: list[Path] = field(default_factory=list)
    present: list[Path] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.missing) == 0


def run_natively(project_root: Path, master_script: str = "code/run.R") -> RunResult:
    """Execute master script with cwd=project_root. Returns stdout/stderr/returncode."""
    result = subprocess.run(
        ["Rscript", master_script],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    return RunResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def validate_outputs(project_root: Path, graph: DependencyGraph) -> ValidationResult:
    """Check that every sourced exhibit exists on disk in project_root."""
    missing: list[Path] = []
    present: list[Path] = []
    for exhibit in graph.exhibits:
        if exhibit.source is None:
            continue  # gap — not expected to exist after run
        full_path = project_root / exhibit.tex_path
        if full_path.exists():
            present.append(exhibit.tex_path)
        else:
            missing.append(exhibit.tex_path)
    return ValidationResult(missing=missing, present=present)
