#!/usr/bin/env python3
"""
DeadReckoning presentation demo — fan-out fidelity: one shared input, two
real Stata scripts, six real exhibits, only some of them stale.

Usage:
    python3 demo/run_demo_landuse_fanout.py
    python3 demo/run_demo_landuse_fanout.py --terse   # one line per step

Extends the real, published LandUse-REStud slice already in
demo/landuse_real/ (untouched by this demo) to a second real script,
code/stata/generatethetas.do, which reads the *same* real input,
data/raw/FRA_base.dta, as code/stata/figure1.do — one shared input, two
scripts, six real exhibits.

Same silent-drift mechanism as the coauthor-drift demo (demo 4): nothing
crashes, every script exits 0, every exhibit lands on disk. The
difference here is scale and discrimination: of six exhibits sharing one
upstream input, only three are actually stale, and check_exhibit_fidelity
has to separate them correctly, not just flag "something touching
FRA_base.dta changed" for all six indiscriminately.

The rig (baked into reference/, not performed at demo-run time): a
provider restatement of two 1950 observations (Land_Agriculture,
Share_Emp_Agr100) in FRA_base.dta. generatethetas.do was rerun after the
restatement, so its three reference exhibits (figureA3.pdf, figure7.pdf,
figureA4.pdf) already reflect the current data. figure1.do was believed
unaffected and never rerun, so its three reference exhibits (figure1.pdf,
figureA2a.pdf, figureA2b.pdf) still reflect the pre-restatement data.
See demo/landuse_fanout/README.md for exactly how the reference set was
built and verified (both scripts run clean, deterministic PDF export
confirmed by byte comparison).

Requires a local Stata install (no LLM step — nothing here crashes, so
there's no fix loop to invoke).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = REPO_ROOT / "demo" / "landuse_fanout"

sys.path.insert(0, str(REPO_ROOT / "src"))

EXHIBITS = [
    Path("output/data/plots/figure1.pdf"),
    Path("output/data/plots/figureA2a.pdf"),
    Path("output/data/plots/figureA2b.pdf"),
    Path("output/data/plots/figureA3.pdf"),
    Path("output/data/plots/figure7.pdf"),
    Path("output/data/plots/figureA4.pdf"),
]


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

    banner("One shared input, two real scripts, six real exhibits")
    print("  code/stata/figure1.do          -> figure1.pdf, figureA2a.pdf, figureA2b.pdf")
    print("  code/stata/generatethetas.do   -> figureA3.pdf, figure7.pdf, figureA4.pdf")
    print("  both read data/raw/FRA_base.dta directly")
    print()
    print("  reference/ ships a mix of two vintages: a provider restatement of two")
    print("  1950 observations. generatethetas.do was rerun after the restatement,")
    print("  figure1.do was believed unaffected and never rerun. Every script still")
    print("  exits 0, every exhibit still lands on disk, nothing crashes.")

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

    # RUN (native) — both scripts, independent (neither consumes the
    # other's output), both reading the current FRA_base.dta.
    if not terse:
        step("RUN (native)", "execute every script in script_order — both read the current FRA_base.dta")
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
    print(f"  {len(matches)}/6 match reference: {[r.exhibit.name for r in matches]}")
    print(f"  {len(mismatches)}/6 MISMATCH:      {[r.exhibit.name for r in mismatches]}")

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
    print("  (expected here: CLEAN's dependency walk doesn't yet cross-reference the 6")
    print("  regenerated plots, the 6 shipped reference/ copies, and the 1 intermediate")
    print("  FRA_model.dta against the exhibits paper.tex declares, so all 13 land in")
    print("  CLEANUP.md even though VALIDATE already confirmed the 6 outputs are the")
    print("  real exhibits. Not a FIDELITY bug — just a gap in CLEAN's matching.)")

    banner("What happened")
    print("  Six exhibits, two scripts, one shared input. DETECT, SCAN, RESOLVE, ASK,")
    print("  FIX, RUN, VALIDATE all passed clean on all six. FIDELITY is the only")
    print("  check that tells the three figure1.do exhibits apart from the three")
    print("  generatethetas.do exhibits — and it converges all three mismatches on")
    print("  the same suspect, data/raw/FRA_base.dta, without ever flagging the")
    print("  three that are actually fine. That discrimination is the point: a tool")
    print("  that flagged all six indiscriminately wouldn't be doing more than grep.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the landuse fan-out fidelity demo.")
    parser.add_argument("--terse", action="store_true",
                         help="One-line-per-step output instead of full step-by-step narration")
    parser.add_argument("--pause", action="store_true",
                         help="Wait for Enter before each pipeline step — for presenting live")
    args = parser.parse_args()
    _PAUSE = args.pause
    main(terse=args.terse)
