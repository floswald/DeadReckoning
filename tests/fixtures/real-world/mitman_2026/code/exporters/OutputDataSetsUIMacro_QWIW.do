* ---------------------------------------------------------------------------
* OutputDataSetsUIMacro_QWIW.do
*
* Wage exporter for paper tab:Benefits_on_Wages (§5.2, main text) and
* tab:app_Benefits_on_Wages (wages appendix). Counterpart Matlab front-end:
* code/matlab/Factor_FrontEnd_QWIW.m.
*
* Unlike the unemployment exporters (which read the pre-differenced
* DataControls), the wage double-differences live in ProcessedWages, built by
* code/build/MakeWageData.do. We load that vintage here and outsheet one
* balanced QBLS per pair. RunFactorModel masks the per-LHS missingness, so the
* three wage measures (stayers / new hires / all workers) each recover their
* own observation count from a single exported panel.
*
* QBLS column contract (var_ind in the front-end picks the LHS column):
*   col 1  fipsnumeric
*   col 2  year
*   col 3  quarter
*   col 4  ben_1                       (double-differenced benefit weeks; RHS)
*   col 5  did_logqwi_wage2f_0         Job Stayers, raw          (app Cols 1)
*   col 6  did_logqwi_wage2f_t_0       Job Stayers, with tax     (app Cols 2)
*   col 7  kqwinew                     New Hires, raw            (app Cols 3)
*   col 8  kqwinew_t                   New Hires, with tax       (app Cols 4)
*   col 9  kqwitot                     All Workers, raw          (main Col 1)
*   col 10 kqwitot_t                   All Workers, with tax     (main Col 2)
*
* The "stayers" LHS is the QWI full-quarter stable-earnings double difference
* (wage2f = qwiw3f/qwiw4f), labelled 'stayers0' in the original front-end.
* The "new hires" and "all workers" LHS are the smoothed-level (kmean_*_1)
* two-period quasi-differences of QWI new-hire (wnhf) and total (wtot) wages,
* matching the original exporter. The _t suffix adds the UI
* payroll-tax adjustment (diff_logui_tax_rate baked into MakeWageData).
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/exporters/"
global ProcessedWages = "${Wages}"
global maindirectory "${processed}/"
global outdirectory "${factor_inputs}/"
cd "${CodeDirec}"

set more off, perm
cap log close
set logtype text


cd "$maindirectory"
use ${ProcessedWages}, clear
sort pair_id_numeric county_index

keep if county_index==1
sort pair_id_numeric quarter_index
by pair_id_numeric: gen kqwipay = kmean_logqwi_wpay_all_1 - L2.kmean_logqwi_wpay_all_1
by pair_id_numeric: gen kqwipay_t = kmean_logqwi_wpay_all_t_1 - L2.kmean_logqwi_wpay_all_t_1
by pair_id_numeric: gen kqwinew = kmean_logqwi_wnhf_all_1 - L2.kmean_logqwi_wnhf_all_1
by pair_id_numeric: gen kqwinew_t = kmean_logqwi_wnhf_all_t_1 - L2.kmean_logqwi_wnhf_all_t_1
by pair_id_numeric: gen kweeks = kmean_logmeanwks_1 - L2.kmean_logmeanwks_1


* --- Drop pairs entirely missing the benefit or any wage LHS. ---
foreach var of varlist 																		///
	kqwinew kqwinew_t kqwipay kqwipay_t ben_1	 { ///

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
capture mkdir QWIW
cd QWIW
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter ben_1 kqwinew kqwinew_t kqwipay kqwipay_t ///
	if pair_id_numeric==`i' using QBLS`i'.txt, replace nonames
}

capture drop st_min
capture drop st_max
capture drop bordersegment

bys pair_id_numeric: egen st_min=min(fipsstate)
by  pair_id_numeric: egen st_max=max(fipsstate)
egen bordersegment=group(st_min st_max)

bys bordersegment pair_id_numeric: gen temp=_n==1
sort bordersegment pair_id_numeric fipsnumeric time
outsheet bordersegment pair_id_numeric using bordersegment_cluster.txt if temp==1, nonames replace
drop temp

cd "${CodeDirec}"
