# Replication package (demo slice): LandUse (REStud)

One-script, one-data-file slice of a real published replication package,
extracted for a DeadReckoning presentation demo.

Source: Oswald, *Land Use, Structural Change and Urban Expansion*, REStud
(github.com/floswald/LandUse-REStud, data on Zenodo). The full package is
Julia + R + Stata across many real-world data sources (GHS, Copernicus
CLC, INSEE, Schauberger yields, Shlomo Angel, IGN, CASD-cleared
aggregates). This slice is deliberately scoped to one self-contained
Stata script and its one real data input.

## Data
- `data/raw/FRA_base_v2.dta` — real French land-use/employment shares,
  1806-2018 (renamed on disk from `FRA_base.dta` for this demo — see below)

## Code
- `code/stata/figure1.do` — produces `output/data/plots/figure1.pdf`
  (plus two appendix figures), the real Figure 1 of the paper

## To reproduce
Run `code/stata/figure1.do` with the project root as the working
directory. Requires Stata.

Paths in this copy are project-root-relative (`data/raw/...`,
`output/data/plots/...`), not the original's `../data/raw/...` — the
original assumes Stata is launched with `code/` as the working directory
(see the real package's `run_all.sh`), which doesn't match how this
pipeline invokes scripts (always cwd = project root). Adapted once here
so the only remaining bug is the one below.

## Rigged for the demo
`figure1.do` still reads `data/raw/FRA_base.dta`, but the file on disk
is `FRA_base_v2.dta` — a data file renamed without the script being
updated (a common deadline-crunch slip). RESOLVE sees a plausible
project-relative path and does nothing; the native run 404s; the LLM fix
loop is what actually spots the renamed file and proposes the fix.
