* analysis.do — main analysis script
* Requires: reghdfe, ftools (user-written ado-files)

* Install packages at project-local ado directory
ssc install reghdfe, replace
ssc install ftools, replace

* Load data — absolute path (bad practice, left over from author's machine)
use "/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.dta", clear

keep if !missing(wage)

* Run regression
reghdfe log_wage age education, absorb(industry) vce(robust)

* Plot — writes to working directory, not figures/ folder LaTeX expects
scatter wage age, title("Wage vs Age")
graph export "fig1.pdf", replace
