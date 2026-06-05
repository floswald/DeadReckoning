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

## Built so far

| Module | Purpose |
|--------|---------|
| `models.py` | Pydantic schema for everything |
| `confidentiality.py` | Filename-only scan — runs before any file read |
| `graph.py` | `build_graph()` → LaTeX → exhibits → scripts → data |
| `capture.py` | renv.lock / requirements.txt / .do → `EnvSpec` |
| `runner.py` | Dispatch by extension: `.R` → Rscript, `.do` → Stata |
| `stata.py` | Three-state detection + advice, log scanning, ssc capture |
| `docker.py` | Dockerfile template, build, container validation (R only) |
| `orchestrator.py` | Sequential pipeline, auto-detects master script |

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
| 11 | CLI entrypoint | next |
| 5 | Deepen R (RESOLVE, path rewrites) | next after CLI |
| 6 | FIX loop — LLM orchestration | Phase 4 |
| 8 | Multi-language (Python, Julia) | Stata done |
| 3 | Fixture generator | deferred |
| 7 | Containerization depth | after native proven |
| 9 | Real-world test cases | ongoing |

## Key gotchas

- **Stata exits 0 on error** — must scan `.log` for `r(N);`
- **Stata log location**: `<basename>.log` in CWD, not beside the script
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
