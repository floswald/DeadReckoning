# Plan: fan-out fidelity demo

Status: **done**, built and verified against real Stata (StataNow 19.5
MP). See `demo/landuse_fanout/README.md` for exactly what shipped and how
it was verified; summary of what changed from this sketch below.

## What changed from the sketch during build

- **The v1 lever in §3/§4 doesn't exist and can't be invented from thin
  air.** Checked before building anything: `ReplicationPackage`,
  `ReplicationPackage-submit`, and `landuse_real/FRA_base_v2.dta` are all
  byte-identical — there never was a captured "pre-revision" snapshot to
  run against. A v1 had to be constructed by perturbing the real,
  on-disk `FRA_base.dta` (never editing the Dropbox source).
- **The originally-proposed lever (restate the 1815 `Land_Agriculture`
  "35500 Lavoisier estimate" value) cannot work and was not used.** Traced
  both scripts: `figure1.do` drops all `year<1840` rows before plotting,
  and 1815 can't leak into any post-1840 interpolated point (1840 itself
  already has a real, non-interpolated value anchoring the interpolation
  window). `generatethetas.do`'s reference would always be rebuilt from
  the same real v2 data regardless. Net effect of that lever: a 0/6
  split — no exhibit would ever mismatch. Caught this by tracing the
  dependency chain before running any Stata, flagged it, and — on
  direction from the user ("that specific mechanism is too real/fragile
  to depend on for a demo, just perturb any other row(s)") — used a
  simpler, arbitrary lever instead: two synthetic-restatement edits to
  the **1950** observations of `Land_Agriculture` and `Share_Emp_Agr100`
  (chosen because both scripts have real, non-missing data at that year,
  and 1950 sits inside the post-1840 range both scripts' final plots
  actually draw from).
- Verified directly (not assumed) that this lever produces exactly the
  intended **3/6** split: `figure1.pdf`/`figureA2a.pdf`/`figureA2b.pdf`
  mismatch, `figureA3.pdf`/`figure7.pdf`/`figureA4.pdf` match — confirmed
  by running both scripts against both data vintages and `cmp`-ing all
  six outputs, then again end-to-end via the demo driver itself.
  `figureA3.pdf` is confirmed byte-identical across both vintages (it
  never reads `Land_Agriculture`), a useful independent sanity check that
  the rig isn't accidentally touching everything.
- Stata batch-mode PDF export reconfirmed deterministic on this exact
  fixture (re-running `generatethetas.do` unchanged reproduces a
  byte-identical `figure7.pdf`), matching the §2 assumption already
  checked for `landuse_real`.

Everything else below (original sketch) matches what was planned.

## Original sketch (for context)

Extends the real, published LandUse-REStud
slice already in `demo/landuse_real/` — no new rigging of a toy package,
no new kind of invented bug. The failure mode is a real, common one
(a shared upstream input gets revised, only some of its downstream
consumers get rerun before submission) shown at the scale this project
was always meant to answer for: several exhibits, one shared input, one
traceable cause — not one exhibit, not a renamed path.

## 1. Why this, not another renamed-path demo

Demos 1–3 share one failure shape: a path breaks, the run crashes, the
LLM fix loop reads the stderr and fixes it. Demo 4 (coauthor drift) is
the other shape: nothing crashes, one exhibit silently goes stale,
`check_exhibit_fidelity` catches a content mismatch no existence check
would ever see.

This demo is a third, genuinely different shape: **the same silent-drift
mechanism as demo 4, but fanned out across several exhibits sharing one
input, where only some of them are actually affected.** That's the part
no existing demo shows:

- `graph.script_order` / `DataFile.produced_by` / `_localize_divergence`
  already support walking from a diverged exhibit back to a shared
  upstream file — built for demo 4, used there for exactly one exhibit.
  Nothing yet demonstrates it doing that for *several* exhibits at once
  and converging on **the same suspect**, which is the whole point of
  having this machinery at scale instead of per-exhibit.
- It also exercises **discrimination**, not just detection: of N exhibits
  reading the same input, only some are stale. A tool that just flags
  "something touching FRA_base.dta changed" for every downstream exhibit
  indiscriminately is not demonstrating anything a `grep` couldn't. The
  demo only earns its claim if it correctly separates the 3 that are
  wrong from the 3 that aren't.

## 2. The real substrate (verified today, not assumed)

`demo/landuse_real/code/stata/figure1.do` already exists, already reads
one real input (`data/raw/FRA_base_v2.dta`, standing in for
`FRA_base.dta`), and already produces **three** real exhibits from it:
`figure1.pdf`, `figureA2a.pdf`, `figureA2b.pdf` (confirmed by reading the
file — see repo). The real package's `code/stata/generatethetas.do`
reads the *same* input (`use "../data/raw/FRA_base.dta"`, confirmed by
reading the actual source in the replication package) and produces three
more: `figureA3.pdf`, `figure7.pdf`, `figureA4.pdf`.

So the real package already gives us, for free: **one shared input, two
scripts, six real exhibits** — exactly the fan-out shape, with zero
invented code.

**Load-bearing assumption checked, not assumed:** `check_exhibit_fidelity`
compares exhibit bytes directly (sha256). Stata PDF export has a
reputation for embedding timestamps/IDs that would make two correct runs
hash-different and break this whole approach. Tested directly today:
ran `figure1.do` twice in a row against unchanged data/code (StataNow MP,
`graph export ..., as(pdf) replace`) and diffed the outputs —
**byte-identical, confirmed by `cmp`, not just by eye.** The hash-based
approach is safe to build on for this Stata version; worth a quick
recheck if the demo ever runs under a different Stata release.

## 3. The state machine

Mirrors demo 4's two-timestamp structure (v1 → revision → partial rerun
→ acceptance → later replication check), fanned out over two scripts:

1. **v1.** `FRA_base.dta` in its original state. Both `figure1.do` and
   `generatethetas.do` are run. All six exhibits are generated from v1.
   This set is what ships as the **reference** (the "published PDF"
   snapshot), same role as demo 4's reference Table 3.
2. **Revision, pre-acceptance.** The data provider restates part of the
   series (this is not invented color — the real README documents
   exactly this kind of restatement risk: *"Land Use in Agriculture
   prior to 1840... must be taken with extreme caution"*, and the
   dataset is stitched from several secondary sources across different
   vintages). Author updates `FRA_base.dta` → v2.
3. **Partial rerun.** A referee asks for Figure 7 to be re-cut. Author
   reruns `generatethetas.do` → `figureA3.pdf` / `figure7.pdf` /
   `figureA4.pdf` now correctly reflect v2. `figure1.do` is believed
   unaffected (reasonable but wrong) and is **not** rerun — `figure1.pdf`
   / `figureA2a.pdf` / `figureA2b.pdf` still reflect v1.
4. **Paper accepted** in this mixed state: 3 current, 3 stale, nobody
   notices because every exhibit exists, every script that was run
   exited 0.
5. **Replication check (now).** A replicator / data editor reruns the
   *current* pipeline from scratch against the *current* `FRA_base.dta`
   (v2 — it's the only copy on disk; nothing preserves v1). Both scripts
   run clean. All six exhibits regenerate. `check_exhibit_fidelity`
   against the shipped reference:
   - `figureA3.pdf`, `figure7.pdf`, `figureA4.pdf` → **match** (reference
     was already v2-based).
   - `figure1.pdf`, `figureA2a.pdf`, `figureA2b.pdf` → **mismatch**
     (reference is stale v1; replication-time run used v2).
6. **Localization.** For each of the 3 mismatches, walk the dependency
   graph back from the exhibit. All three converge on the same upstream
   file: `data/raw/FRA_base.dta`. The 3 non-mismatches are never flagged
   at all — the discrimination is the result, not an assumption fed in.

## 4. What ships in the fixture

New directory `demo/landuse_fanout/` (sibling to `landuse_real`, doesn't
touch it — `landuse_real` keeps its existing renamed-path demo):

```
demo/landuse_fanout/
├── code/stata/
│   ├── figure1.do              # unmodified from landuse_real
│   └── generatethetas.do       # new — real script, trimmed like figure1.do was
├── data/raw/
│   └── FRA_base.dta            # v2 — the only copy on disk (v1 never persisted,
│                                 matching reality: nobody keeps the pre-revision file)
├── reference/
│   ├── figure1.pdf              # v1-based — the "published" snapshot
│   ├── figureA2a.pdf            # v1-based
│   ├── figureA2b.pdf            # v1-based
│   ├── figureA3.pdf             # v2-based
│   ├── figure7.pdf              # v2-based
│   └── figureA4.pdf             # v2-based
├── paper.tex                    # references all six
└── README.md                    # same narration conventions as the other 3 demos
```

Generating the reference set: run both scripts once against a v1
`FRA_base.dta` snapshot (ephemeral, not shipped) to produce the three
v1-based references, then apply the revision and rerun only
`generatethetas.do` against v2 to produce the three v2-based references
— i.e. literally perform the rig once to build fixtures, then discard
the v1 data file. This matches how `demo/coauthor_drift_private/`
already keeps the "other author's machine" artifacts out of the shipped
package — same pattern, not a new one.

## 5. Engineering tasks

1. **Fixture construction** (above) — mechanical, no new pipeline code.
2. **Trim `generatethetas.do`** the same way `figure1.do` was trimmed for
   `landuse_real` (adapt `../data/raw/...` → `data/raw/...` project-root-
   relative paths, strip unrelated sections) — same adaptation already
   documented in `landuse_real/code/stata/README.md`.
3. **New: a small aggregation helper**, e.g.
   `group_fidelity_mismatches(results: list[FidelityResult]) -> dict[Path, list[Path]]`
   in `runner.py`, mapping each suspect path to the list of exhibits it's
   implicated in. `check_exhibit_fidelity` itself stays untouched
   (one-exhibit-in, one-result-out, as today) — this is purely a
   presentation-layer grouping over N results, the same shape the demo
   driver would otherwise reimplement ad hoc. Needs tests: multiple
   exhibits sharing one suspect group together; an exhibit with no
   suspects (chain dead-ends) doesn't appear; a clean exhibit (match)
   contributes nothing.
4. **New demo driver** `demo/run_demo_landuse_fanout.py`, same narration
   conventions as `run_demo_coauthor_drift.py` (`--terse` flag, docstring
   explaining the rig up front, no `--non-interactive` needed since there's
   no questionnaire act here). Calls `check_exhibit_fidelity` six times
   (once per exhibit), then the new aggregation helper, then prints:
   - 3 exhibits: fidelity OK.
   - 3 exhibits: fidelity MISMATCH, all three naming the same suspect
     (`data/raw/FRA_base.dta`), with the evidence tier (git commit, if
     tracked, else mtime-as-lead) exactly as demo 4 already reports it.
5. **Tests** for the new fixture: a `tests/test_demo_landuse_fanout.py`
   mirroring `tests/test_demo_landuse.py`'s structure — marked `local`
   (needs Stata), checks the 3/3 split comes out correct, checks the
   suspect-grouping names `FRA_base.dta` for all three mismatches.

Nothing here touches `orchestrator.py` / the default `run_pipeline` —
FIDELITY is still not wired into the default pipeline (per the existing,
honest status note from the FIDELITY work) and this demo doesn't change
that; it calls the function directly, exactly like demo 4 does.

## 6. Open questions / explicitly not solved here

- **PDF comparison robustness beyond this Stata version.** Today's check
  confirms byte-identical output for this specific Stata release. Not
  verified: whether this holds across Stata versions/platforms, or for
  R/Julia figure backends (ggplot2/Makie don't have the same embedded-
  metadata reputation as some PDF writers, but untested here). If a
  future demo needs cross-version determinism, the fallback is comparing
  something upstream of rendering (the data table feeding the plot)
  rather than the rendered file — not needed for this specific fixture
  since both reference and replication-time runs use the same Stata
  install.
- **Should the aggregation helper go further** — e.g. ranking suspects by
  confidence, or feeding into `AGENT_REPORT.md` once FIDELITY is wired
  into the default pipeline? Out of scope for this sketch; the grouping
  function is deliberately minimal (group by suspect, nothing more).
- **Two scripts sharing one input is the minimal fan-out.** The real
  package has more consumers of `FRA_base.dta`-derived data two steps
  removed (it feeds `FRA_model.dta`, which feeds the Julia structural
  model's ten figures) — a stretch extension once this version works,
  not part of this plan.
