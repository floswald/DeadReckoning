# DeadReckoning — Implementation Guide

## What this is

Python agent that helps economics researchers reconstruct and validate
computational pipelines before submitting a replication package.
Target moment: paper accepted, author needs to prove everything runs.

## Architecture rule

**Deterministic core first, LLM on top.**
Every pipeline step is a pure function returning a pydantic model.
The LLM orchestration layer (Phase 4) calls these as tools.
Test the pure functions; treat LLM calls as integration tests only.

## Pipeline (14 steps)

```
DETECT → CAPTURE → GRAPH → SCAN → ASK → RESOLVE
  → FIX↻ (native) → VALIDATE (native) → CLEAN
  → GENERATE → BUILD → VALIDATE (container) → FIX↻ (Docker) → DELIVER
```

**Docker is the final step.** Native must pass first.
**Stata + Docker: out of scope** — license-locked, no free base image.
**MATLAB + Docker: guidance only** — use mathworks/matlab with browser login; no auto-build.

## Built so far

| Module | Purpose |
|--------|---------|
| `models.py` | Pydantic schema for everything (incl. CleanResult, DeliverResult) |
| `confidentiality.py` | Filename-only scan — runs before any file read |
| `graph.py` | `build_graph()` → LaTeX → exhibits → scripts → data; `here()`/`file.path()` pre-processing |
| `capture.py` | renv.lock / requirements.txt / .do / Manifest.toml / DESCRIPTION → `EnvSpec` |
| `scan.py` | Package + external path extraction — R, Python, Julia, Stata, MATLAB |
| `runner.py` | Dispatch by extension: `.R` `.do` `.jl` `.py` `.m` |
| `stata.py` | Three-state detection + advice, log scanning, ssc capture |
| `matlab.py` | Three-state detection, -batch/-r dispatch, error scanning |
| `resolve.py` | Absolute path rewrites (all languages) + relative path canonicalization (`here::here`, `pathlib`, `@__DIR__`, `fullfile`) |
| `fix_loop.py` | Deterministic FIX loop (wrong-output-path) + LLM dispatcher hook |
| `llm_dispatcher.py` | Claude tool-call FIX loop |
| `docker.py` | Dockerfile generation (R/Python/Julia/unsupported), build, container validation |
| `ask.py` | Author Q&A: gap questions, proprietary license, low-conf env, QUESTIONS.md round-trip |
| `clean.py` | Orphan detection (BFS from exhibit sources), CLEANUP.md, delete/archive/keep |
| `deliver.py` | AEA README template, DELIVERY_REPORT.md, optional zip assembly |
| `orchestrator.py` | Sequential pipeline, auto-detects master script |
| `cli.py` | CLI entrypoint |

## Test strategy

```
pytest -m "not local"          # fast CI — no R/Stata/Docker needed
pytest -m "local and not docker"  # requires R + Stata
pytest -m "local"              # full including Docker
```

Real-world fixtures go in `tests/real_world/` (gitignored).
See issue #10 for protocol on adding them.

## Open issues (priority order)

| # | Title | Status |
|---|-------|--------|
| 3 | Fixture generator | deferred |
| 9 | Real-world test cases | ongoing |

## Test counts (as of last update)

- **Total passing:** 586 (fast CI; includes new Phase 4 tests)
- **Pre-existing failures:** 3 (Stata license on dev machine, Docker not in CI)
- Key test files: `test_ask.py` (44), `test_clean.py` (39), `test_deliver.py` (42),
  `test_resolve_multilang.py` (39), `test_matlab.py` (31), `test_runner_julia_python.py` (13),
  `test_docker.py` (+12 new), `test_llm_dispatcher.py` (+3 multi-lang),
  `test_realworld_bus_locations.py` (48), `test_realworld_bus_location.py` (10)

## Key gotchas

- **Stata exits 0 on error** — must scan `.log` for `r(N);`
- **Stata log location**: `<basename>.log` in CWD, not beside the script
- **MATLAB exits 0 on error (pre-R2019b)** — scan stdout/stderr for `Error/Unrecognized/Undefined`
- **MATLAB `run.m` naming conflict** — script named `run.m` shadows built-in `run()` in `-batch` mode; use `master.m` or any other name
- **Julia `include` resolves relative to script dir** — use `joinpath(@__DIR__, ...)` not bare relative paths
- **`here()` / `file.path()`** — pre-processed in `_extract_write_calls` so write-call patterns match; crucial for R replication packages
- **LaTeX macros**: `\def`, `\newcommand`, `\graphicspath` all need resolving
- **Path resolution**: try script-relative AND project-root-relative
- **Working copy safety**: `orchestrator.run_pipeline()` always copies first
- **Output .tex files**: skip files in `output/` dirs when scanning for inline stats

## Starting a new session

```bash
git log --oneline -5        # see recent work
pytest -m "not local" -q    # verify baseline
gh issue list               # check open issues
```
