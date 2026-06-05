"""Build the output dependency graph rooted at the LaTeX source."""

from __future__ import annotations

import re
from pathlib import Path

from .models import (
    DataFile,
    DependencyGraph,
    Exhibit,
    Gap,
    GapKind,
    OrphanFile,
    ScriptWritesExhibit,
)

# ---------------------------------------------------------------------------
# LaTeX exhibit extraction
# ---------------------------------------------------------------------------

# Patterns that reference external files in LaTeX
_TEX_INCLUDE_RE = re.compile(
    r"\\(?:includegraphics|input|include|lstinputlisting|verbatiminput|includesvg)"
    r"\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}",
    re.MULTILINE,
)

# Inline table: \begin{tabular} appearing outside any \input{} — look for
# tabular environments that contain numbers and are not inside an \input call.
_INLINE_TABULAR_RE = re.compile(
    r"\\begin\{table[*]?\}(.*?)\\end\{table[*]?\}",
    re.DOTALL,
)
_HAS_TABULAR_RE = re.compile(r"\\begin\{tabular\}")
_HAS_INPUT_RE = re.compile(r"\\input\s*\{")

# Inline statistics: decimal numbers that look like regression results.
# Only flag when followed by significance stars or a standard error in parens —
# bare decimals (LaTeX option args, coordinates, scale factors) are too common.
_INLINE_STAT_RE = re.compile(
    r"(?<![\\{\[=,])"           # not inside a LaTeX command arg or option
    r"-?\d+\.\d{2,4}"           # decimal number
    r"(?:"
    r"\s*\*{1,3}"               # significance stars (required for bare number)
    r"|"
    r"\s*\([0-9.]+\)"           # OR standard error in parens (required)
    r")",
)

# \newcommand{\macroname}{value} — capture path-like macro definitions
_NEWCOMMAND_RE = re.compile(
    r"\\newcommand\s*\{\\([A-Za-z]+)\}\s*\{([^}]+)\}"
)

# Commented-out lines — strip before macro/exhibit extraction
_COMMENT_LINE_RE = re.compile(r"(?m)^[^\S\n]*%.*$")
_INLINE_COMMENT_RE = re.compile(r"(?<!\\)%.*$", re.MULTILINE)


def _collect_tex_macros(tex_files: list[Path]) -> dict[str, str]:
    """
    Scan all tex files for \\newcommand{\\name}{value} definitions where
    the value looks like a path (contains / or ..). Returns {name: value}.
    """
    macros: dict[str, str] = {}
    for tex in tex_files:
        try:
            text = tex.read_text(errors="replace")
        except OSError:
            continue
        for name, value in _NEWCOMMAND_RE.findall(text):
            value = value.strip()
            # Only keep macros that look like path fragments
            if "/" in value or value.startswith("..") or value.startswith("."):
                macros[name] = value
    return macros


def _expand_macros(ref: str, macros: dict[str, str]) -> str:
    """Replace \\macroname occurrences in ref with their defined values."""
    for name, value in macros.items():
        ref = ref.replace(f"\\{name}", value)
    return ref


def _extract_exhibits_from_tex(
    tex_path: Path, macros: dict[str, str] | None = None
) -> list[Path]:
    """Return all external file paths referenced via include/input/includegraphics."""
    text = tex_path.read_text(errors="replace")
    # Strip comments so commented-out \includegraphics lines are ignored
    text = _INLINE_COMMENT_RE.sub("", text)
    raw = _TEX_INCLUDE_RE.findall(text)
    exhibits: list[Path] = []
    tex_dir = tex_path.parent
    for ref in raw:
        ref = ref.strip()
        if macros:
            ref = _expand_macros(ref, macros)
        # Skip refs that still contain unexpanded macros (start with \)
        if ref.startswith("\\"):
            continue
        p = Path(ref)
        exhibits.append((tex_dir / p).resolve() if not p.is_absolute() else p.resolve())
    return exhibits


def _find_inline_tables(tex_path: Path) -> list[Gap]:
    """Flag table environments whose content is typed directly (no \\input{})."""
    text = tex_path.read_text(errors="replace")
    gaps: list[Gap] = []
    for m in _INLINE_TABULAR_RE.finditer(text):
        body = m.group(1)
        if _HAS_TABULAR_RE.search(body) and not _HAS_INPUT_RE.search(body):
            start_line = text[: m.start()].count("\n") + 1
            end_line = text[: m.end()].count("\n") + 1
            gaps.append(
                Gap(
                    kind=GapKind.inline_table,
                    location=f"{tex_path.name}:{start_line}-{end_line}",
                    snippet=body[:200].strip(),
                )
            )
    return gaps


def _find_inline_statistics(tex_path: Path) -> list[Gap]:
    """Flag numeric patterns in body text outside any \\input{} that look like results."""
    text = tex_path.read_text(errors="replace")
    # Remove content inside \input{...} blocks (simple heuristic: anything on an \input line)
    cleaned = re.sub(r"\\input\s*\{[^}]*\}", "", text)
    # Remove math environments — we care about prose, not equations
    cleaned = re.sub(r"\$[^$]+\$", "", cleaned)
    cleaned = re.sub(r"\\begin\{equation\*?\}.*?\\end\{equation\*?\}", "", cleaned, flags=re.DOTALL)

    gaps: list[Gap] = []
    for m in _INLINE_STAT_RE.finditer(cleaned):
        val = m.group(0).strip()
        if not val:
            continue
        line = text[: m.start()].count("\n") + 1
        gaps.append(
            Gap(
                kind=GapKind.inline_statistic,
                location=f"{tex_path.name}:{line}",
                snippet=val,
            )
        )
    # Deduplicate by location
    seen: set[str] = set()
    deduped: list[Gap] = []
    for g in gaps:
        if g.location not in seen:
            seen.add(g.location or "")
            deduped.append(g)
    return deduped


# ---------------------------------------------------------------------------
# Script write-call extraction
# ---------------------------------------------------------------------------

# Maps language (by file extension) to patterns that write a file to disk
_WRITE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    ".R": [
        re.compile(r'ggsave\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(r'ggsave\s*\(\s*filename\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(r'pdf\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'png\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'svg\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'cairo_pdf\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'write\.csv\s*\([^,]+,\s*["\']([^"\']+)["\']'),
        re.compile(r'write_csv\s*\([^,]+,\s*["\']([^"\']+)["\']'),
        re.compile(r'saveRDS\s*\([^,]+,\s*["\']([^"\']+)["\']'),
        re.compile(r'sink\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'stargazer\s*\(.*?out\s*=\s*["\']([^"\']+)["\']', re.DOTALL),
        re.compile(r'knitr::kable\s*\(.*?file\s*=\s*["\']([^"\']+)["\']', re.DOTALL),
        re.compile(r'writeLines\s*\([^,]+,\s*["\']([^"\']+)["\']'),
    ],
    ".r": [],  # same as .R — handled below
    ".do": [
        re.compile(r'graph\s+export\s+["\']?([^\s,"\']+)', re.IGNORECASE),
        re.compile(r'outsheet\s+using\s+["\']?([^\s,"\']+)', re.IGNORECASE),
        re.compile(r'save\s+["\']?([^\s,"\']+\.dta)', re.IGNORECASE),
        re.compile(r'esttab\s+.*?using\s+["\']?([^\s,"\']+)', re.IGNORECASE),
        re.compile(r'outreg2\s+.*?using\s+["\']?([^\s,"\']+)', re.IGNORECASE),
        re.compile(r'texsave\s+.*?using\s+["\']?([^\s,"\']+)', re.IGNORECASE),
    ],
    ".py": [
        re.compile(r'savefig\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'to_csv\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'to_parquet\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'open\s*\(\s*["\']([^"\']+)["\'],\s*["\']w'),
    ],
    ".jl": [
        re.compile(r'savefig\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'CSV\.write\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'open\s*\(\s*["\']([^"\']+)["\'],\s*["\']w'),
    ],
}
_WRITE_PATTERNS[".r"] = _WRITE_PATTERNS[".R"]


def _extract_write_calls(script: Path) -> list[ScriptWritesExhibit]:
    """Return all file-write calls found in a script."""
    ext = script.suffix.lower() if script.suffix else script.suffix
    patterns = _WRITE_PATTERNS.get(ext, [])
    if not patterns:
        return []

    try:
        lines = script.read_text(errors="replace").splitlines()
    except OSError:
        return []

    results: list[ScriptWritesExhibit] = []
    for lineno, line in enumerate(lines, start=1):
        for pat in patterns:
            m = pat.search(line)
            if m:
                written = m.group(1).strip()
                results.append(
                    ScriptWritesExhibit(
                        script=script,
                        write_call=pat.pattern.split(r"\s")[0].lstrip("\\"),
                        line=lineno,
                        written_path=Path(written),
                    )
                )
    return results


# ---------------------------------------------------------------------------
# Data file reference extraction (R only for Phase 0)
# ---------------------------------------------------------------------------

_R_READ_RE = re.compile(
    r'(?:read\.csv|read_csv|read\.dta|haven::read_dta|readRDS|load)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_ABSOLUTE_PATH_RE = re.compile(
    r'["\'](?:/|[A-Za-z]:\\\\|~/)[^"\']{5,}["\']'
)


def _extract_data_refs(script: Path, project_root: Path) -> list[DataFile]:
    try:
        text = script.read_text(errors="replace")
    except OSError:
        return []

    results: list[DataFile] = []
    for m in _R_READ_RE.finditer(text):
        raw = m.group(1).strip()
        p = Path(raw)
        is_external = p.is_absolute() or raw.startswith("~/")
        kind: str | None = None
        if is_external:
            low = raw.lower()
            if "dropbox" in low:
                kind = "dropbox"
            elif any(x in low for x in ("/mnt/", "/scratch/", "/nfs/")):
                kind = "network_share" if "/nfs/" in low else "hpc"
            else:
                kind = "absolute_path"
        results.append(
            DataFile(
                path=p,
                exists_on_disk=(project_root / p).exists() if not is_external else p.exists(),
                referenced_by=[script],
                is_external=is_external,
                external_kind=kind,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_SCRIPT_EXTENSIONS = {".R", ".r", ".do", ".py", ".jl", ".m"}


def build_graph(project_root: Path) -> DependencyGraph:
    """
    Build the dependency graph for a project rooted at project_root.
    Pure function: reads files, returns a DependencyGraph. No side effects.
    """
    project_root = project_root.resolve()

    # 1. Find .tex files
    tex_files = sorted(project_root.rglob("*.tex"))

    # 2. Collect LaTeX path macros (\newcommand{\dataplots}{../output/data/plots})
    #    before extracting exhibits so macro-based paths can be expanded.
    macros = _collect_tex_macros(tex_files)

    # 3. Find all scripts
    scripts: list[Path] = []
    for ext in _SCRIPT_EXTENSIONS:
        scripts.extend(project_root.rglob(f"*{ext}"))
    scripts = sorted(set(scripts))

    # 4. Extract all write calls from scripts
    all_writes: list[ScriptWritesExhibit] = []
    for script in scripts:
        all_writes.extend(_extract_write_calls(script))

    # 5. Extract exhibits from .tex files (returns resolved absolute paths)
    raw_exhibit_paths: list[Path] = []
    tex_gaps: list[Gap] = []
    for tex in tex_files:
        raw_exhibit_paths.extend(_extract_exhibits_from_tex(tex, macros))

    # Collect the set of resolved output tex files so we don't scan them
    # for inline content — they're generated tables, not prose.
    # Two complementary heuristics:
    #   1. Any tex file explicitly referenced as an exhibit.
    #   2. Any tex file that lives inside a directory named "output" or "tables"
    #      at any depth — these are generated table fragments, not manuscript prose.
    output_tex_abs: set[Path] = set(raw_exhibit_paths)

    def _is_output_tex(p: Path) -> bool:
        if p.resolve() in output_tex_abs:
            return True
        parts = {part.lower() for part in p.parts}
        return bool(parts & {"output", "outputs"})

    for tex in tex_files:
        if _is_output_tex(tex):
            continue
        tex_gaps.extend(_find_inline_tables(tex))
        tex_gaps.extend(_find_inline_statistics(tex))

    # Deduplicate (already resolved absolute paths)
    seen_exhibits: set[Path] = set()
    exhibit_paths: list[Path] = []
    for p in raw_exhibit_paths:
        if p not in seen_exhibits:
            seen_exhibits.add(p)
            exhibit_paths.append(p)

    # 6. Match exhibits to write calls
    exhibits: list[Exhibit] = []
    gaps: list[Gap] = []

    for abs_tex in exhibit_paths:
        exists = abs_tex.exists()

        # Find a write call whose written_path resolves to the same file.
        # Try both script-relative and project-root-relative resolution —
        # authors often write relative paths that are meant to be relative to
        # the project root, not the script's location.
        source: ScriptWritesExhibit | None = None
        path_mismatch = False

        for w in all_writes:
            written_abs_script = (w.script.parent / w.written_path).resolve()
            written_abs_root = (project_root / w.written_path).resolve()
            if written_abs_script == abs_tex or written_abs_root == abs_tex:
                source = w
                break

        # If no exact match, look for a write call with same filename (different dir)
        if source is None and exists:
            for w in all_writes:
                if w.written_path.name == abs_tex.name:
                    source = w
                    path_mismatch = True
                    break

        # Store exhibit path relative to project root for readability
        try:
            display_path = abs_tex.relative_to(project_root)
        except ValueError:
            display_path = abs_tex  # outside project root (e.g. macro pointing elsewhere)

        exhibits.append(
            Exhibit(
                tex_path=display_path,
                exists_on_disk=exists,
                source=source,
                path_mismatch=path_mismatch,
            )
        )

        if source is None:
            gaps.append(
                Gap(
                    kind=(
                        GapKind.exhibit_missing_from_disk
                        if not exists
                        else GapKind.exhibit_no_source_script
                    ),
                    exhibit=display_path,
                    candidate_scripts=_candidate_scripts(abs_tex, scripts),
                )
            )
        elif path_mismatch:
            gaps.append(
                Gap(
                    kind=GapKind.script_writes_wrong_path,
                    exhibit=display_path,
                    note=(
                        f"{source.script.name} writes to {source.written_path} "
                        f"but LaTeX expects {display_path}"
                    ),
                )
            )

    gaps.extend(tex_gaps)

    # 7. Data files
    data_files: list[DataFile] = []
    seen_data: set[Path] = set()
    for script in scripts:
        for df in _extract_data_refs(script, project_root):
            key = df.path
            if key not in seen_data:
                seen_data.add(key)
                data_files.append(df)
            else:
                # Add this script to the existing entry's referenced_by
                for existing in data_files:
                    if existing.path == key:
                        if script not in existing.referenced_by:
                            existing.referenced_by.append(script)

    # 7. Orphan files: scripts that produce nothing in the exhibit list
    needed_scripts = {e.source.script for e in exhibits if e.source}
    for script in scripts:
        if script not in needed_scripts:
            # Only flag if also not called by any other script (simple heuristic: name not in any script)
            name = script.stem
            referenced = any(
                name in (s.read_text(errors="replace") if s != script else "")
                for s in scripts
            )
            if not referenced:
                gaps_for_script = [
                    g for g in gaps if g.exhibit and g.exhibit.name == script.name
                ]
                if not gaps_for_script:
                    pass  # don't add as orphan yet — Phase 3 handles full orphan detection

    return DependencyGraph(
        project_root=project_root,
        tex_files=tex_files,
        exhibits=exhibits,
        gaps=gaps,
        data_files=data_files,
        orphan_files=[],
    )


def _candidate_scripts(exhibit_abs: Path, scripts: list[Path]) -> list[Path]:
    """Heuristic: scripts whose name resembles the exhibit name."""
    stem = exhibit_abs.stem.lower()
    return [
        s for s in scripts
        if stem in s.stem.lower() or s.stem.lower() in stem
    ]
