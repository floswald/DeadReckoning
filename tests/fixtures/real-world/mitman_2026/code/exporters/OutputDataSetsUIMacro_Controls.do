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
	qdk1_logunemp_rate_laus	diff_judicial diff_logprod_all diff_logprod_priv											///																			///
																									///
	diff_logmeanwks diff_logawardamount_gdp diff_sbsi diff_sbtc diff_bhi diff_logtotal_gdp diff_logincome_gdp diff_loggeneral_sales_gdp diff_bbce_asset2018 { ///

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
capture mkdir Controls
cd Controls
file open myfile using "N.txt", write replace
file write myfile "`maxid'"
file close myfile
forvalues i=1/`maxid'{
	disp(`i')
	outsheet fipsnumeric year quarter diff_logmeanwks qdk1_logunemp_rate_laus diff_logawardamount_gdp diff_sbsi diff_sbtc diff_bhi diff_logtotal_gdp diff_logincome_gdp diff_loggeneral_sales_gdp diff_judicial diff_bbce_asset2018 diff_logawardamount diff_logtotal diff_logincome diff_loggeneral_sales qdsbk1_logunemp_rate_laus ///
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
