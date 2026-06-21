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


// Loop over 8 distance configurations (20/30/40/50 miles, < and >).
// Each writes its own output/factor_inputs/Dist{cut}{Lt|Gt}/ subdirectory of
// QBLS files. The 8-column outsheet contract matches Bench (so a future
// Beg variant of this table is a one-line var_ind change in Matlab):
//   col 1 fipsnumeric, col 2 year, col 3 quarter,
//   col 4 diff_logmeanwks, col 5 qdk1_logunemp_rate_laus,
//   col 6 diff_logprod_priv, col 7 diff_logprod_all,
//   col 8 diff_logmeanwks_pf, col 9 qdsbk1_logunemp_rate_laus.
preserve
foreach cut in 20 30 40 50 {
foreach dir in Lt Gt {

	restore, preserve

	sort pair_id_numeric county_index
	keep if county_index==1

	// dist is a pair-level variable; strict inequalities exhaust the sample
	// (no pairs have dist exactly equal to a cut value).
	if "`dir'"=="Lt" {
		keep if dist < `cut'
	}
	else {
		keep if dist > `cut'
	}

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
	capture mkdir "Dist`cut'`dir'"
	cd "Dist`cut'`dir'"
	file open myfile using "N.txt", write replace
	file write myfile "`maxid'"
	file close myfile
	forvalues i=1/`maxid'{
		qui outsheet fipsnumeric year quarter diff_logmeanwks qdk1_logunemp_rate_laus diff_logprod_priv diff_logprod_all diff_logmeanwks_pf qdsbk1_logunemp_rate_laus ///
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
	qui outsheet bordersegment pair_id_numeric using bordersegment_cluster.txt if temp==1, nonames replace
	drop temp

	cd "${maindirectory}"
	display "Distance Dist`cut'`dir' done (`maxid' pairs)"
}
}
restore

cd "${CodeDirec}"
