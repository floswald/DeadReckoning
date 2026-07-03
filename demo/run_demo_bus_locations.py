#!/usr/bin/env python3
"""
DeadReckoning presentation demo — real-package walkthrough (BusLocations slice).

Usage:
    python3 demo/run_demo_bus_locations.py

Shows the deterministic front-half of the pipeline on a slice of a real,
messy, JPE-style research package: SCAN catches a hardcoded absolute
Dropbox path (the author bypassed their own paths()/R_DROPBOX
convention), RESOLVE rewrites it, and native execution reproduces the
real table from real auction data.

No Docker in this segment — the real package pulls osrm/tidygeocoder
(network calls, precomputed multi-hour distance files); this slice is
scoped to what's local and runs in seconds instead.
"""

from __future__ import annotations

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


def main() -> None:
    from deadreckoning.graph import build_graph
    from deadreckoning.scan import scan_scripts
    from deadreckoning.orchestrator import run_pipeline

    banner("A real replication package: BusLocations (Marra and Oswald)")
    print("code/tables.R reads tenders_edited.csv via a hardcoded absolute path:")
    print('  fread("/Users/floswald/Dropbox/research/BusLocation/Data/tenders_edited.csv")')
    print("(the real package resolves this through paths()/R_DROPBOX — someone")
    print(" bypassed that convention here, a common deadline-crunch slip.)")

    banner("SCAN catches it")
    scan = scan_scripts(PROJECT)
    for ep in scan.external_paths:
        print(f"  {ep.script}:{ep.line}  external path ({ep.kind}): {ep.raw}")

    banner("GRAPH traces the exhibit back to its data input")
    graph = build_graph(PROJECT)
    from deadreckoning.provenance import trace_exhibit_inputs
    for exhibit, inputs in trace_exhibit_inputs(graph).items():
        for data_path in inputs:
            print(f"  {data_path}  ->  {exhibit}")
    print("(this is the data availability statement, generated automatically —")
    print(" and written to DATA-EXHIBIT-MAP.md in the delivered package)")

    banner("Full pipeline run: RESOLVE fixes the path, native R reproduces the table")
    result = run_pipeline(PROJECT, master_script="code/tables.R", skip_docker=True)

    print(f"Working copy: {result.working_copy}")
    if result.resolve:
        for rw in result.resolve.rewrites:
            print(f"  rewrote: {rw.original}")
            print(f"       ->  {rw.rewritten}")
    print(f"\nNative run:   {'OK' if result.native_ok else 'FAILED'}")
    if result.native_validation:
        print(f"Outputs regenerated: {result.native_validation.present}")
        if result.native_validation.missing:
            print(f"Outputs missing:     {result.native_validation.missing}")

    if result.native_ok:
        table_path = result.working_copy / "tables" / "winning-groups.tex"
        if table_path.exists():
            print("\nReproduced table (real numbers from real auction data):")
            print(table_path.read_text())

    if result.error:
        print(f"\nPipeline error: {result.error}")


if __name__ == "__main__":
    main()
