#!/usr/bin/env python3
"""
DeadReckoning presentation demo — toy_paper walkthrough.

Usage:
    STATA_LICENSE_PATH=/path/to/stata.lic python3 demo/run_demo.py
    python3 demo/run_demo.py --stata-image dataeditors/stata18_5-mp:2025-02-26 --stata-license /path/to/stata.lic
    python3 demo/run_demo.py --skip-docker   # steps 1-2 only, no Docker required

Three acts:
  1. The author lies to the intake questionnaire (claims R-only, README backs it up).
  2. The pipeline reads the actual code and catches the lie + an undeclared data file.
  3. Full pipeline run: native Stata execution + Docker build/run against a
     pre-built private Stata image, license mounted at run time.
"""

from __future__ import annotations

import argparse
import json
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


def pause() -> None:
    input("\n[press Enter to continue] ")


def act1_intake_lie(interactive: bool) -> "IntakeResult":  # noqa: F821
    from deadreckoning.intake import questionnaire

    banner("ACT 1 — The author fills out the intake questionnaire")
    print(f"README.md says: \"Requirements: R (tidyverse)\"")
    print("The author confirms that when asked:\n")

    answers = {
        "restricted_data": "no",
        "languages_claimed": "R",
        "last_run_date": "",
        "data_root": "data",
    }
    for k, v in answers.items():
        print(f"  {k}: {v!r}")

    intake = questionnaire(answers=answers)
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


def act3_full_pipeline(stata_image: str | None, stata_license: str | None, skip_docker: bool) -> None:
    from deadreckoning.orchestrator import run_pipeline

    banner("ACT 3 — Full pipeline run: native execution" + ("" if skip_docker else " + Docker"))

    kwargs = dict(
        master_script="code/analysis.do",
        skip_docker=skip_docker,
    )
    if not skip_docker:
        kwargs["stata_image"] = stata_image
        kwargs["stata_license"] = Path(stata_license) if stata_license else None

    result = run_pipeline(PROJECT, **kwargs)

    print(f"Working copy: {result.working_copy}")
    print(f"Native run:   {'OK' if result.native_ok else 'FAILED'}  ({result.native_run})")
    if result.native_validation:
        print(f"Outputs regenerated: {result.native_validation.present}")
        if result.native_validation.missing:
            print(f"Outputs missing:     {result.native_validation.missing}")

    if not skip_docker and result.docker_fix:
        df = result.docker_fix
        print(f"\nDockerfile generated:\n{(df.final_build.dockerfile_text if df.final_build else '(none)')}")
        print(f"Docker build success: {df.final_build.success if df.final_build else None}")
        print(f"Converged (build + run + validate): {df.converged}")
        if df.error:
            print(f"Docker error: {df.error}")

    if result.error:
        print(f"\nPipeline error: {result.error}")


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
    args = parser.parse_args()

    if not args.skip_docker and not args.stata_license:
        print("No Stata license path given (set --stata-license or $STATA_LICENSE_PATH).")
        print("Falling back to --skip-docker for this run.\n")
        args.skip_docker = True

    intake = act1_intake_lie(interactive=not args.non_interactive)
    act2_pipeline_catches_it(intake)
    if not args.non_interactive:
        pause()
    act3_full_pipeline(args.stata_image, args.stata_license, args.skip_docker)


if __name__ == "__main__":
    main()
