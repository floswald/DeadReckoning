# Demo: fan-out fidelity (same input, several exhibits, partial rerun)

Two real Stata scripts from a real, published replication package,
sharing one real data input — extended from `demo/landuse_real/` (which
this fixture does not modify).

Source: Oswald, *Land Use, Structural Change and Urban Expansion*, REStud
(github.com/floswald/LandUse-REStud, data on Zenodo).

## Data
- `data/raw/FRA_base.dta` — real French land-use/employment shares,
  1806-2018. This is the only copy that exists: nothing preserves the
  pre-revision ("v1") values, matching reality.

## Code
- `code/stata/figure1.do` — produces `figure1.pdf`, `figureA2a.pdf`,
  `figureA2b.pdf`
- `code/stata/generatethetas.do` — produces `figureA3.pdf`, `figure7.pdf`,
  `figureA4.pdf`, plus the intermediate `data/processed/FRA_model.dta`

Both scripts read `data/raw/FRA_base.dta` directly — the shared-input,
fan-out shape this demo exists to exercise.

## Rigged for the demo

`reference/` ships a mix of two vintages, mirroring a real, common
mistake: a shared upstream input gets revised, and only some of its
downstream consumers get rerun before submission.

- `reference/figure1.pdf`, `figureA2a.pdf`, `figureA2b.pdf` — built from
  a **pre-revision** snapshot of `FRA_base.dta` (year 1950's
  `Land_Agriculture` and `Share_Emp_Agr100` observations restated). The
  author believed `figure1.do` unaffected by the revision and never
  reran it.
- `reference/figureA3.pdf`, `figure7.pdf`, `figureA4.pdf` — built from
  the **current** `FRA_base.dta` (the one shipped in `data/raw/`).
  `generatethetas.do` *was* rerun after the revision, so its reference
  already reflects it.

Rerunning both scripts today against the current `data/raw/FRA_base.dta`
reproduces this exactly: `generatethetas.do`'s three exhibits match their
reference (both built from the same, current data); `figure1.do`'s three
don't (reference is stale, replication-time run isn't). All six
exhibits land on disk, both scripts exit 0 — nothing crashes.
`check_exhibit_fidelity()` is what catches the mismatch and walks the
dependency graph back to name `data/raw/FRA_base.dta` as the shared
suspect, for all three mismatching exhibits, without ever flagging the
three that are actually fine.

Note: `figureA3.pdf` does not depend on `Land_Agriculture` at all (it's
built purely from price/value-added series), so it's unaffected by the
revision regardless of which script produced it — confirmed directly,
not assumed, when the fixture was built (byte-identical across the two
`FRA_base.dta` vintages). `figure7.pdf` and `figureA4.pdf` are the same
graph exported twice by the script (lines `graph export .../figure7.pdf`
and `graph export .../figureA4.pdf` back to back) — five distinct
renders across six exhibit files, not six independent ones.

## To reproduce
Run `code/stata/figure1.do` and `code/stata/generatethetas.do` with the
project root as the working directory. Requires Stata (tested on
StataNow 19.5 / MP). Confirmed deterministic: re-running either script
against unchanged inputs reproduces byte-identical PDFs.
