# Author 2's private folder — not part of the package

This directory represents coauthor 2's own machine: never committed to the
shared project, never seen by author 1, never touched by DeadReckoning's
SCAN/GRAPH. It only exists here so the two `input_data_from_2.csv`
snapshots shipped in `demo/coauthor_drift/` have a believable origin.

`export.do` is illustrative — the demo never executes it. It shows the real
mechanism behind the drift: Stata's csv export precision is driven by each
variable's *display format*, not a stable default across versions. Author
2's original `.do` file used the older `outsheet` command, which honored
an unset/default display format and truncated to 2 decimals. After
upgrading Stata, author 2 modernized the script to `export delimited` (the
recommended replacement since Stata 13) — without ever setting an explicit
display format, so the full double-precision weight leaked into the csv.
Confirmed via Statalist:
- https://www.stata.com/statalist/archive/2011-01/msg00310.html
- https://www.stata.com/statalist/archive/2010-12/msg00903.html
- https://www.statalist.org/forums/forum/general-stata-discussion/general/1577196-export-excel-and-decimal-places

`input_data_from_2_v1.csv` is what author 2 originally delivered (and what
`demo/coauthor_drift/data/input_data_from_2.csv` ships as, matching the
published Table 3). `input_data_from_2_v2.csv` is what the demo script
swaps in to simulate author 2's later, silent re-export — nobody edited a
number, a tool default just changed.
