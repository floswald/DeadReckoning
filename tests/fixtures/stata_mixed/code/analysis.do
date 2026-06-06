* analysis.do
ssc install reghdfe, replace

use "/Users/jsmith/Dropbox/stata_project/data/lfs_2019.dta", clear
keep if !missing(wage)
reghdfe log_wage age education, absorb(industry) vce(robust)

scatter wage age
graph export "fig1.pdf", replace
outreg2 using "tables/tab1.tex", tex replace
