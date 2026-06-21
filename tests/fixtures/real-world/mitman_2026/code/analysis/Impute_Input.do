* ---------------------------------------------------------------------------
* Impute_Input.do  ->  builds the border-segment input for the search imputation
*                      (the upstream of tab:Imputed_Results / impute_border_search.m)
*
* *** VACANCY-GATED: uses proprietary vacancy data (synthetic stand-in available;
* see SYNTHETIC_VACANCY_PATH.md). ***
*
* Builds the border-segment input on the current base (${CurrentData}). The imputation runs at
* the BORDER-SEGMENT x STATE-SIDE level (paper sec:mobility: "aggregate all
* counties on both sides of a border segment"). For each segment side we sum,
* over the UNIQUE counties on that side, the unemployed, labor force, working-age
* population, and (proprietary) vacancies, then compute the observed job-finding
* rate phi (eq:JFR_Data) and the vacancy-filling rate q.
*
* Mapping to the model (eqs 2101-2135):
*   searchers  s = ũ + zeta*(p - n),  zeta = 5/27           (search base, eq:utilde)
*   ũ = unemp_count_laus,  n = labor_laus,  p = popestimate (total county pop, from
*       population_age.dta) -- NOT the age-restricted working_pop (see below)
*   delta = 3*separation   (Shimer/CPS mean MONTHLY rate from cpssep.dta -> quarterly
*                           flow = 3x)
*   phi^A = (ũ^A_t - ũ^A_{t+1} + delta*(n^A - ũ^A)) / ũ^A    (eq:JFR_Data)
*   q^A   = 1 - (v^A_{t+1} - v^{A,new}_{t+1}) / v^A_t        (vacancy-filling rate)
*   v = total_vacancies_county,  v^new = total_newvacancies_county
*
* Sample 2005Q2-2011Q4 (105 segments x 2 sides). Aggregation choices: (1) p = popestimate
* (total population, so outlabor = Pop - labor); (2) sum over ALL pair-appearances (no dedup
* to unique counties). phi uses uncapped U-dynamics (eq:JFR_Data).
*
* Output: Impute_Input.txt -- one row per (bordersegment, quarter_index) with the
* A/B side aggregates + phiA/phiB + qratio=qA/qB, consumed by the Matlab driver
* that calls impute_border_search.m. A = lower fipsstate side, B = higher.
*
* Inputs to copy into ${rawdata}/ (done): population_age.dta
* (popestimate, keyed fipsnumeric year), cpssep.dta (separation, keyed year quarter).
* total_newvacancies_county is re-derived from the proprietary HWOL monthly source
* new_vac_april2017.dta (under ${hwol}) -- referenced in place, not copied, as it
* is vacancy-gated; this is part of what the synthetic-vacancy path must replace.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/analysis/"
global CurrentData "UIMacro_RevisionData.dta"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"

set more off, perm
cap log close

* Vacancy source switch (same as the build's): config.do sets ${vacfile} to the public
* synthetic stand-in (synthetic-data/new_vac_synthetic.dta) by
* default, so the whole imputation runs on shippable synthetic vacancies (built by
* build/Make_Synthetic_Vacancies.do). The Data Editor reproduces the published numbers by
* pointing ${vacfile} at the licensed HWOL file; the fallback below only fires if cleared.
global hwol "${synthetic}/"
if "${vacfile}"=="" global vacfile "${hwol}new_vac_april2017.dta"

cd "$maindirectory"
use ${CurrentData}, clear

* --- Source BOTH vacancy levels (total + new) from the monthly vacancy file and
*     collapse to a quarterly mean (matching how the build formed
*     total_vacancies_county). CurrentData's own total_vacancies_county is dropped
*     and re-taken from ${vacfile} so the whole imputation is consistent with the
*     chosen (real or synthetic) vacancy source; total_newvacancies_county is not
*     carried in CurrentData at all (the build's collapse drops total_new*). ---
capture drop total_vacancies_county total_newvacancies_county
preserve
use "${vacfile}", clear
gen quarter = floor((month-1)/3)+1
collapse (mean) total_vacancies_county total_newvacancies_county, by(fipsnumeric year quarter)
tempfile vac
save "`vac'"
restore
merge m:1 fipsnumeric year quarter using "`vac'"
drop if _merge==2
drop _merge

* --- Merge population (annual) and the CPS separation rate (year-quarter). ---
merge m:1 fipsnumeric year using "${rawdata}/population_age.dta"
drop if _merge==2
drop _merge

merge m:1 year quarter using "${rawdata}/cpssep.dta"
drop if _merge==2
drop _merge
capture confirm variable separation
* cpssep holds the MEAN MONTHLY separation rate (Shimer 2012). CurrentData is
* quarterly, so the quarterly law of motion needs the quarterly separation flow
* = 3 x the monthly rate, so delta_q = 3*separation in the U-dynamics phi below.
* The imputation uses the regression-based job-finding rate (eq:JFR_Data), not the
* proprietary claims-based job-finding f.
gen delta = 3*separation

* --- Border segment id (state-pair group), and side = min/max state. ---
capture drop st_min st_max bordersegment
bys pair_id_numeric: egen st_min = min(fipsstate)
by  pair_id_numeric: egen st_max = max(fipsstate)
egen bordersegment = group(st_min st_max)

* --- Per-county search base: s = unemployed + zeta*(outlabor),
*     outlabor = County_Population - labor; searchers = labor - emp + outlabor*5/27
*     (paper eq:utilde). County_Population is TOTAL county population -> popestimate
*     (population_age.dta), NOT the age-restricted working_pop. ---
gen searchers = unemp_count_laus + (5/27)*(popestimate - labor_laus)

* --- Aggregate to the segment side by SUMMING over ALL pair-appearances (a county
*     that sits in K pairs within a segment is counted K times -- this is what the
*     original egen sum(...) by(bordersegment quarter_index fipsstate) did, and what
*     makes utilde match; do NOT dedup to unique counties). ---
collapse (sum) b_u=unemp_count_laus b_l=labor_laus b_p=popestimate ///
               b_vac=total_vacancies_county b_newvac=total_newvacancies_county ///
               b_s=searchers (mean) delta year quarter, ///
         by(bordersegment fipsstate st_min st_max quarter_index)

* --- phi (job-finding) and q (vacancy-filling) per segment side, over time. ---
sort bordersegment fipsstate quarter_index
by bordersegment fipsstate (quarter_index): gen b_u_f1   = b_u[_n+1]
by bordersegment fipsstate (quarter_index): gen b_vac_f1 = b_vac[_n+1]
by bordersegment fipsstate (quarter_index): gen b_newvac_f1 = b_newvac[_n+1]

gen phi = (b_u - b_u_f1 + delta*(b_l - b_u)) / b_u
* phi is a job-finding PROBABILITY (fraction of unemployed who find work), so it
* is bounded to (0,1]; the raw U-dynamics expression can overshoot 1 in tight
* labor markets (large delta*(n-u)/u term). Cap as the original did (backoutf used
* max(min(.,0.999),0.001)); this is exactly what produces the historical phi's
* 0.99 plateau in the pre-recession quarters, and keeps the solve well-behaved
* (uncapped phi>1 is unfittable by the matching function and pushes gamma to its
* bound). Recession-era phi (<0.99) is unaffected and matches the historical.
replace phi = max(min(phi, 0.99), 0.001)
gen q   = 1 - (b_vac_f1 - b_newvac_f1) / b_vac

* --- Restrict to the imputation sample (2005Q2-2011Q4). population_age.dta (the popestimate source) only covers
*     2000-2011, so 2012+ rows have b_p=0 -> negative search base; drop them AFTER
*     the forward differences above (so 2011Q4's phi/q can reference 2012Q1). ---
keep if year>=2005 & year<=2011

* --- Assign A (lower state) / B (higher state) and reshape to one row per
*     (bordersegment, quarter_index). ---
gen side = cond(fipsstate==st_min, "A", "B")
keep bordersegment quarter_index st_min st_max side b_u b_l b_p b_vac phi q
reshape wide b_u b_l b_p b_vac phi q, i(bordersegment quarter_index st_min st_max) j(side) string

gen qratio = qA / qB

* Keep periods where the core inputs are present for both sides.
keep if !missing(phiA, phiB, b_vacA, b_vacB, b_uA, b_uB, b_lA, b_lB, b_pA, b_pB, qratio)

* st_min / st_max carry the A / B fipsstate so the driver can write the
* ImputedDataBorder key (bordersegment fipsstate year quarter).
order bordersegment quarter_index st_min st_max b_uA b_uB b_lA b_lB b_pA b_pB b_vacA b_vacB phiA phiB qratio
sort bordersegment quarter_index

* --- Export for the Matlab driver (Run_Impute_Border.m loops bordersegments,
*     calls impute_border_search.m). ---
outsheet bordersegment quarter_index st_min st_max b_uA b_uB b_lA b_lB b_pA b_pB b_vacA b_vacB phiA phiB qratio ///
    using "${latexdir}Impute_Input.txt", replace nonames

cd "${CodeDirec}"
