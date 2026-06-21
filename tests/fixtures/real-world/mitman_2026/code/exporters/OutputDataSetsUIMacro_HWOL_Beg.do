* ---------------------------------------------------------------------------
* OutputDataSetsUIMacro_HWOL_Beg.do  ->  output/factor_inputs/HWOL_Beg/  (tab:macroeffects_beg
*                                        Vacancies + Tightness columns, QWI-separation diff)
*
* QWI-separation ("beg") analog of OutputDataSetsUIMacro_HWOL.do: same vacancy LHS,
* but quasi-differenced with the QWI-beg separation rate (qdsbk1_, the differencing
* used by tab:Benefits_on_unemp_beg) instead of the JOLTS-aggregate qdk1_. QBLS contract:
*   col 4  diff_logmeanwks       (benefit weeks; RHS regressor)
*   col 5  qdsbk1_logtight2      Tightness  (var_ind 5)
*   col 6  qdsbk1_logtight1
*   col 7  qdsbk1_logvacrate2    Vacancies  (var_ind 7)
*   col 8  qdsbk1_logvacrate1
*
* *** VACANCY-GATED *** (uses the proprietary vacancy data): tight2/vacrate2 embed the
* proprietary HWOL vacancies. Real DataControls reproduces the published numbers;
* the synthetic-vacancy DataControls (UIMacro_DataControls_SYNTH) makes it runnable
* without the proprietary data. Set ${DataControls} accordingly.
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

foreach var of varlist 																		///
	qdsbk1_logtight2 qdsbk1_logtight1 qdsbk1_logvacrate2 qdsbk1_logvacrate1					///
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

capture mkdir "${outdirectory}HWOL_Beg"
cd "${outdirectory}HWOL_Beg"
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter diff_logmeanwks qdsbk1_logtight2 qdsbk1_logtight1 qdsbk1_logvacrate2 qdsbk1_logvacrate1 ///
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
