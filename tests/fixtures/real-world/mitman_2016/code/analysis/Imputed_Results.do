* ---------------------------------------------------------------------------
* Imputed_Results.do  ->  paper tab:Imputed_Results
* "Effect of UI Benefits on Imputed Labor Market Variables"
*
* *** VACANCY-GATED (see SYNTHETIC_VACANCY_PATH.md). ***
* Inputs:
*   - county panel = ${CurrentData}
*   - imputed series (x, thet_corr, f, phi, utilde) = ${ImputedFile}, the ImputedDataBorder
*       built by Impute_Input.do -> Run_Impute_Border.m -> Impute_to_Stata.do.
* The imputed series embed vacancies, so this is vacancy-gated: the published numbers
* require the real HWOL vacancies; a synthetic-vacancy run (build ImputedDataBorder with
* vacfile=new_vac_synthetic, then set ImputedFile to it) is demonstrative.
*
* Three columns (each: regife with 2 factors + residual cluster bootstrap over
* border segments, exactly like the benchmark / Mobility_LODES inference):
*   Col 1  Out of State Search  : LHS did_logx, RHS diff_logmeanwks. The differencing is
*          deliberately MIXED (a difference-in-differences LHS on a plain first-difference
*          benefit RHS).
*   Col 2  Imputed Tightness    : LHS jolts_udiff_logthet_corr, RHS diff_logmeanwks
*   Col 3  Imputed Job-finding  : LHS jolts_udiff_logf, RHS diff_logmeanwks
*
* Stata package: regife.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec     ="${code}/analysis/"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"
* County panel = ${CurrentData}; imputed series = the ImputedDataBorder built (into
* data/processed/) by the Impute_Input -> Run_Impute_Border -> Impute_to_Stata chain,
* synthetic by default (config's ${vacfile}). config.do sets both globals; the fallbacks
* below only fire if this is run without config.
if "${CurrentData}"=="" global CurrentData "UIMacro_RevisionData.dta"
if "${ImputedFile}"=="" global ImputedFile "${processed}/ImputedDataBorder.dta"

set seed 5
set more off, perm
cap log close

* ============================ data preparation ============================
use "${maindirectory}${CurrentData}", clear
capture drop f x phi thet_corr utilde searchers

* State-pair key (slo,shi): the bordersegment id numbering differs between the
* CurrentData build and the imputation build, so align on the actual state pair
* + side + time, not the raw id.
capture drop st_min st_max
bys pair_id_numeric: egen slo = min(fipsstate)
by  pair_id_numeric: egen shi = max(fipsstate)
preserve
use "${ImputedFile}", clear
bys bordersegment: egen slo = min(fipsstate)
by  bordersegment: egen shi = max(fipsstate)
keep slo shi fipsstate year quarter f x phi thet_corr utilde
tempfile imp
save "`imp'"
restore
merge m:1 slo shi fipsstate year quarter using "`imp'"
drop if _merge==2
drop _merge

* Log the imputed series (just merged). NOTE: do NOT re-log meanwks -- CurrentData's
* raw meanwks is empty for the analysis years; the benefit measure here is the
* pre-built logmeanwks (= log weeks of benefits), which we keep as-is. The diff_*
* loop below recomputes diff_logmeanwks (the cross-pair benefit difference) from it.
foreach y of varlist f x phi thet_corr utilde {
	capture drop log`y'
	gen log`y' = ln(`y')
}

* seprate is already the JOLTS aggregate separation rate in CurrentData (the build
* renamed jolts_agg_seprate_q -> seprate).
capture confirm variable seprate
if _rc gen seprate=jolts_agg_seprate_q
replace seprate=0.1 if seprate==. & year<2001

sort pair_id_numeric time county_index
foreach var of varlist logf logx logphi logthet_corr logutilde logmeanwks{
	capture drop diff_`var'
	by pair_id_numeric time: gen diff_`var' = `var'[1] - `var'[2]
}

sort pair_id_numeric county_index time
foreach var of varlist logf logx logphi logthet_corr logutilde{
	capture drop f1_`var' l1_`var'
	by pair_id_numeric county_index: gen f1_`var'=diff_`var'[_n+1]
	by pair_id_numeric county_index: gen l1_`var'=diff_`var'[_n-1]
}

foreach var of varlist logf logx logphi logthet_corr logutilde{
	capture drop jolts_udiff_`var' did_`var'
	gen jolts_udiff_`var'=diff_`var'-0.99*(1-seprate)*f1_`var'
	gen did_`var'=diff_`var'-l1_`var'
}

keep if year>2004 & county_index==1

tempfile prepped
save "`prepped'", replace

* ===================== residual cluster bootstrap =====================
capture program drop myboot
program define myboot, rclass
preserve
tempfile OrigSamp
save "`OrigSamp'"
bsample, cluster(bordersegment) id(newborder)
gen newid = newborder*10000+pair_id_numeric
sort newborder pair_id_numeric quarter_index
replace unique_id=_n
keep unique_id ehat newid
rename ehat ehatresamp
merge 1:1 unique_id using "`OrigSamp'"
keep if _merge==3
gen LHSvar = predvar+ehatresamp
xtset newid quarter_index
regife LHSvar diff_logmeanwks, noconst f(pair_id_numeric quarter_index,2)
return scalar wkscoef=_b[diff_logmeanwks]
restore
end

matrix IMP = J(3,5,.)   // rows = cols 1-3; [coef, se, N, R2, n_factors]

* col_lhs holds the LHS variable for each column.
local lhs1 did_logx
local lhs2 jolts_udiff_logthet_corr
local lhs3 jolts_udiff_logf

forvalues i=1/3{
	use "`prepped'", clear
	* Drop rows where this column's LHS (or the benefit RHS) is missing, so the
	* IFE factor structure sees no all-empty quarter levels. CurrentData runs to
	* 2014 but the imputation only covers 2005-2011, so the trailing quarters are
	* empty for the imputed LHS and would otherwise trip regife ("more levels of FE
	* than observations"). (County_Data_contig did not span those years.)
	keep if !missing(`lhs`i'', diff_logmeanwks)
	xtset pair_id_numeric quarter_index

	regife `lhs`i'' diff_logmeanwks, f(pair_id_numeric quarter_index, 2) noconst
	scalar coef`i' = _b[diff_logmeanwks]
	scalar nobs`i' = e(N)
	scalar rsq`i'  = e(r2)

	predict predvar
	gen ehat = `lhs`i'' - predvar
	sort pair_id_numeric quarter_index
	gen unique_id=_n
	keep bordersegment `lhs`i'' diff_logmeanwks pair_id_numeric quarter_index unique_id ehat predvar

	simulate wkscoef=r(wkscoef), reps(200) seed(20180802): myboot
	qui summarize wkscoef
	scalar bse`i' = r(sd)

	matrix IMP[`i',1]=coef`i'
	matrix IMP[`i',2]=bse`i'
	matrix IMP[`i',3]=nobs`i'
	matrix IMP[`i',4]=rsq`i'
	matrix IMP[`i',5]=2
}

* Write CSV: row = column (1 Search / 2 Tightness / 3 Job-finding);
* cols = [coef, bootstrap SE, N, R2, n_factors].
clear
quietly set obs 3
svmat IMP
outsheet using "${latexdir}Imputed_Results.csv", comma nonames replace

cd "${CodeDirec}"
