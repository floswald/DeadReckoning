"""
CLEAN step: identify files not reachable from any exhibit, write CLEANUP.md,
parse author disposition choices, and apply them.

Reachability (conservative — prefer false negatives over false positives):
  - Seed: scripts that directly produce an exhibit (graph.exhibits[i].source.script)
  - Expand: any script whose filename stem appears in any script's text
  - Data: all DataFile.path values that live inside the working copy

Everything else on disk is a candidate orphan, grouped as script/data/output/other.

CLEAN is non-blocking: first encounter writes CLEANUP.md and the pipeline
continues (default action = keep). Author may fill in choices; a second run
parses and applies them.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from .models import (
    CleanApplyResult,
    CleanChoice,
    CleanResult,
    DependencyGraph,
    OrphanFile,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLEANUP_FILE = "CLEANUP.md"
_ARCHIVE_DIR = "_archive"

_SCRIPT_EXTS = frozenset({".R", ".r", ".py", ".jl", ".m", ".do", ".sh"})
_DATA_EXTS = frozenset({
    ".csv", ".tsv", ".dta", ".xlsx", ".xls", ".parquet", ".feather",
    ".rds", ".rda", ".rdata", ".mat", ".nc", ".h5", ".hdf5", ".json",
    ".geojson", ".shp", ".zip", ".gz", ".tar",
})
_OUTPUT_EXTS = frozenset({".pdf", ".png", ".eps", ".svg", ".jpg", ".jpeg", ".tif", ".tiff"})
# Extensions that always belong to prose/config — never flagged as orphan
_PROSE_EXTS = frozenset({
    ".tex", ".bib", ".bbl", ".blg", ".sty", ".cls", ".md", ".txt",
    ".toml", ".lock", ".yml", ".yaml", ".cfg", ".ini", ".env",
    ".gitignore", ".gitattributes",
})
_ALWAYS_KEEP_NAMES = frozenset({
    "README.md", "readme.md", "README.txt", "readme.txt",
    "QUESTIONS.md", "CLEANUP.md", "AGENT_REPORT.md",
    "data-manifest.csv",
    "renv.lock", "requirements.txt", "Manifest.toml", "Project.toml",
    "pyproject.toml", "setup.py", "setup.cfg",
    ".gitignore", ".gitattributes", "Makefile",
})
_SKIP_DIRS = frozenset({
    ".git", "_archive", "renv", "__pycache__",
    ".ipynb_checkpoints", ".mypy_cache", ".pytest_cache",
    "node_modules",
})


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


def _reachable_scripts(working_copy: Path, graph: DependencyGraph) -> set[Path]:
    """
    Conservative BFS from exhibit sources.

    A script is reachable if:
      (a) it directly produces an exhibit, OR
      (b) its filename stem appears in any script's text.
    """
    all_scripts: list[Path] = []
    for ext in _SCRIPT_EXTS:
        all_scripts.extend(
            p for p in working_copy.rglob(f"*{ext}") if p.is_file()
            and not any(part in _SKIP_DIRS for part in p.parts)
        )
    all_scripts = list(set(all_scripts))

    # Read all script texts once
    texts: dict[Path, str] = {}
    for s in all_scripts:
        try:
            texts[s] = s.read_text(errors="replace")
        except OSError:
            texts[s] = ""

    # Seeds: scripts that produce exhibits
    exhibit_sources: set[Path] = set()
    for ex in graph.exhibits:
        if ex.source:
            # source.script may be relative to project_root — resolve to working_copy
            src = ex.source.script
            if not src.is_absolute():
                src = working_copy / src
            if src.exists():
                exhibit_sources.add(src.resolve())

    # Also include scripts in topological order (if graph computed them)
    for sp in graph.script_order:
        if not sp.is_absolute():
            sp = working_copy / sp
        if sp.exists():
            exhibit_sources.add(sp.resolve())

    reachable: set[Path] = set(exhibit_sources)

    all_texts_combined = "\n".join(texts.values())

    # Pass 1: scripts that are CALLED — their stem appears in any script's text
    # (sub-scripts, utility scripts referenced by name)
    for s in all_scripts:
        if s.resolve() not in reachable and s.stem in all_texts_combined:
            reachable.add(s.resolve())

    # Pass 2: scripts that CALL a reachable script — their text mentions a
    # reachable stem (master / orchestrator scripts)
    reachable_stems = {s.stem for s in reachable}
    for s in all_scripts:
        if s.resolve() not in reachable:
            t = texts.get(s, "")
            if any(stem in t for stem in reachable_stems):
                reachable.add(s.resolve())

    return reachable


def _reachable_data(working_copy: Path, graph: DependencyGraph) -> set[Path]:
    """All local data files referenced in the graph."""
    local: set[Path] = set()
    for df in graph.data_files:
        p = df.path
        if not p.is_absolute():
            p = working_copy / p
        p = p.resolve()
        if p.is_relative_to(working_copy.resolve()):
            local.add(p)
    return local


def _file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _SCRIPT_EXTS:
        return "script"
    if ext in _DATA_EXTS:
        return "data"
    if ext in _OUTPUT_EXTS:
        return "output"
    return "other"


def find_orphans(working_copy: Path, graph: DependencyGraph) -> list[OrphanFile]:
    """
    Walk working_copy and return files not reachable from any exhibit.

    Skips prose/config files, always-keep filenames, and _SKIP_DIRS.
    Skips directories entirely (only files are candidates).
    """
    reachable_s = _reachable_scripts(working_copy, graph)
    reachable_d = _reachable_data(working_copy, graph)
    reachable = reachable_s | reachable_d

    # Also keep all tex/bib/lock files (prose and env specs)
    tex_files = {t.resolve() for t in graph.tex_files}

    orphans: list[OrphanFile] = []
    for p in sorted(working_copy.rglob("*")):
        if not p.is_file():
            continue
        # Skip hidden and excluded dirs
        if any(part.startswith(".") or part in _SKIP_DIRS for part in p.relative_to(working_copy).parts):
            continue
        # Skip by name
        if p.name in _ALWAYS_KEEP_NAMES:
            continue
        # Skip prose/config extensions
        if p.suffix.lower() in _PROSE_EXTS:
            continue
        # Skip tex files referenced in graph
        if p.resolve() in tex_files:
            continue
        # Skip reachable
        if p.resolve() in reachable:
            continue

        kind = _file_kind(p)
        if kind == "other":
            continue  # don't flag unknown file types

        rel = p.relative_to(working_copy)
        orphans.append(OrphanFile(path=rel, kind=kind))

    return orphans


# ---------------------------------------------------------------------------
# Write / read CLEANUP.md
# ---------------------------------------------------------------------------


def write_cleanup_file(working_copy: Path, orphans: list[OrphanFile]) -> Path:
    """Write CLEANUP.md with one `> Action:` line per orphan."""
    sections: dict[str, list[OrphanFile]] = {"script": [], "data": [], "output": []}
    for o in orphans:
        sections.get(o.kind, sections["output"]).append(o)

    lines = [
        "# DeadReckoning — Cleanup Candidates\n\n",
        "These files are not referenced by any exhibit in the paper.\n",
        "Fill in each `> Action:` line: `delete`, `archive`, or `keep` (default).\n",
        "Then re-run `deadreckoning run` to apply choices.\n\n",
    ]

    for section, label in [("script", "Orphan Scripts"), ("data", "Orphan Data"), ("output", "Orphan Outputs")]:
        items = sections[section]
        if not items:
            continue
        lines.append(f"## {label}\n\n")
        for item in items:
            try:
                size_bytes = (working_copy / item.path).stat().st_size
                size_str = _fmt_size(size_bytes)
            except OSError:
                size_str = "?"
            lines.append(f"### {item.path}\n\n")
            lines.append(f"**Kind:** {item.kind} | **Size:** {size_str}\n\n")
            lines.append("> Action: keep\n\n")
            lines.append("---\n\n")

    path = working_copy / _CLEANUP_FILE
    path.write_text("".join(lines))
    return path


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def parse_cleanup_choices(
    working_copy: Path,
    orphans: list[OrphanFile],
) -> list[CleanChoice]:
    """
    Read CLEANUP.md and extract Action per orphan.

    Positional: Action[i] → orphans[i]. Default (unmodified) is "keep".
    """
    path = working_copy / _CLEANUP_FILE
    if not path.exists():
        return [CleanChoice(path=o.path, kind=o.kind, action="keep") for o in orphans]

    text = path.read_text()
    raw_actions: list[str] = []
    for line in text.splitlines():
        if line.startswith("> Action:"):
            raw = line[len("> Action:"):].strip().lower()
            if raw in ("delete", "archive", "keep"):
                raw_actions.append(raw)
            else:
                raw_actions.append("keep")

    choices: list[CleanChoice] = []
    for i, o in enumerate(orphans):
        action = raw_actions[i] if i < len(raw_actions) else "keep"
        choices.append(CleanChoice(path=o.path, kind=o.kind, action=action))
    return choices


def apply_cleanup_choices(
    working_copy: Path,
    choices: list[CleanChoice],
) -> CleanApplyResult:
    """Execute disposition choices on working_copy (never touches project_root)."""
    result = CleanApplyResult()
    archive_root = working_copy / _ARCHIVE_DIR

    for c in choices:
        src = working_copy / c.path
        if not src.exists():
            continue

        if c.action == "delete":
            src.unlink()
            result.deleted.append(c.path)

        elif c.action == "archive":
            dest = archive_root / c.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            result.archived.append(c.path)

        else:  # keep
            result.kept.append(c.path)

    return result


# ---------------------------------------------------------------------------
# High-level entry point (called by orchestrator)
# ---------------------------------------------------------------------------


def run_clean_step(
    working_copy: Path,
    graph: DependencyGraph,
) -> tuple[CleanResult, bool]:
    """
    Full CLEAN step.

    Returns (result, needs_review).
    needs_review=True  → first encounter; CLEANUP.md written; pipeline continues
    needs_review=False → no orphans, or choices already applied
    """
    orphans = find_orphans(working_copy, graph)

    if not orphans:
        return CleanResult(orphans=[]), False

    cleanup_path = working_copy / _CLEANUP_FILE

    if not cleanup_path.exists():
        write_cleanup_file(working_copy, orphans)
        return CleanResult(orphans=orphans), True  # advisory only — pipeline still continues

    # File exists — parse choices and apply
    choices = parse_cleanup_choices(working_copy, orphans)
    apply_result = apply_cleanup_choices(working_copy, choices)
    return CleanResult(orphans=orphans, choices=choices, apply=apply_result), False
