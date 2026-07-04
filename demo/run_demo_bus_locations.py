#!/usr/bin/env python3
"""
DeadReckoning presentation demo — real-package walkthrough (BusLocations slice).

Usage:
    python3 demo/run_demo_bus_locations.py
    python3 demo/run_demo_bus_locations.py --terse   # one line per step

Narrates the pipeline step by step on a slice of a real, messy, JPE-style
research package — calling the same functions orchestrator.run_pipeline()
calls internally, one at a time, so each step can be explained live instead
of hidden behind one black-box call.

Two rigged problems: the script hardcodes an absolute Dropbox path instead
of the real package's paths()/R_DROPBOX convention (a common deadline-crunch
slip) — SCAN catches it, RESOLVE rewrites it deterministically. But the
underlying data file was itself renamed on disk (tenders_edited.csv ->
tenders_edited_final.csv) without anyone updating the script or README, so
the rewritten path still 404s natively. RESOLVE only knows the basename the
script asked for — that's where Claude (live API call) actually reasons
about the failure and fixes it.

Docker runs by default (this scoped slice is just R + data.table/kableExtra/
readr — no proprietary software, no license, no network calls at run time —
unlike the full real package, which pulls osrm/tidygeocoder and precomputed
multi-hour distance files; that's why this demo is scoped down to one table).
Pass --skip-docker to stop after the native run.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = REPO_ROOT / "demo" / "bus_locations_real"

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


def main(terse: bool = False, skip_docker: bool = False) -> None:
    import shutil
    import tempfile

    from deadreckoning.ask import run_ask_step
    from deadreckoning.capture import capture_env
    from deadreckoning.clean import run_clean_step
    from deadreckoning.confidentiality import check_restricted
    from deadreckoning.docker import run_docker_fix_loop
    from deadreckoning.fix_loop import append_fix_report, run_fix_loop, run_llm_fix_loop
    from deadreckoning.graph import build_graph
    from deadreckoning.provenance import render_data_exhibit_map, trace_exhibit_inputs, write_data_exhibit_map
    from deadreckoning.resolve import resolve_paths
    from deadreckoning.runner import run_natively, validate_outputs
    from deadreckoning.scan import scan_scripts

    master_script = "code/tables.R"

    banner("A real replication package: BusLocations (Marra and Oswald)")
    print("code/tables.R reads tenders_edited.csv via a hardcoded absolute path:")
    print('  fread("/Users/floswald/Dropbox/research/BusLocation/Data/tenders_edited.csv")')
    print("(the real package resolves this through paths()/R_DROPBOX — someone")
    print(" bypassed that convention here, a common deadline-crunch slip. The data")
    print(" file was also renamed on disk since — a second, independent slip.)")

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

    # RESOLVE
    resolve = resolve_paths(working_copy, scan)
    if not terse:
        step("RESOLVE", "rewrite external/absolute paths to project-relative ones")
    print(f"  {resolve.rewrite_count} path rewrite(s)")
    for rw in resolve.rewrites:
        print(f"    {rw.original}\n      -> {rw.rewritten}")

    # here::here() adoption (R) introduces a new dependency CAPTURE never saw
    # (it ran before this rewrite) — add it back so Docker installs it too.
    if (resolve.here_adoptions > 0 and env_spec.language.upper() == "R"
            and not any(p.name == "here" for p in env_spec.packages)):
        from deadreckoning.models import PackageSpec, PinMethod
        env_spec.packages.append(PackageSpec(name="here", pin_method=PinMethod.unknown))
        print(f"  (+ 'here' added to packages — introduced by RESOLVE's here::here() rewrite)")

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
        step("RUN (native)", "actually execute the master script, unmodified sandbox aside — "
                              "RESOLVE's rewrite still points at a renamed file")
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

    table_path = working_copy / "tables" / "winning-groups.tex"
    if table_path.exists():
        banner("Reproduced table (real numbers from real auction data)")
        print(table_path.read_text())

    if skip_docker:
        return

    # DOCKER
    if not terse:
        step("DOCKER (GENERATE + BUILD + RUN, auto-fix loop)",
             "generate a Dockerfile, build it, run the master script inside, "
             "and if that fails, dispatch to Claude again — same fix loop, containerized")
    image_tag = f"deadreckoning-{PROJECT.name}:latest"
    print(f"  image tag: {image_tag}")
    docker_fix = run_docker_fix_loop(
        working_copy, graph, env_spec,
        image_tag=image_tag,
        master_script=master_script,
    )
    if docker_fix.final_build is not None:
        if not terse:
            print(f"\n  Dockerfile:\n" + "\n".join(f"    {l}" for l in docker_fix.final_build.dockerfile_text.splitlines()))
        print(f"  build success: {docker_fix.final_build.success}")
    print(f"  converged (build + run + validate): {docker_fix.converged}")
    if docker_fix.error:
        print(f"  error: {docker_fix.error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the BusLocations real-package demo.")
    parser.add_argument("--terse", action="store_true",
                         help="One-line-per-step output instead of full step-by-step narration")
    parser.add_argument("--skip-docker", action="store_true",
                         help="Stop after the native run; don't build/run the Docker image")
    args = parser.parse_args()
    main(terse=args.terse, skip_docker=args.skip_docker)
