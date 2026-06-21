* ---------------------------------------------------------------------------
* Mobility_LODES.do  ->  paper tab:Mobility_LODES
* "Unemployment Benefit Extensions and Mobility Across State Borders. LODES data."
*
* Bounds the potential commuting bias under the extreme assumption that every
* cross-border commuter would instead have been unemployed in their home county.
* Construct a counterfactual home-county unemployment rate by adding half the
* annual change in commuters (half-year time-aggregation adjustment) to the
* unemployed count, then log / quasi-difference / pair-difference it
* (qdk1_logadju_c). The benchmark interactive-effects time factors (fq1, fq2
* from the Bench Col-1 regife) are held FIXED and the loadings + benefit
* coefficient are re-estimated by absorbing pair x factor interactions
* (reghdfe abs(i.pair#c.fq1 i.pair#c.fq2)) -- the same factors-fixed
* decomposition used in Check_UFU. Inference is a residual cluster bootstrap
* over border segments (200 reps).
*
*
* Dependencies: ${CurrentData} (un-differenced, both counties) and the LODES
* commuter file fraction_commuters_lite_flag.dta (fr_st_commuter, fr_cty_commuter,
* commuters, emp_byresidence; keyed pair_id_numeric year county_index), built by
* the LODES producer in code/build/RawDataScripts/LODES/.
* Stata packages: regife, reghdfe.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/analysis/"
global CurrentData "UIMacro_RevisionData.dta"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"

set seed 5
set more off, perm
cap log close

cd "$maindirectory"
use ${CurrentData}, clear

* The build may already carry commuter columns; drop them so the LODES merge is
* authoritative (capture so a missing variable is not an error).
capture drop logfr_st_commuter logfr_cty_commuter logstate_commuters logcommuters state_commuters
capture drop diff_logfr_st_commuter diff_logfr_cty_commuter diff_logstate_commuters diff_logcommuters
capture drop avgcommuters mincommuters st_min st_max bordersegment
capture drop fr_st_commuter fr_cty_commuter commuters emp_byresidence

merge m:1 pair_id_numeric year county_index using "${rawdata}/fraction_commuters_lite_flag.dta"
drop if _merge==2
drop _merge

sort pair_id_numeric quarter_index county_index
gen state_commuters = fr_st_commuter*emp_byresidence
foreach var of varlist fr_st_commuter fr_cty_commuter state_commuters commuters {
gen log`var'=ln(`var')
by pair_id_numeric quarter_index: gen diff_log`var'=log`var'[1]-log`var'[2]
by pair_id_numeric quarter_index: gen diff_`var'=`var'[1]-`var'[2]
}

* Half the annual (4-quarter) change in commuters -> counterfactual unemployment.
sort pair_id_numeric county_index quarter_index
foreach var of varlist state_commuters commuters{
by pair_id_numeric county_index: gen tdiff4_`var'=`var'[_n]-`var'[_n-4]
}

gen adju_c  = (unemp_count_laus+0.5*tdiff4_commuters)/labor_laus
gen adju_s  = (unemp_count_laus+0.5*tdiff4_state_commuters)/labor_laus
gen adju_c2 = (unemp_count_laus)/(labor_laus-0.5*tdiff4_commuters)
gen adju_s2 = (unemp_count_laus)/(labor_laus-0.5*tdiff4_state_commuters)

sort pair_id_numeric quarter_index county_index
foreach var of varlist adju_*{
gen log`var'=ln(`var')
by pair_id_numeric quarter_index: gen diff_log`var'=log`var'[1]-log`var'[2]
by pair_id_numeric quarter_index: gen diff_`var'=`var'[1]-`var'[2]
}

drop if pair_id_numeric==.
keep if county_index==1
duplicates drop pair_id_numeric time, force
sort pair_id_numeric quarter_index

* Quasi-difference the counterfactual unemployment (same QD as the benchmark).
foreach var of varlist fr_st_commuter fr_cty_commuter state_commuters commuters adju*{
by pair_id_numeric: gen f1_`var' = diff_log`var'[_n+1]
by pair_id_numeric: gen qdk1_log`var' = diff_log`var'-0.99*(1-seprate)*f1_`var'
}

* Drop pairs entirely missing any analysis variable.
foreach var of varlist 																		///
	qdk1_logunemp_rate_laus qdk1_logunemp_add diff_logprod_priv diff_logprod_all			///
	diff_logmeanwks qdk1_logadju_c qdk1_logadju_c2 qdk1_logadju_s qdk1_logadju_s2 { ///

	qui bys pair_id_numeric fipsnumeric: egen nmissing=count(`var')
	by pair_id_numeric: egen nmissing2=min(nmissing)
	qui tab nmissing
	drop if nmissing2==0
	qui drop nmissing nmissing2

}

qui sort pair_id_numeric fipsnumeric year quarter
qui by pair_id_numeric: gen temp=_n==1
qui gen temp2=sum(temp)
tab temp2
qui drop pair_id_numeric
qui ren temp2 pair_id_numeric
qui drop temp
qui sum pair_id_numeric
local maxid=r(max)
qui sum time
local mint=r(min)
replace time=time-`mint'+1

sort pair_id_numeric quarter_index

capture drop st_min st_max bordersegment
bys pair_id_numeric: egen st_min=min(fipsstate)
by  pair_id_numeric: egen st_max=max(fipsstate)
egen bordersegment=group(st_min st_max)

keep if inrange(year,2005,2012)
gen id = pair_id_numeric
xtset id quarter_index

* Benchmark factors (Bench Col 1): save fixed time factors fq1, fq2.
regife qdk1_logunemp_rate_laus diff_logmeanwks, noconst f(fid=id fq=quarter_index,2)

* Re-estimate loadings + benefit coef on the counterfactual LHS, factors fixed.
reghdfe qdk1_logadju_c diff_logmeanwks if inrange(year,2005,2012), ///
    abs(i.pair_id_numeric#c.fq1 i.pair_id_numeric#c.fq2) res(ehat)
scalar ml_coef = _b[diff_logmeanwks]
scalar ml_n    = e(N)
scalar ml_r2   = e(r2)

gen predvar = qdk1_logadju_c-ehat
matrix observe=_b[diff_logmeanwks]
sort pair_id_numeric quarter_index
gen unique_id=_n
keep bordersegment qdk1_logadju_c diff_logmeanwks id pair_id_numeric quarter_index unique_id ehat predvar fq1 fq2

* --- Residual cluster bootstrap over border segments (200 reps) ---
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
reghdfe LHSvar diff_logmeanwks, abs(i.newid#c.fq1 i.newid#c.fq2)
return scalar wkscoef=_b[diff_logmeanwks]
restore
end

simulate wkscoef=r(wkscoef), reps(200) seed(12345): myboot
qui summarize wkscoef
scalar ml_bse = r(sd)

* Write the single-coefficient result: [coef, bootstrap SE, N.factors, R2, Nobs].
clear
quietly set obs 1
gen coef    = ml_coef
gen bse     = ml_bse
gen factors = 2
gen r2      = ml_r2
gen nobs    = ml_n
outsheet coef bse factors r2 nobs using "${latexdir}Mobility_LODES.csv", comma nonames replace

cd "${CodeDirec}"
