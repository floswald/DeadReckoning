do "config.do"
global CodeDirec ="${code}/exporters/"
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
// drop if year<2005
// drop if year>2012


foreach var of varlist 																		///
																											///
	qdk1_logunemp_rate_laus	diff_logprod_priv diff_logprod_all												///																			///
																									///
	diff_logmeanwks { ///

	qui bys pair_id_numeric fipsnumeric: egen nmissing=count(`var')
	by pair_id_numeric: egen nmissing2=min(nmissing)
	qui tab nmissing
	drop if nmissing2==0
	qui drop nmissing nmissing2

}
	*qdk1_inf* diff_inf* { ///{{ *diff_inf

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
capture mkdir Bench
cd Bench
// cd "${outdirectory}IND_PairSep"
*cd "$outdirectory/LAUSScramble`sdno'"
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
* QBLS column contract (var_ind / exorange indices in the Matlab front-ends):
*  1 fipsnumeric  2 year  3 quarter  4 diff_logmeanwks (benefit regressor)
*  5 qdk1_logunemp_rate_laus (LHS, var_ind 5)  6 diff_logprod_priv  7 diff_logprod_all
*  8 diff_logmeanwks_pf  9 qdsbk1_logunemp_rate_laus (Beg LHS)
* 10 qdk1_logunemp_add  (LAUS-additivity-factors-removed LHS, var_ind 10;
*    app:data_quality_additivity inline 0.054 -- Factor_FrontEnd_Additivity.m)
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter diff_logmeanwks qdk1_logunemp_rate_laus diff_logprod_priv diff_logprod_all diff_logmeanwks_pf qdsbk1_logunemp_rate_laus qdk1_logunemp_add ///
	if pair_id_numeric==`i' using QBLS`i'.txt, replace nonames
}
* diff_logqcew_emp_priv
* diff_logvacrate2 diff_logtight2
* diff_bhi diff_sbsi diff_sbtc diff_bbce	diff_logproperty diff_loggeneral_sales diff_logincome diff_logcorp_income diff_logtotal

* Emit the ORIGINAL (finer, ~108) DataControls border-segment id per renumbered pair,
* BEFORE the coarse state-pair bordersegment is recomputed below. The Monte-Carlo
* methodology check (tab:Monte-Carlo-Results / Estimate_Error_Structure) assigns the
* common spatial shock at this 108-segment level, matching the published baseline_results.
preserve
bysort pair_id_numeric: keep if _n==1
sort pair_id_numeric
outsheet pair_id_numeric bordersegment using mc_borderid.txt, replace nonames
restore

capture drop st_min
capture drop st_max
capture drop bordersegment

bys pair_id_numeric: egen st_min=min(fipsstate)
by  pair_id_numeric: egen st_max=max(fipsstate)
egen bordersegment=group(st_min st_max)

*save MinWageDataSet, replace

bys bordersegment pair_id_numeric: gen temp=_n==1
sort bordersegment pair_id_numeric fipsnumeric time
outsheet bordersegment pair_id_numeric using bordersegment_cluster.txt if temp==1, nonames replace
drop temp

/*
bysort pair_id_numeric: keep if _n==1
sort Ave_SS_diff_share

outsheet pair_id_numeric Ave_SS_diff_share using DistanceMeasureList.txt, replace nonames
*/
cd "${CodeDirec}"
