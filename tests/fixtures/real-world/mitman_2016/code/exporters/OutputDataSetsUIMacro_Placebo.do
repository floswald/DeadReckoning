* ---------------------------------------------------------------------------
* OutputDataSetsUIMacro_Placebo.do  ->  output/factor_inputs/Placebo/  (§sec:placebo_test
*                                       inline numbers: 0.008/0.35 and footnote 0.015)
*
* Builds the QBLS
* files for the placebo test: the estimator applied to 1996-2000 (a period with no
* real benefit extensions) using an ARTIFICIAL placebo benefit measure based on a
* hypothetical extension trigger. QBLS column contract (var_ind in the front-end):
*   col 1  fipsnumeric
*   col 2  year
*   col 3  quarter
*   col 4  diff_logmeanwks            (real benefit weeks; unused in the placebo reg)
*   col 5  qdk1_logunemp_rate_laus    LHS (quasi-diff unemployment)   (var_ind 5)
*   col 6..13  diff_pwks_{u,sa}{4,5,6,7}_13  placebo benefit (cross-pair log diff)
*              under unadjusted (u) / seasonally-adjusted (sa) state-urate triggers
*              at 4/5/6/7% thresholds, 13-week extension. The paper's reported spec
*              is sa6 (3-mo avg SA state urate > 6%) = col 12 (front-end exo_var_1=12).
*
* *** REQUIRES the artificial placebo-weeks data: PlaceboWeeksData.dta ***, keyed
* (fipsstate year quarter), with the pwks_{u,sa}{4,5,6,7}_13 variables. The original
* file is currently lost (empty placeholder); set ${placebofile} to its location.
* The placebo weeks are derived from public state SA unemployment rates + a trigger
* rule (26 base + 13-wk extension when 3-mo avg state SA urate > threshold), so they
* are public/shippable once recovered or rebuilt.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/exporters/"
if "${CurrentData}"=="" global CurrentData "UIMacro_RevisionData.dta"
global maindirectory "${processed}/"
global outdirectory "${factor_inputs}/"
if "${placebofile}"=="" global placebofile "${rawdata}/PlaceboWeeksData.dta"
cd "${CodeDirec}"

set more off, perm
cap log close
set logtype text

cd "$maindirectory"
use ${CurrentData}, clear

* Merge the artificial placebo benefit weeks (state x quarter).
merge m:1 fipsstate year quarter using "${placebofile}"
drop if _merge==2
drop _merge

* Cross-pair log difference of each placebo weeks measure.
sort pair_id_numeric quarter_index county_index
foreach var of varlist pwks*{
	by pair_id_numeric quarter_index: gen diff_`var'=log(`var'[1])-log(`var'[2])
}

keep if county_index==1
duplicates drop pair_id_numeric time, force

foreach var of varlist 																		///
	qdk1_logunemp_rate_laus diff_pwks*														///
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
capture mkdir "${outdirectory}Placebo"
cd "${outdirectory}Placebo"
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter diff_logmeanwks qdk1_logunemp_rate_laus ///
	diff_pwks_u4_13 diff_pwks_u5_13 diff_pwks_u6_13 diff_pwks_u7_13 diff_pwks_sa4_13 diff_pwks_sa5_13 diff_pwks_sa6_13 diff_pwks_sa7_13 ///
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
