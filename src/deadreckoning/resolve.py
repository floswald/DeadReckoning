"""
RESOLVE step: rewrite absolute/external paths in R scripts to project-relative
paths, generate data-manifest.csv, and write AGENT_REPORT.md.

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
    here_adoptions: int = 0
    data_manifest: list[DataManifestEntry] = Field(default_factory=list)
    report_path: Path | None = None
    secrets_excluded: list[str] = Field(default_factory=list)

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
    Rewrite absolute/external paths in R scripts to project-relative paths.

    Writes:
      - modified R scripts (in-place on working copy)
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

        # Apply rewrite to each affected script
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

    # here::here() adoption — wrap remaining string literals that look like
    # relative data paths: "data/..." or "output/..." etc.
    here_count = 0
    if adopt_here and rewrites:
        here_count = _adopt_here(working_copy, manifest_entries)

    # Exclude secret files from working copy
    excluded: list[str] = []
    for sf in scan.secret_files:
        target_path = working_copy / sf.path
        if target_path.exists():
            target_path.unlink()
            excluded.append(str(sf.path))

    # Write data-manifest.csv
    _write_data_manifest(working_copy, manifest_entries)

    # Write AGENT_REPORT.md
    report_path = _write_agent_report(
        working_copy,
        rewrites=rewrites,
        here_count=here_count,
        manifest=manifest_entries,
        secrets_excluded=excluded,
        download_calls=scan.download_calls,
    )

    return ResolveResult(
        rewrites=rewrites,
        here_adoptions=here_count,
        data_manifest=manifest_entries,
        report_path=report_path,
        secrets_excluded=excluded,
    )


# ---------------------------------------------------------------------------
# here::here() adoption
# ---------------------------------------------------------------------------

# Matches relative paths like "data/foo.csv" or "output/fig1.pdf" in R strings
_REL_DATA_PATH_RE = re.compile(
    r'(["\'])((data|output|figures|tables|code|results)/[^"\']+)\1'
)


def _adopt_here(working_copy: Path, _manifest: list[DataManifestEntry]) -> int:
    """
    Wrap relative path strings in here::here(...).

    Only modifies lines that are NOT already using here::here().
    Returns total number of adoptions across all scripts.
    """
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

    lines.append(f"\n## here::here() adoptions\n\n{here_count} relative paths wrapped.")

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
