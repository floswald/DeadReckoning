#!/usr/bin/env python3
"""
DeadReckoning presentation demo — toy_paper walkthrough.

Usage:
    STATA_LICENSE_PATH=/path/to/stata.lic python3 demo/run_demo.py
    python3 demo/run_demo.py --stata-image dataeditors/stata18_5-mp:2025-02-26 --stata-license /path/to/stata.lic
    python3 demo/run_demo.py --skip-docker   # acts 1-3 only, no Docker required
    python3 demo/run_demo.py --terse         # one-line-per-step output instead of full narration

Three acts:
  1. The author lies to the intake questionnaire (claims R-only, README backs it up).
  2. The pipeline reads the actual code and catches the lie + an undeclared data file.
  3. Full pipeline run, narrated step by step (same functions orchestrator.run_pipeline
     calls, just called directly here so each step can be explained as it happens):
     native Stata execution fails on a typo'd input path, Claude (live API call)
     diagnoses and fixes it, then — unless --skip-docker — Docker build/run against
     a pre-built private Stata image, license mounted at run time.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = REPO_ROOT / "demo" / "toy_paper"

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


def pause() -> None:
    input("\n[press Enter to continue] ")


def act1_intake_lie(interactive: bool, scripted: bool) -> "IntakeResult":  # noqa: F821
    from deadreckoning.intake import questionnaire

    banner("ACT 1 — The author fills out the intake questionnaire")
    print(f"README.md says: \"Requirements: R (tidyverse)\"")

    if scripted:
        # --non-interactive: no human at the keyboard, use canned answers
        # so the demo still runs end-to-end unattended (CI, recording checks).
        print("The author confirms that when asked (scripted, --non-interactive):\n")
        answers = {
            "restricted_data": "no",
            "languages_claimed": "R",
            "last_run_date": "",
            "data_root": "data",
            "master_script": "",
        }
        for k, v in answers.items():
            print(f"  {k}: {v!r}")
        intake = questionnaire(answers=answers)
    else:
        print("You are the author now — this is the real intake questionnaire,")
        print("answered live at the keyboard. Play along with the README and")
        print("claim the project is R-only.\n")
        intake = questionnaire()  # real stdin — presenter types the answers live

    if interactive:
        pause()
    return intake


def act2_pipeline_catches_it(intake) -> None:
    from deadreckoning.ask import identify_questions
    from deadreckoning.graph import build_graph
    from deadreckoning.scan import scan_scripts
    from deadreckoning.provenance import trace_exhibit_inputs

    banner("ACT 2 — The pipeline reads the code and catches it")

    graph = build_graph(PROJECT)
    scan = scan_scripts(PROJECT)

    print("Data files actually read by code/analysis.do (per GRAPH step):")
    for df in graph.data_files:
        flag = "  <-- NOT in README" if df.path.name == "region_boost.csv" else ""
        print(f"  - {df.path}{flag}")

    questions = identify_questions(graph, None, scan=scan, intake=intake)
    print("\nContradiction(s) raised against the intake answers:")
    for q in questions:
        if q.gap_kind == "intake_contradiction":
            print(f"  [{q.gap_kind}] {q.question}")

    print("\nAnd it doesn't just spot the undeclared file — it traces exactly")
    print("which exhibit each data file feeds (the data availability statement,")
    print("written automatically):")
    mapping = trace_exhibit_inputs(graph)
    for exhibit, inputs in mapping.items():
        for data_path in inputs:
            flag = "  <-- undeclared in README" if data_path.name == "region_boost.csv" else ""
            print(f"  {data_path}  ->  {exhibit}{flag}")


def act3_full_pipeline(
    stata_image: str | None,
    stata_license: str | None,
    skip_docker: bool,
    intake=None,
    terse: bool = False,
) -> None:
    """
    Narrates the same sequence orchestrator.run_pipeline() runs in one call —
    calling each real step function directly so it can be explained live,
    instead of hiding it all behind one black-box call.
    """
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

    master_script = "code/analysis.do"

    banner("ACT 3 — Full pipeline run, step by step" + ("" if skip_docker else " (+ Docker)"))

    # DETECT — the author's own intake answer is checked first (§4.1: ask
    # before opening anything takes priority over the filename heuristic),
    # then the filename-only scan as a secondary check (§4.2).
    if not terse:
        step("DETECT", "author's intake answer checked first, then filename-only scan — "
                        "before any file is opened")
    if intake is not None and intake.restricted_data:
        print("  restricted: True (author confirmed via intake questionnaire)")
        return

    restricted = check_restricted(PROJECT)
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
    # stata_image cannot be inferred from disk (proprietary, no lockfile) — author-supplied
    if stata_image and env_spec.language.upper() == "STATA":
        env_spec.stata_image = stata_image
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
    qa, needs_input, graph, env_spec = run_ask_step(working_copy, graph, env_spec, scan, intake=intake)
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
        step("RUN (native)", "actually execute the master script, unmodified sandbox aside")
    print(f"  {'OK' if native_run.success else 'FAILED'}")

    if not native_run.success:
        if not terse:
            print(f"\n  stderr / log excerpt:\n" + "\n".join(f"    {l}" for l in native_run.stderr.strip().splitlines()))

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
        stata_license=Path(stata_license) if stata_license else None,
    )
    if docker_fix.final_build is not None:
        if not terse:
            print(f"\n  Dockerfile:\n" + "\n".join(f"    {l}" for l in docker_fix.final_build.dockerfile_text.splitlines()))
        print(f"  build success: {docker_fix.final_build.success}")
    print(f"  converged (build + run + validate): {docker_fix.converged}")
    if docker_fix.error:
        print(f"  error: {docker_fix.error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DeadReckoning presentation demo.")
    parser.add_argument("--stata-image", default="dataeditors/stata18_5-mp:2025-02-26",
                         help="Pre-built private Stata Docker image tag")
    parser.add_argument("--stata-license", default=os.environ.get("STATA_LICENSE_PATH"),
                         help="Host path to stata.lic (default: $STATA_LICENSE_PATH)")
    parser.add_argument("--skip-docker", action="store_true",
                         help="Run acts 1-3 without Docker (native execution only)")
    parser.add_argument("--non-interactive", action="store_true",
                         help="Don't pause between acts (for a scripted/recorded run)")
    parser.add_argument("--terse", action="store_true",
                         help="One-line-per-step output instead of full step-by-step narration")
    args = parser.parse_args()

    if not args.skip_docker and not args.stata_license:
        print("No Stata license path given (set --stata-license or $STATA_LICENSE_PATH).")
        print("Falling back to --skip-docker for this run.\n")
        args.skip_docker = True

    intake = act1_intake_lie(interactive=not args.non_interactive, scripted=args.non_interactive)
    act2_pipeline_catches_it(intake)
    if not args.non_interactive:
        pause()
    act3_full_pipeline(args.stata_image, args.stata_license, args.skip_docker, intake=intake, terse=args.terse)


if __name__ == "__main__":
    main()
