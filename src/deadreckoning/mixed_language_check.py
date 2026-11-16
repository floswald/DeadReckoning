"""
Mixed-language compilation risk detection — Rcpp, Cython, MEX, and similar
setups where one language's build machinery silently depends on another
language's compiler toolchain.

Why this is its own check, separate from compile_check.py: a standalone
Fortran/C/C++ script with no build artifact genuinely CANNOT run at all,
so that check blocks the pipeline. Rcpp/Cython/MEX are different — the
embedding language (R's `sourceCpp`, Python's Cython build backend,
MATLAB's `mex`) usually CAN auto-compile the embedded C/C++ code with
system-default flags, so a native run doesn't fail outright. The actual
failure mode is quieter and more dangerous: a custom flag the author's own
machine happens to supply (an OpenMP flag, a header-only library include
path, a specific C++ standard) that lives nowhere in the package — not in
`src/Makevars`, not in a `setup.py` `cythonize()` call, not in a `mex()`
invocation with explicit flags — means a replicator's run may compile
successfully with DIFFERENT flags (silently different numerics, e.g. no
OpenMP so a parallel reduction order changes) or fail outright on a
stricter default toolchain. This is exactly the kind of "worked when I
wrote it, breaks for the replicator" failure a reproducibility check
should surface early.

Non-blocking — writes MIXED-LANGUAGE-WARNINGS.md, same posture as
CLEANUP.md / RNG-WARNINGS.md. Best-effort regex, like the rest of the
static layer.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

_MIXED_LANGUAGE_WARNINGS_FILE = "MIXED-LANGUAGE-WARNINGS.md"

_SKIP_DIRS = frozenset({".git", "_archive", "__pycache__", "node_modules", "renv"})


def _rel_parts(p: Path, project_root: Path) -> tuple[str, ...]:
    return p.relative_to(project_root).parts


def _iter_files(project_root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found: set[Path] = set()
    for suf in suffixes:
        found.update(
            p for p in project_root.rglob(f"*{suf}")
            if p.is_file() and not any(part in _SKIP_DIRS for part in _rel_parts(p, project_root))
        )
    return sorted(found)


def _read(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Rcpp
# ---------------------------------------------------------------------------

_RCPP_R_USAGE_RE = re.compile(
    r"\blibrary\s*\(\s*Rcpp\s*\)|\bRcpp::sourceCpp\s*\(|\bsourceCpp\s*\("
)
_RCPP_CPP_USAGE_RE = re.compile(
    r"//\s*\[\[Rcpp::|#include\s*[<\"]Rcpp\.h[>\"]"
)
_DESCRIPTION_RCPP_RE = re.compile(
    r"^(?:LinkingTo|Imports|Depends)\s*:.*\bRcpp\b", re.MULTILINE
)


def _uses_rcpp(project_root: Path) -> bool:
    for p in _iter_files(project_root, (".R", ".r")):
        if _RCPP_R_USAGE_RE.search(_read(p)):
            return True
    for p in _iter_files(project_root, (".cpp", ".cc", ".cxx")):
        if _RCPP_CPP_USAGE_RE.search(_read(p)):
            return True
    description = project_root / "DESCRIPTION"
    if description.is_file() and _DESCRIPTION_RCPP_RE.search(_read(description)):
        return True
    return False


def _has_makevars(project_root: Path) -> bool:
    return any(
        (project_root / "src" / name).is_file()
        for name in ("Makevars", "Makevars.in", "Makevars.win")
    ) or any(
        p.name in ("Makevars", "Makevars.in", "Makevars.win")
        for p in project_root.rglob("Makevars*")
        if p.is_file()
    )


# ---------------------------------------------------------------------------
# Cython
# ---------------------------------------------------------------------------

_CYTHON_PY_USAGE_RE = re.compile(r"\bpyximport\b|\bcythonize\s*\(")


def _uses_cython(project_root: Path) -> bool:
    if _iter_files(project_root, (".pyx", ".pxd")):
        return True
    for p in _iter_files(project_root, (".py",)):
        if _CYTHON_PY_USAGE_RE.search(_read(p)):
            return True
    return False


def _has_cython_build_instructions(project_root: Path) -> bool:
    setup_py = project_root / "setup.py"
    if setup_py.is_file() and "cythonize" in _read(setup_py):
        return True
    for p in _iter_files(project_root, (".toml",)):
        text = _read(p)
        if "cython" in text.lower() and ("build-system" in text or "[tool." in text):
            return True
    return False


# ---------------------------------------------------------------------------
# MEX (MATLAB)
# ---------------------------------------------------------------------------

_MEXFUNCTION_RE = re.compile(r"\bmexFunction\b")
_MEX_BUILD_CALL_RE = re.compile(r"\bmex\s*\(")


def _uses_mex(project_root: Path) -> bool:
    for p in _iter_files(project_root, (".c", ".cpp", ".cc", ".cxx")):
        if _MEXFUNCTION_RE.search(_read(p)):
            return True
    return False


def _has_mex_build_instructions(project_root: Path) -> bool:
    for p in _iter_files(project_root, (".m", ".sh")):
        if _MEX_BUILD_CALL_RE.search(_read(p)):
            return True
    return False


# ---------------------------------------------------------------------------
# Output model + top-level check
# ---------------------------------------------------------------------------


class MixedLanguageFinding(BaseModel):
    language: str   # "Rcpp" | "Cython" | "MEX"
    note: str


class MixedLanguageCheckResult(BaseModel):
    findings: list[MixedLanguageFinding] = Field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0


def check_mixed_language_compilation(project_root: Path) -> MixedLanguageCheckResult:
    findings: list[MixedLanguageFinding] = []

    if _uses_rcpp(project_root) and not _has_makevars(project_root):
        findings.append(
            MixedLanguageFinding(
                language="Rcpp",
                note=(
                    "Rcpp code found (library(Rcpp)/sourceCpp()/Rcpp:: attributes or "
                    "DESCRIPTION LinkingTo: Rcpp) but no src/Makevars or "
                    "src/Makevars.win was found. The C++ compile step will fall back "
                    "to R's default toolchain flags — if the author's own machine "
                    "relies on a flag that isn't R's default (OpenMP, a header-only "
                    "library include path, a specific C++ standard), a replicator's "
                    "run may compile with different flags (silently different "
                    "numerics) or fail outright."
                ),
            )
        )

    if _uses_cython(project_root) and not _has_cython_build_instructions(project_root):
        findings.append(
            MixedLanguageFinding(
                language="Cython",
                note=(
                    "Cython (.pyx) code or pyximport/cythonize() usage found, but no "
                    "setup.py calling cythonize() and no pyproject.toml Cython build "
                    "config was found. Without a declared build step, compile flags "
                    "and the C/C++ compiler used are whatever the replicator's "
                    "environment happens to default to."
                ),
            )
        )

    if _uses_mex(project_root) and not _has_mex_build_instructions(project_root):
        findings.append(
            MixedLanguageFinding(
                language="MEX",
                note=(
                    "A MEX gateway function (mexFunction) was found in C/C++ source, "
                    "but no script was found calling MATLAB's mex() build command. "
                    "Without a recorded mex() call (and its flags), a replicator has "
                    "no record of how the .mex file was built, including any compiler "
                    "flags the author relied on."
                ),
            )
        )

    return MixedLanguageCheckResult(findings=findings)


def write_mixed_language_warnings_file(
    working_copy: Path, result: MixedLanguageCheckResult
) -> Path:
    lines = [
        "# DeadReckoning — Mixed-Language Compilation Warnings\n\n",
        "Code embedding one language's compiled extensions inside another "
        "(Rcpp, Cython, MEX, ...) was found with no declared build step for "
        "the compiled part. This is advisory only; the pipeline is not "
        "blocked by it.\n\n",
    ]
    for f in result.findings:
        lines.append(f"## {f.language}\n\n{f.note}\n\n")
    path = working_copy / _MIXED_LANGUAGE_WARNINGS_FILE
    path.write_text("".join(lines))
    return path


def run_mixed_language_check_step(working_copy: Path) -> MixedLanguageCheckResult:
    result = check_mixed_language_compilation(working_copy)
    if result.has_findings:
        write_mixed_language_warnings_file(working_copy, result)
    return result
