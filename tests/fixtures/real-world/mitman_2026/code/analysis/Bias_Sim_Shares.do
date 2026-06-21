* ---------------------------------------------------------------------------
* Bias_Sim_Shares.do  ->  output/factor_results/Bias_Sim_Shares.csv
*
* §calibration_bias (~L1960): the county employment-share facts underlying the
* calibration-bias simulation. The paper sets the county<->state productivity
* correlation to 0.02 for border counties accounting for <15% of state employment
* (1,113 counties, avg 2%) and to 0.35 for those >=15% (59 counties, avg 35%), then
* simulates the model to show the induced bias is small (estimate 0.0569 vs true
* 0.0532). Here we reproduce the DATA FACTS (counts + average shares); the 0.0569
* simulation itself is a model-section output.
*
* emp_share = the border county's share of its state's employment (already in
* DataControls; it is the variable the EmpShare Table-1 pairing cuts on at 0.15).
* One county per pair (county_index==1); the two groups partition the 1,172 pairs.
* ---------------------------------------------------------------------------

do "config.do"
global maindirectory "${processed}/"
global DataControls "UIMacro_DataControls"
global latexdir "${factor_csv}/"
set more off, perm

cd "$maindirectory"
use ${DataControls}.dta, clear
keep if county_index==1
collapse (mean) emp_share, by(pair_id_numeric)
drop if missing(emp_share)

count if emp_share<0.15
scalar n_small = r(N)
qui sum emp_share if emp_share<0.15
scalar avg_small = r(mean)

count if emp_share>=0.15
scalar n_large = r(N)
qui sum emp_share if emp_share>=0.15
scalar avg_large = r(mean)

di as txt "================ Bias-simulation county shares ================"
di as txt "  <15% of state emp:  n=" as res n_small as txt " (paper 1,113), avg=" as res %4.1f 100*avg_small as txt "% (paper 2%)"
di as txt "  >=15% of state emp: n=" as res n_large as txt " (paper 59), avg="    as res %4.1f 100*avg_large as txt "% (paper 35%)"
di as txt "==============================================================="

file open f using "${latexdir}Bias_Sim_Shares.csv", write replace
file write f "group,n_counties,avg_share_pct,published_n,published_avg_pct" _n
file write f "lt15pct,"  (n_small) "," (100*avg_small) ",1113,2"  _n
file write f "ge15pct,"  (n_large) "," (100*avg_large) ",59,35"   _n
file close f
