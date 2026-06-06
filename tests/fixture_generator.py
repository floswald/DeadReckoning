"""
Composable fault-injection generator for DeadReckoning test fixtures.

Design:
- Start from a clean "gold" directory.
- Apply fault modules (each returns a ManifestDelta).
- Accumulate deltas → write manifest.yaml.
- Output goes to any target dir (tmp_path in tests, tests/fixtures/ for committed fixtures).
- Never overwrites existing committed fixtures.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import yaml

from deadreckoning.models import (
    ExpectedGap,
    ExpectedVersionPin,
    GapKind,
    Manifest,
    PathRewrite,
    PinMethod,
)


# ---------------------------------------------------------------------------
# Manifest delta — accumulated by fault modules
# ---------------------------------------------------------------------------


@dataclass
class ManifestDelta:
    gaps: list[ExpectedGap] = field(default_factory=list)
    path_rewrites: list[PathRewrite] = field(default_factory=list)
    version_pins: list[ExpectedVersionPin] = field(default_factory=list)
    files_removed: list[str] = field(default_factory=list)
    is_restricted: bool = False
    restricted_trigger: Optional[str] = None
    notes_lines: list[str] = field(default_factory=list)


def _merge_deltas(base: ManifestDelta, delta: ManifestDelta) -> ManifestDelta:
    base.gaps.extend(delta.gaps)
    base.path_rewrites.extend(delta.path_rewrites)
    base.version_pins.extend(delta.version_pins)
    base.files_removed.extend(delta.files_removed)
    if delta.is_restricted:
        base.is_restricted = True
        base.restricted_trigger = delta.restricted_trigger
    base.notes_lines.extend(delta.notes_lines)
    return base


# ---------------------------------------------------------------------------
# Fault modules — pure functions, mutate target dir, return ManifestDelta
# ---------------------------------------------------------------------------


def delete_lockfile(target: Path) -> ManifestDelta:
    """Remove renv.lock (or any lockfile). Agent must infer version from date."""
    removed: list[str] = []
    for name in ("renv.lock", "Manifest.toml", "Project.toml", "requirements.txt", "environment.yml"):
        p = target / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return ManifestDelta(
        version_pins=[ExpectedVersionPin(language="R", method=PinMethod.inferred_from_date)],
        files_removed=removed,
        notes_lines=[f"Lockfile removed ({', '.join(removed)}). Agent must infer snapshot date."],
    )


def absolutize_paths(
    target: Path,
    abs_root: str = "/Users/testuser/Dropbox/project",
    extensions: tuple[str, ...] = (".R", ".r", ".py", ".jl", ".do", ".m"),
) -> ManifestDelta:
    """
    Replace relative data path references with absolute paths in all scripts.
    Looks for patterns like read_csv("data/..."), use "data/...", etc.
    """
    rewrites: list[PathRewrite] = []
    data_pattern = re.compile(
        r'(["\'])(?!http|/)((?:data|raw_data)/[^\'"]+)(["\'])'
    )

    for ext in extensions:
        for script in target.rglob(f"*{ext}"):
            text = script.read_text(errors="replace")
            matches = data_pattern.findall(text)
            if not matches:
                continue
            new_text = data_pattern.sub(
                lambda m: m.group(1) + abs_root + "/" + m.group(2) + m.group(3),
                text,
            )
            script.write_text(new_text)
            for q, rel, _ in matches:
                abs_path = abs_root + "/" + rel
                rewrites.append(PathRewrite(
                    original=abs_path,
                    rewritten=rel,
                    scripts_affected=[script.relative_to(target)],
                ))
    return ManifestDelta(
        path_rewrites=rewrites,
        notes_lines=[f"Absolutized data paths to {abs_root}."],
    )


def remove_write_path(
    target: Path,
    script_rel: str,
    filename: str,
    write_call: Optional[str] = None,
) -> ManifestDelta:
    """
    Strip the directory prefix from a write call in script so it writes to cwd.
    E.g. ggsave("figures/fig1.pdf") → ggsave("fig1.pdf").
    """
    script = target / script_rel
    if not script.exists():
        return ManifestDelta()

    text = script.read_text(errors="replace")
    basename = Path(filename).name
    # Replace quoted full path with just filename
    new_text = re.sub(
        r'(["\'])' + re.escape(filename) + r'(["\'])',
        lambda m: m.group(1) + basename + m.group(2),
        text,
    )
    if new_text == text:
        return ManifestDelta()
    script.write_text(new_text)

    exhibit = filename  # the path LaTeX expects
    return ManifestDelta(
        gaps=[ExpectedGap(
            kind=GapKind.script_writes_wrong_path,
            exhibit=exhibit,
            note=f"{script_rel} writes '{basename}' to cwd instead of '{filename}'.",
        )],
        notes_lines=[f"Removed dir prefix from write call in {script_rel}: '{filename}' → '{basename}'."],
    )


def inline_table_in_tex(
    target: Path,
    table_name: str = "tab1",
) -> ManifestDelta:
    """Replace \\input{tables/tab1.tex} with a hardcoded tabular environment."""
    inline_tabular = (
        "\\begin{table}\n"
        "\\begin{tabular}{lcc}\n"
        "\\hline\n"
        "Variable & Coef & SE \\\\\n"
        "\\hline\n"
        "Age & 0.23 & (0.05) \\\\\n"
        "Income & 1.47 & (0.12) \\\\\n"
        "\\hline\n"
        "\\end{tabular}\n"
        f"\\caption{{Table {table_name} (inlined)}}\n"
        "\\end{table}\n"
    )
    matched = False
    for tex in target.rglob("*.tex"):
        text = tex.read_text(errors="replace")
        # Match \input{tables/tab1} or \input{tables/tab1.tex}
        pattern = re.compile(
            r'\\input\{' + re.escape(f"tables/{table_name}") + r'(?:\.tex)?\}'
        )
        if pattern.search(text):
            matched = True
            # Use re.sub with a lambda to avoid backslash interpretation in replacement
            new_text = pattern.sub(lambda _: inline_tabular, text)
            tex.write_text(new_text)

    if not matched:
        return ManifestDelta()

    return ManifestDelta(
        gaps=[ExpectedGap(
            kind=GapKind.inline_table,
            location="paper.tex",
            note=f"Table '{table_name}' inlined as tabular — no \\input{{}}.",
        )],
        notes_lines=[f"Inlined table '{table_name}' directly in LaTeX."],
    )


def add_orphan_script(
    target: Path,
    name: str = "old_analysis_v2.R",
    language: str = "R",
) -> ManifestDelta:
    """Add a script that exists but is never called by anything."""
    scripts_dir = target / "code"
    scripts_dir.mkdir(exist_ok=True)
    content = _orphan_content(name, language)
    (scripts_dir / name).write_text(content)
    return ManifestDelta(
        notes_lines=[f"Added orphan script code/{name} (not called by any other script)."],
    )


def _orphan_content(name: str, language: str) -> str:
    if language == "R":
        return f"# {name} — orphaned cleaning script\nlibrary(dplyr)\n# old code, never called\n"
    if language == "Python":
        return f"# {name} — orphaned script\nimport pandas as pd\n# old code, never called\n"
    if language == "Stata":
        return f"* {name} — orphaned do-file\n* old code, never called\n"
    return f"# {name} — orphaned script\n"


def add_restricted_filename(
    target: Path,
    name: str = "census_microdata_restricted.dta",
    subdir: str = "data",
) -> ManifestDelta:
    """Add a file with a restricted-data sentinel filename."""
    d = target / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("placeholder\n")
    trigger = f"{subdir}/{name}"
    return ManifestDelta(
        is_restricted=True,
        restricted_trigger=trigger,
        notes_lines=[f"Added restricted-data sentinel: {trigger}."],
    )


def inject_inline_statistic(
    target: Path,
    statistic: str = "0.047*** (0.012)",
    section: str = "Results",
) -> ManifestDelta:
    """Inject an inline statistic into body text of paper.tex."""
    for tex in target.rglob("*.tex"):
        text = tex.read_text(errors="replace")
        if rf"\section{{{section}}}" in text:
            new_text = text.replace(
                rf"\section{{{section}}}",
                rf"\section{{{section}}}"
                f"\nThe estimated coefficient is {statistic}.\n",
            )
            tex.write_text(new_text)
    return ManifestDelta(
        gaps=[ExpectedGap(
            kind=GapKind.inline_statistic,
            location="paper.tex",
            note=f"Inline statistic '{statistic}' in body text.",
        )],
        notes_lines=[f"Injected inline statistic '{statistic}' in body text."],
    )


# ---------------------------------------------------------------------------
# Manifest serialization
# ---------------------------------------------------------------------------


def _manifest_to_dict(manifest: Manifest) -> dict:
    d: dict = {"fixture_name": manifest.fixture_name}
    d["gaps"] = [
        {k: v for k, v in g.model_dump().items() if v is not None}
        for g in manifest.gaps
    ]
    for gap in d["gaps"]:
        if "kind" in gap:
            gap["kind"] = str(gap["kind"].value) if hasattr(gap["kind"], "value") else gap["kind"]
    d["path_rewrites"] = [
        {
            "original": pr.original,
            "rewritten": pr.rewritten,
            "scripts_affected": [str(p) for p in pr.scripts_affected],
        }
        for pr in manifest.path_rewrites
    ]
    d["version_pins"] = [
        {k: v for k, v in vp.model_dump().items() if v is not None}
        for vp in manifest.version_pins
    ]
    for vp in d["version_pins"]:
        if "method" in vp:
            vp["method"] = str(vp["method"].value) if hasattr(vp["method"], "value") else vp["method"]
    if manifest.files_removed:
        d["files_removed"] = manifest.files_removed
    d["is_restricted"] = manifest.is_restricted
    if manifest.restricted_trigger:
        d["restricted_trigger"] = manifest.restricted_trigger
    if manifest.notes:
        d["notes"] = manifest.notes
    return d


def write_manifest(target: Path, manifest: Manifest) -> Path:
    path = target / "manifest.yaml"
    path.write_text(yaml.dump(_manifest_to_dict(manifest), default_flow_style=False, allow_unicode=True))
    return path


# ---------------------------------------------------------------------------
# Generator — orchestrates gold + fault modules
# ---------------------------------------------------------------------------


class FixtureGenerator:
    """
    Build a fixture by copying a gold directory and applying fault modules.

    Usage:
        gen = FixtureGenerator("my_fixture", gold_dir, target_dir)
        gen.apply(delete_lockfile)
        gen.apply(absolutize_paths, abs_root="/Users/testuser/Dropbox")
        gen.apply(remove_write_path, script_rel="code/run.R", filename="figures/fig1.pdf")
        manifest = gen.finalize(version_pins=[...], notes="Some notes.")
    """

    def __init__(self, fixture_name: str, gold_dir: Path, target_dir: Path) -> None:
        self.fixture_name = fixture_name
        self.target = target_dir
        self._delta = ManifestDelta()

        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(gold_dir, target_dir)

    def apply(self, fault_fn: Callable, **kwargs) -> "FixtureGenerator":
        """Apply a fault module and accumulate its manifest delta."""
        delta = fault_fn(self.target, **kwargs)
        _merge_deltas(self._delta, delta)
        return self

    def finalize(
        self,
        version_pins: Optional[list[ExpectedVersionPin]] = None,
        notes: Optional[str] = None,
    ) -> Manifest:
        """Merge accumulated deltas + explicit pins → write manifest.yaml, return Manifest."""
        all_pins = list(self._delta.version_pins)
        if version_pins:
            all_pins.extend(version_pins)

        all_notes = "\n".join(self._delta.notes_lines)
        if notes:
            all_notes = (notes + "\n" + all_notes).strip()

        manifest = Manifest(
            fixture_name=self.fixture_name,
            gaps=list(self._delta.gaps),
            path_rewrites=list(self._delta.path_rewrites),
            version_pins=all_pins,
            files_removed=list(self._delta.files_removed),
            is_restricted=self._delta.is_restricted,
            restricted_trigger=self._delta.restricted_trigger,
            notes=all_notes or None,
        )
        write_manifest(self.target, manifest)
        return manifest


# ---------------------------------------------------------------------------
# Gold project seeds — minimal clean projects used as generator inputs
# ---------------------------------------------------------------------------


def create_gold_r(target: Path) -> None:
    """Create a minimal clean R project (gold seed for R-based fixture generation)."""
    (target / "code").mkdir(parents=True, exist_ok=True)
    (target / "figures").mkdir(exist_ok=True)
    (target / "tables").mkdir(exist_ok=True)
    (target / "data").mkdir(exist_ok=True)

    (target / "code" / "run.R").write_text(
        'library(ggplot2)\nlibrary(dplyr)\n\n'
        'df <- readRDS("data/raw/sample.rds")\n\n'
        'p <- ggplot(df, aes(x=x, y=y)) + geom_point()\n'
        'ggsave("figures/fig1.pdf", plot=p)\n'
    )
    (target / "paper.tex").write_text(
        r"""\documentclass{article}
\usepackage{graphicx}
\begin{document}
\section{Results}
\begin{figure}
  \includegraphics[width=\textwidth]{figures/fig1.pdf}
  \caption{Main result}
\end{figure}
\input{tables/tab1.tex}
\end{document}
"""
    )
    (target / "tables" / "tab1.tex").write_text(
        "\\begin{tabular}{lc}\n\\hline\nA & 1 \\\\\n\\hline\n\\end{tabular}\n"
    )
    (target / "figures" / "fig1.pdf").write_text("placeholder")
    (target / "renv.lock").write_text(
        '{"R":{"Version":"4.3.1","Repositories":[{"Name":"CRAN",'
        '"URL":"https://packagemanager.posit.co/cran/2023-09-01"}]},'
        '"Packages":{"ggplot2":{"Package":"ggplot2","Version":"3.4.3","Source":"Repository"},'
        '"dplyr":{"Package":"dplyr","Version":"1.1.3","Source":"Repository"}}}\n'
    )


def create_gold_stata(target: Path) -> None:
    """Create a minimal clean Stata project (gold seed)."""
    (target / "code").mkdir(parents=True, exist_ok=True)
    (target / "figures").mkdir(exist_ok=True)
    (target / "tables").mkdir(exist_ok=True)
    (target / "data").mkdir(exist_ok=True)

    (target / "code" / "analysis.do").write_text(
        "* analysis.do\n"
        "ssc install reghdfe, replace\n\n"
        'use "data/lfs_2019.dta", clear\n'
        "keep if !missing(wage)\n"
        "reghdfe log_wage age education, absorb(industry) vce(robust)\n\n"
        'scatter wage age\n'
        'graph export "figures/fig1.pdf", replace\n'
        'outreg2 using "tables/tab1.tex", tex replace\n'
    )
    (target / "code" / "tables.do").write_text(
        "* tables.do — summary statistics\n"
        'use "data/lfs_2019.dta", clear\n'
        'tabulate education, gen(edu_d)\n'
        'outreg2 using "tables/tab2.tex", tex replace\n'
    )
    (target / "paper.tex").write_text(
        r"""\documentclass{article}
\usepackage{graphicx}
\begin{document}
\section{Results}
\begin{figure}
  \includegraphics[width=\textwidth]{figures/fig1.pdf}
  \caption{Wage vs Age}
\end{figure}
\input{tables/tab1.tex}
\input{tables/tab2.tex}
\end{document}
"""
    )
    (target / "figures" / "fig1.pdf").write_text("placeholder")
    (target / "tables" / "tab1.tex").write_text("placeholder")
    (target / "tables" / "tab2.tex").write_text("placeholder")


def create_gold_python(target: Path) -> None:
    """Create a minimal clean Python project (gold seed)."""
    (target / "code").mkdir(parents=True, exist_ok=True)
    (target / "figures").mkdir(exist_ok=True)
    (target / "data").mkdir(exist_ok=True)

    (target / "code" / "analysis.py").write_text(
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n\n"
        'df = pd.read_csv("data/lfs_2019.csv")\n'
        "df = df[df['wage'].notna()].copy()\n\n"
        "fig, ax = plt.subplots()\n"
        "ax.scatter(df['age'], df['wage'], alpha=0.3)\n"
        'ax.set_xlabel("Age"); ax.set_ylabel("Wage")\n'
        'plt.savefig("figures/fig1.pdf")\n'
        'plt.savefig("figures/fig2.pdf")\n'
    )
    (target / "requirements.txt").write_text(
        "pandas==2.0.3\nmatplotlib==3.7.2\n"
    )
    (target / "paper.tex").write_text(
        r"""\documentclass{article}
\usepackage{graphicx}
\begin{document}
\section{Results}
\begin{figure}
  \includegraphics[width=\textwidth]{figures/fig1.pdf}
  \caption{Distribution}
\end{figure}
\begin{figure}
  \includegraphics[width=\textwidth]{figures/fig2.pdf}
  \caption{Robustness}
\end{figure}
\end{document}
"""
    )
    (target / "figures" / "fig1.pdf").write_text("placeholder")
    (target / "figures" / "fig2.pdf").write_text("placeholder")


# ---------------------------------------------------------------------------
# Committed fixture builders — call these to (re)generate committed fixtures
# that don't yet exist. Idempotent: skip if manifest.yaml already present.
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def build_multi_language_full_manifest() -> Path:
    """Write manifest.yaml for existing multi_language_full fixture (no content change)."""
    target = FIXTURES_DIR / "multi_language_full"
    manifest_path = target / "manifest.yaml"
    if manifest_path.exists():
        return manifest_path

    manifest = Manifest(
        fixture_name="multi_language_full",
        gaps=[
            ExpectedGap(
                kind=GapKind.script_writes_wrong_path,
                exhibit="figures/fig_r.pdf",
                note="analysis.R writes 'fig_r.pdf' to cwd instead of figures/fig_r.pdf.",
            ),
            ExpectedGap(
                kind=GapKind.script_writes_wrong_path,
                exhibit="figures/fig_jl.pdf",
                note="analysis.jl writes 'fig_jl.pdf' to cwd instead of figures/fig_jl.pdf.",
            ),
            ExpectedGap(
                kind=GapKind.script_writes_wrong_path,
                exhibit="figures/fig_stata.pdf",
                note="analysis.do writes 'fig_stata.pdf' to cwd instead of figures/fig_stata.pdf.",
            ),
        ],
        path_rewrites=[
            PathRewrite(
                original="/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.dta",
                rewritten="data/lfs_2019.dta",
                scripts_affected=[Path("code/analysis.R"), Path("code/analysis.do")],
            ),
            PathRewrite(
                original="/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.csv",
                rewritten="data/lfs_2019.csv",
                scripts_affected=[Path("code/analysis.jl")],
            ),
        ],
        version_pins=[
            ExpectedVersionPin(language="R", method=PinMethod.inferred_from_date),
            ExpectedVersionPin(language="Julia", method=PinMethod.inferred_from_date),
            ExpectedVersionPin(language="Stata", method=PinMethod.inferred_from_date),
        ],
        is_restricted=False,
        notes=(
            "Three-language project: R + Julia + Stata. "
            "All three scripts have path mismatches (write to cwd). "
            "All three have absolute Dropbox paths to rewrite. "
            "No lockfiles — env must be inferred from date for all three languages."
        ),
    )
    write_manifest(target, manifest)
    return manifest_path


def build_stata_mixed(target_dir: Path) -> Manifest:
    """
    Generate stata_mixed fixture: Stata project with two scripts, path mismatch,
    absolute data paths, and an inline table.
    """
    gold = Path(__file__).parent / "_gold_stata"
    create_gold_stata(gold)
    try:
        gen = FixtureGenerator("stata_mixed", gold, target_dir)
        gen.apply(absolutize_paths, abs_root="/Users/jsmith/Dropbox/stata_project", extensions=(".do",))
        gen.apply(remove_write_path, script_rel="code/analysis.do", filename="figures/fig1.pdf")
        gen.apply(inline_table_in_tex, table_name="tab1")
        gen.apply(add_orphan_script, name="old_merge.do", language="Stata")
        manifest = gen.finalize(
            version_pins=[ExpectedVersionPin(language="Stata", method=PinMethod.inferred_from_date)],
            notes="Mixed Stata fixture: 2 scripts, path mismatch, absolute data paths, inline table.",
        )
    finally:
        shutil.rmtree(gold, ignore_errors=True)
    return manifest


def build_python_external_data(target_dir: Path) -> Manifest:
    """
    Generate python_external_data fixture: Python project with external absolute
    data paths and two path-mismatch figures.
    """
    gold = Path(__file__).parent / "_gold_python"
    create_gold_python(gold)
    try:
        gen = FixtureGenerator("python_external_data", gold, target_dir)
        gen.apply(absolutize_paths, abs_root="/Users/jsmith/Dropbox/python_project", extensions=(".py",))
        gen.apply(remove_write_path, script_rel="code/analysis.py", filename="figures/fig1.pdf")
        gen.apply(remove_write_path, script_rel="code/analysis.py", filename="figures/fig2.pdf")
        manifest = gen.finalize(
            version_pins=[ExpectedVersionPin(language="Python", method=PinMethod.pip_freeze)],
            notes="Python project with external Dropbox data paths and two path-mismatch figures.",
        )
    finally:
        shutil.rmtree(gold, ignore_errors=True)
    return manifest
