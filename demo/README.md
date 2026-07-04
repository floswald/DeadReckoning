# DeadReckoning presentation demo

Two segments, ~5 minutes total. Both drive the real pipeline
(`run_pipeline` / `deadreckoning run`), not hand-built objects.

## 1. Toy package — `run_demo.py`

Fake paper (`toy_paper/`) with three rigged problems: the author claims
R-only (README says so too) but the actual code is Stata; the Stata
script silently reads an undeclared second CSV (`region_boost.csv`) never
mentioned in the README; and the script has a typo'd input filename
(`survey_data.csv` instead of `survey.csv`) that only surfaces as a real
runtime failure — this is the one the LLM fix loop actually fixes.

```bash
python3 demo/run_demo.py                     # interactive — you play the author, live
python3 demo/run_demo.py --non-interactive   # scripted answers, straight through, no pauses (CI)
python3 demo/run_demo.py --skip-docker       # acts 1-3 only, no Stata license needed
python3 demo/run_demo.py --terse             # one line per step instead of full narration
```

Act 1 is the real intake questionnaire (`deadreckoning.intake.questionnaire()`)
answered live at the keyboard by whoever's presenting — you play the author
and claim the project is R-only, same as the real README says. `--non-interactive`
swaps in canned scripted answers instead, so the demo still runs unattended for
CI/verification without a human typing.

Act 3 calls each pipeline step directly (GRAPH, CAPTURE, SCAN, RESOLVE, ASK,
FIX, RUN, VALIDATE, CLEAN, DOCKER) — the same functions
`orchestrator.run_pipeline()` calls internally, just narrated one at a time
instead of hidden behind a single call, with a one-line explanation of what
each step does and the actual generated artifacts (DATA-EXHIBIT-MAP.md,
Dockerfile, etc.) printed as they're produced.

Shows: intake questionnaire catching the language lie, GRAPH tracing the
undeclared file straight to the exhibit it feeds, then a full run —
native Stata execution fails on the typo'd path, and **this is where an
LLM (Claude, live API call) actually does the thinking**: it's handed
the failing stderr/log excerpt plus a directory listing, reasons about
which file was meant, and proposes a `rewrite_path` fix that gets applied
and re-run natively. Everywhere else in the pipeline (SCAN, GRAPH,
RESOLVE, intake contradictions) is deterministic — the LLM only engages
when a native run actually fails and no static/deterministic fix applies.
Then Docker build/run against a pre-built private Stata image
(`dataeditors/stata18_5-mp:2025-02-26` by default) if not skipped.

Needs `ANTHROPIC_API_KEY` set for the LLM fix-loop act to actually call
Claude — without it, the dispatcher silently returns no fix and the demo
reports "still failing" for that step.

Needs for the Docker path: `$STATA_LICENSE_PATH` set to a valid
`stata.lic`, and that base image built locally already (falls back to
`--skip-docker` automatically if the license isn't set).

## 2. Real package — `run_demo_bus_locations.py`

One-table slice of a real JPE-style package (BusLocations, Marra and
Oswald) with real tender-auction data. Two rigged problems: the script
hardcodes an absolute Dropbox path instead of using the real package's
`paths()`/`R_DROPBOX` convention (a common deadline-crunch slip); and
the underlying data file was renamed on disk (`tenders_edited.csv` ->
`tenders_edited_final.csv`) without anyone updating the script or
README — a classic "which version is the real one" slip.

```bash
python3 demo/run_demo_bus_locations.py           # full step-by-step narration
python3 demo/run_demo_bus_locations.py --terse   # one line per step
```

Same narrated-step-by-step treatment as segment 1: each real pipeline
function (GRAPH, CAPTURE, SCAN, RESOLVE, ASK, FIX, RUN, VALIDATE, CLEAN)
called directly and explained as it runs, instead of one call to
`run_pipeline()`. No Docker step here (this fixture always runs with
`skip_docker=True`).

Shows: SCAN flagging the hardcoded path, GRAPH tracing the exhibit to its
data input, RESOLVE deterministically rewriting the absolute path to a
project-relative one — which still 404s natively, because RESOLVE only
knows the basename the script asked for, not that the file was renamed.
**That's where Claude (live API call) does the actual reasoning**: given
the failing stderr and a directory listing, it identifies the renamed
file and proposes the fix, which gets applied and re-run natively to
reproduce the real table with real numbers. No Docker in this segment —
the real package pulls in osrm/tidygeocoder (network calls) and
multi-hour precomputed distance files; this slice is scoped to what runs
in seconds.

Needs `ANTHROPIC_API_KEY` for the LLM fix-loop act, same as segment 1.

## Notes

- Neither script touches `demo/toy_paper/` or `demo/bus_locations_real/`
  directly — the pipeline always works on a temp copy, printed as
  "Working copy" in the output.
- Both scripts write `DATA-EXHIBIT-MAP.md` into that working copy (the
  generated data availability statement).
