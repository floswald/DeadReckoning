* ---------------------------------------------------------------------------
* OutputDataSetsUIMacro_DiscFactor.do  ->  output/factor_inputs/DiscFactor/
*
* Discount-factor robustness footnote (§baseline_results, ~L780): re-estimating the
* baseline under beta = 0.9975 or 0.98 (vs the standard 0.99) and computing the
* permanent effect alpha_hat/(1-beta(1-s)) yields 0.484 and 0.491 (vs 0.488 at 0.99).
*
* Both the estimated coefficient AND the mapping change with beta, because beta enters
* the 1-period quasi-difference qd = diff_logunemp - beta(1-s)*f1_diff_logunemp. The
* benchmark DataControls qdk1_logunemp_rate_laus uses beta=0.99; here we RECOMPUTE the
* quasi-difference at beta=0.9975 and beta=0.98 from the same pieces (diff_logunemp,
* f1_logunemp, seprate; qdk1 = diff - 0.99*(1-seprate)*f1), then
* re-estimate the IFE. Same Bench skeleton/sample (keep county_index==1, same window
* drop=60/trunc=8), benefit regressor diff_logmeanwks at col 4.
*
* QBLS columns / var_ind in Factor_FrontEnd_DiscFactor.m:
*   1 fipsnumeric  2 year  3 quarter  4 diff_logmeanwks (benefit regressor)
*   5 qd_b9975   (quasi-diff unemployment at beta=0.9975)   -> permanent 0.484
*   6 qd_b98     (quasi-diff unemployment at beta=0.98)     -> permanent 0.491
*   7 qdk1_logunemp_rate_laus  (beta=0.99 anchor)           -> permanent 0.488
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec     = "${code}/exporters/"
global DataControls "UIMacro_DataControls"
global maindirectory "${processed}/"
global outdirectory "${factor_inputs}/"
cd "${CodeDirec}"

set more off, perm
cap log close
set logtype text

cd "$maindirectory"
use ${DataControls}.dta, clear
sort pair_id_numeric county_index
keep if county_index==1

* recompute the 1-period quasi-difference at the two alternate discount factors
gen qd_b9975 = diff_logunemp_rate_laus - 0.9975*(1-seprate)*f1_logunemp_rate_laus
gen qd_b98   = diff_logunemp_rate_laus - 0.98  *(1-seprate)*f1_logunemp_rate_laus

foreach var of varlist qdk1_logunemp_rate_laus qd_b9975 qd_b98 diff_logmeanwks {
	qui bys pair_id_numeric fipsnumeric: egen nmissing=count(`var')
	by pair_id_numeric: egen nmissing2=min(nmissing)
	qui drop if nmissing2==0
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
cd "$outdirectory"
capture mkdir DiscFactor
cd DiscFactor
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter diff_logmeanwks qd_b9975 qd_b98 qdk1_logunemp_rate_laus ///
	if pair_id_numeric==`i' using QBLS`i'.txt, replace nonames
}

capture drop st_min st_max bordersegment
bys pair_id_numeric: egen st_min=min(fipsstate)
by  pair_id_numeric: egen st_max=max(fipsstate)
egen bordersegment=group(st_min st_max)
bys bordersegment pair_id_numeric: gen temp=_n==1
sort bordersegment pair_id_numeric fipsnumeric time
outsheet bordersegment pair_id_numeric using bordersegment_cluster.txt if temp==1, nonames replace
drop temp

cd "${CodeDirec}"
