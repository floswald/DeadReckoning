* ---------------------------------------------------------------------------
* OutputDataSetsUIMacro_QWIWStayers.do
*
* Standalone Job Stayers wage exporter, SEPARATE from the QWIW (New Hires /
* All Workers) pairing. Counterpart: code/matlab/Factor_FrontEnd_QWIWStayers.m.
*
* Produces the Job Stayers columns of tab:app_Benefits_on_Wages (raw 0.023187,
* tax 0.023711; 4 factors, R^2=0.521, N=25,940). The LHS is the 3-quarter
* accumulated stayer-wage difference-in-differences:
*   - did_logqwi_wage2f_3    -> stayer-wage DiD, raw    (front-end var_ind=5)
*   - did_logqwi_wage2f_t_3  -> stayer-wage DiD, w/ tax (front-end var_ind=6)
*   - ben_3                  -> 3-quarter accumulated benefit (RHS, col 4)
* MakeWageData.do builds the accumulation as did_..._y = did_..._{y-1} +
* did_..._0[_n+y], so wage2f_3 sums the contemporaneous stayer-wage DiD over
* horizons 0..3.
*
* SAMPLE: prune pairs entirely missing ANY of the wage2f horizons (incl. the 2-
* and 3-quarter-ahead ones), the kqwi measures, ben_3, kweeks, or the lagged
* benefits. Pruning on the higher-horizon vars drops short pairs, taking N from
* ~28K down to 25,940.
*
* QBLS column contract (var_ind in the front-end picks the LHS column):
*   col 1  fipsnumeric
*   col 2  year
*   col 3  quarter
*   col 4  ben_3                     (3-qtr accumulated benefit; RHS)
*   col 5  did_logqwi_wage2f_3        Job Stayers, raw      (var_ind=5)
*   col 6  did_logqwi_wage2f_t_3      Job Stayers, with tax (var_ind=6)
*   col 7  ben_2                       \
*   col 8  Lben1                        | extra RHS candidates, available for
*   col 9  Lben2                        | p>1 / exorange experiments
*   col 10 kweeks                      /
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/exporters/"
global ProcessedWages = "${Wages}"
global maindirectory "${processed}/"
* --- Alternative vintage (uncomment to run on the 2018-09-18 wage panel instead):
* global ProcessedWages = "ProcessedWages_2018_09_18.dta"
* global maindirectory ="${rawdata}/"
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

* --- Build the variables the historical QWIWages2 prune/RHS depend on. ---
by pair_id_numeric: gen kqwitot   = kmean_logqwi_wtot_all_1   - L2.kmean_logqwi_wtot_all_1
by pair_id_numeric: gen kqwitot_t = kmean_logqwi_wtot_all_t_1 - L2.kmean_logqwi_wtot_all_t_1
by pair_id_numeric: gen kqwipay   = kmean_logqwi_wpay_all_1   - L2.kmean_logqwi_wpay_all_1
by pair_id_numeric: gen kqwipay_t = kmean_logqwi_wpay_all_t_1 - L2.kmean_logqwi_wpay_all_t_1
by pair_id_numeric: gen kqwinew   = kmean_logqwi_wnhf_all_1   - L2.kmean_logqwi_wnhf_all_1
by pair_id_numeric: gen kqwinew_t = kmean_logqwi_wnhf_all_t_1 - L2.kmean_logqwi_wnhf_all_t_1
by pair_id_numeric: gen kweeks    = kmean_logmeanwks_1        - L2.kmean_logmeanwks_1
by pair_id_numeric: gen Lben1 = ben_1[_n-1]
by pair_id_numeric: gen Lben2 = ben_2[_n-1]

* --- Heavy prune matching the original Sept-2018 QWIWages2 run:
*     drop pairs entirely missing any wage2f horizon, any kqwi measure, ben_3,
*     kweeks, or the lagged benefits. This is what pins N to ~25,940. Scoped to
*     this pairing, so it never touches the QWIW New-Hire / All-Worker samples. ---
foreach var of varlist 																		///
	kqwitot kqwitot_t kqwipay kqwipay_t kqwinew kqwinew_t									///
	did_logqwi_wage2f_t_0 did_logqwi_wage2f_0 did_logqwi_wage2f_t_1 did_logqwi_wage2f_1		///
	did_logqwi_wage2f_t_2 did_logqwi_wage2f_2 did_logqwi_wage2f_t_3 did_logqwi_wage2f_3		///
	ben_3 kweeks Lben1 Lben2 { ///

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
capture mkdir QWIWStayers
cd QWIWStayers
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter ben_3 did_logqwi_wage2f_3 did_logqwi_wage2f_t_3 ben_2 Lben1 Lben2 kweeks ///
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
