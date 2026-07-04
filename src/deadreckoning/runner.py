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
    """
    Dispatch to the right runner based on script extension.

    .R / .r  → Rscript
    .do      → Stata (via stata.run_stata, wrapped into RunResult)
    .jl      → julia
    .py      → python
    """
    ext = Path(master_script).suffix.lower()
    if ext in (".r",):
        return _run_r(project_root, master_script)
    if ext == ".do":
        return _run_stata(project_root, master_script)
    if ext == ".jl":
        return _run_julia(project_root, master_script)
    if ext == ".py":
        return _run_python(project_root, master_script)
    if ext == ".m":
        return _run_matlab(project_root, master_script)
    return RunResult(
        returncode=1,
        stdout="",
        stderr=f"Unsupported script extension '{ext}' for {master_script}",
    )


def _run_r(project_root: Path, master_script: str) -> RunResult:
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


def _run_julia(project_root: Path, master_script: str) -> RunResult:
    result = subprocess.run(
        ["julia", master_script],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    return RunResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_python(project_root: Path, master_script: str) -> RunResult:
    import sys
    result = subprocess.run(
        [sys.executable, master_script],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    return RunResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_matlab(project_root: Path, master_script: str) -> RunResult:
    from .matlab import detect_matlab, run_matlab
    install = detect_matlab()
    if not install.found:
        return RunResult(
            returncode=1,
            stdout="",
            stderr=f"MATLAB not found.\n{install.advice or ''}",
        )
    matlab_result = run_matlab(
        project_root, master_script,
        binary=install.binary,
        supports_batch=install.supports_batch,
    )
    stderr = matlab_result.stderr
    if matlab_result.log_has_error and matlab_result.error_snippet:
        stderr += f"\nMATLAB error detected: {matlab_result.error_snippet}"
    return RunResult(
        returncode=0 if matlab_result.success else 1,
        stdout=matlab_result.stdout,
        stderr=stderr,
    )


def _run_stata(project_root: Path, master_script: str) -> RunResult:
    from .stata import detect_stata, run_stata
    install = detect_stata()
    if not install.found:
        return RunResult(
            returncode=1,
            stdout="",
            stderr=f"Stata not found.\n{install.advice or ''}",
        )
    if not install.on_path:
        # still runnable via resolved binary path
        pass
    stata_result = run_stata(project_root, master_script, binary=install.binary)
    stderr = stata_result.stderr
    if stata_result.log_has_error:
        stderr += f"\nStata error r({stata_result.error_code}) in log: {stata_result.log_path}"
        if stata_result.log_snippet:
            stderr += f"\n\nLog excerpt:\n{stata_result.log_snippet}"
    return RunResult(
        returncode=0 if stata_result.success else 1,
        stdout=stata_result.stdout,
        stderr=stderr,
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
