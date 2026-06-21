do "config.do"
global CodeDirec ="${code}/analysis/"
global DataControls "UIMacro_DataControls"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"

cd ${maindirectory}
use ${DataControls}, clear


// Lead of diff_logsnap was used in the original Controls bundle; not used
// here for the OLS Col 10 (we follow the BBCEA variant: 9 controls,
// no Fsnap, no diff_bbce2018). Generate just in case any of the controls
// require it; safe no-op if unused.

la var diff_logmeanwks "Benefits"
la var diff_logawardamount_gdp "Stimulus (GDP)"
la var diff_logtotal_gdp "Total Tax (GDP)"
la var diff_logincome_gdp "Income Tax (GDP)"
la var diff_loggeneral_sales_gdp "Sales Tax (GDP)"
la var diff_sbsi "SBSI"
la var diff_sbtc "SBTC"
la var diff_bhi "BHI"
la var diff_judicial "Foreclosure (judicial dummy)"
la var diff_bbce_asset2018 "SNAP Broad Eligibility"

// OLS regression matching the IFE Controls Col 10 spec, using the
// same 9 GDP-normalized state policy controls.
reghdfe qdk1_logunemp_rate_laus diff_logmeanwks ///
	diff_logawardamount_gdp diff_sbsi diff_sbtc diff_bhi ///
	diff_logtotal_gdp diff_logincome_gdp diff_loggeneral_sales_gdp ///
	diff_judicial diff_bbce_asset2018 ///
	if inrange(year,2005,2012), absorb(id) cluster(bordersegment)

// Save a single-row 1x4 CSV: [coef, se, N, R^2] for the benefits coefficient.
// The 9 control coefficients are not used in paper Col 10 (only the
// benefits headline is shown in tab:Benefits_on_unemp_OLS).
matrix table1_ols_col10 = (_b[diff_logmeanwks], _se[diff_logmeanwks], e(N), e(r2))

preserve
clear
svmat table1_ols_col10
qui outsheet using "${latexdir}Table1_OLS_Controls.csv", comma nonames replace
restore
