#!/usr/bin/env python3
"""
DeadReckoning presentation demo — fan-out fidelity AND chain drift in one
run: one shared input, two real Stata scripts, six real exhibits, plus a
seventh synthetic exhibit one stage further downstream — only some of the
seven are stale, and for two different reasons.

Usage:
    python3 demo/run_demo_landuse_fanout.py
    python3 demo/run_demo_landuse_fanout.py --terse   # one line per step

Extends the real, published LandUse-REStud slice already in
demo/landuse_real/ (untouched by this demo) to a second real script,
code/stata/generatethetas.do, which reads the *same* real input,
data/raw/FRA_base.dta, as code/stata/figure1.do — one shared input, two
scripts, six real exhibits. On top of that, code/julia/combine_theta_summary.jl
reads generatethetas.do's rural TFP series and a coauthor-supplied decade
weighting scheme to produce a seventh exhibit, output/TableTheta.tex —
fabricated for this demo (not part of the real published package; see
demo/landuse_fanout/README.md), added so this demo can show both drift
shapes from the deck in one run: Demo 4's chain (a downstream consumer
never rerun) and the parallel fan-out this demo already exercised.

Same silent-drift mechanism as the coauthor-drift demo (demo 4): nothing
crashes, every script exits 0, every exhibit lands on disk. check_exhibit_fidelity
has to separate the exhibits that are actually stale from the ones that
aren't, not just flag "something changed" indiscriminately — and, unlike
demo 4, it has to do that across two unrelated upstream causes converging
on different exhibits in the same run.

Two independent rigs:
  1. Fan-out (baked into reference/, not performed at demo-run time): a
     provider restatement of two 1950 observations (Land_Agriculture,
     Share_Emp_Agr100) in FRA_base.dta. generatethetas.do was rerun after
     the restatement, so its three reference exhibits (figureA3.pdf,
     figure7.pdf, figureA4.pdf) already reflect the current data.
     figure1.do was believed unaffected and never rerun, so its three
     reference exhibits (figure1.pdf, figureA2a.pdf, figureA2b.pdf) still
     reflect the pre-restatement data.
  2. Chain (performed at demo-run time, like demo 4): a coauthor's
     private export script modernizes outsheet -> export delimited with
     no display format set, silently leaking full double-precision decade
     weights into data/decade_weights.csv. combine_theta_summary.jl, the
     downstream consumer, is never rerun before the swap — so the one
     reference exhibit it's responsible for, TableTheta.tex, is stale too,
     for a completely different reason than the other three.

See demo/landuse_fanout/README.md for exactly how both rigs were built
and verified.

Requires a local Stata install and a local Julia install with CSV.jl /
DataFrames.jl (no LLM step — nothing here crashes, so there's no fix loop
to invoke).
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil as _shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = REPO_ROOT / "demo" / "landuse_fanout"
PRIVATE = REPO_ROOT / "demo" / "landuse_fanout_private"

sys.path.insert(0, str(REPO_ROOT / "src"))

EXHIBITS = [
    Path("output/data/plots/figure1.pdf"),
    Path("output/data/plots/figureA2a.pdf"),
    Path("output/data/plots/figureA2b.pdf"),
    Path("output/data/plots/figureA3.pdf"),
    Path("output/data/plots/figure7.pdf"),
    Path("output/data/plots/figureA4.pdf"),
    Path("output/TableTheta.tex"),
]

# Timeline for the chain-drift stage, stamped explicitly via os.utime()
# below — mirrors demo/run_demo_coauthor_drift.py's T_DELIVERED/T_REEXPORT.
T_DELIVERED = datetime.datetime(2024, 1, 10).timestamp()
T_REEXPORT = datetime.datetime(2024, 3, 5).timestamp()


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


_PAUSE = False  # set from --pause in main(); step() waits for Enter when True


def step(name: str, explanation: str) -> None:
    if _PAUSE:
        input("\n[press Enter for the next step] ")
    print(f"\n--- {name} " + "-" * max(0, 68 - len(name)))
    print(f"    {explanation}")


def main(terse: bool = False) -> None:
    import shutil
    import tempfile

    from deadreckoning.ask import run_ask_step
    from deadreckoning.capture import capture_env
    from deadreckoning.clean import run_clean_step
    from deadreckoning.confidentiality import check_restricted
    from deadreckoning.fix_loop import append_fix_report, run_fix_loop
    from deadreckoning.graph import build_graph
    from deadreckoning.resolve import resolve_paths
    from deadreckoning.runner import check_exhibit_fidelity, group_fidelity_mismatches, run_natively, validate_outputs
    from deadreckoning.scan import scan_scripts

    banner("One shared input, two real scripts, plus a synthetic chain stage")
    print("  code/stata/figure1.do          -> figure1.pdf, figureA2a.pdf, figureA2b.pdf")
    print("  code/stata/generatethetas.do   -> figureA3.pdf, figure7.pdf, figureA4.pdf")
    print("  both read data/raw/FRA_base.dta directly")
    print()
    print("  code/julia/combine_theta_summary.jl -> TableTheta.tex")
    print("  reads generatethetas.do's theta series + a coauthor-supplied decade")
    print("  weighting scheme (fabricated for this demo — see README.md)")
    print()
    print("  reference/ ships a mix of vintages, for two unrelated reasons:")
    print("  a provider restatement of two 1950 observations in FRA_base.dta")
    print("  (generatethetas.do was rerun after it, figure1.do wasn't), and a")
    print("  coauthor's private re-export of decade_weights.csv that")
    print("  combine_theta_summary.jl never got rerun to pick up. Every script")
    print("  still exits 0, every exhibit still lands on disk, nothing crashes.")

    paper_pdf = PROJECT / "paper.pdf"
    print(f"\n  Already-published paper (compiled ahead of time, output/ seeded from")
    print(f"  reference/ — this is what the audience has in hand before any of this")
    print(f"  runs): {paper_pdf}")

    banner("Full pipeline run, step by step")

    # DETECT
    restricted = check_restricted(PROJECT)
    if not terse:
        step("DETECT", "filename-only scan for restricted/confidential data, before any file is opened")
    print(f"  restricted: {restricted.is_restricted}")
    if restricted.is_restricted:
        print(f"  reason: {restricted.reason}")
        return

    tmpdir = Path(tempfile.mkdtemp(prefix="dr_")).resolve()
    working_copy = tmpdir / PROJECT.name
    shutil.copytree(PROJECT, working_copy)
    print(f"  working copy: {working_copy}  (original project untouched)")

    # The published reference set — captured now, before anything is
    # regenerated. Mixed vintage by construction: see module docstring.
    reference_content = {
        exhibit: (working_copy / "reference" / exhibit.name).read_bytes() for exhibit in EXHIBITS
    }

    # GRAPH
    graph = build_graph(working_copy)
    if not terse:
        step("GRAPH", "parse paper.tex + scripts into exhibits / data files / gaps")
    print(f"  {len(graph.exhibits)} exhibit(s), {len(graph.data_files)} data file(s), {len(graph.gaps)} gap(s)")
    print(f"  script_order: {[s.relative_to(working_copy) for s in graph.script_order]}")
    for df in graph.data_files:
        print(f"    {df.path}  referenced_by={[s.relative_to(working_copy) for s in df.referenced_by]}")

    # CAPTURE
    env_spec = capture_env(working_copy)
    if not terse:
        step("CAPTURE", "infer language/packages/pin-method from lockfiles or static scan")
    print(f"  language={env_spec.language}  confidence={env_spec.confidence:.2f}")

    # SCAN
    scan = scan_scripts(working_copy)
    if not terse:
        step("SCAN", "extract external paths / package refs / secrets from every script")
    print(f"  {len(scan.external_paths)} external path(s), {len(scan.used_packages)} package ref(s)")

    # RESOLVE
    resolve = resolve_paths(working_copy, scan)
    if not terse:
        step("RESOLVE", "rewrite external/absolute paths to project-relative ones")
    print(f"  {resolve.rewrite_count} path rewrite(s)")

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

    banner("Time passes: the coauthor re-exports, combine_theta_summary.jl doesn't rerun")
    print("  Stamping the timeline explicitly (mtimes don't survive git clone/CI,")
    print("  so this demo rigs them rather than relying on whatever ships):")
    print(f"    decade_weights.csv v1 delivered, combine_theta_summary.jl run once:")
    print(f"      {datetime.datetime.fromtimestamp(T_DELIVERED).date()}  (-> TableTheta.tex that ends up in reference/)")
    print(f"    coauthor upgrades Stata, reruns export_weights.do, csv overwritten with v2:")
    print(f"      {datetime.datetime.fromtimestamp(T_REEXPORT).date()}  (combine_theta_summary.jl is NOT rerun)")

    weights_path = working_copy / "data" / "decade_weights.csv"
    os.utime(weights_path, (T_DELIVERED, T_DELIVERED))
    _shutil.copy(PRIVATE / "decade_weights_v2.csv", weights_path)
    os.utime(weights_path, (T_REEXPORT, T_REEXPORT))
    print("\n  data/decade_weights.csv swapped for the coauthor's re-exported version")
    print("  (full double precision now, where it used to be truncated to 2 decimals)")
    print("  — this already happened before acceptance; the accepted TableTheta.tex")
    print("  simply never reflected it, because combine_theta_summary.jl was never")
    print("  rerun to pick it up.")

    # RUN (native) — figure1.do and generatethetas.do are independent
    # (neither consumes the other's output), both reading the current
    # FRA_base.dta. combine_theta_summary.jl runs last, after
    # generatethetas.do, since it consumes FRA_model.csv — the topological
    # order GRAPH derived from the produced_by link.
    if not terse:
        step("RUN (native)", "execute every script in script_order — figure1.do/generatethetas.do read "
                              "the current FRA_base.dta, combine_theta_summary.jl re-reads the "
                              "(now re-exported) decade weights")
    all_ok = True
    for script in graph.script_order:
        rel = script.relative_to(working_copy)
        result = run_natively(working_copy, master_script=str(rel))
        print(f"  {rel}: {'OK' if result.success else 'FAILED'}")
        all_ok = all_ok and result.success
        if not result.success:
            print(f"    stderr: {result.stderr.strip()[:300]}")

    if not all_ok:
        print("\nPipeline error: a native run failed unexpectedly")
        return

    # VALIDATE (native)
    validation = validate_outputs(working_copy, graph)
    if not terse:
        step("VALIDATE (native)", "check every exhibit the script claims to produce actually landed on disk")
    print(f"  present: {len(validation.present)}  missing: {len(validation.missing)}")
    print("  (green — exit 0, every file exists. Nothing here can tell you a number is wrong.)")

    # FIDELITY — run once per exhibit, then aggregate.
    if not terse:
        step("FIDELITY (new)", "compare each regenerated exhibit against its published reference")
    results = [
        check_exhibit_fidelity(working_copy, graph, exhibit, reference_content[exhibit])
        for exhibit in EXHIBITS
    ]
    matches = [r for r in results if r.matches_reference]
    mismatches = [r for r in results if not r.matches_reference]
    n = len(EXHIBITS)
    print(f"  {len(matches)}/{n} match reference: {[r.exhibit.name for r in matches]}")
    print(f"  {len(mismatches)}/{n} MISMATCH:      {[r.exhibit.name for r in mismatches]}")

    grouped = group_fidelity_mismatches(results)
    print(f"\n  {len(grouped)} suspect upstream file(s) implicated:")
    for suspect_path, implicated_exhibits in grouped.items():
        print(f"    {suspect_path}  <- implicates {[e.name for e in implicated_exhibits]}")
        evidence = next(
            s for r in mismatches for s in r.suspects if s.path == suspect_path
        )
        print(f"      [{evidence.evidence}, confidence={evidence.confidence}] {evidence.detail}")

    # CLEAN
    clean, needs_review = run_clean_step(working_copy, graph)
    if not terse:
        step("CLEAN", "BFS from exhibits back through scripts to flag files nothing reaches (orphans)")
    print(f"  {len(clean.orphans)} orphan(s){' — CLEANUP.md written' if needs_review else ''}")
    print("  (expected here: CLEAN's dependency walk doesn't yet cross-reference the")
    print("  regenerated plots/table, the shipped reference/ copies, and the")
    print("  intermediate FRA_model.dta/csv against the exhibits paper.tex declares, so")
    print("  files VALIDATE already confirmed are real exhibits land in CLEANUP.md too.")
    print("  Not a FIDELITY bug — just a gap in CLEAN's matching.)")

    banner("What happened")
    print(f"  {n} exhibits, three scripts, two independent drift mechanisms. DETECT,")
    print("  SCAN, RESOLVE, ASK, FIX, RUN, VALIDATE all passed clean on all seven.")
    print("  FIDELITY is the only check that tells them apart. figure1.do's three")
    print("  exhibits implicate only data/raw/FRA_base.dta (the provider")
    print("  restatement) — without ever flagging the three generatethetas.do")
    print("  exhibits that are actually fine. TableTheta.tex implicates two files:")
    print("  data/raw/FRA_base.dta (a real but incidental upstream link —")
    print("  combine_theta_summary.jl's input is produced by generatethetas.do,")
    print("  which also reads FRA_base.dta) and data/decade_weights.csv, the")
    print("  actual cause. FIDELITY names every upstream file in the chain, not")
    print("  just the guilty one — same 'lead, not proof' caveat as demo 4. That")
    print("  discrimination is still the point: a tool that flagged everything")
    print("  touching any changed upstream file indiscriminately wouldn't be")
    print("  doing more than grep.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the landuse fan-out fidelity demo.")
    parser.add_argument("--terse", action="store_true",
                         help="One-line-per-step output instead of full step-by-step narration")
    parser.add_argument("--pause", action="store_true",
                         help="Wait for Enter before each pipeline step — for presenting live")
    args = parser.parse_args()
    _PAUSE = args.pause
    main(terse=args.terse)
