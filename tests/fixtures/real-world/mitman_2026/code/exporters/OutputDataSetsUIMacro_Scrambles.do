do "config.do"
global CodeDirec ="${code}/exporters/"
global DataControls "UIMacro_DataControls"
global CurrentData "UIMacro_RevisionData.dta"
global maindirectory "${processed}/"
global outdirectory "${factor_inputs}/"
global latexdir "${factor_csv}/"
cd "${CodeDirec}"

set more off, perm
cap log close
set logtype text


cd "$maindirectory"
use ${CurrentData}, clear


// Generate 200 scrambled pair assignments.  The RNG seed below is fixed so the
// random pairings are reproducible on the same underlying county set (these are
// the Table 1 Cols 3-4 scrambles).
keep fipsnumeric quarter_index county_index logmeanwks* logunemp* logprod* logxstate* seprate year quarter fipsstate pair_id_numeric pair_sepr_beg pair_sepr_tot

preserve
keep pair_id_numeric fipsnumeric
sort pair_id_numeric fipsnumeric
duplicates drop pair_id_numeric fipsnumeric, force

set seed 85237940
forvalues x=1/200{
	sort pair_id_numeric fipsnumeric
	gen rand=runiform()
	sort rand
	gen new_pair_id`x'=floor((_n+1)/2)
	drop rand
	sort new_pair_id`x' fipsnumeric
	by new_pair_id`x': gen new_county_index`x'=_n
}

sort pair_id_numeric fipsnumeric
tempfile scrambles
save `scrambles', replace
restore

merge m:1 pair_id_numeric fipsnumeric using `scrambles', keep(match) nogen


// Loop: for each scramble x, replace the pair/county identifiers with the
// scrambled ones, recompute pair-differences and quasi-differences, and write
// QBLS files for the Matlab factor model into output/factor_inputs/Scramble`x'/.
// Inside the same loop, also run the OLS specification used by the additive-
// effects appendix table (tab:Benefits_on_unemp_OLS) Cols 3-4 -- baseline and
// + State GDP per Worker control (diff_logprod_all). Per-scramble OLS coefs
// and clustered SEs collected into matrices and written out after the loop.
matrix scramble_ols_base = J(200, 4, .)
matrix scramble_ols_prod = J(200, 6, .)
preserve
forvalues x=1/200{

	replace pair_id_numeric = new_pair_id`x'
	replace county_index = new_county_index`x'

	capture drop time
	gen time = quarter_index

	// Pair-differences (across counties within a scrambled pair)
	sort pair_id_numeric time county_index
	capture drop diff_logmeanwks
	capture drop diff_logunemp_rate_laus
	capture drop diff_logprod_priv
	capture drop diff_logprod_all
	foreach var of varlist logmeanwks logunemp_rate_laus logprod_priv logprod_all {
		qui by pair_id_numeric time: gen diff_`var' = `var'[1] - `var'[2]
	}

	// Forward (lead) and 1-period quasi-differences of unemployment.
	// qdk1 uses the JOLTS-style seprate; qdsbk1 uses the QWI beginning-of-quarter
	// pair separation rate, normalised by 1.353 so its mean matches JOLTS (the
	// scaling factor follows the build script and the paper appendix).
	sort pair_id_numeric county_index time
	capture drop f1_logunemp_rate_laus
	capture drop qdk1_logunemp_rate_laus
	capture drop qdsbk1_logunemp_rate_laus
	qui by pair_id_numeric county_index: gen f1_logunemp_rate_laus = diff_logunemp_rate_laus[_n+1]
	qui by pair_id_numeric county_index: gen qdk1_logunemp_rate_laus = diff_logunemp_rate_laus - ((0.99*(1-seprate))^1)*f1_logunemp_rate_laus
	qui by pair_id_numeric county_index: gen qdsbk1_logunemp_rate_laus = diff_logunemp_rate_laus - ((0.99*(1-pair_sepr_beg/1.353))^1)*f1_logunemp_rate_laus

	keep if county_index==1
	qui duplicates drop pair_id_numeric quarter_index, force

	foreach var of varlist 																		///
																												///
		qdk1_logunemp_rate_laus	diff_logprod_priv diff_logprod_all												///																			///
																										///
		diff_logmeanwks { ///

		qui bys pair_id_numeric fipsnumeric: egen nmissing=count(`var')
		qui by pair_id_numeric: egen nmissing2=min(nmissing)
		qui drop if nmissing2==0
		qui drop nmissing nmissing2

	}

	qui sort pair_id_numeric fipsnumeric year quarter
	qui by pair_id_numeric: gen temp=_n==1
	qui gen temp2=sum(temp)
	qui drop pair_id_numeric
	qui ren temp2 pair_id_numeric
	qui drop temp
	qui sum pair_id_numeric
	local maxid=r(max)
	qui sum time
	local mint=r(min)
	qui replace time=time-`mint'+1

	sort pair_id_numeric quarter_index

	cd "$outdirectory"
	capture mkdir "Scramble`x'"
	cd "Scramble`x'"
	file open myfile using "N.txt", write replace
	file write myfile "`maxid'"
	file close myfile

	forvalues i=1/`maxid'{
		qui outsheet fipsnumeric year quarter diff_logmeanwks qdk1_logunemp_rate_laus diff_logprod_priv diff_logprod_all qdsbk1_logunemp_rate_laus ///
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

	// OLS sub-experiments for tab:Benefits_on_unemp_OLS Cols 3-4.
	// Spec matches code/analysis/Table1_OLS.do: reghdfe with pair fixed effects,
	// clustered SE by bordersegment, restricted to 2005-2012.
	qui reghdfe qdk1_logunemp_rate_laus diff_logmeanwks if inrange(year,2005,2012), absorb(pair_id_numeric) cluster(bordersegment)
	matrix scramble_ols_base[`x',1] = _b[diff_logmeanwks]
	matrix scramble_ols_base[`x',2] = _se[diff_logmeanwks]
	matrix scramble_ols_base[`x',3] = e(N)
	matrix scramble_ols_base[`x',4] = e(r2)

	qui reghdfe qdk1_logunemp_rate_laus diff_logmeanwks diff_logprod_all if inrange(year,2005,2012), absorb(pair_id_numeric) cluster(bordersegment)
	matrix scramble_ols_prod[`x',1] = _b[diff_logmeanwks]
	matrix scramble_ols_prod[`x',2] = _se[diff_logmeanwks]
	matrix scramble_ols_prod[`x',3] = _b[diff_logprod_all]
	matrix scramble_ols_prod[`x',4] = _se[diff_logprod_all]
	matrix scramble_ols_prod[`x',5] = e(N)
	matrix scramble_ols_prod[`x',6] = e(r2)

	cd "${maindirectory}"
	display "Scramble `x' of 200 done"

	restore, preserve
}
restore

// Save the OLS scramble distributions to output/.
// Scrambles_OLS_baseline.csv: 200 rows x 4 cols = [coef, se, N, R^2] per scramble
// Scrambles_OLS_prodall.csv:  200 rows x 6 cols = [b_coef, b_se, prod_coef, prod_se, N, R^2]
clear
svmat scramble_ols_base
qui outsheet using "${latexdir}Scrambles_OLS_baseline.csv", comma nonames replace

clear
svmat scramble_ols_prod
qui outsheet using "${latexdir}Scrambles_OLS_prodall.csv", comma nonames replace

cd "${CodeDirec}"
