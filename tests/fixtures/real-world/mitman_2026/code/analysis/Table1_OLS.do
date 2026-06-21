do "config.do"
global CodeDirec ="${code}/analysis/"
global DataControls "UIMacro_DataControls"
global WageData = "${Wages}"
global CurrentData "UIMacro_RevisionData.dta"
global maindirectory "${processed}/"
global outdirectory "${tables}/"   // outreg2 cross-check tex/txt

cd ${maindirectory}
use ${DataControls}, clear

la var diff_logmeanwks "Benefits"
la var diff_logmeanwks_pf "Perfect Foresight Benefits"
la var qdk1_logunemp_rate_laus "Unemp"
la var qdk1_logunemp_add "Unemp - No Add"
la var diff_logprod_all "State GDP per Worker"
cd ${outdirectory}

global TableName = "Table1OLS.tex"

// In addition to the existing outreg2 Table1OLS.tex output (kept as a
// cross-check artifact), collect each regression's result as a row of
// table1_ols and write a clean CSV at the end. Layout per row:
//   [b_coef, b_se, control_coef, control_se, N, R^2]
// Row mapping to paper tab:Benefits_on_unemp_OLS columns:
//   row 1 -> Col 1 (baseline)
//   row 2 -> Col 2 (+ State GDP per Worker, diff_logprod_all_old)
//   row 3 -> Col 5 (emp_share<0.15)
//   row 4 -> Col 6 (industry_low: l2 industry-distance <= median)
//   row 5 -> Col 7 (dist<30)
//   row 6 -> Col 8 (samecbsa==1)
//   row 7 -> Col 9 (perfect-foresight benefits, RHS = diff_logmeanwks_pf)
matrix table1_ols = J(8, 6, .)

reghdfe qdk1_logunemp_rate_laus diff_logmeanwks  if inrange(year,2005,2012) , abs(id  ) cluster(bordersegment)
outreg2 using $TableName, label replace keep(diff_logmeanwks )
matrix table1_ols[1,1] = _b[diff_logmeanwks]
matrix table1_ols[1,2] = _se[diff_logmeanwks]
matrix table1_ols[1,5] = e(N)
matrix table1_ols[1,6] = e(r2)

reghdfe qdk1_logunemp_rate_laus diff_logmeanwks diff_logprod_all if inrange(year,2005,2012) , abs(id  ) cluster(bordersegment)
outreg2 using $TableName, label append keep(diff_logmeanwks diff_logprod_all )
matrix table1_ols[2,1] = _b[diff_logmeanwks]
matrix table1_ols[2,2] = _se[diff_logmeanwks]
matrix table1_ols[2,3] = _b[diff_logprod_all]
matrix table1_ols[2,4] = _se[diff_logprod_all]
matrix table1_ols[2,5] = e(N)
matrix table1_ols[2,6] = e(r2)

reghdfe qdk1_logunemp_rate_laus diff_logmeanwks  if inrange(year,2005,2012) & emp_share<0.15 , abs(id  ) cluster(bordersegment)
outreg2 using $TableName, label append keep(diff_logmeanwks  )
matrix table1_ols[3,1] = _b[diff_logmeanwks]
matrix table1_ols[3,2] = _se[diff_logmeanwks]
matrix table1_ols[3,5] = e(N)
matrix table1_ols[3,6] = e(r2)

reghdfe qdk1_logunemp_rate_laus diff_logmeanwks  if inrange(year,2005,2012) & industry_low==1 , abs(id  ) cluster(bordersegment)
outreg2 using $TableName, label append keep(diff_logmeanwks  )
matrix table1_ols[4,1] = _b[diff_logmeanwks]
matrix table1_ols[4,2] = _se[diff_logmeanwks]
matrix table1_ols[4,5] = e(N)
matrix table1_ols[4,6] = e(r2)

reghdfe qdk1_logunemp_rate_laus diff_logmeanwks  if inrange(year,2005,2012) & dist<30 , abs(id  ) cluster(bordersegment)
outreg2 using $TableName, label append keep(diff_logmeanwks  )
matrix table1_ols[5,1] = _b[diff_logmeanwks]
matrix table1_ols[5,2] = _se[diff_logmeanwks]
matrix table1_ols[5,5] = e(N)
matrix table1_ols[5,6] = e(r2)

reghdfe qdk1_logunemp_rate_laus diff_logmeanwks  if inrange(year,2005,2012) & samecbsa==1 , abs(id  ) cluster(bordersegment)
outreg2 using $TableName, label append keep(diff_logmeanwks  )
matrix table1_ols[6,1] = _b[diff_logmeanwks]
matrix table1_ols[6,2] = _se[diff_logmeanwks]
matrix table1_ols[6,5] = e(N)
matrix table1_ols[6,6] = e(r2)

reghdfe qdk1_logunemp_rate_laus diff_logmeanwks_pf  if inrange(year,2005,2012) , abs(id  ) cluster(bordersegment)
outreg2 using $TableName, label append keep(diff_logmeanwks_pf  )
matrix table1_ols[7,1] = _b[diff_logmeanwks_pf]
matrix table1_ols[7,2] = _se[diff_logmeanwks_pf]
matrix table1_ols[7,5] = e(N)
matrix table1_ols[7,6] = e(r2)


// Save the matrix as a CSV that make_tables.py can read.
preserve
clear
svmat table1_ols
qui outsheet using "${latexdir}Table1_OLS_reghdfe.csv", comma nonames replace
restore

