* ---------------------------------------------------------------------------
* OutputDataSetsUIMacro_HWOL.do  ->  output/factor_inputs/HWOL/  (tab:Benefits_on_JobCreation
*                                    Vacancies + Tightness columns)
*
* Exporter half of the HWOL (Help-Wanted-OnLine vacancy) IFE pairing. Writes one QBLS{i}.txt per
* county pair for Factor_FrontEnd_HWOL.m. QBLS column contract (var_ind in the
* front-end picks the LHS column):
*   col 1  fipsnumeric
*   col 2  year
*   col 3  quarter
*   col 4  diff_logmeanwks        (benefit weeks, first difference; RHS regressor)
*   col 5  qdk1_logtight2         Tightness  (V/U), Uhlig quasi-diff   (var_ind 5)
*   col 6  qdk1_logtight1
*   col 7  qdk1_logvacrate2       Vacancies  (V/L), Uhlig quasi-diff   (var_ind 7)
*   col 8  qdk1_logvacrate1
* The published table reports Vacancies = qdk1_logvacrate2 and Tightness =
* qdk1_logtight2 (both 1 factor).
*
* *** VACANCY-GATED *** (uses the proprietary vacancy data): tight2/vacrate2 derive from
* total_vacancies_county (HWOL, proprietary). Builds on the real DataControls vintage
* reproduce the published numbers; a synthetic-vacancy DataControls (UIMacro_DataControls_SYNTH,
* from UIMacro_BuildData_Synthetic.do) makes this runnable without the proprietary data
* (demonstrative). Set ${DataControls} accordingly.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/exporters/"
if "${DataControls}"=="" global DataControls "UIMacro_DataControls"
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

* Drop pairs missing any of the LHS / benefit columns (same pair-completeness filter
* as the benchmark exporters).
foreach var of varlist 																		///
	qdk1_logtight2 qdk1_logtight1 qdk1_logvacrate2 qdk1_logvacrate1							///
	diff_logmeanwks { ///

	qui bys pair_id_numeric fipsnumeric: egen nmissing=count(`var')
	by pair_id_numeric: egen nmissing2=min(nmissing)
	qui tab nmissing
	drop if nmissing2==0
	qui drop nmissing nmissing2

}

* Renumber pairs to a dense 1..maxid sequence (the Matlab front-end loops 1..N).
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

capture mkdir "${outdirectory}HWOL"
cd "${outdirectory}HWOL"
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter diff_logmeanwks qdk1_logtight2 qdk1_logtight1 qdk1_logvacrate2 qdk1_logvacrate1 ///
	if pair_id_numeric==`i' using QBLS`i'.txt, replace nonames
}

* Border-segment (state-pair) clustering key for the bootstrap.
capture drop st_min st_max bordersegment
bys pair_id_numeric: egen st_min=min(fipsstate)
by  pair_id_numeric: egen st_max=max(fipsstate)
egen bordersegment=group(st_min st_max)

bys bordersegment pair_id_numeric: gen temp=_n==1
sort bordersegment pair_id_numeric fipsnumeric time
outsheet bordersegment pair_id_numeric using bordersegment_cluster.txt if temp==1, nonames replace
drop temp

cd "${CodeDirec}"
