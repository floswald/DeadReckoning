* ---------------------------------------------------------------------------
* OutputDataSetsUIMacro_JFR.do  ->  output/factor_inputs/JFR/  (app:data_quality_claims
*                                   inline numbers: alpha_f = -0.0486, and the
*                                   LAUS-on-same-sample 0.0475)
*
* Exports the claims
* "job-finding rate" sample for the factor model. The quasi-differenced log job-finding
* rates (qdk1_logf_cl*) are PRE-BUILT in DataControls: the build backs the monthly
* job-finding rate out of the BLS administrative claims data (continuing claims + final
* payments, via the eq:claims recursion -- cohort backout) and merges it in, exactly
* as it does for qdk1_logunemp_add. The BLS provided and permits distributing these
* claims data, so this ships in the kit.
*
* The single-county-LMA restriction and pair construction are already baked into the
* DataControls job-finding variables, so this is the SAME skeleton as the Bench
* exporter: keep county_index==1, drop pairs all-missing in the key vars, export QBLS.
*
* QBLS column contract (var_ind in Factor_FrontEnd_JFR.m). Only the two REPORTED specs are
* exported; the three unreported job-finding clamps (f_cl/f_cl2/f_cl_q) were pruned from the
* build, this exporter, and the front-end (no need to compute numbers the paper doesn't report).
* Filtering on {unemp, f_cl2_q} drops the same 282 pairs as filtering on the full
* {unemp, f_cl, f_cl2, f_cl_q, f_cl2_q} set, so the sample (and alpha_f/alpha_u) is unchanged.
*   1 fipsnumeric  2 year  3 quarter  4 diff_logmeanwks (benefit regressor)
*   5 qdk1_logunemp_rate_laus  (LAUS unemployment LHS -> alpha_u 0.0475, var_ind 5)
*   6 qdk1_logf_cl2_q          (quarterly-compounded cl2 job-finding -> alpha_f -0.0486, var_ind 6)
* The claims sample is ~282 pairs / 9,024 quarterly obs (2005-2012).
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec     = "${code}/exporters/"
global DataControls "UIMacro_DataControls"
global CurrentData "UIMacro_RevisionData.dta"
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

foreach var of varlist 																		///
	qdk1_logunemp_rate_laus qdk1_logf_cl2_q		///
	diff_logmeanwks { ///

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
cd "$outdirectory"
capture mkdir JFR
cd JFR
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter diff_logmeanwks qdk1_logunemp_rate_laus qdk1_logf_cl2_q ///
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
