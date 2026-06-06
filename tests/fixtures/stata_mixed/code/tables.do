* tables.do — summary statistics
use "/Users/jsmith/Dropbox/stata_project/data/lfs_2019.dta", clear
tabulate education, gen(edu_d)
outreg2 using "tables/tab2.tex", tex replace
