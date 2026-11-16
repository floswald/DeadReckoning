# Plan: fan-out fidelity demo — doc/slides integration

Status: **code done**, docs/slides integration outstanding.

The build itself (fixture, trimmed `generatethetas.do`,
`group_fidelity_mismatches`, `demo/run_demo_landuse_fanout.py`, tests)
is complete, committed (`93546c1`), and verified end-to-end against real
Stata: reruns the current fixture, reproduces the intended 3/6 split
(`figureA3.pdf`/`figure7.pdf`/`figureA4.pdf` match; `figure1.pdf`/
`figureA2a.pdf`/`figureA2b.pdf` mismatch), and converges all three
mismatches on the single correct suspect (`data/raw/FRA_base.dta`).
`demo/landuse_fanout/README.md` documents exactly what shipped — that
file does not need to change.

What's left is that this demo is currently **invisible** outside its own
README: nothing else in the repo's docs or slides knows it exists.

## 1. `demo/README.md` — add it as segment 5

- Line 3 ("Four segments, ~9 minutes total.") and line 7's framing
  sentence ("the first three... the fourth is the harder case") both
  need to account for a fifth segment.
- Add a `## 5. Fan-out fidelity — demo/run_demo_landuse_fanout.py`
  section after the existing "## 4. Synthetic package" section, same
  style as sections 1–4: what's rigged, the command to run it
  (`--terse` flag), what it shows, any prerequisites (Stata, no
  `ANTHROPIC_API_KEY` needed — no LLM fix-loop act here either, same as
  demo 4).
- Update the "## Notes" footer at the bottom: the "None of the four
  scripts touch..." and "All four scripts write `DATA-EXHIBIT-MAP.md`..."
  lines both currently omit `demo/landuse_fanout/` and the fifth script
  — fix both to "five."

## 2. Root `README.md` — update the demo pointer

- Line 88: "`demo/` has four runnable, narrated walkthroughs... The
  first three show every pipeline step live... the fourth shows a run
  that passes DETECT through VALIDATE cleanly and is still wrong, and
  how FIDELITY catches it." Needs a clause for the fifth (fan-out:
  FIDELITY catching drift across several exhibits sharing one input,
  not just one).
- Line 362 (§9 FIDELITY description): currently says "See
  `demo/run_demo_coauthor_drift.py` for the full walkthrough" —
  singular. Either add the fanout driver alongside it, or leave as the
  single-exhibit intro case and let the fan-out detail live only in
  `demo/README.md` (lower priority than §1 above; use judgment, not a
  hard requirement).

## 3. `slides/` — check for a demo enumeration

- `slides/record-casts.sh` and `slides/dead-reckoning.qmd` may each
  enumerate demo drivers (for recording asciinema casts / walking
  through in the deck). Grep both for `fanout` specifically — a prior
  grep for `landuse` hit both files, but that could be `run_demo_landuse.py`
  (segment 3), not the fanout demo. If either file lists drivers and
  omits `run_demo_landuse_fanout.py`, add it in the same style as the
  other four.

## 4. Driver narration — explain the orphan count

- Running `python3 demo/run_demo_landuse_fanout.py --terse` today prints
  "13 orphan(s) — CLEANUP.md written" with no explanation. Confirmed
  benign (not a bug): CLEAN's dependency walk doesn't currently link the
  6 generated `output/data/plots/*.pdf`, the 6 shipped `reference/*.pdf`,
  and the 1 intermediate `data/processed/FRA_model.dta` back to the
  exhibits paper.tex declares, so all 13 land in `CLEANUP.md` as
  "orphans" even though the 6 outputs are in fact the exhibits VALIDATE
  just confirmed present. Doesn't affect FIDELITY's correctness (checked
  — VALIDATE and FIDELITY both use the correct exhibit set; only CLEAN's
  orphan list is over-inclusive here), but a presenter will get asked
  about an unexplained "13 orphans" line live on stage.
- Fix: one line of narration in `demo/run_demo_landuse_fanout.py` right
  after the orphan count is printed, explaining it's expected/benign for
  this fixture (reference copies + regenerated outputs + one intermediate
  file, none of which CLEAN currently cross-references against declared
  exhibits) — not a new pipeline bug to chase down. Do not change
  `CLEAN`/`runner.py` orphan-detection logic itself; that's a pre-existing
  gap unrelated to this demo's purpose and out of scope here.

## Not in scope here

- No changes to `check_exhibit_fidelity`, `group_fidelity_mismatches`,
  the fixture itself, or its tests — all already verified correct.
- Not fixing CLEAN's orphan-matching gap generally (item 4 is narration
  only, not a logic fix) — that's a separate, pre-existing limitation.
