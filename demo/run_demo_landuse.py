#!/usr/bin/env python3
"""
DeadReckoning presentation demo — real-package walkthrough (LandUse slice).

Usage:
    python3 demo/run_demo_landuse.py
    python3 demo/run_demo_landuse.py --terse   # one line per step

Narrates the pipeline step by step on a slice of a real, published,
own-authored replication package — Oswald, *Land Use, Structural Change
and Urban Expansion* (REStud), github.com/floswald/LandUse-REStud, data
on Zenodo. The full package is Julia + R + Stata across many real-world
data sources (GHS, Copernicus CLC, INSEE, Schauberger yields, Shlomo
Angel, IGN, CASD-cleared aggregates). This slice is deliberately scoped
to one self-contained Stata script and its one real data input:
`code/stata/figure1.do`, which reads `data/raw/FRA_base.dta` — real
French land-use/employment shares, 1806-2018 — and produces the paper's
actual Figure 1.

One rigged problem, same "deadline-crunch slip" pattern as the other two
demos: the data file was renamed on disk (FRA_base.dta -> FRA_base_v2.dta)
without the script being updated. The script's `use "../data/raw/FRA_base.dta"`
is a plain project-relative path, so SCAN/RESOLVE see nothing wrong (no
external/absolute path to flag or rewrite) — the native run 404s, and
that's where Claude (live API call) reasons about the directory listing,
spots the renamed file, and proposes the fix.

No Docker: this fixture is Stata-only, one script, seconds to run.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = REPO_ROOT / "demo" / "landuse_real"

sys.path.insert(0, str(REPO_ROOT / "src"))


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def step(name: str, explanation: str) -> None:
    print(f"\n--- {name} " + "-" * max(0, 68 - len(name)))
    print(f"    {explanation}")


def show_file(path: Path, label: str | None = None) -> None:
    if not path.exists():
        return
    print(f"\n  [{label or path.name}]")
    for line in path.read_text().splitlines():
        print(f"    {line}")


def main(terse: bool = False) -> None:
    import shutil
    import tempfile

    from deadreckoning.ask import run_ask_step
    from deadreckoning.capture import capture_env
    from deadreckoning.clean import run_clean_step
    from deadreckoning.confidentiality import check_restricted
    from deadreckoning.fix_loop import append_fix_report, run_fix_loop, run_llm_fix_loop
    from deadreckoning.graph import build_graph
    from deadreckoning.provenance import render_data_exhibit_map, trace_exhibit_inputs, write_data_exhibit_map
    from deadreckoning.resolve import resolve_paths
    from deadreckoning.runner import run_natively, validate_outputs
    from deadreckoning.scan import scan_scripts

    master_script = "code/stata/figure1.do"

    banner("A real replication package: LandUse (Oswald, REStud)")
    print("code/stata/figure1.do reads FRA_base.dta via a project-relative path:")
    print('  use "data/raw/FRA_base.dta", clear')
    print("(real French land-use/employment shares, 1806-2018 — produces the")
    print(" paper's actual Figure 1. The data file was renamed on disk since —")
    print(" a common deadline-crunch slip: nobody updates the script when a")
    print(" file gets renamed. No hardcoded/external path here for SCAN to")
    print(" catch — this one only surfaces as a real runtime failure.)")

    banner("Full pipeline run, step by step")

    # DETECT
    restricted = check_restricted(PROJECT)
    if not terse:
        step("DETECT", "filename-only scan for restricted/confidential data, before any file is opened")
    print(f"  restricted: {restricted.is_restricted}")
    if restricted.is_restricted:
        print(f"  reason: {restricted.reason}")
        return

    tmpdir = Path(tempfile.mkdtemp(prefix="dr_"))
    working_copy = tmpdir / PROJECT.name
    shutil.copytree(PROJECT, working_copy)
    print(f"  working copy: {working_copy}  (original project untouched)")

    # GRAPH
    graph = build_graph(working_copy)
    if not terse:
        step("GRAPH", "parse paper.tex + scripts into exhibits / data files / gaps")
    print(f"  {len(graph.exhibits)} exhibit(s), {len(graph.data_files)} data file(s), {len(graph.gaps)} gap(s)")
    print("  (no paper.tex in this slice — just the one script + its one data input)")

    provenance = trace_exhibit_inputs(graph)
    write_data_exhibit_map(working_copy, render_data_exhibit_map(provenance))
    if not terse:
        print("  -> DATA-EXHIBIT-MAP.md written (data availability statement)")
        show_file(working_copy / "DATA-EXHIBIT-MAP.md")

    # CAPTURE
    env_spec = capture_env(working_copy)
    if not terse:
        step("CAPTURE", "infer language/packages/pin-method from lockfiles or static scan")
    print(f"  language={env_spec.language}  confidence={env_spec.confidence:.2f}  "
          f"packages={[p.name for p in env_spec.packages] or '(none pinned)'}")

    # SCAN
    scan = scan_scripts(working_copy)
    if not terse:
        step("SCAN", "extract external paths / package refs / secrets from every script")
    print(f"  {len(scan.external_paths)} external path(s), {len(scan.used_packages)} package ref(s)")
    for ep in scan.external_paths:
        print(f"    {ep.script}:{ep.line}  ({ep.kind}): {ep.raw}")
    if not scan.external_paths and not terse:
        print("  (nothing to flag — the renamed-file slip isn't visible to a static scan)")

    # RESOLVE
    resolve = resolve_paths(working_copy, scan)
    if not terse:
        step("RESOLVE", "rewrite external/absolute paths to project-relative ones")
    print(f"  {resolve.rewrite_count} path rewrite(s)")
    for rw in resolve.rewrites:
        print(f"    {rw.original}\n      -> {rw.rewritten}")

    # ASK
    qa, needs_input, graph, env_spec = run_ask_step(working_copy, graph, env_spec, scan)
    if not terse:
        step("ASK", "surface gaps/contradictions that need the author, before spending compute")
    print(f"  {len(qa.questions)} question(s) raised; author input required: {needs_input}")
    if needs_input:
        print("  -> QUESTIONS.md written; pipeline would halt here for a real package")
        return

    # FIX (deterministic)
    fix_result, graph = run_fix_loop(working_copy, graph, env_spec)
    append_fix_report(working_copy, fix_result)
    if not terse:
        step("FIX (deterministic)", "no-LLM fixes only, e.g. a script writing to the wrong output path")
    print(f"  {fix_result.iterations} iteration(s), {len(fix_result.fixes_applied)} fix(es) applied")
    for fa in fix_result.fixes_applied:
        print(f"    {fa.kind}: {fa.script}  {fa.old_path} -> {fa.new_path}")

    # RUN (native)
    native_run = run_natively(working_copy, master_script=master_script)
    if not terse:
        step("RUN (native)", "actually execute the master script — the renamed data file "
                              "means this 404s, nothing upstream could have caught it")
    print(f"  {'OK' if native_run.success else 'FAILED'}")

    if not native_run.success:
        if not terse:
            print(f"\n  stderr excerpt:\n" + "\n".join(f"    {l}" for l in native_run.stderr.strip().splitlines()[-15:]))

        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        if not terse:
            step("FIX (LLM)", "native run failed and no deterministic fix applies — "
                              "hand the stderr + a directory listing to Claude")
        print(f"  dispatching to Claude ({'live call' if has_key else 'no API key, skipped'})")

        llm_result, graph = run_llm_fix_loop(
            working_copy, graph, env_spec,
            master_script=master_script,
            initial_stderr=native_run.stderr,
        )
        append_fix_report(working_copy, llm_result)
        print(f"  {llm_result.iterations} iteration(s), converged={llm_result.converged}")
        for line in llm_result.llm_reasoning:
            print(f"\n  [model reasoning] {line}")
        for fa in llm_result.fixes_applied:
            print(f"\n  -> applied: {fa.kind}  {fa.script}  {fa.old_path or fa.package_name} -> "
                  f"{fa.new_path or fa.package_version}")

        native_run = run_natively(working_copy, master_script=master_script)
        print(f"\n  re-run after LLM fix: {'OK' if native_run.success else 'still failing'}")

        if not native_run.success:
            print("\nPipeline error: native run failed even after LLM fix loop")
            return

    # VALIDATE (native)
    validation = validate_outputs(working_copy, graph)
    if not terse:
        step("VALIDATE (native)", "check every exhibit the script claims to produce actually landed on disk")
    print(f"  present: {validation.present}")
    if validation.missing:
        print(f"  missing: {validation.missing}")

    # CLEAN
    clean, needs_review = run_clean_step(working_copy, graph)
    if not terse:
        step("CLEAN", "BFS from exhibits back through scripts to flag files nothing reaches (orphans)")
    print(f"  {len(clean.orphans)} orphan(s){' — CLEANUP.md written' if needs_review else ''}")

    figure_path = working_copy / "output" / "data" / "plots" / "figure1.pdf"
    banner("Reproduced figure (real numbers from real French land-use data, 1840-2018)")
    if figure_path.exists():
        print(f"  {figure_path}  ({figure_path.stat().st_size} bytes)")
    else:
        print(f"  expected but missing: {figure_path}")
    print("\n  This is the real paper's Figure 1. The manuscript includes it via:")
    print(r"    \includegraphics[scale=1.0]{\dataplots/figure1.pdf}")
    print("  (quoted read-only from paper/20250609-sec-1-2.tex in the source")
    print("   repo — not copied into this fixture)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the LandUse real-package demo.")
    parser.add_argument("--terse", action="store_true",
                         help="One-line-per-step output instead of full step-by-step narration")
    parser.add_argument("--skip-docker", action="store_true",
                         help="No-op for this demo (Stata-only fixture, no Docker act) — kept for symmetry")
    args = parser.parse_args()
    main(terse=args.terse)
