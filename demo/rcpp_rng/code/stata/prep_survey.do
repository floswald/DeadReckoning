* Picks one "anchor" respondent per region from the raw survey and writes
* their income as the per-region baseline the downstream R step perturbs
* with income shocks.
*
* Survey respondents are NOT uniquely ordered within a region in the raw
* file (three respondents share each region code) -- `sort region` alone
* does not uniquely determine which respondent ends up first within a
* region. Stata's default sort breaks such ties with an internal random
* tiebreaker that is not guaranteed stable across runs, Stata editions,
* or machines (see `help sortseed`) -- unlike R's/Python's/Julia's sort,
* which is specified to keep tied rows in their input order.
clear all
set more off

import delimited "data/raw/survey_raw.csv", clear

sort region
by region: keep if _n==1

keep region income
rename income anchor_income

save "data/survey_prepped.dta", replace
