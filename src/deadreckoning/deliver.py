"""
DELIVER step: produce the final replication package artefacts.

Outputs written to working_copy:
  README.md          — AEA-format template populated from graph + env_spec
  DELIVERY_REPORT.md — pipeline summary for the Data Editor

Optional:
  <name>.zip         — zip of working_copy minus internal DR files

Design rule: every field that can be derived from disk is derived;
author-facing fields that require human judgement are left as TODO markers.
"""

from __future__ import annotations

import shutil
import zipfile
from datetime import date
from pathlib import Path
from typing import Optional

from .models import (
    AuthorQA,
    CleanResult,
    DeliverResult,
    DependencyGraph,
    EnvSpec,
)

# Files written by DeadReckoning itself — excluded from the delivered package
_DR_INTERNAL = frozenset({
    "QUESTIONS.md",
    "CLEANUP.md",
    "AGENT_REPORT.md",
    "DELIVERY_REPORT.md",
    "data/data-manifest.csv",
})
_SKIP_DIRS = frozenset({
    ".git", "__pycache__", "_archive",
    ".mypy_cache", ".pytest_cache", ".ipynb_checkpoints",
    "renv",
})
_README_FILE = "README.md"
_REPORT_FILE = "DELIVERY_REPORT.md"

# ---------------------------------------------------------------------------
# README generation
# ---------------------------------------------------------------------------

_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _iso_to_human(iso: str) -> str:
    """'2023-03-01' → 'March 2023'."""
    try:
        parts = iso.split("-")
        y, m = int(parts[0]), int(parts[1])
        return f"{_MONTH_NAMES[m]} {y}"
    except Exception:
        return iso


def generate_readme(
    graph: DependencyGraph,
    env_spec: EnvSpec,
    qa: Optional[AuthorQA] = None,
) -> str:
    """Return AEA-format README.md content (str) ready to write."""
    lines: list[str] = []

    def h(n: int, text: str) -> None:
        lines.append(f"{'#' * n} {text}\n\n")

    def p(*parts: str) -> None:
        lines.append("".join(parts) + "\n\n")

    def li(text: str) -> None:
        lines.append(f"- {text}\n")

    def table(headers: list[str], rows: list[list[str]]) -> None:
        sep = " | "
        lines.append(sep.join(headers) + "\n")
        lines.append(sep.join(["---"] * len(headers)) + "\n")
        for row in rows:
            lines.append(sep.join(row) + "\n")
        lines.append("\n")

    # ── Title ──────────────────────────────────────────────────────────────
    h(1, "Replication Package — [Paper Title]")
    p(
        "> **Instructions to authors:** Replace every `[placeholder]` with the ",
        "actual value. Lines marked `TODO` require your input.",
    )
    p(
        "This package contains the code and data to reproduce all results in ",
        '"[Paper Title]", [Journal], [Year].',
    )
    p("**Authors:** [Author 1], [Author 2]")

    # ── Data Availability ──────────────────────────────────────────────────
    h(2, "Data Availability and Provenance Statements")

    # Gather external data paths from graph
    external = [df for df in graph.data_files if df.is_external]
    if external:
        p("The following data are **not** included in this package:")
        for df in external:
            kind = df.external_kind or "external"
            li(f"`{df.path}` ({kind}) — TODO: describe access/download instructions")
        lines.append("\n")
    else:
        p("All data used in this paper are included in the `data/` directory.")

    # ── Dataset list ───────────────────────────────────────────────────────
    h(2, "Dataset List")
    local_data = [df for df in graph.data_files if not df.is_external]
    if local_data:
        rows = []
        for df in local_data:
            try:
                rel = df.path.relative_to(graph.project_root)
            except ValueError:
                rel = df.path
            rows.append([f"`{rel}`", "[Source — TODO]", "Yes"])
        table(["Filename", "Source", "Provided"], rows)
    else:
        p("TODO: list all data files used.")

    # ── Computational Requirements ─────────────────────────────────────────
    h(2, "Computational Requirements")
    h(3, "Software Requirements")

    lang = env_spec.language
    ver = env_spec.language_version or "[version — TODO]"
    li(f"{lang} {ver}")

    if env_spec.packages:
        for pkg in env_spec.packages[:30]:  # cap at 30 to keep README readable
            ver_str = f" ({pkg.version})" if pkg.version else ""
            li(f"  - {pkg.name}{ver_str}")
        if len(env_spec.packages) > 30:
            lines.append(
                f"  - ... and {len(env_spec.packages) - 30} more "
                f"(see lockfile for complete list)\n"
            )
    lines.append("\n")

    if env_spec.snapshot_date:
        p(
            f"Package versions correspond to {_iso_to_human(env_spec.snapshot_date)}. "
            f"For R, restore via `renv::restore()`. "
            f"For Python, use `pip install -r requirements.txt`.",
        )

    h(3, "Memory and Runtime Requirements")
    p("**Approximate time:** TODO (e.g. '30 minutes on a laptop')")
    p("**Memory:** TODO (e.g. '8 GB RAM')")
    p("**OS:** Tested on [OS — TODO]")

    # ── Code Description ───────────────────────────────────────────────────
    h(2, "Description of Programs / Code")

    # Master script detection
    master = None
    for sp in graph.script_order:
        master = sp
        break  # first in topological order is typically master
    if master is None and graph.exhibits:
        for ex in graph.exhibits:
            if ex.source:
                master = ex.source.script
                break

    if master:
        try:
            master_rel = master.relative_to(graph.project_root)
        except ValueError:
            master_rel = master
        p(f"**Master script:** `{master_rel}`")
    else:
        p("**Master script:** TODO")

    # Per-exhibit script table
    sourced = graph.sourced_exhibits
    if sourced:
        h(3, "Output Scripts")
        rows = []
        for ex in sourced:
            try:
                script_rel = ex.source.script.relative_to(graph.project_root)
            except (ValueError, AttributeError):
                script_rel = ex.source.script
            rows.append([f"`{script_rel}`", f"`{ex.tex_path}`"])
        table(["Script", "Output"], rows)

    # Gaps — flag missing sources
    if graph.gaps:
        h(3, "Unresolved Outputs")
        p(
            "The following outputs have no identified source script. "
            "See `QUESTIONS.md` for author Q&A."
        )
        for gap in graph.gaps:
            li(f"`{gap.exhibit}` — {gap.kind.value}")
        lines.append("\n")

    # ── Instructions ───────────────────────────────────────────────────────
    h(2, "Instructions to Replicators")

    step = 1
    # Install software
    if lang.lower() == "r":
        p(f"{step}. Install R {ver} from https://cran.r-project.org")
        step += 1
        if any(pkg.name == "renv" for pkg in env_spec.packages):
            p(f"{step}. Open R in the project directory and run `renv::restore()`")
            step += 1
    elif lang.lower() == "python":
        p(f"{step}. Install Python {ver}")
        step += 1
        p(f"{step}. Run `pip install -r requirements.txt`")
        step += 1
    elif lang.lower() == "julia":
        p(f"{step}. Install Julia {ver} from https://julialang.org")
        step += 1
        p(f"{step}. From the Julia REPL: `using Pkg; Pkg.instantiate()`")
        step += 1
    elif lang.lower() == "stata":
        p(f"{step}. Ensure Stata {ver} is installed and licensed")
        step += 1
    elif lang.lower() == "matlab":
        p(f"{step}. Ensure MATLAB {ver} is installed and licensed")
        step += 1

    if master:
        try:
            master_rel = master.relative_to(graph.project_root)
        except ValueError:
            master_rel = master
        ext = Path(str(master_rel)).suffix.lower()
        if ext == ".r":
            cmd = f"Rscript {master_rel}"
        elif ext == ".py":
            cmd = f"python {master_rel}"
        elif ext == ".jl":
            cmd = f"julia {master_rel}"
        elif ext == ".do":
            cmd = f"stata -b do {master_rel}"
        elif ext == ".m":
            cmd = f"matlab -batch \"run('{master_rel}')\")"
        else:
            cmd = f"[run] {master_rel}"
        p(f"{step}. Run the master script: `{cmd}`")
        step += 1

    p(f"{step}. All outputs will be regenerated in their original locations.")

    # ── Output list ────────────────────────────────────────────────────────
    h(2, "List of Tables and Figures")
    if graph.exhibits:
        rows = []
        for ex in graph.exhibits:
            script = ""
            if ex.source:
                try:
                    script = str(ex.source.script.relative_to(graph.project_root))
                except ValueError:
                    script = str(ex.source.script)
            rows.append(["TODO", script or "TODO", str(ex.tex_path)])
        table(["Figure/Table", "Script", "Output File"], rows)
    else:
        p("TODO: list all figures and tables.")

    # ── Unanswered questions note ───────────────────────────────────────────
    if qa and qa.questions:
        unanswered = [
            q for i, q in enumerate(qa.questions)
            if i >= len(qa.responses) or not qa.responses[i].answer
        ]
        if unanswered:
            h(2, "Open Questions")
            p(
                f"{len(unanswered)} question(s) were raised during preparation "
                "of this package. See `QUESTIONS.md` for details."
            )

    return "".join(lines)


def write_readme(
    working_copy: Path,
    graph: DependencyGraph,
    env_spec: EnvSpec,
    qa: Optional[AuthorQA] = None,
    overwrite: bool = False,
) -> Path:
    """Write README.md to working_copy. Skips if file already exists and overwrite=False."""
    dest = working_copy / _README_FILE
    if dest.exists() and not overwrite:
        return dest
    dest.write_text(generate_readme(graph, env_spec, qa))
    return dest


# ---------------------------------------------------------------------------
# Delivery report (Data Editor — internal)
# ---------------------------------------------------------------------------


def generate_delivery_report(
    graph: DependencyGraph,
    env_spec: EnvSpec,
    resolve=None,
    qa: Optional[AuthorQA] = None,
    clean: Optional[CleanResult] = None,
    native_ok: bool = False,
    container_ok: bool = False,
) -> str:
    today = date.today().isoformat()
    lines = [f"# DeadReckoning — Delivery Report\n\nGenerated: {today}\n\n"]

    def row(label: str, value: str) -> str:
        return f"| {label} | {value} |\n"

    lines.append("## Pipeline Summary\n\n")
    lines.append("| Step | Result |\n| --- | --- |\n")

    n_exhibits = len(graph.exhibits)
    n_gaps = len(graph.gaps)
    gap_str = f"⚠ {n_gaps} gap(s)" if n_gaps else "✓ no gaps"
    lines.append(row("Graph", f"{n_exhibits} exhibit(s), {gap_str}"))

    conf_pct = f"{env_spec.confidence:.0%}"
    lang_str = f"{env_spec.language} {env_spec.language_version or '(version unknown)'}"
    pin = env_spec.pin_method.value if env_spec.pin_method else "unknown"
    lines.append(row("Env", f"{lang_str}, {pin}, confidence {conf_pct}"))

    if resolve is not None:
        rw = getattr(resolve, "rewrite_count", 0)
        lines.append(row("Resolve", f"{rw} absolute path rewrite(s)"))

    if qa is not None:
        nq = len(qa.questions)
        na = sum(1 for r in qa.responses if r.answer)
        lines.append(row("ASK", f"{nq} question(s), {na} answered"))
    else:
        lines.append(row("ASK", "0 questions"))

    lines.append(row("Native run", "✓" if native_ok else "✗ failed"))
    lines.append(row("Container", "✓" if container_ok else "⚠ skipped or failed"))

    if clean is not None:
        n_orphans = len(clean.orphans)
        if clean.apply:
            n_del = len(clean.apply.deleted)
            n_arc = len(clean.apply.archived)
            lines.append(row("Clean", f"{n_orphans} orphan(s): {n_del} deleted, {n_arc} archived"))
        else:
            status = f"{n_orphans} orphan(s) found" if n_orphans else "✓ no orphans"
            lines.append(row("Clean", status))

    lines.append("\n")

    # Outstanding issues
    issues: list[str] = []
    if graph.gaps:
        for g in graph.gaps:
            issues.append(f"- Graph gap `{g.exhibit}`: {g.kind.value}")
    if not native_ok:
        issues.append("- Native run failed")
    if not container_ok:
        issues.append("- Container validation skipped or failed")
    if qa:
        for i, q in enumerate(qa.questions):
            ans = qa.responses[i].answer if i < len(qa.responses) else ""
            if not ans:
                issues.append(f"- Unanswered question: {q.gap_kind} ({q.exhibit or '—'})")

    lines.append("## Outstanding Issues\n\n")
    if issues:
        lines.append("\n".join(issues) + "\n\n")
    else:
        lines.append("None.\n\n")

    # Env advice
    if env_spec.note:
        lines.append(f"## Environment Notes\n\n{env_spec.note}\n\n")

    return "".join(lines)


def write_delivery_report(
    working_copy: Path,
    graph: DependencyGraph,
    env_spec: EnvSpec,
    **kw,
) -> Path:
    dest = working_copy / _REPORT_FILE
    dest.write_text(generate_delivery_report(graph, env_spec, **kw))
    return dest


# ---------------------------------------------------------------------------
# Package assembly
# ---------------------------------------------------------------------------


def assemble_package(working_copy: Path, dest_zip: Optional[Path] = None) -> tuple[Path, int, int]:
    """
    Zip working_copy → dest_zip, excluding DR-internal and hidden/cache files.

    Returns (dest_zip, included_count, excluded_count).
    """
    if dest_zip is None:
        dest_zip = working_copy.parent / f"{working_copy.name}.zip"

    included = 0
    excluded = 0

    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(working_copy.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(working_copy)
            parts = rel.parts

            # Skip hidden dirs and internal dirs
            if any(part.startswith(".") or part in _SKIP_DIRS for part in parts):
                excluded += 1
                continue

            # Skip DR-internal files
            rel_str = str(rel)
            if rel_str in _DR_INTERNAL or rel.name in _DR_INTERNAL:
                excluded += 1
                continue

            # Skip compiled Python
            if p.suffix in (".pyc", ".pyo"):
                excluded += 1
                continue

            zf.write(p, rel)
            included += 1

    return dest_zip, included, excluded


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_deliver_step(
    working_copy: Path,
    graph: DependencyGraph,
    env_spec: EnvSpec,
    qa: Optional[AuthorQA] = None,
    clean: Optional[CleanResult] = None,
    resolve=None,
    native_ok: bool = False,
    container_ok: bool = False,
    assemble_zip: bool = False,
) -> DeliverResult:
    """
    Full DELIVER step.

    Always writes README.md (unless already present) and DELIVERY_REPORT.md.
    Optionally zips the package if assemble_zip=True.
    """
    result = DeliverResult()

    result.readme_path = write_readme(working_copy, graph, env_spec, qa=qa)
    result.report_path = write_delivery_report(
        working_copy, graph, env_spec,
        resolve=resolve,
        qa=qa,
        clean=clean,
        native_ok=native_ok,
        container_ok=container_ok,
    )

    if assemble_zip:
        dest_zip = working_copy.parent / f"{working_copy.name}.zip"
        dest_zip, inc, exc = assemble_package(working_copy, dest_zip)
        result.package_path = dest_zip
        result.included_count = inc
        result.excluded_count = exc

    return result
