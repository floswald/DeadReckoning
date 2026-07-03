# DeadReckoning presentation demo

Two segments, ~5 minutes total. Both drive the real pipeline
(`run_pipeline` / `deadreckoning run`), not hand-built objects.

## 1. Toy package — `run_demo.py`

Fake paper (`toy_paper/`) with two rigged problems: the author claims
R-only (README says so too) but the actual code is Stata, and the Stata
script silently reads an undeclared second CSV (`region_boost.csv`) never
mentioned in the README.

```bash
python3 demo/run_demo.py                     # interactive, pauses between acts
python3 demo/run_demo.py --non-interactive   # straight through, no pauses
python3 demo/run_demo.py --skip-docker       # acts 1-2 only, no Stata license needed
```

Shows: intake questionnaire catching the language lie, GRAPH tracing the
undeclared file straight to the exhibit it feeds, then a full run —
native Stata execution + Docker build/run against a pre-built private
Stata image (`dataeditors/stata18_5-mp:2025-02-26` by default).

Needs for the Docker path: `$STATA_LICENSE_PATH` set to a valid
`stata.lic`, and that base image built locally already (falls back to
`--skip-docker` automatically if the license isn't set).

## 2. Real package — `run_demo_bus_locations.py`

One-table slice of a real JPE-style package (BusLocations, Marra and
Oswald) with real tender-auction data. The rigged problem: the script
hardcodes an absolute Dropbox path instead of using the real package's
`paths()`/`R_DROPBOX` convention — a common deadline-crunch slip.

```bash
python3 demo/run_demo_bus_locations.py
```

Shows: SCAN flagging the hardcoded path, GRAPH tracing the exhibit to its
data input, then RESOLVE rewriting the path and native R reproducing the
real table with real numbers. No Docker in this segment — the real
package pulls in osrm/tidygeocoder (network calls) and multi-hour
precomputed distance files; this slice is scoped to what runs in seconds.

## Notes

- Neither script touches `demo/toy_paper/` or `demo/bus_locations_real/`
  directly — the pipeline always works on a temp copy, printed as
  "Working copy" in the output.
- Both scripts write `DATA-EXHIBIT-MAP.md` into that working copy (the
  generated data availability statement).
