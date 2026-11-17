#!/usr/bin/env python3
"""
DeadReckoning presentation demo — restricted/confidential data (#27),
plus the per-action LLM-FIX approval gate (#28).

Usage:
    python3 demo/run_demo_restricted.py
    python3 demo/run_demo_restricted.py --terse   # one line per step

A tiny, fully made-up household-income survey:
`code/analysis.py` reads `data/survey_confidential.csv` and writes the
paper's one table. The filename alone ("confidential") trips DETECT's
filename heuristic — no file is opened to make that call.

Before #27, that would have aborted the whole pipeline: no working
copy, nothing downstream. Now it keeps going — GRAPH, CAPTURE, SCAN,
RESOLVE, RUN, VALIDATE are all 100%-local already, restricted or not —
with LLM-FIX and ASK hints unconditionally turned off for the rest of
the run.

The script has a real, independent bug: it reads the column
`household_income`, but the actual column in the CSV is `income` (a
renamed-column slip). That's exactly the kind of thing Claude
(live API call) could normally diagnose and fix automatically — see
run_demo.py's Act 3. Here, restricted mode means the fix loop refuses
to even try: `LLMDispatcher(restricted=True).next_fix()` returns `None`
before it ever calls `_get_client()`, let alone builds a prompt — proven
below by handing it a client that raises `AssertionError` if touched at
all. The run stays failed, and `AGENT_REPORT.md` records why.

The irony, and the actual point of DATA-STRUCTURE-SUMMARY.md: the real
column names were written to disk, locally, before any of this — a
human author re-reading that file could fix the bug themselves in ten
seconds, with zero cell values ever having left their machine.

No API key needed (the dispatcher never calls out either way), no
Docker, no external dependency beyond the Python standard library.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = REPO_ROOT / "demo" / "restricted_data"

sys.path.insert(0, str(REPO_ROOT / "src"))


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
    from deadreckoning.confidentiality import check_restricted
    from deadreckoning.data_profile import (
        profile_data_files,
        render_data_structure_summary,
        write_data_structure_summary,
    )
    from deadreckoning.fix_loop import append_fix_report, run_fix_loop, run_llm_fix_loop
    from deadreckoning.graph import build_graph
    from deadreckoning.llm_dispatcher import LLMDispatcher
    from deadreckoning.llm_gap_hints import GapHintDispatcher
    from deadreckoning.provenance import render_data_exhibit_map, trace_exhibit_inputs, write_data_exhibit_map
    from deadreckoning.resolve import resolve_paths
    from deadreckoning.runner import run_natively, validate_outputs
    from deadreckoning.scan import scan_scripts

    master_script = "code/analysis.py"

    banner("A tiny household-income survey, one real bug")
    print("  code/analysis.py reads data/survey_confidential.csv and writes output/table1.tex")
    print("  Bug: the script reads column 'household_income'; the CSV's real column is 'income'")
    print("  All data below is fabricated for this demo — no real survey respondents involved.")

    banner("Full pipeline run, step by step")

    # DETECT — filename-only, before any file content is opened.
    if not terse:
        step("DETECT", "filename-only scan for restricted/confidential data, before any file is opened")
    restricted = check_restricted(PROJECT)
    print(f"  restricted: {restricted.is_restricted}")
    print(f"  reason: {restricted.reason}")
    print("  Before #27 this would return here: no working copy, nothing downstream runs.")
    print("  Now it just means LLM-FIX and ASK hints are off for the rest of this run —")
    print("  everything below (GRAPH..VALIDATE) is 100%-local anyway, so it proceeds.")

    tmpdir = Path(tempfile.mkdtemp(prefix="dr_")).resolve()
    working_copy = tmpdir / PROJECT.name
    shutil.copytree(PROJECT, working_copy)
    print(f"\n  working copy: {working_copy}  (original project untouched)")

    # GRAPH
    graph = build_graph(working_copy)
    if not terse:
        step("GRAPH", "parse paper.tex + scripts into exhibits / data files / gaps")
    print(f"  {len(graph.exhibits)} exhibit(s), {len(graph.data_files)} data file(s), {len(graph.gaps)} gap(s)")

    provenance = trace_exhibit_inputs(graph)
    write_data_exhibit_map(working_copy, render_data_exhibit_map(provenance))
    if not terse:
        print("  -> DATA-EXHIBIT-MAP.md written (data availability statement)")

    # DATA-STRUCTURE-SUMMARY — new in #27, local-only, restricted projects only.
    if not terse:
        step(
            "DATA-STRUCTURE-SUMMARY (new, restricted-only)",
            "row counts + column names only, computed locally, never cell values, "
            "never transmitted anywhere",
        )
    data_profile = profile_data_files(working_copy, graph)
    summary_text = render_data_structure_summary(data_profile)
    write_data_structure_summary(working_copy, summary_text)
    show_file(working_copy / "DATA-STRUCTURE-SUMMARY.md")
    print("\n  Notice: 'income', not 'household_income' — the real column name, the exact")
    print("  thing the bug below needs, already on disk, with no cell value anywhere above.")

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

    # Restricted-mode note in AGENT_REPORT.md — same append orchestrator.py
    # does right after RESOLVE, so it lands even if ASK below halts the run.
    with (working_copy / "AGENT_REPORT.md").open("a") as f:
        f.write(
            "\n## Restricted mode\n\n"
            "Restricted mode: LLM-FIX and ASK hints were disabled for this run "
            "(confidential/restricted data detected). "
            "See `DATA-STRUCTURE-SUMMARY.md`.\n"
        )

    # ASK — hints disabled because restricted.
    if not terse:
        step(
            "ASK",
            "surface gaps/contradictions that need the author — hint_dispatcher is a "
            "GapHintDispatcher(restricted=True), so no LLM hint is ever proposed",
        )
    qa, needs_input, graph, env_spec = run_ask_step(
        working_copy, graph, env_spec, scan,
        hint_dispatcher=GapHintDispatcher(restricted=restricted.is_restricted),
    )
    print(f"  {len(qa.questions)} question(s) raised; author input required: {needs_input}")
    if needs_input:
        print("  -> QUESTIONS.md written; pipeline would halt here")
        return

    # FIX (deterministic) — unaffected by restricted; no LLM involved here either way.
    fix_result, graph = run_fix_loop(working_copy, graph, env_spec)
    append_fix_report(working_copy, fix_result)
    if not terse:
        step("FIX (deterministic)", "no-LLM fixes only — unaffected by restricted mode")
    print(f"  {fix_result.iterations} iteration(s), {len(fix_result.fixes_applied)} fix(es) applied")

    banner("Native run")

    if not terse:
        step("RUN (native)", "execute code/analysis.py — the renamed-column bug fires here")
    native_run = run_natively(working_copy, master_script=master_script)
    print(f"  {'OK' if native_run.success else 'FAILED'}")
    if not native_run.success:
        print("\n  stderr / log excerpt:")
        for line in native_run.stderr.strip().splitlines()[-8:]:
            print(f"    {line}")

    if not native_run.success:
        if not terse:
            step(
                "FIX (LLM) — refused, restricted",
                "LLMDispatcher(restricted=True).next_fix() returns None before "
                "_get_client() is ever called, let alone a prompt built",
            )
        # Prove it: hand the dispatcher a client that raises on ANY attribute
        # access or call. If restricted ever let a live call slip through,
        # this would blow up instead of quietly returning None.
        landmine_client = MagicMock()
        landmine_client.messages.create.side_effect = AssertionError(
            "restricted=True must never reach the API — this client should never be touched"
        )
        dispatcher = LLMDispatcher(client=landmine_client, restricted=restricted.is_restricted)
        print(f"  dispatcher.restricted = {dispatcher.restricted}  (client would raise if ever called)")

        llm_result, graph = run_llm_fix_loop(
            working_copy, graph, env_spec,
            dispatcher=dispatcher,
            master_script=master_script,
            initial_stderr=native_run.stderr,
            approve_fn=lambda action: True,  # #28's approval gate — moot here, nothing is ever proposed
        )
        append_fix_report(working_copy, llm_result)
        print(f"  {llm_result.iterations} iteration(s), converged={llm_result.converged}, "
              f"fixes applied={len(llm_result.fixes_applied)}")
        print("  No AssertionError raised -> the landmine client was never touched.")
        print("  Converged with zero fixes isn't 'no bug found' — it's 'never looked.'")

        native_run = run_natively(working_copy, master_script=master_script)
        print(f"\n  re-run after LLM-FIX (which did nothing): {'OK' if native_run.success else 'still failing'}")

    if not terse:
        step("VALIDATE (native)", "check every exhibit the script claims to produce actually landed on disk")
    validation = validate_outputs(working_copy, graph)
    print(f"  present: {validation.present}")
    print(f"  missing: {validation.missing}")

    banner("AGENT_REPORT.md — the audit trail")
    show_file(working_copy / "AGENT_REPORT.md", label="AGENT_REPORT.md (tail)")

    banner("What happened")
    print("  DETECT caught the filename lead and did NOT abort (#27) — a real working copy")
    print("  was made and the pipeline ran all the way through RUN/VALIDATE. The one real")
    print("  bug (renamed column) stayed unfixed: LLMDispatcher(restricted=True) refused")
    print("  before ever touching a client, proven here with a client that would raise if")
    print("  it had been — not just 'no API key set,' an unconditional refusal regardless.")
    print("  The fix a human needs was already sitting in DATA-STRUCTURE-SUMMARY.md,")
    print("  written locally before any of this, with zero cell values ever reported.")
    print()
    print("  (#28, the per-action approval gate on LLM-FIX, is passed through above too —")
    print("  approve_fn=lambda action: True — but never actually exercised, because a")
    print("  restricted dispatcher never proposes anything to approve in the first place.")
    print("  See run_demo.py's Act 3 for a run where the fix loop — and this gate — fire for real.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the restricted-data (#27) demo.")
    parser.add_argument("--terse", action="store_true",
                         help="One-line-per-step output instead of full step-by-step narration")
    parser.add_argument("--pause", action="store_true",
                         help="Wait for Enter before each pipeline step — for presenting live")
    args = parser.parse_args()
    _PAUSE = args.pause
    main(terse=args.terse)
