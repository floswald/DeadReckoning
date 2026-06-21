"""
RESOLVE step: rewrite absolute/external paths in scripts to project-relative
paths, generate data-manifest.csv, and write AGENT_REPORT.md.

Supports R, Python, Julia, MATLAB, and Stata.
All mutations happen on the working copy — never the original.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .models import PathRewrite
from .scan import ExternalPath, ScanResult


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class DataManifestEntry(BaseModel):
    original_path: str
    rewritten_path: str
    kind: str
    exists_on_disk: bool
    scripts_affected: list[str] = Field(default_factory=list)


class ResolveResult(BaseModel):
    rewrites: list[PathRewrite] = Field(default_factory=list)
    here_adoptions: int = 0        # R: here::here()
    pathlib_adoptions: int = 0     # Python: Path(__file__).parents[N]
    at_dir_adoptions: int = 0      # Julia: joinpath(@__DIR__, ...)
    fullfile_adoptions: int = 0    # MATLAB: fullfile(fileparts(mfilename(...)))
    data_manifest: list[DataManifestEntry] = Field(default_factory=list)
    report_path: Path | None = None
    secrets_excluded: list[str] = Field(default_factory=list)
    config_do_written: bool = False

    @property
    def rewrite_count(self) -> int:
        return len(self.rewrites)


# ---------------------------------------------------------------------------
# Path rewrite logic
# ---------------------------------------------------------------------------

def _target_relative_path(raw: str) -> str:
    """
    Derive a project-relative target path from an absolute/external path.

    Strategy: keep only the basename, place under data/.
    e.g. /Users/jsmith/Dropbox/paper/data/lfs_2019.dta  →  data/lfs_2019.dta
         //server/share/project/results/tab1.tex          →  data/tab1.tex
         C:\\Users\\jsmith\\data\\survey.csv              →  data/survey.csv
    """
    # Split on both / and \ to handle cross-platform paths on any OS
    parts = re.split(r"[/\\]", raw.rstrip("/\\"))
    basename = parts[-1] if parts else raw
    return f"data/{basename}"


def _make_rewrite_pattern(raw: str) -> re.Pattern[str]:
    """Return a regex that matches the exact quoted string in R source."""
    escaped = re.escape(raw)
    return re.compile(
        r'(["\'])' + escaped + r'\1'
    )


def _apply_rewrite(text: str, raw: str, target: str) -> tuple[str, int]:
    """Replace all occurrences of quoted raw path with quoted target. Returns (new_text, count)."""
    pattern = _make_rewrite_pattern(raw)
    count = len(pattern.findall(text))
    new_text = pattern.sub(lambda m: m.group(1) + target + m.group(1), text)
    return new_text, count


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_paths(
    working_copy: Path,
    scan: ScanResult,
    *,
    adopt_here: bool = True,
) -> ResolveResult:
    """
    Rewrite absolute/external paths in scripts to project-relative paths.

    Supports R, Python, Julia, MATLAB, Stata.
    Writes:
      - modified scripts (in-place on working copy)
      - data/data-manifest.csv
      - AGENT_REPORT.md

    Returns ResolveResult describing every change made.
    """
    if scan.external_paths:
        _ensure_data_dir(working_copy)

    # Group external paths by raw string so we rewrite once per unique path
    unique: dict[str, list[ExternalPath]] = {}
    for ep in scan.external_paths:
        unique.setdefault(ep.raw, []).append(ep)

    rewrites: list[PathRewrite] = []
    manifest_entries: list[DataManifestEntry] = []

    for raw, occurrences in unique.items():
        target = _target_relative_path(raw)
        scripts_affected = sorted({str(ep.script) for ep in occurrences})

        # Apply rewrite to each affected script (language-agnostic)
        for script_rel in scripts_affected:
            script_abs = working_copy / script_rel
            if not script_abs.exists():
                continue
            original = script_abs.read_text(errors="replace")
            updated, n = _apply_rewrite(original, raw, target)
            if n:
                script_abs.write_text(updated)

        rewrites.append(PathRewrite(
            original=raw,
            rewritten=target,
            scripts_affected=[Path(s) for s in scripts_affected],
        ))
        manifest_entries.append(DataManifestEntry(
            original_path=raw,
            rewritten_path=target,
            kind=occurrences[0].kind,
            exists_on_disk=(working_copy / target).exists(),
            scripts_affected=scripts_affected,
        ))

    # Language-specific relative path canonicalization.
    # Wraps relative data/output/figures/... paths in idiomatic project-root
    # expressions so scripts work regardless of the calling working directory.
    here_count = 0
    pathlib_count = 0
    at_dir_count = 0
    fullfile_count = 0
    if adopt_here and rewrites:
        here_count = _adopt_here(working_copy, manifest_entries)
        pathlib_count = _adopt_python_pathlib(working_copy, manifest_entries)
        at_dir_count = _adopt_julia_at_dir(working_copy, manifest_entries)
        fullfile_count = _adopt_matlab_fullfile(working_copy, manifest_entries)

    # Exclude secret files from working copy
    excluded: list[str] = []
    for sf in scan.secret_files:
        target_path = working_copy / sf.path
        if target_path.exists():
            target_path.unlink()
            excluded.append(str(sf.path))

    # For Stata projects: generate code/_config.do (ado install + sysdir redirect)
    config_do_written = False
    if list(working_copy.rglob("*.do")):
        from .scan import _scan_stata_internals
        from .stata import write_config_do
        stata_specific_pkgs, _ = _scan_stata_internals(working_copy)
        if stata_specific_pkgs:
            write_config_do(working_copy, sorted(stata_specific_pkgs))
            config_do_written = True

    # Write data-manifest.csv
    _write_data_manifest(working_copy, manifest_entries)

    # Write AGENT_REPORT.md
    report_path = _write_agent_report(
        working_copy,
        rewrites=rewrites,
        here_count=here_count,
        pathlib_count=pathlib_count,
        at_dir_count=at_dir_count,
        fullfile_count=fullfile_count,
        manifest=manifest_entries,
        secrets_excluded=excluded,
        download_calls=scan.download_calls,
    )

    return ResolveResult(
        rewrites=rewrites,
        here_adoptions=here_count,
        pathlib_adoptions=pathlib_count,
        at_dir_adoptions=at_dir_count,
        fullfile_adoptions=fullfile_count,
        data_manifest=manifest_entries,
        report_path=report_path,
        secrets_excluded=excluded,
        config_do_written=config_do_written,
    )


# ---------------------------------------------------------------------------
# Language-specific relative path canonicalization
# ---------------------------------------------------------------------------

# Matches relative paths like "data/foo.csv" or "output/fig1.pdf" in any string
_REL_DATA_PATH_RE = re.compile(
    r'(["\'])((data|output|figures|tables|code|results)/[^"\']+)\1'
)


def _script_depth(script: Path, working_copy: Path) -> int:
    """Directory depth of script relative to project root (0 = at root, 1 = in code/, etc.)"""
    try:
        rel = script.relative_to(working_copy)
        return len(rel.parts) - 1
    except ValueError:
        return 0


def _adopt_here(working_copy: Path, _manifest: list[DataManifestEntry]) -> int:
    """Wrap relative path strings in R scripts with here::here(...)."""
    count = 0
    for script in working_copy.rglob("*.R"):
        text = script.read_text(errors="replace")
        lines_out: list[str] = []
        changed = False
        for line in text.splitlines(keepends=True):
            if "here::here" in line or line.lstrip().startswith("#"):
                lines_out.append(line)
                continue
            new_line, n = _REL_DATA_PATH_RE.subn(
                lambda m: f'here::here("{m.group(2)}")',
                line,
            )
            if n:
                lines_out.append(new_line)
                count += n
                changed = True
            else:
                lines_out.append(line)
        if changed:
            script.write_text("".join(lines_out))
    return count


def _adopt_python_pathlib(working_copy: Path, _manifest: list[DataManifestEntry]) -> int:
    """
    Wrap relative data paths in Python scripts with Path(__file__).parents[N] expressions.

    Inserts `from pathlib import Path` if not already present.
    Skips scripts at project root (depth=0) where relative paths work as-is.
    """
    count = 0
    for script in working_copy.rglob("*.py"):
        depth = _script_depth(script, working_copy)
        if depth == 0:
            continue
        text = script.read_text(errors="replace")
        needs_import = (
            "from pathlib import Path" not in text
            and "import pathlib" not in text
        )
        lines_out: list[str] = []
        changed = False
        import_added = False
        for line in text.splitlines(keepends=True):
            # Insert import before first non-comment, non-blank, non-import line
            if needs_import and not import_added and line.strip() and not line.lstrip().startswith("#"):
                lines_out.append("from pathlib import Path\n")
                import_added = True
            if "Path(__file__)" in line or line.lstrip().startswith("#"):
                lines_out.append(line)
                continue
            new_line, n = _REL_DATA_PATH_RE.subn(
                lambda m, d=depth: f'str(Path(__file__).parents[{d}] / "{m.group(2)}")',
                line,
            )
            if n:
                lines_out.append(new_line)
                count += n
                changed = True
            else:
                lines_out.append(line)
        if changed:
            script.write_text("".join(lines_out))
    return count


def _adopt_julia_at_dir(working_copy: Path, _manifest: list[DataManifestEntry]) -> int:
    """
    Wrap relative data paths in Julia scripts with joinpath(@__DIR__, ...) expressions.

    Skips scripts at project root (depth=0).
    """
    count = 0
    for script in working_copy.rglob("*.jl"):
        depth = _script_depth(script, working_copy)
        if depth == 0:
            continue
        ups = ", ".join(['"..\"'] * depth)
        text = script.read_text(errors="replace")
        lines_out: list[str] = []
        changed = False
        for line in text.splitlines(keepends=True):
            if "@__DIR__" in line or line.lstrip().startswith("#"):
                lines_out.append(line)
                continue
            new_line, n = _REL_DATA_PATH_RE.subn(
                lambda m, u=ups: f'joinpath(@__DIR__, {u}, "{m.group(2)}")',
                line,
            )
            if n:
                lines_out.append(new_line)
                count += n
                changed = True
            else:
                lines_out.append(line)
        if changed:
            script.write_text("".join(lines_out))
    return count


def _adopt_matlab_fullfile(working_copy: Path, _manifest: list[DataManifestEntry]) -> int:
    """
    Wrap relative data paths in MATLAB scripts with fullfile(fileparts(mfilename(...))) expressions.

    Skips scripts at project root (depth=0).
    """
    _REL_MATLAB_RE = re.compile(
        r"(['\"])((data|output|figures|tables|code|results)/[^'\"]+)\1"
    )
    count = 0
    for script in working_copy.rglob("*.m"):
        depth = _script_depth(script, working_copy)
        if depth == 0:
            continue
        ups = ", '..'" * depth
        prefix = f"fullfile(fileparts(mfilename('fullpath')){ups}, "
        text = script.read_text(errors="replace")
        lines_out: list[str] = []
        changed = False
        for line in text.splitlines(keepends=True):
            if "mfilename" in line or line.lstrip().startswith("%"):
                lines_out.append(line)
                continue
            new_line, n = _REL_MATLAB_RE.subn(
                lambda m, p=prefix: f"{p}'{m.group(2)}')",
                line,
            )
            if n:
                lines_out.append(new_line)
                count += n
                changed = True
            else:
                lines_out.append(line)
        if changed:
            script.write_text("".join(lines_out))
    return count


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------

def _ensure_data_dir(working_copy: Path) -> None:
    (working_copy / "data").mkdir(exist_ok=True)


def _write_data_manifest(
    working_copy: Path,
    entries: list[DataManifestEntry],
) -> None:
    if not entries:
        return
    out = working_copy / "data" / "data-manifest.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["original_path", "rewritten_path", "kind",
                        "exists_on_disk", "scripts_affected"],
        )
        writer.writeheader()
        for e in entries:
            writer.writerow({
                "original_path":  e.original_path,
                "rewritten_path": e.rewritten_path,
                "kind":           e.kind,
                "exists_on_disk": e.exists_on_disk,
                "scripts_affected": "; ".join(e.scripts_affected),
            })


def _write_agent_report(
    working_copy: Path,
    *,
    rewrites: list[PathRewrite],
    here_count: int,
    pathlib_count: int = 0,
    at_dir_count: int = 0,
    fullfile_count: int = 0,
    manifest: list[DataManifestEntry],
    secrets_excluded: list[str],
    download_calls: list,
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# DeadReckoning — Agent Report",
        f"\nGenerated: {ts}",
        "\n## Path rewrites\n",
    ]

    if rewrites:
        lines.append("| Original | Rewritten | Scripts |")
        lines.append("|----------|-----------|---------|")
        for r in rewrites:
            scripts = ", ".join(str(s) for s in r.scripts_affected)
            lines.append(f"| `{r.original}` | `{r.rewritten}` | {scripts} |")
    else:
        lines.append("_No path rewrites needed._")

    canonicalizations = [
        ("R `here::here()`", here_count),
        ("Python `Path(__file__).parents`", pathlib_count),
        ("Julia `joinpath(@__DIR__, ...)`", at_dir_count),
        ("MATLAB `fullfile(fileparts(mfilename(...)))`", fullfile_count),
    ]
    canon_lines = [f"  - {label}: {n}" for label, n in canonicalizations if n > 0]
    if canon_lines:
        lines.append("\n## Relative path canonicalization\n")
        lines.extend(canon_lines)
    else:
        lines.append("\n## Relative path canonicalization\n\n_None needed._")

    if secrets_excluded:
        lines.append("\n## Secrets excluded\n")
        for s in secrets_excluded:
            lines.append(f"- `{s}`")
    else:
        lines.append("\n## Secrets excluded\n\n_None._")

    if download_calls:
        lines.append("\n## External downloads detected\n")
        lines.append("These URLs were found in `download.file()` calls. "
                      "Checksums should be added before final submission.\n")
        for dl in download_calls:
            lines.append(f"- `{dl.url}` ({dl.script}:{dl.line})")

    lines.append("\n## Data manifest\n")
    if manifest:
        lines.append("See `data/data-manifest.csv` for full list.")
    else:
        lines.append("_No external data files detected._")

    report = working_copy / "AGENT_REPORT.md"
    report.write_text("\n".join(lines) + "\n")
    return report
