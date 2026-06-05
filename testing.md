# DeadReckoning — Testing Strategy

## Approach

Good testing requires synthetic "messy" fixtures with known ground truth — the broken state is constructed deliberately, so the correct "fixed" state is known in advance and can be asserted automatically.

Two-tier structure:

- **Unit tests** on individual pipeline steps (GRAPH, CAPTURE, RESOLVE, path-rewriting): fast, no language runtimes required, run on every commit.
- **End-to-end integration tests** on full fixtures: slow, require real runtimes, run on a schedule or before release.

The most important thing to build first is the **fixture generator** — a script that takes a clean project and injects specific faults in a parameterized way. Without it, adding new test cases is manual and expensive.

---

## Fixture library

Each fixture needs three things:

1. A broken starting state (what the author hands the agent)
2. A ground-truth manifest (what the fully repaired state looks like)
3. A fault list (the specific problems the agent must detect and fix)

| Fixture | Languages | What's broken |
|---------|-----------|--------------|
| `r_no_lockfile` | R | No `renv.lock`, absolute Dropbox paths, one figure with no source script, one table typed directly into `.tex` |
| `stata_mixed` | R + Stata | Missing `ssc` packages, wrong Stata version in code, output written to `~/Desktop/` instead of project |
| `python_external_data` | Python | conda env, data referenced via `$DATA_DIR` env var not set in package |
| `restricted_data` | R | Filename `census_microdata_restricted.dta` present; agent must detect and enter restricted mode without being told |
| `multi_language_full` | R + Julia + Stata | No lockfiles anywhere, circular script dependency, two exhibits unreachable from any script |
| `already_clean` | R | `renv.lock` present, relative paths throughout, working master script — agent must confirm and not break anything |

---

## Fixture generator

A script that takes a clean "gold" project and injects faults by composing fault modules:

```
generate_fixture(gold_project, faults=[
    delete_lockfile(),
    absolutize_paths(root="/Users/testuser/Dropbox/project"),
    remove_ggsave_path("fig3b.R"),           # script produces figure but writes to working dir
    inline_table_in_tex("tab2.tex"),          # replaces \input{tables/tab2.tex} with hardcoded tabular
    add_unreferenced_script("old_cleaning_v3.R"),
])
```

Each fault module is independently testable and can be composed arbitrarily to create new scenarios.

---

## Ground-truth manifest format

For each fixture, a structured manifest listing what the agent must find and do:

```yaml
# fixtures/r_no_lockfile/manifest.yaml

gaps:
  - type: figure_no_source_script
    exhibit: figures/fig3b.pdf
    expected_action: flag_and_ask

  - type: inline_table
    location: paper.tex
    lines: [412, 441]
    expected_action: flag_and_ask

path_rewrites:
  - from: /Users/testuser/Dropbox/project/data/lfs_2019.dta
    to: data/raw/lfs_2019.dta
    scripts_affected: [code/clean.R, code/analysis.R]

version_pins:
  - language: R
    method: posit_ppm_snapshot
    date_source: rhistory_timestamp

files_removed:
  - path: code/old_cleaning_v3.R
    reason: unreachable_from_dependency_graph
```

The test runner diffs agent output against the manifest. Every gap must be detected, every path rewrite must match, every version pin must use the correct method.

---

## Unit tests: per-step

### GRAPH step (static analysis — highest priority)

GRAPH is pure static analysis and the most testable step in isolation. It drives everything downstream.

| Test | Input | Assert |
|------|-------|--------|
| Extract exhibit list | `.tex` with known `\includegraphics` and `\input` calls | Exhibit list matches ground truth exactly |
| Map exhibit to script | Scripts with known `ggsave`/`graph export`/`savefig` calls | Correct script-to-exhibit mapping |
| Flag exhibit with no source | Exhibit on disk, no script writes it | Flagged as gap |
| Flag hand-typed table | `\begin{tabular}` in `.tex` body, no `\input{}` | Flagged as inline table |
| Flag hand-typed statistics | `0.047***` pattern in `.tex` body outside `\input{}` | Flagged as untraced statistic |
| Flag orphaned script | Script not reachable from any exhibit in dependency graph | Flagged as candidate for removal |
| Handle chains correctly | `prep.R → panel_clean.dta → analysis.R → fig1.pdf` | All links in chain marked as needed |

### CAPTURE / RESOLVE

| Test | Input | Assert |
|------|-------|--------|
| R with `renv.lock` | Known `renv.lock` file | Versions read directly, no date inference needed |
| R no lockfile + date | `library()` calls + known file timestamp | Correct Posit PPM snapshot URL generated |
| Python conda | `environment.yml` present | Versions read from file |
| Python no env file | `import` scan + known date | Package list extracted; conda/pip distinguished |
| Stata version | `creturn` output + `ado dir` | Correct version and ado-file list |
| Path absolutize | Absolute path `C:\Users\name\Dropbox\data\file.dta` | Rewritten to `data/raw/file.dta`; change recorded in report |
| Path env var | `$DATA_DIR/file.csv` | Flagged for resolution; not silently rewritten |

### Confidentiality detection

| Test | Input | Assert |
|------|-------|--------|
| Known restricted filename | `hmda_2019_restricted.csv` | Restricted mode triggered before any file is read |
| Census pattern | `acs_pums_2018.dta` | Restricted mode triggered |
| Clean filename | `survey_responses.csv` | Not triggered |
| DUA document present | `data_use_agreement.pdf` anywhere in project | Restricted mode triggered |
| Code pattern: large seeded sample | `set.seed(42); N <- 500000` with no public URL | Warning emitted; author asked to confirm |

### Working copy safety

| Test | Assert |
|------|--------|
| Original project after any agent run | Byte-for-byte identical to pre-run state |
| Working copy path reported | Shown to author before copy starts |
| Credential exclusion | `.env`, `id_rsa`, `credentials.json` not copied; exclusions listed in report |

---

## End-to-end integration tests

Three fixtures that run code all the way through to native validation. Slow; run on a schedule, not on every commit.

### `r_no_lockfile` (minimum viable integration test)
- R only, no proprietary software, short runtime
- Success: delete all outputs → run master script → every exhibit in `paper.tex` exists at correct path
- Also assert: `AGENT_REPORT.md` records the path rewrites and version pins made

### `python_external_data`
- Tests data-path resolution and conda environment reconstruction
- Success: data correctly found via resolved path → all outputs regenerated natively

### `multi_language_full` (stress test)
- R + Julia + Stata; run only on full CI schedule
- Validates that multi-language version pinning and the fix loop converge
- Also tests `--platform linux/amd64` selection for Stata

**Success assertion for all end-to-end tests:**

Delete all outputs from the fixture's working copy. Run the master script natively. Check that every exhibit listed in `paper.tex` exists on disk at the path specified by the dependency graph. Binary pass/fail — no partial credit.

---

## What to build first

1. **Fixture generator** — parameterized fault injection. Unlocks all other tests.
2. **GRAPH step harness** — run GRAPH in isolation against a fixture, inspect the dependency graph as structured data. Most critical step to test; most leverage per hour spent.
3. **Ground-truth manifest schema + diff runner** — the assertion layer that makes test results interpretable.
4. **`r_no_lockfile` end-to-end** — cheapest full-pipeline test; validates that unit-tested steps compose correctly.

Confidentiality detection tests can be written immediately with no fixtures — just filenames and directory trees, no real code needed.
