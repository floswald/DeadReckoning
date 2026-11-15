#!/usr/bin/env python3
"""
DeadReckoning presentation demo — Rcpp mixed-language package, three
static leads before anything even runs, one of which actually explains a
real numeric drift.

Usage:
    python3 demo/run_demo_rcpp_rng.py
    python3 demo/run_demo_rcpp_rng.py --terse   # one line per step

A small simulation package: code/stata/prep_survey.do picks one "anchor"
respondent per region from a household survey, code/simulate.R reads
that anchor and perturbs it with simulated income shocks computed by a
compiled Rcpp routine, src/shocks.cpp, producing the paper's Table 1 and
Figure 1.

Three real, independent reproducibility gaps, all surfaced statically —
before any native run, before any crash:

  1. SORT-CHECK (new): prep_survey.do does `sort region` (no `, stable`,
     no `set sortseed`) then `by region: keep if _n==1` to pick the
     anchor respondent. Three respondents share each region code in the
     raw survey, so the sort key alone does not determine which one ends
     up first. Stata's default sort breaks ties with an internal random
     tiebreaker that is not guaranteed stable across runs, Stata
     editions, or machines — unlike R's/Python's/Julia's sort, which is
     specified to preserve input order for ties. See
     https://www.stata.com/help13.cgi?sortseed=,
     https://www.stata.com/manuals/dsort.pdf,
     https://www.statalist.org/forums/forum/general-stata-discussion/general/1345163-how-does-stata-randomize-observations-with-the-same-value-when-using-the-command-sort-without-stable

  2. MIXED-LANGUAGE-CHECK (existing): src/shocks.cpp is Rcpp-embedded
     C++ (`// [[Rcpp::export]]`, `#include <Rcpp.h>`) with no
     src/Makevars shipped. R's sourceCpp() auto-compiles it with R's
     default toolchain flags — the file's own comment records that the
     author's machine actually built it with a personal ~/.R/Makevars
     setting PKG_CXXFLAGS = -O3, a flag that lives nowhere in
     this package. This does NOT block the pipeline (sourceCpp() IS a
     real build step — compile_check.py now exempts Rcpp-embedded
     sources from the blocking "no build script" gap it raises for
     standalone Fortran/C/C++); it is a non-blocking lead about which
     flags might silently differ on a replicator's machine.

  3. RNG-CHECK (existing, now Rcpp-aware): shocks.cpp calls
     Rcpp::rnorm() — R's own RNG stream, the same stream set.seed()
     anywhere upstream in code/simulate.R would control — with no
     set.seed() anywhere in this package. rng_check.py's C++ patterns
     used to only catch std::rand()/<random> engines; Rcpp::rnorm /
     R::rnorm / norm_rand / unif_rand are new additions, specifically so
     this case is caught rather than silently passed through.

Of the three, only the missing RNG seed actually perturbs the numbers at
runtime in this demo — the Makevars gap is real but latent (this
environment's R default flags happen to compile shocks.cpp successfully
either way), and the sort-tiebreak gap is real but this demo does not
force two different Stata editions/thread-counts to show two different
anchor picks. Mixing more than one live numeric cause into the same
exhibit would make the drift impossible to attribute to anything
specific — see demo/rcpp_rng/README.md.

Needs a local R install with Rcpp and haven, a C++ compiler, and a local
Stata install for the native RUN step. No LLM fix-loop act — nothing
here crashes, so there is no fix loop to invoke. No Docker.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = REPO_ROOT / "demo" / "rcpp_rng"

sys.path.insert(0, str(REPO_ROOT / "src"))


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def step(name: str, explanation: str) -> None:
    print(f"\n--- {name} " + "-" * max(0, 68 - len(name)))
    print(f"    {explanation}")


def main(terse: bool = False) -> None:
    import shutil
    import tempfile

    from deadreckoning.ask import run_ask_step
    from deadreckoning.capture import capture_env
    from deadreckoning.clean import run_clean_step
    from deadreckoning.compile_check import check_compiled_language_build
    from deadreckoning.confidentiality import check_restricted
    from deadreckoning.fix_loop import append_fix_report, run_fix_loop
    from deadreckoning.graph import build_graph
    from deadreckoning.mixed_language_check import run_mixed_language_check_step
    from deadreckoning.provenance import render_data_exhibit_map, trace_exhibit_inputs, write_data_exhibit_map
    from deadreckoning.resolve import resolve_paths
    from deadreckoning.rng_check import run_rng_check_step
    from deadreckoning.runner import check_exhibit_fidelity, run_natively, validate_outputs
    from deadreckoning.scan import scan_scripts
    from deadreckoning.sort_check import run_sort_check_step

    exhibit_path = Path("output/Table1.tex")

    banner("One package, three languages: Stata -> R -> Rcpp (C++)")
    print("  code/stata/prep_survey.do  -> data/survey_prepped.dta  (one anchor respondent/region)")
    print("  code/simulate.R            -> output/Table1.tex, output/fig1.pdf")
    print("  src/shocks.cpp (Rcpp, sourced by simulate.R) draws the simulated shocks")
    print()
    print("  Three independent reproducibility gaps, all findable before any native run:")
    print("    1. prep_survey.do sorts a non-unique key, then picks 'first per group'")
    print("    2. src/shocks.cpp has no src/Makevars -- compile flags are unrecorded")
    print("    3. src/shocks.cpp draws from R's RNG with no set.seed() anywhere upstream")

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

    # The published reference — a baked-in snapshot of Table 1 as it
    # appeared when the paper was accepted (unlike the other demos, this
    # package's own output/ starts empty: nothing has run yet).
    reference_content = (working_copy / "reference" / "Table1.tex").read_bytes()

    # GRAPH
    graph = build_graph(working_copy)
    if not terse:
        step("GRAPH", "parse paper.tex + scripts into exhibits / data files / gaps")
    print(f"  {len(graph.exhibits)} exhibit(s), {len(graph.data_files)} data file(s), {len(graph.gaps)} gap(s)")
    print(f"  script_order (topological): {[str(s.relative_to(working_copy)) for s in graph.script_order]}")
    print("  (prep_survey.do before simulate.R — the data dependency DeadReckoning needs")
    print("   to walk later for the RNG-CHECK 'seeded upstream' logic and for RUN order)")

    provenance = trace_exhibit_inputs(graph)
    write_data_exhibit_map(working_copy, render_data_exhibit_map(provenance))
    if not terse:
        print("  -> DATA-EXHIBIT-MAP.md written (data availability statement)")

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

    # COMPILE-CHECK — the gate this demo needs to NOT trip.
    if not terse:
        step(
            "COMPILE-CHECK",
            "would normally block the pipeline if compiled source has no build script — "
            "Rcpp-embedded sources are exempted, since sourceCpp() IS the build step",
        )
    compile_gap = check_compiled_language_build(working_copy)
    print(f"  blocking gap raised: {compile_gap is not None}")
    print("  (src/shocks.cpp has // [[Rcpp::export]] and #include <Rcpp.h> — recognized")
    print("   as Rcpp-embedded, so it does not trip the standalone-C++ blocking check)")

    # SORT-CHECK — new in this demo.
    if not terse:
        step(
            "SORT-CHECK (new)",
            "flag a Stata sort/gsort with no , stable and no set sortseed feeding a "
            "tie-sensitive by ... : ... _n==1/_n==_N operation",
        )
    sort_result = run_sort_check_step(working_copy)
    print(f"  {len(sort_result.findings)} finding(s){' — SORT-WARNINGS.md written' if sort_result.has_findings else ''}")
    for f in sort_result.findings:
        print(f"    {f.script}:{f.line} `{f.sort_call}` feeds {f.script}:{f.tie_sensitive_line} `{f.tie_sensitive_call}`")
    if sort_result.has_findings:
        print("  (three respondents share each region code in the raw survey — which one")
        print("   ends up 'first' after an unstable sort is not guaranteed across runs)")

    # MIXED-LANGUAGE-CHECK — existing, this is the Rcpp/Makevars lead.
    if not terse:
        step(
            "MIXED-LANGUAGE-CHECK",
            "Rcpp/Cython/MEX usage with no declared build step for the compiled part "
            "(non-blocking — the embedding language CAN auto-compile with default flags)",
        )
    mlc_result = run_mixed_language_check_step(working_copy)
    print(f"  {len(mlc_result.findings)} finding(s){' — MIXED-LANGUAGE-WARNINGS.md written' if mlc_result.has_findings else ''}")
    for f in mlc_result.findings:
        print(f"    [{f.language}] {f.note[:140]}...")

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

    # RNG-CHECK — existing, now Rcpp-aware. Run after FIX so graph.script_order
    # is current, same ordering the native RUN step below will use.
    if not terse:
        step(
            "RNG-CHECK",
            "unseeded stochastic call, walking script_order so an upstream seed call "
            "covers downstream scripts — now covers Rcpp/R-API calls inside .cpp too",
        )
    rng_result = run_rng_check_step(working_copy, graph)
    print(f"  {len(rng_result.findings)} finding(s){' — RNG-WARNINGS.md written' if rng_result.has_findings else ''}")
    for f in rng_result.findings:
        print(f"    {f.script}:{f.line} ({f.language}) — `{f.call}`")
    if rng_result.has_findings:
        print("  (src/shocks.cpp draws from R's RNG stream with no set.seed() anywhere")
        print("   upstream in script_order — this is the one finding above that will")
        print("   actually perturb the numbers when this runs natively, below)")

    banner("Native run")

    # RUN (native) — Stata, then R (which sourceCpp()s the Rcpp file).
    if not terse:
        step(
            "RUN (native)",
            "execute every script in script_order — prep_survey.do picks the anchor, "
            "simulate.R compiles shocks.cpp on the fly and draws the shocks",
        )
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
    print(f"  present: {validation.present}")
    print(f"  missing: {validation.missing}")
    print("  (green — exit 0, both files exist. Nothing here can tell you the numbers")
    print("   are different from the ones already published.)")

    # FIDELITY
    graph = build_graph(working_copy)
    fidelity = check_exhibit_fidelity(working_copy, graph, exhibit_path, reference_content)
    if not terse:
        step("FIDELITY", "compare the regenerated exhibit against the published reference")
    regenerated_content = (working_copy / exhibit_path).read_text()
    print(f"  matches published reference: {fidelity.matches_reference}")
    if not fidelity.matches_reference:
        print(f"\n  published Table 1:\n{reference_content.decode().strip()}")
        print(f"\n  regenerated Table 1:\n{regenerated_content.strip()}")
        print(f"\n  nondeterminism_note: {fidelity.nondeterminism_note}")
        print(f"\n  {len(fidelity.suspects)} upstream file(s) implicated by mtime:")
        for s in fidelity.suspects:
            print(f"    {s.path}  [{s.evidence}, confidence={s.confidence}]")
        print()
        print("  Neither suspect above actually changed content in this run — both mtime")
        print("  leads are noise, because the real cause isn't an upstream file at all.")
        print("  nondeterminism_note is None too: that check only looks for a wall-clock/")
        print("  PID/tempdir call in the exhibit's producing script, which is a different")
        print("  failure mode from an unseeded RNG. The real explanation is the RNG-CHECK")
        print("  finding above, already on disk in RNG-WARNINGS.md before this run even")
        print("  started -- FIDELITY tells you THAT it drifted, RNG-CHECK already told you")
        print("  WHY, and neither one alone would have been enough.")

    # CLEAN
    clean, needs_review = run_clean_step(working_copy, graph)
    if not terse:
        step("CLEAN", "BFS from exhibits back through scripts to flag files nothing reaches (orphans)")
    print(f"  {len(clean.orphans)} orphan(s){' — CLEANUP.md written' if needs_review else ''}")
    print("  (expected here: CLEAN's reachability walk covers scripts and data files, not")
    print("   output/fig1.pdf itself — a known gap, same one noted in the landuse_fanout")
    print("   demo, not something this demo's checks are meant to fix)")

    banner("What happened")
    print("  Three static checks — SORT-CHECK (new), MIXED-LANGUAGE-CHECK, RNG-CHECK —")
    print("  each wrote their own .md file before the native run even started, flagging")
    print("  three independent reproducibility gaps in a 3-language package. DETECT,")
    print("  SCAN, RESOLVE, ASK, FIX, COMPILE-CHECK, RUN, and VALIDATE all passed clean")
    print("  — nothing crashed, both exhibits landed on disk. FIDELITY still caught a")
    print("  real numeric drift (the unseeded Rcpp RNG draw), but its own mtime-based")
    print("  localization pointed at two files that never actually changed. Getting the")
    print("  real explanation took the static RNG-CHECK finding, written earlier for a")
    print("  completely different reason (before any run, let alone a failed one) —")
    print("  that's the case for running all these checks together, not just the ones")
    print("  that happen to fire when something crashes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Rcpp/RNG/sort demo.")
    parser.add_argument("--terse", action="store_true",
                         help="One-line-per-step output instead of full step-by-step narration")
    args = parser.parse_args()
    main(terse=args.terse)
