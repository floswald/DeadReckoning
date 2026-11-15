"""
Compiled-language build-step detection — Action Point 4 in compare.md.

A Fortran/C/C++ source file can't be "run" the way run_natively executes
an R/Python/Stata/Julia/MATLAB script — it has to be compiled first.
Unlike every other language DeadReckoning targets, there is no guarantee a
build artifact (Makefile, CMakeLists.txt, a build/compile shell script)
exists at all: an author may just be re-running a compile command from
shell history (fish, like most modern shells, makes this easy to do
without ever having saved the command to a file). DeadReckoning cannot
guess that command from disk, so when compiled-language source is present
and no build artifact is found anywhere in the project, this must be a
blocking question, not a silent skip or a non-blocking warning.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .models import Gap, GapKind

_COMPILED_EXTS = (".f90", ".f95", ".f", ".for", ".c", ".cpp", ".cc", ".cxx")

_BUILD_FILENAMES = (
    "Makefile", "makefile", "GNUmakefile",
    "CMakeLists.txt", "configure", "build.sh", "compile.sh",
)

_COMPILER_INVOCATION_RE = re.compile(
    r"\b(?:gcc|g\+\+|gfortran|clang|clang\+\+|cmake|make)\b"
)

_SKIP_DIRS = frozenset({".git", "_archive", "__pycache__", "node_modules"})


def _rel_parts(p: Path, project_root: Path) -> tuple[str, ...]:
    return p.relative_to(project_root).parts


def find_compiled_sources(project_root: Path) -> list[Path]:
    """Every Fortran/C/C++ source file in the project, skipping VCS/cache dirs."""
    sources: set[Path] = set()
    for ext in _COMPILED_EXTS:
        sources.update(
            p for p in project_root.rglob(f"*{ext}")
            if p.is_file() and not any(part in _SKIP_DIRS for part in _rel_parts(p, project_root))
        )
    return sorted(sources)


def find_build_script(project_root: Path) -> Optional[Path]:
    """
    A named build file (checked at the project root and one level into a
    conventional code/ dir), or any .sh/.bat script whose content invokes a
    compiler or build tool. First match wins — existence is what matters,
    not which one it is.
    """
    for name in _BUILD_FILENAMES:
        for base in (project_root, project_root / "code"):
            candidate = base / name
            if candidate.is_file():
                return candidate

    for p in sorted(project_root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".sh", ".bat"):
            continue
        if any(part in _SKIP_DIRS for part in _rel_parts(p, project_root)):
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        if _COMPILER_INVOCATION_RE.search(text):
            return p
    return None


def check_compiled_language_build(project_root: Path) -> Optional[Gap]:
    """
    None if there's no compiled-language source in the project, or a build
    artifact was found for it. Otherwise a blocking Gap asking the author
    for the exact compile (and run) command — see ask.py's wiring of
    GapKind.compiled_language_no_build_script.
    """
    sources = find_compiled_sources(project_root)
    if not sources:
        return None
    if find_build_script(project_root) is not None:
        return None

    shown = sources[:5]
    names = ", ".join(str(s.relative_to(project_root)) for s in shown)
    more = f" (+{len(sources) - 5} more)" if len(sources) > 5 else ""
    return Gap(
        kind=GapKind.compiled_language_no_build_script,
        exhibit=None,
        location="compiled_language_build",
        note=(
            f"Compiled-language source found ({names}{more}) but no "
            "Makefile/CMakeLists.txt/build script, and no shell/batch "
            "script invoking a compiler, was found anywhere in the project."
        ),
    )
