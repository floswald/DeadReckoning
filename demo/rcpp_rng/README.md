# Demo: Rcpp mixed-language package — missing seed, missing build flags, nondeterministic sort

Synthetic fixture, three languages: Stata prepares survey data, R drives
the analysis, and a compiled Rcpp routine does the actual simulation.
Three independent, real reproducibility gaps, all found statically
before any native run.

## Pipeline
- `code/stata/prep_survey.do` — reads `data/raw/survey_raw.csv` (12
  respondents, 3 per region across 4 regions), picks one "anchor"
  respondent per region, writes `data/survey_prepped.dta`.
- `code/simulate.R` — reads the anchor incomes, calls
  `Rcpp::sourceCpp("src/shocks.cpp")`, draws 2000 simulated income
  shocks around each anchor, writes `output/Table1.tex` and
  `output/fig1.pdf`.
- `src/shocks.cpp` — the compiled Rcpp routine. Draws from `Rcpp::rnorm`,
  i.e. R's own RNG stream, not C++'s.

## The three gaps

1. **Nondeterministic sort** (`code/stata/prep_survey.do:17-18`). Three
   respondents share each region code, so `sort region` alone does not
   determine which one ends up first; `by region: keep if _n==1` then
   picks whichever respondent that unstable sort happened to put first.
   Stata's default sort breaks ties among equal key values with an
   internal random tiebreaker that is not guaranteed stable across runs,
   Stata editions (SE vs MP), or machine thread counts — `set sortseed`
   exists for exactly this, but Stata's own docs call it "highly
   esoteric," reserved for replication studies. See
   https://www.stata.com/help13.cgi?sortseed=,
   https://www.stata.com/manuals/dsort.pdf,
   https://www.statalist.org/forums/forum/general-stata-discussion/general/1345163-how-does-stata-randomize-observations-with-the-same-value-when-using-the-command-sort-without-stable.
   Caught by the new `sort_check.py` (`SORT-WARNINGS.md`).

2. **Undeclared compiler flags** (`src/shocks.cpp`). It's Rcpp-embedded
   C++ (`// [[Rcpp::export]]`, `#include <Rcpp.h>`), compiled on the fly
   by R's `sourceCpp()` — there is no `src/Makevars` anywhere in this
   package. The file's own comment records that the author's personal
   `~/.R/Makevars` sets `PKG_CXXFLAGS = -fopenmp -O3`; that flag lives
   nowhere in the package itself. `sourceCpp()` auto-compiles with R's
   default flags regardless, so this does not crash — it's a silent
   "might compile differently on a replicator's machine" risk. Caught by
   the existing `mixed_language_check.py` (`MIXED-LANGUAGE-WARNINGS.md`).

3. **Missing RNG seed** (`src/shocks.cpp:24`, `Rcpp::rnorm(...)`).
   Rcpp's RNG functions draw from R's own RNG stream — the same stream
   `set.seed()` in the calling R script would control — not C++'s
   `std::rand()`/`<random>`. There is no `set.seed()` anywhere in this
   package. Caught by `rng_check.py`, which previously only recognized
   `std::rand()`/`<random>` engines in `.cpp` files; this demo is the
   reason `Rcpp::rnorm`/`R::rnorm`/`norm_rand`/`unif_rand` patterns were
   added.

## Why only one of the three actually perturbs the numbers here

Mixing more than one live numeric cause into the same exhibit would make
a mismatch impossible to attribute to anything specific — see the
demo script's module docstring. So in this fixture:

- The missing seed is the one gap that's actually live: every native run
  of `code/simulate.R` draws a fresh, different `Rcpp::rnorm()` sequence,
  so `output/Table1.tex` differs from `reference/Table1.tex` (the
  snapshot baked into this fixture) on every single run.
- The Makevars gap is real but latent in this demo environment: R's
  default compile flags happen to build `shocks.cpp` successfully either
  way here, so it doesn't itself change `output/Table1.tex` — it's a
  static lead about a risk, not a live cause in this run.
- The sort-tiebreak gap is real but not forced live either: this demo
  runs a single Stata edition/thread-count, so it won't itself show two
  different anchor picks across runs — it's the same class of risk as
  the Makevars gap, surfaced the same way, before anything runs.

## To reproduce

Requires a local Stata install, R with the `Rcpp` and `haven` packages,
and a C++ compiler (tested with StataMP 19.5, R 4.5, g++). Run
`code/stata/prep_survey.do`, then `code/simulate.R`, from the project
root. `reference/Table1.tex` was captured once from an actual run and
will not byte-match any subsequent run, by design — see above.
