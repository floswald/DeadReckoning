# Demo 3: LandUse (REStud) — build instructions

Third presentation demo, same narrated step-by-step style as `run_demo.py`
(toy_paper) and `run_demo_bus_locations.py` (bus_locations_real). Payoff:
real, published, own paper (Oswald, *Land Use, Structural Change and Urban
Expansion*, REStud, github.com/floswald/LandUse-REStud, data on Zenodo) —
proves DeadReckoning on a genuine multi-language (Julia/R/Stata), many-
dataset package, not just a toy.

Source repo (read-only, never modify):
`/Users/floswald/Library/CloudStorage/Dropbox/research/LandUse/ReplicationPackage-submit`

## 1. Fixture to build: `demo/landuse_real/`

Copy ONLY these paths from the source repo — nothing else, ever:

```
code/stata/figure1.do
data/raw/FRA_base.dta
```

Directory layout to create:

```
demo/landuse_real/
  code/
    stata/
      figure1.do
  data/
    raw/
      FRA_base.dta
```

**Hard exclusions — do not copy, reference, or let any script touch:**
- `not-shared/` (real CASD secure-enclave microdata + its outputs) — never.
- `data/CASD/` (disclosure-cleared aggregate; harmless but irrelevant to
  this slice — leave out, don't need it).
- Anything else under `data/`, `code/LandUseR/`, `code/LandUse.jl/`,
  `paper/`, `paper_production/`, `.devcontainer/`, `renv.lock`,
  `Manifest.toml` — out of scope for this one-script slice.

Add a small `code/stata/README.md` inside the fixture (optional) noting
this is a trimmed slice of the real package, for context if anyone opens it.

## 2. Rig the bug

Real convention in the full package: `code/LandUseR/R/paths.R::dboxdir()`
requires `R_LANDUSE` env var — pattern is "resolve everything through one
root variable, never hardcode." `figure1.do` itself already uses a
relative path (`../data/raw/FRA_base.dta`), so to get a rigged, realistic
failure matching demos 1 & 2's "deadline-crunch slip" pattern:

Edit the fixture's `code/stata/figure1.do` (not the source original) to
introduce ONE of:
- **Option A (path rename slip, matches BusLocations pattern):** rename
  `data/raw/FRA_base.dta` to e.g. `data/raw/FRA_base_v2.dta` in the fixture,
  but leave the script's `use "../data/raw/FRA_base.dta"` unchanged. RESOLVE
  will see a plausible relative path and do nothing wrong; native run 404s;
  LLM fix loop sees the directory listing, spots the renamed file, proposes
  `rewrite_path` fix.
- **Option B (hardcoded absolute path slip, matches BusLocations pattern
  more literally):** change the `use` line to a hardcoded absolute path
  like `/Users/floswald/Dropbox/research/LandUse/ReplicationPackage-submit/data/raw/FRA_base.dta`.
  SCAN flags it as external, RESOLVE deterministically rewrites to
  `data/raw/FRA_base.dta` — which works immediately (no LLM step needed).

Recommend **Option A** — gives the same three-act arc as demo 2 (SCAN/
RESOLVE do the easy part, real failure needs Claude's reasoning), and is a
more realistic slip (nobody hardcodes personal Dropbox paths in Stata as
often as they rename a data file without updating the script).

## 3. Write `demo/run_demo_landuse.py`

Copy `demo/run_demo_bus_locations.py` as the template. Changes needed:

- `PROJECT = REPO_ROOT / "demo" / "landuse_real"`
- `master_script = "code/stata/figure1.do"`
- Update the opening `banner()` text: describe the real package (Julia +
  R + Stata, many real-world data sources — GHS, Copernicus CLC, INSEE,
  Schauberger yields, Shlomo Angel, IGN, CASD-cleared aggregates — this
  slice is one self-contained Stata script + its one real data input,
  `FRA_base.dta`, real French land-use/employment shares 1806–2018), and
  the specific rigged slip you chose (A or B above).
- Same step sequence as bus_locations demo: DETECT (confidentiality
  filename scan — should return NOT restricted for this trimmed slice,
  since CASD/not-shared are excluded — good to show a clean pass here,
  contrasting with what a full-package scan would flag) → GRAPH → CAPTURE
  → SCAN → RESOLVE → ASK → FIX (deterministic) → RUN (native, fails on
  the rigged slip) → FIX (LLM) → RUN (native, succeeds) → VALIDATE → CLEAN.
- No Docker step: this fixture is Stata-only, one script, seconds to run;
  add `--skip-docker` flag for symmetry but it's a no-op / can just omit
  the Docker act entirely (unlike bus_locations, which does run Docker).
- Final banner: print the reproduced `figure1.pdf`'s existence + maybe the
  underlying data (land/employment share numbers) since a PDF can't be
  printed to terminal — e.g. read `FRA_base.dta` summary stats via Stata
  output captured earlier, or just confirm file presence + size + the
  paper's actual `\includegraphics{...figure1.pdf}` line from
  `paper/20250609-sec-1-2.tex` (as a read-only quote, not copied into the
  fixture) to show the loop back to the real paper.

## 4. Test

Add `--non-interactive`-equivalent smoke test if the other demos have one
(check `tests/` for `test_realworld_mitman_broken.py`-style pattern, or
CLI-invocation tests for `run_demo.py` / `run_demo_bus_locations.py` first
— follow whatever convention exists there rather than inventing a new one).

Needs `ANTHROPIC_API_KEY` for the LLM fix act, same as the other two demos.

## 5. Update `demo/README.md`

Add a "3. Real package — `run_demo_landuse.py`" section following the
exact structure of the existing two sections (see current README.md for
the template: what's rigged, usage lines, what it shows, needs).

## Reminders

- Never run any command against the original Dropbox path — it's read
  from once (to copy the two files above), then untouched.
- Never let `not-shared/` or `data/CASD/` enter the fixture, this repo,
  git, or any log output.
- The working-copy-in-tmpdir convention (see bus_locations demo) applies
  here too — the pipeline never touches `demo/landuse_real/` directly.
