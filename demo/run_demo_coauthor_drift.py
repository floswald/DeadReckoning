#!/usr/bin/env python3
"""
DeadReckoning presentation demo — silent coauthor data drift, no version
control, the author can't reproduce their own accepted paper.

Usage:
    python3 demo/run_demo_coauthor_drift.py
    python3 demo/run_demo_coauthor_drift.py --terse   # one line per step

Unlike the other three demos (toy_paper, bus_locations, landuse), which
all rig a broken/renamed file path that *crashes* and gets fixed by the
LLM fix-loop, this one is silent: everything runs clean, exit 0, every
exhibit lands on disk — and the regenerated Table 3 no longer matches
the published PDF. Nothing in DETECT/SCAN/RESOLVE/ASK/FIX/RUN/VALIDATE
can catch this; it's exactly the "ran it, got a different number than
my own accepted paper, no idea why" case.

Two coauthors, no git discipline for author 2:
  - clean.R (author 1)   -> data/panel.csv            (8 regions, revenue)
  - export.do (author 2) -> data/input_data_from_2.csv (region weights)
    (author 2's script lives only on their own machine — it's never part
    of this package, never scanned by GRAPH, see demo/coauthor_drift_private/)
  - combine.jl (author 1) reads both -> output/Table3.tex (weighted
    average regional revenue)

Author 2's do-file originally used `outsheet`, which (with no display
format ever set) truncates exported numbers to 2 decimals. At some point
before the paper is accepted, author 2 upgrades their Stata version and
modernizes the script to `export delimited` (the recommended replacement
since Stata 13) — still with no display format set, so the full
double-precision weight now leaks into the csv. Same underlying data,
same code logic, just a different export command with a different
default. Confirmed via Statalist:
  https://www.stata.com/statalist/archive/2011-01/msg00310.html
  https://www.stata.com/statalist/archive/2010-12/msg00903.html
  https://www.statalist.org/forums/forum/general-stata-discussion/general/1577196-export-excel-and-decimal-places

Author 2 runs the script and regenerates `input_data_from_2.csv`, then
drops it into the shared Dropbox folder "to tidy up." But the downstream
consumer of that file, `combine.jl`, is never rerun — so what actually
goes into the accepted paper is `combine.jl`'s old output, generated
before the re-export, now silently out of sync with the csv already
sitting on disk. Later, when author 1 reruns the whole pipeline to
check reproducibility — native execution succeeds, VALIDATE passes —
`combine.jl` picks up the already-updated csv and produces a different
number than the one in the PDF.
check_exhibit_fidelity() is the new check that catches this: it compares
the regenerated exhibit against the published reference, and on mismatch
walks the dependency chain to name the upstream file(s) most likely
responsible. Since author 2's machine has no git, the only evidence
available is filesystem mtime — reported explicitly as a lead, not
proof (Dropbox/zip/scp all rewrite mtimes without a real edit happening).
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = REPO_ROOT / "demo" / "coauthor_drift"
PRIVATE = REPO_ROOT / "demo" / "coauthor_drift_private"

sys.path.insert(0, str(REPO_ROOT / "src"))

# Timeline stamped explicitly via os.utime() below — mtimes do not survive
# a fresh git clone/CI checkout, so this demo can't rely on whatever mtimes
# happen to ship in the repo.
T_DELIVERED = datetime.datetime(2024, 1, 10).timestamp()   # initial delivery: panel.csv + input_data_from_2.csv v1, combine.jl run once -> the Table 3 that ships in the accepted paper
T_REEXPORT = datetime.datetime(2024, 3, 5).timestamp()     # author 2 upgrades Stata, reruns export.do -> csv overwritten with v2 — but combine.jl is never rerun
T_ACCEPTED = datetime.datetime(2024, 6, 1).timestamp()     # paper accepted with the stale (pre-re-export) Table 3 still in the PDF, narrative only, no file tied to this


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
    from deadreckoning.confidentiality import check_restricted
    from deadreckoning.fix_loop import append_fix_report, run_fix_loop
    from deadreckoning.graph import build_graph
    from deadreckoning.provenance import render_data_exhibit_map, trace_exhibit_inputs, write_data_exhibit_map
    from deadreckoning.resolve import resolve_paths
    from deadreckoning.runner import check_exhibit_fidelity, run_natively, validate_outputs
    from deadreckoning.scan import scan_scripts

    exhibit_path = Path("output/Table3.tex")

    banner("Two coauthors, one shared Dropbox folder, no version control")
    print("  clean.R (author 1)    -> data/panel.csv             (revenue panel)")
    print("  export.do (author 2)  -> data/input_data_from_2.csv (region weights)")
    print("  combine.jl (author 1) reads both -> output/Table3.tex")
    print()
    print("  Author 2's export.do never lives in this package — it's on their")
    print("  own machine, never shared, never git-tracked. See")
    print(f"  {PRIVATE.relative_to(REPO_ROOT)}/ for what it actually contains.")
    print()
    print("  At some point before the paper is accepted, author 2 upgrades their")
    print("  Stata version and modernizes the script (outsheet -> export delimited,")
    print("  the Stata 13+ recommended replacement) without ever setting a display")
    print("  format. Same data, same logic — outsheet truncated to 2 decimals under")
    print("  the unset default; export delimited doesn't. Author 2 reruns the script")
    print("  and drops the re-exported csv in the shared folder 'to tidy up.'")
    print("  (github.com/statalist archives: msg00310.html, msg00903.html;")
    print("   statalist.org forum 1577196 — real mechanism, not invented.)")
    print()
    print("  But combine.jl, the downstream consumer of that csv, is never rerun.")
    print("  What goes into the accepted paper is combine.jl's old output, generated")
    print("  before the re-export — already out of sync with the csv on disk by the")
    print("  time the paper is accepted. Nobody notices because nothing crashes.")

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

    # The published reference — captured now, before anything is regenerated.
    # This is deliberately the author's own accepted-paper table, not a
    # separate oracle file: it's what already ships in the fixture.
    reference_content = (working_copy / exhibit_path).read_bytes()

    # GRAPH
    graph = build_graph(working_copy)
    if not terse:
        step("GRAPH", "parse paper.tex + scripts into exhibits / data files / gaps")
    print(f"  {len(graph.exhibits)} exhibit(s), {len(graph.data_files)} data file(s), {len(graph.gaps)} gap(s)")
    print(f"  script_order (topological): {[s.relative_to(working_copy) for s in graph.script_order]}")
    for df in graph.data_files:
        producer = df.produced_by.relative_to(working_copy) if df.produced_by else None
        print(f"    {df.path}  produced_by={producer}")
    print("  (input_data_from_2.csv shows produced_by=None — author 2's export.do")
    print("   is genuinely invisible to GRAPH, exactly the real situation)")

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
    if not scan.external_paths and not terse:
        print("  (nothing to flag — every path here is plain project-relative)")

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

    banner("Time passes: author 2 re-exports, combine.jl doesn't rerun, paper gets accepted")
    print("  Stamping the timeline explicitly (mtimes don't survive git clone/CI,")
    print("  so this demo rigs them rather than relying on whatever ships):")
    print(f"    panel.csv + input_data_from_2.csv v1 delivered, combine.jl run once:")
    print(f"      {datetime.datetime.fromtimestamp(T_DELIVERED).date()}  (-> the Table 3 that ends up in the PDF)")
    print(f"    author 2 upgrades Stata, reruns export.do, csv overwritten with v2:")
    print(f"      {datetime.datetime.fromtimestamp(T_REEXPORT).date()}  (combine.jl is NOT rerun)")
    print(f"    paper accepted, still carrying the pre-re-export Table 3:")
    print(f"      {datetime.datetime.fromtimestamp(T_ACCEPTED).date()}")

    os.utime(working_copy / "data" / "input_data_from_2.csv", (T_DELIVERED, T_DELIVERED))
    shutil.copy(PRIVATE / "input_data_from_2_v2.csv", working_copy / "data" / "input_data_from_2.csv")
    os.utime(working_copy / "data" / "input_data_from_2.csv", (T_REEXPORT, T_REEXPORT))
    print("\n  data/input_data_from_2.csv swapped for author 2's re-exported version")
    print("  (full double precision now, where it used to be rounded to 2 decimals)")
    print("  — this already happened before acceptance; the accepted Table 3 simply")
    print("  never reflected it, because combine.jl was never rerun to pick it up.")

    # RUN (native) — every script in dependency order, driven by the now-real
    # script_order (previously an aspirational field that build_graph never
    # actually populated).
    if not terse:
        step("RUN (native)", "execute every script in script_order — clean.R regenerates panel.csv, "
                              "combine.jl re-reads the (now re-exported) weights")
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

    # clean.R regenerated panel.csv byte-for-byte identical to what it always
    # was — backdate its mtime to reflect that nothing about it actually
    # changed, so the localizer's timeline isn't confused by "just reran."
    os.utime(working_copy / "data" / "panel.csv", (T_DELIVERED, T_DELIVERED))

    # VALIDATE (native)
    validation = validate_outputs(working_copy, graph)
    if not terse:
        step("VALIDATE (native)", "check every exhibit the script claims to produce actually landed on disk")
    print(f"  present: {validation.present}")
    print(f"  missing: {validation.missing}")
    print("  (green — exit 0, file exists. Nothing here can tell you the number is wrong.)")

    # FIDELITY — the new check this demo exists to showcase. Rebuild the
    # graph first: the one built earlier captured data_files[].mtime before
    # author 2's re-export landed, so it's stale by now.
    graph = build_graph(working_copy)
    fidelity = check_exhibit_fidelity(working_copy, graph, exhibit_path, reference_content)
    if not terse:
        step("FIDELITY (new)", "compare the regenerated exhibit against the published reference — "
                                "catches a divergence that every check above missed")
    regenerated_content = (working_copy / exhibit_path).read_text()
    print(f"  matches published reference: {fidelity.matches_reference}")
    if not fidelity.matches_reference:
        print(f"\n  published Table 3:\n{reference_content.decode().strip()}")
        print(f"\n  regenerated Table 3:\n{regenerated_content.strip()}")
        print(f"\n  {len(fidelity.suspects)} upstream file(s) implicated:")
        for s in fidelity.suspects:
            print(f"    {s.path}  [{s.evidence}, confidence={s.confidence}]")
            print(f"      {s.detail}")

    # CLEAN
    clean, needs_review = run_clean_step(working_copy, graph)
    if not terse:
        step("CLEAN", "BFS from exhibits back through scripts to flag files nothing reaches (orphans)")
    print(f"  {len(clean.orphans)} orphan(s){' — CLEANUP.md written' if needs_review else ''}")

    banner("What happened")
    print("  DETECT, SCAN, RESOLVE, ASK, FIX, RUN, VALIDATE — every one of them")
    print("  passed clean. No crash, no warning, no missing file. The paper's")
    print("  own author, rerunning their own accepted paper, would see a Table 3")
    print("  that silently no longer matches the PDF — and nothing before the")
    print("  new FIDELITY check could have told them why.")
    print()
    print("  The localizer's answer here is a mtime lead, not a verdict —")
    print("  author 2's machine has no git, so that's genuinely the best")
    print("  evidence available. On a git-tracked package, the same check")
    print("  would instead report an exact commit, date, and author.")
    print()
    print("  The 'correct' fix is putting the whole pipeline under git with CI")
    print("  checking every exhibit on every push — but that's not a realistic")
    print("  ask for most social scientists. This check exists for the world")
    print("  as it actually is: no git, no CI, just a shared Dropbox folder.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the coauthor-drift demo.")
    parser.add_argument("--terse", action="store_true",
                         help="One-line-per-step output instead of full step-by-step narration")
    args = parser.parse_args()
    main(terse=args.terse)
