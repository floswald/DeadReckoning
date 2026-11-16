"""Run research scripts natively and validate that expected outputs exist."""

from __future__ import annotations

import datetime
import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .models import DataFile, DependencyGraph
from .nondeterminism import find_nondeterministic_calls


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


_COMPILED_EXTS = (".f90", ".f95", ".f", ".for", ".c", ".cpp", ".cc", ".cxx")


def run_natively(
    project_root: Path,
    master_script: str = "code/run.R",
    compile_command: str | None = None,
) -> RunResult:
    """
    Dispatch to the right runner based on script extension.

    .R / .r  → Rscript
    .do      → Stata (via stata.run_stata, wrapped into RunResult)
    .jl      → julia
    .py      → python
    .sh      → bash (a multi-language orchestrator — see _run_shell)
    .f90/.f95/.f/.for, .c, .cpp/.cc/.cxx → compile_command (see _run_compiled;
        a Fortran/C/C++ source file isn't directly executable the way the
        above are — ASK's compiled_language_no_build_script question is
        what supplies compile_command when no build script was found)
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
    if ext == ".sh":
        return _run_shell(project_root, master_script)
    if ext in _COMPILED_EXTS:
        return _run_compiled(project_root, master_script, compile_command)
    return RunResult(
        returncode=1,
        stdout="",
        stderr=f"Unsupported script extension '{ext}' for {master_script}",
    )


def _run_compiled(
    project_root: Path, master_script: str, compile_command: str | None
) -> RunResult:
    """Fortran/C/C++ source can't be executed directly — `compile_command`
    (the author's answer to ASK's compiled_language_no_build_script
    question, or a discovered build script's invocation) is shelled out to
    compile AND run it. No compile_command reaching here is a logic error
    upstream: ASK should have blocked the pipeline first."""
    if not compile_command:
        return RunResult(
            returncode=1,
            stdout="",
            stderr=(
                f"No build script found and no compile command supplied for "
                f"compiled-language source {master_script!r}. This should "
                "have been caught by ASK (compiled_language_no_build_script) "
                "before reaching RUN."
            ),
        )
    result = subprocess.run(
        compile_command,
        shell=True,
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    return RunResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_subprocess(cmd: list[str], cwd: Path, interpreter_label: str) -> RunResult:
    """subprocess.run wrapped into a RunResult, with the interpreter simply
    not being installed turned into a normal (non-crashing) failure result
    instead of an uncaught FileNotFoundError — the same "not found" posture
    _run_matlab()/_run_stata() already get from detect_matlab()/
    detect_stata() before they ever shell out."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        return RunResult(
            returncode=1,
            stdout="",
            stderr=f"{interpreter_label!r} not found on PATH — is it installed?",
        )
    return RunResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_r(project_root: Path, master_script: str) -> RunResult:
    return _run_subprocess(["Rscript", master_script], project_root, "Rscript")


def _run_julia(project_root: Path, master_script: str) -> RunResult:
    return _run_subprocess(["julia", master_script], project_root, "julia")


def _run_python(project_root: Path, master_script: str) -> RunResult:
    import sys
    return _run_subprocess([sys.executable, master_script], project_root, sys.executable)


def _run_shell(project_root: Path, master_script: str) -> RunResult:
    """
    A shell-script master (the run_all.sh-style multi-language orchestrator
    `_detect_master_script` prefers above any single-language script) is
    conventionally run FROM ITS OWN DIRECTORY, not the project root —
    every relative path inside it, including paths handed to whatever
    Stata/R/Julia process it launches, is written assuming that. Using
    project_root as cwd here breaks a correct package the moment the shell
    script references anything by relative path.

    Confirmed against a real published package: `code/run_all.sh` invokes
    `stata-mp -b stata/replication_aggregate_main.do`, a path only valid
    with cwd=code/ (= run_all.sh's own directory) — the README's own setup
    instructions say exactly this ("navigate to code/, then ./run_all.sh").
    With cwd=project_root instead, that first line fails immediately,
    before Stata, R, or Julia ever run.
    """
    script_path = project_root / master_script
    return _run_subprocess(["bash", str(script_path)], script_path.parent, "bash")


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


@dataclass
class SuspectFile:
    path: Path
    evidence: str       # "git" | "mtime"
    confidence: str      # "high" | "low"
    detail: str


@dataclass
class FidelityResult:
    exhibit: Path
    matches_reference: bool
    reference_hash: str | None = None
    regenerated_hash: str | None = None
    suspects: list[SuspectFile] = field(default_factory=list)
    # Set on mismatch when the producing script writes the wall clock, a
    # PID, or a tempdir path — a byte mismatch here may be expected, not
    # drift. See nondeterminism.py / Action Point 3 in compare.md.
    nondeterminism_note: str | None = None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_exhibit_fidelity(
    project_root: Path,
    graph: DependencyGraph,
    exhibit_tex_path: Path,
    reference_content: bytes,
) -> FidelityResult:
    """
    Compare a regenerated exhibit against a reference snapshot (e.g. the
    exhibit as it appeared in the published PDF, captured before the run).

    Unlike validate_outputs(), which only checks existence, this catches the
    "ran clean, exit 0, file exists, but the numbers are no longer what was
    published" case — a run that is green by every existing check and still
    not reproducible. On mismatch, walks the dependency chain feeding this
    exhibit to name the upstream data file(s) most likely responsible.
    """
    full_path = project_root / exhibit_tex_path
    if not full_path.exists():
        return FidelityResult(
            exhibit=exhibit_tex_path,
            matches_reference=False,
            reference_hash=_sha256(reference_content),
            regenerated_hash=None,
        )

    regenerated_content = full_path.read_bytes()
    reference_hash = _sha256(reference_content)
    regenerated_hash = _sha256(regenerated_content)

    if reference_hash == regenerated_hash:
        return FidelityResult(
            exhibit=exhibit_tex_path,
            matches_reference=True,
            reference_hash=reference_hash,
            regenerated_hash=regenerated_hash,
        )

    return FidelityResult(
        exhibit=exhibit_tex_path,
        matches_reference=False,
        reference_hash=reference_hash,
        regenerated_hash=regenerated_hash,
        suspects=_localize_divergence(project_root, graph, exhibit_tex_path),
        nondeterminism_note=_nondeterminism_note(graph, exhibit_tex_path),
    )


def _nondeterminism_note(graph: DependencyGraph, exhibit_tex_path: Path) -> str | None:
    """None unless the script producing this exhibit writes the wall clock,
    a PID, or a tempdir path — in which case name the call(s) found."""
    exhibit = next((e for e in graph.exhibits if e.tex_path == exhibit_tex_path), None)
    if exhibit is None or exhibit.source is None:
        return None
    calls = find_nondeterministic_calls(exhibit.source.script)
    if not calls:
        return None
    joined = ", ".join(calls)
    return (
        f"{exhibit.source.script.name} calls {joined} — this exhibit may "
        "legitimately differ byte-for-byte on every run (a timestamp/PID/"
        "tempdir path), independent of whether the underlying numbers match."
    )


def _upstream_data_files(graph: DependencyGraph, source_script: Path) -> list[DataFile]:
    """Walk backwards from a script through produced_by links to collect
    every upstream data file feeding it, however many stages back."""
    visited_scripts: set[Path] = set()
    to_visit = [source_script]
    upstream: list[DataFile] = []
    seen_paths: set[Path] = set()

    while to_visit:
        script = to_visit.pop()
        if script in visited_scripts:
            continue
        visited_scripts.add(script)
        for df in graph.data_files:
            if script not in df.referenced_by or df.path in seen_paths:
                continue
            seen_paths.add(df.path)
            upstream.append(df)
            if df.produced_by is not None and df.produced_by not in visited_scripts:
                to_visit.append(df.produced_by)

    return upstream


def _git_last_change(project_root: Path, actual_path: Path) -> str | None:
    """`git log --follow` for a path, if the project is a git repo and the
    path is tracked. Returns None (never raises) when git/the path/the repo
    isn't usable, so callers fall back to the mtime heuristic."""
    try:
        rel = actual_path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--follow", "--format=%H %ad %an", "--date=short", "--", str(rel)],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _localize_divergence(
    project_root: Path, graph: DependencyGraph, exhibit_tex_path: Path
) -> list[SuspectFile]:
    """
    Name the upstream data file(s) most likely responsible for a content
    divergence. Prefers git history (exact commit/date/author) when the
    project is a git repo and the path is tracked; otherwise falls back to
    filesystem mtime — a lead, not proof, since Dropbox sync / zip / scp
    routinely rewrite mtimes without any real edit having happened.
    """
    exhibit = next((e for e in graph.exhibits if e.tex_path == exhibit_tex_path), None)
    if exhibit is None or exhibit.source is None:
        return []

    is_git_repo = (project_root / ".git").exists()
    suspects: list[SuspectFile] = []

    for df in _upstream_data_files(graph, exhibit.source.script):
        actual_path = df.path if df.is_external else (project_root / df.path)

        if is_git_repo:
            detail = _git_last_change(project_root, actual_path)
            if detail:
                suspects.append(
                    SuspectFile(path=df.path, evidence="git", confidence="high", detail=detail)
                )
                continue

        if df.mtime is not None:
            ts = datetime.datetime.fromtimestamp(df.mtime).isoformat(timespec="seconds")
            suspects.append(
                SuspectFile(
                    path=df.path,
                    evidence="mtime",
                    confidence="low",
                    detail=(
                        f"last modified {ts} (filesystem mtime only — not reliable "
                        "provenance; Dropbox sync, zip/unzip, and scp all rewrite "
                        "mtimes without a real edit happening. Treat this as a lead, "
                        "not proof — confirm with the author who touched it.)"
                    ),
                )
            )

    return suspects


def group_fidelity_mismatches(results: list[FidelityResult]) -> dict[Path, list[Path]]:
    """
    Group a batch of check_exhibit_fidelity() results by suspect: map each
    upstream file implicated in at least one mismatch to the exhibit(s) it's
    implicated in.

    Presentation-layer aggregation only — check_exhibit_fidelity() itself
    stays one-exhibit-in, one-result-out. Lets a driver running the check
    across several exhibits show "these N exhibits all point at the same
    upstream file" instead of reimplementing the grouping itself.

    Matching exhibits and exhibits whose suspect list is empty (mismatched,
    but the dependency chain dead-ends before naming anything) contribute
    nothing.
    """
    grouped: dict[Path, list[Path]] = {}
    for result in results:
        if result.matches_reference:
            continue
        for suspect in result.suspects:
            grouped.setdefault(suspect.path, []).append(result.exhibit)
    return grouped
