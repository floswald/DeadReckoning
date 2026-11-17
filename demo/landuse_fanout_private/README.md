# A synthetic coauthor's private folder — not part of the real package

Unlike the rest of `demo/landuse_fanout/` (real Stata scripts, real data,
real exhibits from the published LandUse-REStud slice), this directory and
the downstream-consumer stage it feeds are **fabricated for this demo**.
No such coauthor, script, or weighting scheme exists in the actual
published package. It's added here to give Demo 5 the same chain-drift
shape as Demo 4 (`demo/coauthor_drift/`) — a shared Dropbox folder, no
version control, a downstream script that never gets rerun — but running
live, with real Stata output feeding it, alongside the real fan-out drift.

This directory represents that coauthor's own machine: never committed to
the shared project, never seen by the paper's actual author, never touched
by DeadReckoning's SCAN/GRAPH. It only exists so the two
`decade_weights_v*.csv` snapshots shipped into
`demo/landuse_fanout/data/decade_weights.csv` have a believable origin.

`export_weights.do` is illustrative — the demo never executes it. Same
real mechanism as Demo 4: Stata's csv export precision is driven by each
variable's *display format*, not a stable default across versions. The
coauthor's original `.do` file used the older `outsheet` command, which
honored an unset/default display format and truncated `weight` to 2
decimals. After upgrading Stata, the coauthor modernized the script to
`export delimited` (the recommended replacement since Stata 13) — without
ever setting an explicit display format, so the full double-precision
weight leaked into the csv. Confirmed via Statalist:
- https://www.stata.com/statalist/archive/2011-01/msg00310.html
- https://www.stata.com/statalist/archive/2010-12/msg00903.html
- https://www.statalist.org/forums/forum/general-stata-discussion/general/1577196-export-excel-and-decimal-places

`decade_weights_v1.csv` is what the coauthor originally delivered (and
what `demo/landuse_fanout/data/decade_weights.csv` ships as, matching
`reference/TableTheta.tex`). `decade_weights_v2.csv` is what the demo
script swaps in to simulate the coauthor's later, silent re-export —
nobody edited a number, a tool default just changed. `combine_theta_summary.jl`
(the real script, in `demo/landuse_fanout/code/julia/`) is never rerun
between the swap and "acceptance" — it reads whichever weights file is
sitting on disk, just like `combine.jl` does in Demo 4.
