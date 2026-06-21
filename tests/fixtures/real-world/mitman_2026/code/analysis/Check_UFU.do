// Reproduces the §4.2 "Under the Hood of the Quasi-Difference" inline
// coefficients (paper text mentions 0.418 and 0.406). The methodology:
//   1. Run regife on qdk1_logunemp ~ diff_logmeanwks with 2 factors
//      (i.e., Bench Col 1) and save the time factors (fq1, fq2) and
//      pair loadings (fid1, fid2) as variables on the panel.
//   2. With those factors held fixed, run two follow-up OLS regressions
//      where the pair-specific loadings are re-estimated as absorbed
//      pair-x-factor interactions:
//          reghdfe LHS diff_logmeanwks, abs(c.fq1#i.id c.fq2#i.id) cluster(bordersegment)
//      for LHS = diff_logunemp_rate_laus (current period u_t) and
//      LHS = f1_logunemp_rate_laus (lead u_{t+1}).
//

do "config.do"
global CodeDirec ="${code}/analysis/"
global DataControls "UIMacro_DataControls"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"

cd ${maindirectory}
use ${DataControls}, clear

xtset id quarter_index

capture drop fid* fq* fac1 fac2

// Step 1: Bench Col 1 IFE; save factors fq1/fq2 and loadings fid1/fid2.
regife qdk1_logunemp_rate_laus diff_logmeanwks if inrange(year,2005,2012), ///
    f(fid=id fq=quarter_index,2) noconst

// Optional: an additive-controls variant, kept as a cross-check (not the
// spec used for the published numbers).
gen fac1=fid1*fq1
gen fac2=fid2*fq2
reg diff_logunemp_rate_laus diff_logmeanwks fac1 fac2 if inrange(year,2005,2012), noconst
reg f1_logunemp_rate_laus   diff_logmeanwks fac1 fac2 if inrange(year,2005,2012), noconst

// Step 2: factors-fixed, loadings-re-estimated decomposition with
// clustered SE.  These are the regressions that produce the published
// 0.418 and 0.406 numbers in §4.2.
matrix check_ufu = J(2, 4, .)

reghdfe diff_logunemp_rate_laus diff_logmeanwks if inrange(year,2005,2012), ///
    abs(c.fq1#i.id c.fq2#i.id) cluster(bordersegment)
scalar p_diff = ttail(e(df_r), abs(_b[diff_logmeanwks]/_se[diff_logmeanwks]))
matrix check_ufu[1,1] = _b[diff_logmeanwks]
matrix check_ufu[1,2] = _se[diff_logmeanwks]
matrix check_ufu[1,3] = p_diff
matrix check_ufu[1,4] = e(N)

reghdfe f1_logunemp_rate_laus diff_logmeanwks if inrange(year,2005,2012), ///
    abs(c.fq1#i.id c.fq2#i.id) cluster(bordersegment)
scalar p_lead = ttail(e(df_r), abs(_b[diff_logmeanwks]/_se[diff_logmeanwks]))
matrix check_ufu[2,1] = _b[diff_logmeanwks]
matrix check_ufu[2,2] = _se[diff_logmeanwks]
matrix check_ufu[2,3] = p_lead
matrix check_ufu[2,4] = e(N)

// Layout per row: [coef, se, one-sided p, N]; row 1 = u_t, row 2 = u_{t+1}.
// One-sided (directional) p matches the paper's standing convention; the
// values are ~1e-8 so the conclusion is unaffected by the choice.
preserve
clear
svmat check_ufu
qui outsheet using "${latexdir}Check_UFU.csv", comma nonames replace
restore
