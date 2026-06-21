* ---------------------------------------------------------------------------
* TableA2.do  ->  paper app_tab:A-1
* "County Unemployment and Employment as a Function of Pair County and State"
*
* The Hall (2013) "alternative endogeneity test" robustness check: regress a
* county's own variable on the ADJACENT (out-of-state pair) county's variable
* and the STATE-level variable, in 2007, in logs of the level. A large state
* coefficient is shown NOT to indicate LAUS imputation, because the same
* pattern appears in QCEW employment (not subject to imputation).
*
* Produces the paper's app_tab:A-1 (the script name says A2; the exhibit label is A-1).
*
* Three regressions:
*   (rate)  unemp_rate_laus     on other-county rate + state rate   -> the
*           INLINE Hall numbers in the text (state ~0.951, adjacent ~0.316),
*           displayed but not tabulated here.
*   Col 1   logunemp_count_laus on other-county + state (log levels) -> table.
*   Col 2   logqcew_emp         on other-county + state (log levels) -> table.
*
* NOTE for the data editor: the paper text (§ Alternative Endogeneity Test) says
* the employment column uses "QWI employment", but the code regresses QCEW
* employment (logqcew_emp). Flagged in discoveries_lite.tex.
*
* Dependencies: ${CurrentData} (un-differenced, both counties) and
* StateQuarterlyU.dta (state quarterly unemployment: state_ur_u_pre,
* state_uc_u_pre), copied into ${rawdata}/ from
* ${rawdata}/. The original also merged
* claims_quarterly.dta, but that feeds only the inline continuing-claims
* numbers (state ~1.121, adjacent ~0.415), whose regression is not in this
* script, so it is omitted here.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/analysis/"
global CurrentData "UIMacro_RevisionData.dta"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"

set more off, perm
cap log close

cd "${maindirectory}"
use ${CurrentData}, clear

* State quarterly unemployment (state_ur_u_pre = rate, state_uc_u_pre = count).
merge m:1 fipsstate year quarter using "${rawdata}/StateQuarterlyU"
drop if _merge==2
drop _merge

* Log levels (create if the build did not already carry them).
capture gen logunemp_count_laus = log(unemp_count_laus)
capture gen logqcew_emp        = log(qcew_emp)
gen logstate_uc                = log(state_uc_u_pre)
capture gen logstate_qcew_emp  = log(state_qcew_emp)

* --- "Other county" = adjacent out-of-state pair county. Within each
*     pair-quarter the two rows are county_index 1 and 2; assign each county
*     the OTHER one's value. ---
sort pair_id_numeric quarter_index county_index

by pair_id_numeric quarter_index: gen cur1 = unemp_rate_laus[1]
by pair_id_numeric quarter_index: gen cur2 = unemp_rate_laus[2]
gen othercur = cur1 if county_index==2
replace othercur = cur2 if county_index==1

by pair_id_numeric quarter_index: gen cuc1 = logunemp_count_laus[1]
by pair_id_numeric quarter_index: gen cuc2 = logunemp_count_laus[2]
gen othercuc = cuc1 if county_index==2
replace othercuc = cuc2 if county_index==1

by pair_id_numeric quarter_index: gen cec1 = logqcew_emp[1]
by pair_id_numeric quarter_index: gen cec2 = logqcew_emp[2]
gen othercec = cec1 if county_index==2
replace othercec = cec2 if county_index==1

* ===== Regressions (2007 cross-section) =====
matrix A2 = J(2,6,.)

* Inline Hall numbers (rate spec, app:Hall_endogeneity ~L2162): state ~0.951, adjacent ~0.316.
reg unemp_rate_laus othercur state_ur_u_pre if year==2007
scalar b_oth_laus = _b[othercur]
scalar se_oth_laus = _se[othercur]
scalar b_st_laus = _b[state_ur_u_pre]
scalar se_st_laus = _se[state_ur_u_pre]

* Col 1: county log unemployment count.
reg logunemp_count_laus othercuc logstate_uc if year==2007
matrix A2[1,1]=_b[othercuc]
matrix A2[1,2]=_se[othercuc]
matrix A2[1,3]=_b[logstate_uc]
matrix A2[1,4]=_se[logstate_uc]
matrix A2[1,5]=e(N)
matrix A2[1,6]=e(r2)

* Col 2: county log QCEW employment.
reg logqcew_emp othercec logstate_qcew_emp if year==2007
matrix A2[2,1]=_b[othercec]
matrix A2[2,2]=_se[othercec]
matrix A2[2,3]=_b[logstate_qcew_emp]
matrix A2[2,4]=_se[logstate_qcew_emp]
matrix A2[2,5]=e(N)
matrix A2[2,6]=e(r2)

* Write CSV: row 1 = unemployment column, row 2 = employment column;
* cols = [b_other, se_other, b_state, se_state, N, R2].
preserve
clear
quietly set obs 2
svmat A2
outsheet using "${latexdir}LAUS_Imputation.csv", comma nonames replace
restore

* ===== Inline Hall test on continuing claims / population (app:Hall_endogeneity ~L2164) =====
* "the same regression with continuing claims divided by population". Published state
* coefficient 1.121 / adjacent 0.415. The producing script was lost; this reconstruction
* uses the ALL-COUNTY state aggregate (chosen construction) and yields state ~0.89 /
* adjacent ~0.31 -- close to the LAUS values above and reproducing the paper's conclusion
* (claims, which are not imputed, show the same large-state pattern). The exact published
* magnitudes depend on the unrecovered original state-claims/pop construction -- see
* discoveries_lite.tex. cont_claims from claims_quarterly.dta (county, all U.S.
* counties), popestimate from population_age.dta (annual county population).
tempfile lausdata
save `lausdata'

use "${rawdata}/claims_quarterly.dta", clear
merge m:1 fipsnumeric year using "${rawdata}/population_age.dta", keep(match) keepusing(popestimate) nogen
gen fipsstate = floor(fipsnumeric/1000)
gen claimspop = cont_claims/popestimate
* all-county state aggregate: sum continuing claims (quarterly) / sum population (annual)
preserve
	bysort fipsnumeric year: keep if _n==1
	collapse (sum) state_pop=popestimate, by(fipsstate year)
	tempfile sp
	save `sp'
restore
preserve
	collapse (sum) state_cc=cont_claims, by(fipsstate year quarter)
	merge m:1 fipsstate year using `sp', keep(match) nogen
	gen state_claimspop = state_cc/state_pop
	keep fipsstate year quarter state_claimspop
	tempfile st
	save `st'
restore
keep fipsnumeric year quarter claimspop
tempfile cp
save `cp'

use `lausdata', clear
merge m:1 fipsnumeric year quarter using `cp', keep(master match) nogen
merge m:1 fipsstate year quarter using `st', keep(master match) nogen
sort pair_id_numeric year quarter county_index
by pair_id_numeric year quarter: gen cp1 = claimspop[1]
by pair_id_numeric year quarter: gen cp2 = claimspop[2]
gen othercp = cp1 if county_index==2
replace othercp = cp2 if county_index==1

reg claimspop othercp state_claimspop if year==2007
scalar b_oth_cl = _b[othercp]
scalar se_oth_cl = _se[othercp]
scalar b_st_cl = _b[state_claimspop]
scalar se_st_cl = _se[state_claimspop]

di as txt "==== Hall inline numbers ===="
di as txt "  LAUS  (rate):  state=" as res %5.3f b_st_laus as txt " (se " as res %5.3f se_st_laus as txt "), adjacent=" as res %5.3f b_oth_laus as txt " (se " as res %5.3f se_oth_laus as txt ")  [paper 0.951/0.316]"
di as txt "  Claims/pop:    state=" as res %5.3f b_st_cl   as txt " (se " as res %5.3f se_st_cl   as txt "), adjacent=" as res %5.3f b_oth_cl   as txt " (se " as res %5.3f se_oth_cl   as txt ")  [paper 1.121/0.415; all-county aggregate]"

* CSV: row 1 = LAUS rate spec, row 2 = claims/pop spec; cols = [b_other, se_other, b_state, se_state].
file open f using "${latexdir}Hall_Inline.csv", write replace
file write f "spec,b_adjacent,se_adjacent,b_state,se_state,published_state,published_adjacent" _n
file write f "laus_rate,"  (b_oth_laus) "," (se_oth_laus) "," (b_st_laus) "," (se_st_laus) ",0.951,0.316" _n
file write f "claims_pop," (b_oth_cl)   "," (se_oth_cl)   "," (b_st_cl)   "," (se_st_cl)   ",1.121,0.415" _n
file close f

cd "${CodeDirec}"
