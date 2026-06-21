* ---------------------------------------------------------------------------
* Endog_Vars.do  ->  paper tab:Endog_Vars
* "Unemployment Benefit Extensions and Unemployment, Controlling for
*  County-Level House Prices, Income, and Debt"
*
* Robustness check that adds (endogenous) county-level house prices, income and
* debt to the specification. Three columns, ALL estimated in Stata (clean, no Matlab):
*   Col 1  Factor Model : interactive fixed-effects (regife, 2 factors). regife
*                         reports no R^2, so it is computed here as 1 - SSR/SSY
*                         from the residuals (no constant), matching the factor-
*                         model R^2 definition used in the paper table.
*   Col 2  OLS          : reghdfe with county-pair fixed effects.
*   Col 3  IV-GLS       : ivreg2 instrumenting the house-price term with the
*                         Saiz land-supply elasticity (diff_elas) and the
*                         Wharton land-use regulation index (diff_wharton).
*                         The instruments are time-invariant MSA-level, so no
*                         fixed effects and a much smaller (MSA) sample.
*
* Controls (the "house prices, income, and debt" set):
*   diff_fhfa_lev  house prices (log FHFA HPI, pair difference)
*   diff_agi       income (IRS adjusted gross income)
*   diff_dti_high  debt (debt-to-income)
* All constructed in code/build/MakeDataControls.do. See discoveries_lite.tex for
* the control-set choice: the published 0.059/0.045/0.054 come from a
* hand-assembled set of runs whose exact spec was not preserved in one script.
*
* Dependencies (Stata user packages): regife, reghdfe, ivreg2.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/analysis/"
global DataControls "UIMacro_DataControls"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"

set more off, perm
cap log close

cd "${maindirectory}"
use ${DataControls}, clear
xtset id quarter_index

matrix EV = J(3,5,.)   // rows = cols 1-3; [coef, se, N, R2, n_factors]

* --- Col 1: Factor Model (interactive FE, 2 factors) ---
regife qdk1_logunemp_rate_laus diff_logmeanwks diff_fhfa_lev diff_agi diff_dti_high, ///
    f(id quarter_index, 2) noconst residuals(_res_rg)
* regife returns no R^2; compute 1 - SSR/SSY over the estimation sample (no constant)
qui gen double _y2  = qdk1_logunemp_rate_laus^2 if e(sample)
qui gen double _rr2 = _res_rg^2             if e(sample)
qui sum _rr2
scalar _ssr = r(sum)
qui sum _y2
scalar _ssy = r(sum)
matrix EV[1,1]=_b[diff_logmeanwks]
matrix EV[1,2]=_se[diff_logmeanwks]
matrix EV[1,3]=e(N)
matrix EV[1,4]= 1 - _ssr/_ssy
matrix EV[1,5]=2
qui drop _res_rg _y2 _rr2

* --- Col 2: OLS with county-pair fixed effects ---
reghdfe qdk1_logunemp_rate_laus diff_logmeanwks diff_fhfa_lev diff_agi diff_dti_high, ///
    abs(id) cluster(bordersegment)
matrix EV[2,1]=_b[diff_logmeanwks]
matrix EV[2,2]=_se[diff_logmeanwks]
matrix EV[2,3]=e(N)
matrix EV[2,4]=e(r2)

* --- Col 3: IV-GLS (house price instrumented by Saiz elasticity + Wharton index;
*     instruments are time-invariant MSA-level, so no fixed effects) ---
ivreg2 qdk1_logunemp_rate_laus diff_logmeanwks diff_agi diff_dti_high ///
    (diff_fhfa_lev = diff_elas diff_wharton)
matrix EV[3,1]=_b[diff_logmeanwks]
matrix EV[3,2]=_se[diff_logmeanwks]
matrix EV[3,3]=e(N)
matrix EV[3,4]=e(r2)

* Write CSV: row = column (1 Factor / 2 OLS / 3 IV); cols = [coef, se, N, R2, n_factors].
preserve
clear
quietly set obs 3
svmat EV
outsheet using "${latexdir}Endog_Vars.csv", comma nonames replace
restore

cd "${CodeDirec}"
