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


keep if county_index==1
// drop if year<2005
// drop if year>2012


foreach var of varlist 																		///
																											///
	qdk*_logunemp_rate_laus qdk1_logunemp_add diff_logprod_priv diff_logprod_all						///																			///
																									///
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
capture mkdir QDK
cd QDK
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile

// QBLS column contract for tab:Forward_Spec / Factor_FrontEnd_QDK.m:
//   col 1   fipsnumeric
//   col 2   year
//   col 3   quarter
//   col 4   diff_logmeanwks                 (benefits at t)
//   col 5-12 qdk1..qdk8_logunemp_rate_laus  (k-period-ahead quasi-differenced unemployment)
//   col 13-19 f1..f7_logmeanwks             (leads of benefits)
forvalues i=1/`maxid'{
	qui outsheet fipsnumeric year quarter diff_logmeanwks qdk1_logunemp_rate_laus ///
		qdk2_logunemp_rate_laus qdk3_logunemp_rate_laus qdk4_logunemp_rate_laus qdk5_logunemp_rate_laus ///
		qdk6_logunemp_rate_laus qdk7_logunemp_rate_laus qdk8_logunemp_rate_laus ///
		f1_logmeanwks f2_logmeanwks f3_logmeanwks f4_logmeanwks f5_logmeanwks f6_logmeanwks f7_logmeanwks ///
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
