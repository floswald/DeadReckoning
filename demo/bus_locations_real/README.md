# Replication package (demo slice): BusLocations

One-table slice of a real JPE-style replication package, extracted for a
DeadReckoning presentation demo.

## Data
- `data/tenders_edited.csv` — TfL bus route tender/auction data, 2003-2019

## Code
- `code/tables.R` — produces `tables/winning-groups.tex`

## To reproduce
Run `code/tables.R` from the project root. Requires R with data.table,
kableExtra, readr.
