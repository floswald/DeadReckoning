* ---------------------------------------------------------------------------
* Endog_Bartik_Scrambles.do  ->  output/factor_results/Scrambles_IV_bartik.csv
*
* §sec:endogeneity_test, the "power of the test" paragraph (~L935). The endogeneity
* test (add Bartik-instrumented state unemployment as a 2nd regressor) is run on the
* 200 SCRAMBLED "border" samples, where random pairing mechanically introduces the
* very endogeneity the test is meant to detect. Paper:
*   "...reveals a highly significant coefficient of -2.234 (p 0) on this variable and
*    leads to a substantial change of the coefficient on benefits from 0.107 (p 0) to
*    -0.069 (p 0.31). ... reveals the power of the test."
*
* So on scrambled samples: the benefits coef (without control) is the upward-biased
* 0.107 (already reproduced as ~0.106 = mean of Scrambles_OLS_baseline.csv); adding the
* IV control drives it to -0.069 and the chi on instrumented state unemployment is
* -2.234. p-values are the kit's one-sided (directional) convention applied to the
* 200-scramble distribution.
*
* STANDALONE: it replays the
* SAME 200 scrambles as OutputDataSetsUIMacro_Scrambles.do (identical seed 85237940 and
* generation method, so the pairings match Table 1 Cols 3-4) but runs ONLY the IV
* regressions -- it does NOT regenerate the 200x~1100 scramble QBLS files. Per scramble:
*   reghdfe qdk1_logunemp_rate_laus diff_logmeanwks                  (no control -> 0.107)
*   xtivreg qdk1_logunemp_rate_laus diff_logmeanwks (did_stateu = did_bartik), fe
*                                                    (-> benefits -0.069, did_stateu -2.234)
* did_stateu / did_bartik built as in Endog_Bartik.do (time-diff of the cross-pair diff
* in log state unemployment / Bartik state shock).
*
* Output Scrambles_IV_bartik.csv: 200 rows x 4 cols =
*   [benefits_noctrl, benefits_iv, did_stateu_iv, N].
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec     = "${code}/exporters/"
global CurrentData "UIMacro_RevisionData.dta"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"

set more off, perm

cd "$maindirectory"
use ${CurrentData}, clear
keep fipsnumeric quarter_index county_index logmeanwks* logunemp* logxstate* bartik_state seprate year quarter fipsstate pair_id_numeric

* ---- generate the 200 scrambles (identical seed/method to the kit Scrambles exporter) ----
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

* ---- loop: per scramble, build the IV regressors and run the endogeneity test ----
matrix scramble_iv = J(200, 4, .)   // [benefits_noctrl, benefits_iv, did_stateu_iv, N]
preserve
forvalues x=1/200{

	qui replace pair_id_numeric = new_pair_id`x'
	qui replace county_index    = new_county_index`x'

	* cross-pair differences (across the two counties of a scrambled pair)
	sort pair_id_numeric quarter_index county_index
	foreach var of varlist logmeanwks logunemp_rate_laus logxstate_unemp bartik_state {
		capture drop diff_`var'
		qui by pair_id_numeric quarter_index: gen diff_`var' = `var'[1] - `var'[2]
	}

	* 1-period quasi-difference of unemployment (LHS)
	sort pair_id_numeric county_index quarter_index
	capture drop f1_logunemp_rate_laus
	capture drop qdk1_logunemp_rate_laus
	qui by pair_id_numeric county_index: gen f1_logunemp_rate_laus = diff_logunemp_rate_laus[_n+1]
	qui by pair_id_numeric county_index: gen qdk1_logunemp_rate_laus = ///
		diff_logunemp_rate_laus - ((0.99*(1-seprate))^1)*f1_logunemp_rate_laus

	keep if county_index==1
	qui duplicates drop pair_id_numeric quarter_index, force

	* time-differences: the (instrumented) change in cross-pair state unemployment
	sort pair_id_numeric quarter_index
	capture drop did_stateu
	capture drop did_bartik
	qui by pair_id_numeric: gen did_stateu = diff_logxstate_unemp[_n] - diff_logxstate_unemp[_n-1]
	qui by pair_id_numeric: gen did_bartik = diff_bartik_state[_n]   - diff_bartik_state[_n-1]

	xtset pair_id_numeric quarter_index

	* benefits without the control (the upward-biased scrambled estimate ~0.107)
	qui reghdfe qdk1_logunemp_rate_laus diff_logmeanwks if inrange(year,2005,2012), ///
		absorb(pair_id_numeric)
	matrix scramble_iv[`x',1] = _b[diff_logmeanwks]

	* add Bartik-instrumented change in state unemployment (chi) -> benefits, did_stateu
	capture xtivreg qdk1_logunemp_rate_laus diff_logmeanwks (did_stateu = did_bartik) ///
		if inrange(year,2005,2012), fe
	if _rc==0 {
		matrix scramble_iv[`x',2] = _b[diff_logmeanwks]
		matrix scramble_iv[`x',3] = _b[did_stateu]
		matrix scramble_iv[`x',4] = e(N)
	}

	display "Scramble `x' of 200 done"
	restore, preserve
}
restore

* ---- save the 200-scramble distribution ----
clear
svmat scramble_iv
rename scramble_iv1 benefits_noctrl
rename scramble_iv2 benefits_iv
rename scramble_iv3 did_stateu_iv
rename scramble_iv4 Nobs
qui outsheet using "${latexdir}Scrambles_IV_bartik.csv", comma replace

* ---- report means + one-sided p (kit convention) across scrambles ----
foreach v in benefits_noctrl benefits_iv did_stateu_iv {
	qui sum `v'
	scalar m_`v'   = r(mean)
	qui count if `v'>0 & !missing(`v')
	scalar fgt0 = r(N)
	qui count if !missing(`v')
	scalar ntot = r(N)
	scalar p_`v' = min(fgt0/ntot, 1-fgt0/ntot)
	di as txt "`v': mean=" as res %8.4f m_`v' as txt "  frac>0=" as res %5.3f (fgt0/ntot) as txt "  one-sided p=" as res %5.3f p_`v'
}
di as txt "(targets: benefits_noctrl ~0.107 p0 ; benefits_iv -0.069 p0.31 ; did_stateu -2.234 p0)"
