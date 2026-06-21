* ---------------------------------------------------------------------------
* MO_Tightness_Figures.do  ->  the Missouri tightness-dynamics figures
*   fig:MO_All_Borders     -> motight_pooled.pdf
*   fig:MO_Each_Border     -> motight_all.pdf
*   fig:motight_border{11,46,52,56,59,81,82,83} -> motight_border{l}.pdf
*   (inside fig:MO_vacPuD and fig:Tightness_MO_Borders)
*
* For each Missouri state border (MO = fipsstate 29 vs the neighbor), plots the
* cross-border difference in log labor-market tightness (V/U), binscattered against
* quarters-since-the-April-2011 benefit-duration cut (rdtime = quarter_index - 26),
* over the window 2010Q2 .. 2012Q1. Missouri is county_index2==1, so the difference
* is log tightness_MO - log tightness_neighbor.
*
* *** VACANCY-GATED *** (uses the proprietary vacancy data): tightness uses
* total_vacancies_state (state-level HWOL vacancies). The input
* StateMonthlyBorderData_2018_07_25.dta is the proprietary state-level border panel
* (referenced in place under ${proprietary}, not copied/shipped). Reproduces the
* published figures with the real data; a synthetic state-vacancy panel would be
* needed to ship these figures (the county-level synthetic path does not cover this
* state-aggregated input).
*
* Figures are written bare into output/figures/ (flat-folder convention; the paper's
* \includegraphics use bare names, dropping figures/Missouri/). Needs `binscatter`.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec   ="${code}/analysis/"
global proprietary "${synthetic}/" // synthetic stand-in for the proprietary state-vacancy panel
global maindirectory "${processed}/"
if "${latexdir}"=="" global latexdir "${factor_csv}/"
* State-border-panel switch: default = the real (proprietary-vacancy) file. For a
* shippable synthetic run, build code/build/Make_Synthetic_StateBorderData.do and set
*   global statefile "${rawdata}/StateMonthlyBorderData_synthetic.dta"
* (public state columns + summed synthetic county vacancies; figures are demonstrative).
if "${statefile}"=="" global statefile "${proprietary}StateMonthlyBorderData_2018_07_25.dta"

set more off, perm
cap log close

use "${statefile}", clear

* Keep border segments where one side is Missouri (fipsstate 29).
gen temp=0
replace temp = 1 if fipsstate==29
bys bordersegment: egen mopair=max(temp)
drop temp
keep if mopair==1

* Missouri = county_index2 1, neighbor = 2 (so cross-border diffs are MO - neighbor).
gen county_index2=2
replace county_index2=1 if fipsstate==29

collapse county_index2 total_vacancies_state state_labor_sa state_l_u_post meanwks ///
         year quarter pop state_unemp_count_sa, by(bordersegment fipsstate quarter_index)

gen time=quarter_index

* Labor-market tightness (V/U), vacancy rate (V/L), unemployment rate (U/L), and
* their cross-border log differences (MO - neighbor). Note ln(tight) = ln(vacrate) -
* ln(urate) since labor cancels, so diff_ltight = diff_lvac_sa - diff_lunemp -- the
* decomposition reported in tab:MO_V_U.
gen tight=total_vacancies_state/state_unemp_count_sa
gen vacrate_sa=total_vacancies_state/state_labor_sa
gen unemp=state_unemp_count_sa/state_labor_sa
sort bordersegment time county_index2
by bordersegment time: gen diff_ltight= ln(tight[1])- ln(tight[2])
by bordersegment time: gen diff_lvac_sa= ln(vacrate_sa[1])- ln(vacrate_sa[2])
by bordersegment time: gen diff_lunemp= ln(unemp[1])- ln(unemp[2])

* Quarters since the April-2011 cut (quarter_index 26 = the cut).
gen rdtime=time-26

* Window: 2010Q2 .. 2012Q1.
local window (year==2012 & quarter<2) | year==2011 | (year==2010 & quarter>1)

* Per-border figures.
levelsof bordersegment, local(levels)
foreach l of local levels {
    binscatter diff_ltight rdtime if bordersegment == `l' & (`window'), ///
        rd(-0.5) discrete graphregion(fcolor(white)) ///
        ytitle("Tightness") xtitle("Quarters since cut") scale(2)
    graph export "${figures}/motight_border`l'.pdf", replace
}

* Pooled across all Missouri borders.
binscatter diff_ltight rdtime if (`window'), ///
    rd(-0.5) discrete graphregion(fcolor(white)) ///
    ytitle("Tightness") xtitle("Quarters since cut") scale(2)
graph export "${figures}/motight_pooled.pdf", replace

* All borders overlaid, demeaned to their pre-cut (rdtime==-1) level.
gen blah=diff_ltight if rdtime==-1
bys bordersegment: egen pretight=min(blah)
gen dm_tight = diff_ltight-pretight
binscatter dm_tight rdtime if (`window'), by(bordersegment) ///
    rd(-0.5) discrete graphregion(fcolor(white)) ///
    ytitle("Tightness") xtitle("Quarters since cut") ///
    legend( region(lw(none) m(zero)) ring(0) cols(2) pos(11) ///
        lab(1 "AR") lab(2 "IL") lab(3 "IA") lab(4 "KS") lab(5 "KY") ///
        lab(6 "NE") lab(7 "OK") lab(8 "TN")) scale(2)
graph export "${figures}/motight_all.pdf", replace

* ---------------------------------------------------------------------------
* tab:MO_V_U -- the jump in log V/U at the April-2011 cut, decomposed into the
* vacancy rise and the unemployment decline, per border. The jump is the
* quarter-to-quarter change (did_*) in the cross-border log difference evaluated
* at the cut quarter (2011Q2 = quarter_index 26). Export one row per Missouri
* border for make_tables.py (MO_V_U.csv: bordersegment, tightness, vacancies,
* unemployment changes), sorted by bordersegment = AR,IL,IA,KS,KY,NE,OK,TN.
* ---------------------------------------------------------------------------
keep if county_index2==1
sort bordersegment time
by bordersegment: gen did_ltight  = diff_ltight[_n]  - diff_ltight[_n-1]
by bordersegment: gen did_lvac_sa = diff_lvac_sa[_n] - diff_lvac_sa[_n-1]
by bordersegment: gen did_lunemp  = diff_lunemp[_n]  - diff_lunemp[_n-1]

preserve
keep if quarter_index==26
sort bordersegment
outsheet bordersegment did_ltight did_lvac_sa did_lunemp using "${latexdir}MO_V_U.csv", comma replace nonames
restore

cd "${CodeDirec}"
