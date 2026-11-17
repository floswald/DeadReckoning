# Demo: fan-out fidelity AND chain drift (same input, several exhibits,
# partial rerun, plus a downstream consumer that never reran)

Two real Stata scripts from a real, published replication package,
sharing one real data input — extended from `demo/landuse_real/` (which
this fixture does not modify) — plus a third, synthetic script,
`code/julia/combine_theta_summary.jl`, added so this demo can show both
drift shapes from the deck in one run: the parallel fan-out below, and
the chain-drift mechanism from `demo/coauthor_drift/` (Demo 4), live, fed
by real Stata output.

Source: Oswald, *Land Use, Structural Change and Urban Expansion*, REStud
(github.com/floswald/LandUse-REStud, data on Zenodo).

## Data
- `data/raw/FRA_base.dta` — real French land-use/employment shares,
  1806-2018. This is the only copy that exists: nothing preserves the
  pre-revision ("v1") values, matching reality.
- `data/decade_weights.csv` — **fabricated for this demo**, not part of
  the real published package. Stands in for a coauthor-supplied decade
  weighting scheme, the way `demo/coauthor_drift/data/input_data_from_2.csv`
  stands in for Demo 4's region weights. See `demo/landuse_fanout_private/README.md`.

## Code
- `code/stata/figure1.do` — produces `figure1.pdf`, `figureA2a.pdf`,
  `figureA2b.pdf`
- `code/stata/generatethetas.do` — produces `figureA3.pdf`, `figure7.pdf`,
  `figureA4.pdf`, plus the intermediate `data/processed/FRA_model.dta` /
  `FRA_model.csv`
- `code/julia/combine_theta_summary.jl` — **fabricated for this demo.**
  Reads `generatethetas.do`'s `FRA_model.csv` and `data/decade_weights.csv`,
  produces `output/TableTheta.tex`.

`figure1.do` and `generatethetas.do` both read `data/raw/FRA_base.dta`
directly — the shared-input, fan-out shape this demo exists to exercise.
`combine_theta_summary.jl` extends that chain one stage further
downstream, exactly like `combine.jl` does in Demo 4.

## Rigged for the demo

Two independent rigs, one per drift shape.

**Fan-out** — `reference/` ships a mix of two vintages, mirroring a real, common mistake: a shared upstream input gets revised, and only some of its downstream consumers get rerun before submission.

- `reference/figure1.pdf`, `figureA2a.pdf`, `figureA2b.pdf` — built from
  a **pre-revision** snapshot of `FRA_base.dta` (year 1950's
  `Land_Agriculture` and `Share_Emp_Agr100` observations restated). The
  author believed `figure1.do` unaffected by the revision and never
  reran it.
- `reference/figureA3.pdf`, `figure7.pdf`, `figureA4.pdf` — built from
  the **current** `FRA_base.dta` (the one shipped in `data/raw/`).
  `generatethetas.do` *was* rerun after the revision, so its reference
  already reflects it.

**Chain** — fabricated for this demo, performed live by
`demo/run_demo_landuse_fanout.py` rather than baked into `reference/`
ahead of time (mirrors `demo/run_demo_coauthor_drift.py`):
`data/decade_weights.csv` ships as the pre-re-export ("v1", 2-decimal
truncated) version, matching `reference/TableTheta.tex`. Mid-run, the
script swaps in `demo/landuse_fanout_private/decade_weights_v2.csv`
(full double precision) before `combine_theta_summary.jl` executes —
simulating the coauthor's silent re-export landing *before*
`combine_theta_summary.jl` is ever rerun to pick it up.

Rerunning everything today against the current `data/raw/FRA_base.dta`
and the swapped-in `decade_weights.csv` (v2) reproduces both rigs at
once: `generatethetas.do`'s three exhibits match their reference (both
built from the same, current data); `figure1.do`'s three don't (reference
is stale, replication-time run isn't); and `TableTheta.tex` doesn't
either (reference used v1 weights, this run used v2). All seven exhibits
land on disk, all three scripts exit 0 — nothing crashes.
`check_exhibit_fidelity()` is what catches both mismatches. It walks the
dependency graph back from each exhibit: `figure1.do`'s three name only
`data/raw/FRA_base.dta`; `TableTheta.tex` names both `data/raw/FRA_base.dta`
(a real but incidental upstream link, since `combine_theta_summary.jl`'s
input is itself produced by `generatethetas.do`) and
`data/decade_weights.csv` (the actual cause) — without ever flagging the
three `generatethetas.do` exhibits that are actually fine.

Note: `figureA3.pdf` does not depend on `Land_Agriculture` at all (it's
built purely from price/value-added series), so it's unaffected by the
revision regardless of which script produced it — confirmed directly,
not assumed, when the fixture was built (byte-identical across the two
`FRA_base.dta` vintages). `figure7.pdf` and `figureA4.pdf` are the same
graph exported twice by the script (lines `graph export .../figure7.pdf`
and `graph export .../figureA4.pdf` back to back) — five distinct
renders across the six Stata-sourced exhibit files, not six independent
ones.

## To reproduce
Run `code/stata/figure1.do` and `code/stata/generatethetas.do` with the
project root as the working directory, then `code/julia/combine_theta_summary.jl`
(requires `data/decade_weights.csv` and `generatethetas.do`'s
`data/processed/FRA_model.csv` to already exist). Requires Stata (tested
on StataNow 19.5 / MP) and Julia (CSV.jl, DataFrames.jl). Confirmed
deterministic: re-running any script against unchanged inputs reproduces
byte-identical output.
