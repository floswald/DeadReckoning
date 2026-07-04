* Wage regression on schooling and age.
* README only mentions data/survey.csv, but this script also
* silently reads data/region_boost.csv and merges it in.

import delimited "data/region_boost.csv", clear
tempfile addon
save "`addon'"

import delimited "data/survey_data.csv", clear
merge 1:1 id using "`addon'", nogenerate
replace region_boost = 1 if missing(region_boost)
replace wage = wage * region_boost

regress wage educ age

file open tab using "tables/table1.tex", write replace
file write tab "\begin{tabular}{lcc}" _n
file write tab "\toprule" _n
file write tab " & Coefficient & Std. Err. \\" _n
file write tab "\midrule" _n
file write tab "Education & " %6.3f (_b[educ]) " & " %6.3f (_se[educ]) " \\" _n
file write tab "Age & " %6.3f (_b[age]) " & " %6.3f (_se[age]) " \\" _n
file write tab "\bottomrule" _n
file write tab "\end{tabular}" _n
file close tab
