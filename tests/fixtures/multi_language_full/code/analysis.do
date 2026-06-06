ssc install reghdfe, replace

use "/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.dta", clear
keep if !missing(wage)

scatter wage age
graph export "fig_stata.pdf", replace
