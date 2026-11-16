# DeadReckoning vs. ReproAI Prep

Tracking issue: [#25](https://github.com/floswald/DeadReckoning/issues/25) ("Check against" — https://github.com/reproai/reproai)

## What ReproAI Prep is

By Leo Yang Yang and Yiqing Xu ([reproai/reproai](https://github.com/reproai/reproai)). A Claude Code / OpenAI Codex
plugin + Python engine (`reproai-prep`) that **statically pre-lints** a Stata/R/Python replication
package against a fixed 55-rule set before a journal or IQSS Certify runs it. A deterministic
engine decides what's wrong (graded P0–P4 by downstream cost, tagged `defect` vs
`normalization`); the host LLM explains findings and drafts fixes on a *copy* of the package
(never the original). It optionally rehearses the fixed copy twice under certification-like
conditions, but never executes code during the static `check`/`comply`/`fix`/`map` commands —
only the opt-in `debug`/rehearse step runs anything, and it explicitly **never compares
coefficients to the paper or issues a reproducibility verdict**.

## Core philosophical difference

ReproAI is a code-content linter built as an LLM-plugin from the start: a Claude Code/Codex
plugin fronting a rule engine, designed to run inside an AI assistant session. DeadReckoning is
~90% static Python that actually **executes** the replication package (native run, then
optionally Docker) and only calls an LLM narrowly, as `LLM-FIX`, scoped to a real stderr after a
real failure. That's a deliberate difference, not an oversight — ReproAI pre-lints before any run
ever happens; DeadReckoning runs first and diagnoses real failures. The cost of DeadReckoning's
bet: several of ReproAI's P0 rules are exactly the "doesn't crash, just produces a different
number" failure modes that an execution-first pipeline can walk straight past if nothing is
checking for them (see Action Points below).

## The 55-rule coverage map

Legend: **COVERED** = equivalent logic exists and runs by default · **PARTIAL** = related
mechanism exists but doesn't close the specific failure mode · **GAP** = no equivalent today.

### structural (18 rules)

| rule_id | priority | kind | status | note |
|---|---|---|---|---|
| A3-data-load | P0 | defect | GAP | No check that estimation commands have a prior load; surfaces at runtime as an undefined-variable error → LLM-FIX, not caught statically. |
| A5-stable-includes | P0 | defect | PARTIAL | `graph.py` resolves tex→script and script→data references; no check that a `do`/`source` *script→script* include target exists on disk. |
| A6-guarded-fallback-load | P0 | defect | GAP | No pattern for Stata `capture use A; if _rc!=0 {use B}` dead-fallback detection. |
| A7-var-lifecycle-contradiction | P0 | defect | GAP | No variable-lifecycle tracking (would need a real parser). |
| A8-data-ref-extension-mismatch | P0 | defect | GAP | Data refs extracted literally; no same-stem-different-extension reconciliation. |
| A9-nested-cd | P0 | defect | GAP | No scan for mid-script `cd`; breaks at runtime → RUN failing, then LLM-FIX if key is set. |
| A14-missing-input | P0 | defect | **GAP — verified, see Action Point 1** | The signal already exists (`graph.py`'s `DataFile.exists_on_disk` + `.produced_by`) but nothing consumes it to flag a genuinely missing, non-produced input before a run. |
| A16-no-executable-code | P1 | defect | GAP | No explicit "data present, zero scripts" finding. |
| A1-master-entry | P1 | defect | COVERED | `orchestrator.py:_detect_master_script` + intake question (`master_script` field). |
| A11-explicit-run-order | P1 | defect | COVERED | `graph.py:_topological_script_order` derives order from the write/read dependency graph. |
| A13-unreferenced-script | P2 | defect | COVERED | `clean.py` BFS reachability from the graph, writes `CLEANUP.md` (non-blocking, same posture as ReproAI's). |
| A15-ambiguous-input-path | P2 | defect | GAP | No basename-collision check across shipped files. |
| A17-undefined-r-callable | P2 | defect | GAP | No R symbol-resolution/export-snapshot logic. |
| A18-runtime-assembled-path | P2 | normalization | GAP (known limitation) | `scan.py`/`graph.py` only match literal string paths; a `paste0()`/f-string path silently fails to resolve. |
| A12-table-comment-mapping | P2 | normalization | GAP (different mechanism) | DeadReckoning links exhibits via the **tex** source (regex over `\includegraphics`/`\input`), not `* --> Table N` code comments — same goal, doesn't flag scripts missing such comments. |
| A2-table-grouping | P3 | normalization | GAP | No check. |
| A4-panel-declare | P3 | defect | GAP | No `tsset`/`xtset`-before-`L.`/`D.` check. |
| A10-commented-restricted-regression | P3 | normalization | GAP | `confidentiality.py` only scans **filenames**, never script content for commented-out regressions near "restricted/confidential" wording. |
| D1-output-artifact-coverage | P2 | normalization | PARTIAL | VALIDATE's `exhibit_missing_from_disk` confirms claimed exhibits exist; no check that every table-building estimation *writes* to a `tables/`/`figures/` folder in the first place. |
| D3-intermediate-data-hygiene | P1 | defect | PARTIAL | `resolve.py` canonicalizes a `data/` folder on rewrite; no existence-guard insertion before a dependent read. |
| D4-per-file-documentation | P3 | normalization | PARTIAL | `deliver.py:generate_readme` auto-writes an AEA-format README from the graph/env_spec; doesn't audit an *existing* author README for per-file gaps. |
| D5-duplicate-readme | P2 | defect | GAP | No multi-README detection. |
| D6-readme-missing-paths | P3 | defect | GAP | No README-vs-package path cross-check. |
| D7-codebook-coverage | P3 | normalization | GAP | No codebook/variable-coverage check. |
| D8-results-not-shipped | P3 | normalization | GAP | No check (edge case: no-code package). |
| D9-llm-data-provenance | P2 | normalization | GAP | No LLM-generated-data provenance check. |
| D10-package-size-cap | P0 | defect | GAP — out of scope, see below | `clean.py` already walks file sizes for the cleanup report but never sums/flags total package size against a cap. Deliberately not actioned — an author running into a 1GB+ package is already aware of its size; low value for the effort. |

### code-style (11 rules)

| rule_id | priority | kind | status | note |
|---|---|---|---|---|
| B8-r-table-call-syntax | P0 | defect | GAP | No delimiter-balance check on R calls. |
| B9-suppressed-data-load | P0 | defect | GAP | No `quietly use` detection. |
| B10-embedded-foreign-code | P0 | defect | GAP | No cross-language embedding check. |
| B11-rmd-chunk-in-r | P0 | defect | GAP | No ` ```{r} ` fence check in `.R` files. |
| C9-console-transcript | P0 | defect | GAP | No console-prompt / stray-command detection in `.do` files. |
| B7-no-cross-script-clearall | P1 | defect | GAP | No `clear all` placement check. |
| B1-minimize-loops | P2 | normalization | GAP | No loop-export-collision check. |
| B2-stata-abbrev | P2 | normalization | GAP | No Stata abbreviation detection. |
| B3-no-wide-wildcard | P3 | normalization | GAP | No wildcard-varlist check. |
| B4-no-abs-paths | P3 | defect | **COVERED, stronger** | `scan.py` (`_ABS_PATH_RE`/`_EXTERNAL_KIND_RULES`) detects absolute/UNC/cloud-drive paths; `resolve.py` auto-rewrites them relative to the package root — ReproAI only flags, DeadReckoning also fixes. |
| B5-graphics-out-of-main | P3 | normalization | GAP | No interactive/graphics-command placement check. |
| B6-rederive-from-raw | P3 | normalization | GAP | No derived-vs-raw provenance check beyond the exhibit graph itself. |

### environment (12 rules)

| rule_id | priority | kind | status | note |
|---|---|---|---|---|
| C2-vendor-ado | P0 | defect | different by design | `scan.py` detects `ssc install`/`net install` to know what to pre-install in Docker (`capture.py`/`docker.py`), not to vendor files for a network-closed run. Only a real gap if DeadReckoning ever targets an offline-certification venue. |
| C10-no-runtime-code-fetch | P0 | defect | different by design | Same as above — recorded as a dependency to install, never flagged as a reproducibility risk. |
| C11-no-external-adopath | P0 | defect | GAP | No `adopath`/`sysdir` external-target check. |
| C4-deprecated-syntax-signature | P1 | defect | GAP | No known-breaking-signature list. |
| C5-deprecated-r-packages | P1 | defect | GAP | No removed-CRAN-package list. |
| C6-old-stata-merge-syntax | P1 | defect | GAP | No pre-Stata-11 `merge` syntax check. |
| C7-nonreproducible-parallel-rng | P1 | defect | **GAP — see Action Point 2/3** | No `%dopar%`/doRNG check. |
| C8-unseeded-stochastic | P1 | defect | **GAP — see Action Point 2/3** | No seed-before-stochastic-op check in any language. |
| C12-no-wallclock-in-output | P1 | defect | **GAP — see Action Point 3** | No clock/tempdir-in-output check — directly relevant to `check_exhibit_fidelity()`, since this is exactly the kind of thing that makes fidelity checks fail spuriously (a timestamp differs, not the actual numbers). |
| C3-declare-stata-version | P1 | normalization | PARTIAL | `capture.py` records the environment (lockfiles, `creturn list`) to *replicate*, rather than inserting `version NN` to *pin the script*. Different strategy, same goal. |
| C1-pin-deps | P3 | normalization | **COVERED, stronger** | `capture.py` infers exact installed versions from lockfiles/`pip freeze`/`Pkg.status()` and pins the Docker environment to them — stronger than "add a version pin to the install line," since it captures what was actually used rather than relying on the author to remember. |

### normalization (5 rules)

| rule_id | priority | kind | status | note |
|---|---|---|---|---|
| N1-no-delimit-semicolon | P2 | normalization | GAP | No `#delimit ;` check. |
| N2-explicit-table-commands | P2 | normalization | GAP | No loop-unrolling for estimation-in-loop. |
| N3-compact-r-table-calls | P2 | normalization | GAP | No table-call reflow check. |
| N4-named-estimation-calls | P3 | normalization | GAP | No estimation-wrapped-in-function check. |
| N5-unsafe-filename | P3 | normalization | GAP | No unsafe-filename check (spaces/shell metacharacters). |

**Totals: 55 rules — 5 COVERED (2 stronger than ReproAI's version), 7 PARTIAL, 2 different-by-design, 41 GAP.**

The 41 gaps cluster almost entirely in code-content linting (Stata/R/Python syntax and
semantics) — a category DeadReckoning doesn't attempt today by design, since its static layer
(`scan.py`/`graph.py`) extracts paths, packages, and exhibit↔script links, not language
semantics. Most of those gaps crash loudly and get caught downstream by RUN failing + LLM-FIX.
The ones that matter are the P0/P1s that **don't crash** — they silently produce a different
number, which is the one failure class an execution-first, run-it-and-see pipeline is
structurally blind to unless something specifically checks for it.

## What we're already doing better, not just differently

- **B4 (no abs paths)**: ReproAI flags; DeadReckoning (`scan.py` → `resolve.py`) flags *and*
  auto-rewrites.
- **C1 (pin deps)**: ReproAI tells the author to add a version pin; `capture.py` captures the
  *actual* installed versions from lockfiles and pins the Docker build to them — no reliance on
  the author remembering correctly.
- **A1/A11 (master script, run order)**: `orchestrator.py` auto-detects with an intake-question
  fallback; `graph.py`'s topological sort derives run order from the dependency graph itself
  rather than requiring the author to document it.
- **A13 (orphan scripts)**: same BFS-reachability idea as ReproAI, non-blocking report
  (`CLEANUP.md`), already shipped.

## Action points

### 1. A14 — missing-input check (pre-run, static)

**Verified as a genuine gap by reading the code directly**, not inferred. `graph.py`'s
`_extract_data_refs()` (line 763) already builds a `DataFile` per data-read call and already sets
`exists_on_disk` (line 789: `(project_root / p).exists()`). The graph-build loop (lines
1081–1100) already sets `produced_by` by walking write calls to find an upstream producer script,
if any. **Nothing consumes this signal.** Checked every place it could be used:

- `models.py`'s `GapKind` enum has no "missing input" kind — only exhibit-side kinds
  (`exhibit_missing_from_disk`, `script_writes_wrong_path`, etc.).
- `ask.py`'s "external data not found" question only reads `scan.external_paths`, which only
  comes from `scan.py`'s `_extract_external_paths()` — and that regex (`_ABS_PATH_RE`) only
  matches **absolute** paths. A relative in-package read like `read.csv("data/raw/foo.csv")`
  never reaches it.
- `runner.py`'s `_upstream_data_files()` walks `produced_by` chains, but only post-hoc, for
  `check_exhibit_fidelity()`'s mismatch localization — never pre-RUN as a gate.

**Fix, scoped small**: add `GapKind.input_missing_from_disk`. At the end of `build_graph()`, loop
over `data_files` where `not exists_on_disk and produced_by is None and not is_external` and
append a `Gap`. Add one new branch to `ask.py`'s existing gap-walk reusing the same
question-generation machinery as `exhibit_missing_from_disk`. No new infrastructure — the data's
already computed.

### 2/3. Unseeded-stochastic + wall-clock-in-output check, redesigned for all 8 languages

Original fork proposal was Stata/R-only — rejected. DeadReckoning's stated scope is 8 languages:
Stata, Python, R, MATLAB, Julia, Fortran, C, C++. Correction made and verified against the actual
dispatch table in `runner.py:run_natively` (line 35): **today DeadReckoning only executes R,
Python, Stata, Julia, MATLAB, and `.sh` orchestrators — there is no Fortran/C/C++ runner and no
scanner for them either.** Fortran/C/C++ still matter even without a runner of their own, because
they routinely show up as *compiled helper code* called from an R/Python/Stata master script
(Rcpp, `ctypes`, MEX files) — so scanning them for seed hygiene is worth doing independent of
whether they can be a master script.

Per-language seed-setter vs. stochastic-call pairs to detect:

| Language | Seed call(s) | Stochastic call(s) needing a prior seed |
|---|---|---|
| Stata (`.do`) | `set seed` | `runiform()`, `rnormal()`, `rbeta()`, `rpoisson()`, `bootstrap`, `bsample`, `permute`, `simulate`, `mi impute`, `sample N` |
| R (`.R`) | `set.seed(` | `sample(`, `rnorm(`, `runif(`, `rbinom(`, `rpois(`, `rexp(`, `rgamma(`, `boot(`, `mvrnorm(` |
| Python (`.py`) | `random.seed(`, `np.random.seed(`, `np.random.default_rng(` *with an arg*, `torch.manual_seed(` | `random.random/choice/shuffle(`, `np.random.rand/randn/normal/choice/permutation(`, `torch.randn(` |
| Julia (`.jl`) | `Random.seed!(` | `rand(`, `randn(`, `randexp(`, `sample(` (StatsBase), `shuffle(` |
| MATLAB (`.m`) | `rng(` | `rand(`, `randn(`, `randi(`, `randperm(`, `datasample(` |
| Fortran (`.f90`/`.f`/`.f95`) | `call random_seed(put=` | `call random_number(` |
| C (`.c`) | `srand(` | `rand(` |
| C++ (`.cpp`/`.cc`/`.cxx`/`.hpp`) | `std::mt19937`/`std::default_random_engine` constructed with a literal/variable seed | same engine constructed from `std::random_device{}()` (flag — deliberately non-reproducible), or a `dist(gen)` draw where `gen` was never seeded |

**C7 (parallel RNG)** folds into the same check: Python/R/Julia parallel constructs
(`%dopar%`/`doParallel`, `multiprocessing`, Julia `Threads`/`Distributed`) need per-worker
reproducible seeding (e.g. `doRNG` in R), not just a single top-level seed call — same
detection shape, additional pattern for "parallel construct present + ordinary seed call but no
RNG-stream-safe variant."

**Mechanism** (reuses existing architecture, no new infra):
1. Extend `scan.py`'s per-language internals (`_scan_r_internals`, `_scan_python_internals`,
   etc.) with a seed-regex / stochastic-regex pair per suffix; add
   `_scan_fortran_internals`/`_scan_c_internals`/`_scan_cpp_internals` in the same shape.
2. For a script with a stochastic-call match, check for a seed-call match in the same script OR
   an upstream script in `graph.script_order` (reuse the topological order `graph.py` already
   builds — no new cross-script tracking needed).
3. Non-blocking: write to a new `RNG-WARNINGS.md`, same posture as `CLEANUP.md` (flag, don't
   block — false positives are likely: a helper script relying on the master having already
   seeded, or library code with internal seeding).

**C12 (wall-clock/PID/tempdir in output)** is a related, separate regex pass over write-call
argument chains (`Sys.time()`, `os.getpid()`, `tempdir()`, `date`, `c(date())`, etc., per
language). Wire its finding into `check_exhibit_fidelity()`'s mismatch report directly ("this
exhibit's script writes a timestamp/PID — a byte mismatch here may be expected, not drift")
rather than a disconnected check — it makes an existing feature more reliable instead of just
adding a new standalone one.

### 4. Compiled-language build step — not in ReproAI's rule set at all, but a real gap for us

Not one of the 55 rules (ReproAI only covers Stata/R/Python, all interpreted), but it falls
straight out of adding Fortran/C/C++ to our own scope in Action Point 2: a compiled-language
script isn't runnable by executing the source file the way `_run_r`/`_run_python` do — it has to
be **built** first, and nothing in the pipeline looks for a build step today. `_find_all_scripts`
and `run_natively`'s dispatch table don't look for a Makefile/CMakeLists.txt/build script at all.

**This has to be a blocking question, not a warning.** Reasoning: an author working in
Fortran/C/C++ may have no build script whatsoever — they may just be re-running a compile command
from shell history (fish, like most modern shells, surfaces exactly this: re-run a prior command
without ever having saved it to a file). There is no static artifact to infer the compile command
from in that case, so DeadReckoning cannot guess it, and silently skipping the compile step means
the "native run" step will simply fail to find a binary to execute. This must surface immediately,
before the pipeline tries to run anything, not get buried in a non-blocking report the author
might not read.

**Detection logic:**
1. If `scan.py` finds any `.f90`/`.f`/`.f95`/`.c`/`.cpp`/`.cc`/`.cxx` source files anywhere in the
   project (Action Point 2's new per-language scanners already walk these), check for a build
   artifact: `Makefile`, `makefile`, `CMakeLists.txt`, `configure`, `build.sh`, `compile.sh`, or
   any `.sh`/`.bat` file whose content matches a compiler invocation (`gcc`, `g++`, `gfortran`,
   `clang`, `cmake`, `make`).
2. **Found** → no question needed; the pipeline already knows how to invoke it (and `run_natively`
   gets a new case to shell out to the discovered build script before running the produced
   binary — a `runner.py` addition, not just a detection one).
3. **Not found** → this is a red flag, not a warning. Add a new blocking `AuthorQuestion`
   (`gap_kind="compiled_language_no_build_script"`) in `ask.py`'s existing blocking-question
   machinery (`_BLOCKING_GAP_KINDS` / `all_blocking_answered`, same mechanism as
   `exhibit_missing_from_disk`): ask the author for the **exact compile command** they run
   (compiler, flags, output binary name) — not just "do you have a Makefile," since the premise
   of asking is exactly that one may not exist. The pipeline halts (same as any other unanswered
   blocking question) until this is answered, then uses the answer to drive the compile step the
   same way a discovered build script would.

**Status: implemented and verified end-to-end, including inside a real Docker container.**
`compile_check.py` (detection) + `GapKind.compiled_language_no_build_script` + `ask.py` blocking
question + `EnvSpec.compile_command` + `runner.py`'s `_run_compiled()`. Tests: `test_compile_check.py`
(11 cases — detection across all languages, Makefile at root/in `code/`, named build scripts,
content-sniffed shell scripts, unrelated shell scripts not counted), `test_runner_compiled.py`
(5 cases, **real compiler invocations** — `gfortran`, `gcc`, `g++` all actually run, not mocked),
`test_compiled_pipeline.py` (1 case — the full round trip: a Fortran-only fixture with no build
script blocks at ASK with `QUESTIONS.md`, the answer is filled in exactly the way the CLI's own
printed instructions describe, and a second `run_pipeline()` call against the answered working
copy proceeds past ASK and actually compiles+runs with real `gfortran`, producing the correct
`result.txt`). Also hand-verified outside the test suite: built and ran a real Docker image
(`debian:bookworm-slim` + `apt-get install gfortran`, compiling the same `simulate.f90` during
`docker build`) — the container prints the correct `55.00`, confirming the same compile-then-run
path works inside a container, not just natively. Full suite (911 tests incl. the one
`@pytest.mark.docker` test, daemon running): all passing, 28 skipped (environment-gated), 0 failed.

### 5. Mixed-language compilation risk (Rcpp, Cython, MEX) — also not in ReproAI's rule set

A different failure mode from Action Point 4, surfaced while implementing it: Action Point 4
covers a *standalone* Fortran/C/C++ script with literally no build step — the native run fails
outright, so it has to block. Rcpp (R calling C++ via `sourceCpp()`/`library(Rcpp)`), Cython
(Python `.pyx` modules), and MEX (MATLAB calling compiled C/C++ via `mex()`) are a quieter
variant: the embedding language's own tooling usually auto-compiles the embedded code with
system-default flags, so nothing fails outright on a native run. The actual risk is a custom flag
the author's own machine supplies (an OpenMP flag, a header-only library include path, a specific
C++ standard) that lives nowhere in the package — not in `src/Makevars`, not in a `setup.py`
`cythonize()` call, not in a `mex()` call with explicit flags. A replicator's run can then compile
successfully with *different* flags (silently different numerics — e.g. no OpenMP changes a
parallel reduction's order) or fail outright on a stricter default toolchain. Non-blocking, unlike
Action Point 4: nothing here stops a native run from attempting to proceed.

**Detection** (`mixed_language_check.py`): Rcpp usage (`library(Rcpp)`/`sourceCpp()`/`// [[Rcpp::`
attributes/`#include <Rcpp.h>`, or `DESCRIPTION`'s `LinkingTo: Rcpp`) flagged when no
`src/Makevars`/`Makevars.win` exists anywhere in the project. Cython usage (`.pyx` files,
`pyximport`, `cythonize(`) flagged when no `setup.py` calling `cythonize()` (or a `pyproject.toml`
Cython build config) is found. MEX usage (a `mexFunction` gateway in C/C++ source) flagged when no
script anywhere calls MATLAB's `mex()` build command. Non-blocking — writes
`MIXED-LANGUAGE-WARNINGS.md`, same posture as `CLEANUP.md`/`RNG-WARNINGS.md`. Wired into
`orchestrator.py` right after RNG-CHECK.

**Status: implemented.** 11 tests in `test_mixed_language_check.py`, including the exact scenario
asked for: Rcpp code present (via `sourceCpp()`), no `src/Makevars`, no `src/Makevars.win`, no
documented flags anywhere — flagged, with the finding naming Makevars specifically. Also covers:
Rcpp declared only via `DESCRIPTION`'s `LinkingTo:` (not `sourceCpp()`), Rcpp with a Makevars
present (not flagged), Cython via `.pyx`/`pyximport` with and without a `cythonize()` build step,
MEX with and without a `mex()` build call, multiple findings firing independently in the same
project, and a clean project producing none.

## Priority order

1. **A14** (Action Point 1) — smallest, fully scoped, data already computed.
2. **C8/C7 unseeded-stochastic, all 8 languages** (Action Point 2) — highest-value: this is the
   "run succeeds, VALIDATE sees the exhibit landed, number is wrong" class, which is the single
   biggest blind spot given `check_exhibit_fidelity()` already exists to catch drift but not its
   root cause.
3. **C12 wall-clock-in-output** (Action Point 3) — ties into and strengthens
   `check_exhibit_fidelity()` directly.
4. **Compiled-language build-step detection** (Action Point 4) — gates on Action Point 2's new
   Fortran/C/C++ scanners existing first, but the blocking-question mechanism itself is cheap to
   add once they're in place.

**Status: Action Point 1 (A14) implemented** — `GapKind.input_missing_from_disk` in `models.py`,
detection in `graph.py` (`build_graph` §7d, with a `_RUNTIME_MACRO_RE` guard added after testing
against the real `mitman_2026` fixture turned up 9 false positives, all unresolved Stata
`${macro}` paths rather than genuinely missing files — an A18 case, not A14), question-asking in
`ask.py` (reuses the existing blocking-question machinery). Tests in `test_graph.py` and
`test_ask.py`. Verified: full suite passes, real-world fixture's gap count unchanged (46) once
the macro false positives were filtered.

**Status: Action Point 2 (C7/C8, all 8 languages) implemented** — new `rng_check.py`: per-suffix
seed/stochastic regex pairs for R, Python, Stata, Julia, MATLAB, Fortran, C, C++; walks
`graph.script_order` so a seed call in an earlier script (e.g. one `set.seed()` in a master
script) covers every stochastic call reached afterward, not just the current script in
isolation; falls back to a stable sort for any script the graph didn't connect (covers
Fortran/C/C++ helper files, which `graph.py`'s own script discovery doesn't walk, since they're
never a master script). C++ specifically: an engine seeded from `std::random_device` does *not*
count as seeded — that's deliberately non-reproducible, not hygiene. Wired into `orchestrator.py`
right after CLEAN, writing `RNG-WARNINGS.md` non-blocking, same posture as `CLEANUP.md`. Tests in
`test_rng_check.py` (20 cases, two per language: unseeded-flagged / seeded-not-flagged, plus the
cross-script-upstream-seed and C++ random_device cases). Verified against the real `mitman_2026`
fixture: 2 genuine findings, both unseeded `bootstrap` calls in `Endog_Bartik.do` — exactly the
silent-wrong-number class this check targets, not a false positive.

**Status: Action Point 3 (C12, wall-clock/PID/tempdir-in-output) implemented** — new
`nondeterminism.py`: per-suffix regex (same 8 languages) for calls that write the current time, a
PID, or a tempdir path. Wired into `runner.py`'s `check_exhibit_fidelity()` as a new
`FidelityResult.nondeterminism_note` field, populated only on mismatch by checking the exhibit's
producing script — exactly the design in this doc: it makes an existing feature (fidelity
checking) more reliable, not a disconnected new warning. Tests: `test_nondeterminism.py` (12
cases, one per language plus an unsupported-extension and a dedup case) and two new cases in
`test_fidelity.py` (note absent for an ordinary mismatch, note present and naming the right
script/call when the producing script calls `now()`). Checked against the real `mitman_2026`
fixture: no matches, as expected — it's a clean fixture with no wall-clock/PID calls, so this
doesn't fire on it; the match path itself is exercised by the dedicated unit/integration tests.

## Out of scope, and why

The four action points above close 4 of the 55 rules (A14, C7, C8, C12), plus one novel check
neither list has (compiled-language build-step detection). That leaves roughly 37 of ReproAI's
rules as GAP in the coverage map with no action point against them. That's a deliberate stopping
point, not an oversight — worth saying explicitly rather than leaving silent.

**Why these four (plus the build-step check) and not the rest**: they're the ones that corrupt a
result *silently* (C7/C8/C12 — the run succeeds, VALIDATE sees the exhibit landed, the number is
wrong) or were close to free given data the pipeline already computes (A14). The compiled-language
check is the same shape: a correctness gate that execution would otherwise walk straight past (a
missing binary isn't a "different number," it's "nothing to run" — but same principle: don't let
a silent gap reach the author as a confusing downstream failure).

**D10 (package size cap) was considered and dropped.** `clean.py` already walks file sizes, so the
check itself would be near-free — but the failure mode it catches isn't silent. An author sitting
on a 1GB+ replication package already knows it's large; this isn't a case of the pipeline knowing
something the author doesn't, unlike C7/C8/C12 or A14. Not worth the surface area for a check
that mostly tells people something they already know.

**The remaining ~37 GAPs split into two buckets, neither of which gets an action point:**

1. **Code-content syntax/style linting** — the large majority: B1–B11, N1–N5, most of
   A2/A4/A7/A8/A9/A15/A17, C4–C6/C9/C11. These are genuine Stata/R/Python static-analysis rules
   (deprecated syntax, variable abbreviations, delimiter style, embedded-language detection,
   loop-unrolling, etc.). Closing them properly means building a real per-language parser/linter
   — exactly the kind of LLM-plugin-fronted rule engine ReproAI is, and exactly what you don't
   want DeadReckoning to become (90% static Python that runs the code, not a syntax linter).
   Most of these also crash loudly and get caught by RUN → LLM-FIX anyway, which is the actual
   point of the execution-first design: they cost a wasted run cycle, not a wrong answer, so the
   existing pipeline already has a (coarser, slower, but correct) answer for them.
2. **Documentation/metadata checks** — D5 (duplicate README), D6 (README references paths that
   don't exist), D7 (codebook/variable coverage), D9 (LLM-data-provenance recording), A12/A2
   (table↔code comment conventions). Cheap to build, but low-value for a tool whose job is "make
   the code run and produce the right numbers," not "grade the prose." `deliver.py` already
   generates a correct README from the graph, which covers the case that matters most (no README
   at all) without auditing an author-supplied one line by line.

If either bucket turns out to matter in practice — e.g. a real submission bounces specifically
because of a duplicate README or a deprecated-syntax crash that LLM-FIX couldn't resolve — revisit
this list then, rather than speculatively building against rules that haven't caused a problem
yet.
