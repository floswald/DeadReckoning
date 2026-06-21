* ---------------------------------------------------------------------------
* Derived_Policy_Calcs.do  ->  output/factor_results/Derived_Policy_Calcs.csv
*
* Reproduces the DERIVED inline policy-scenario numbers in the paper -- closed-form
* extrapolations of the benchmark estimates via the model formulas (no new factor-model
* runs). Four groups:
*
* (A) Permanent unanticipated 26->99-week extension (eq:partial_sum, n=infinity),
*     §baseline_results (~L780) + footnote + employment analog (~L1081):
*       permanent multiplier  = alpha / (1 - beta(1-s))                       -> 0.488
*       permanent log-effect  = mult * (log(99) - log(26))                    -> 0.653
*       long-run u            = 5% * exp(log-effect)                          -> 9.6%
*       long-run employment   = 1 - u                                95% ->   -> 90.4%  (4.6pp)
*     alpha = 0.0532 (benchmark Table 1 Col 1), s = 0.10 (avg JOLTS quarterly sep),
*     beta = 0.99.
*
* (B) Tightness -> unemployment decomposition, §macro_effects (~L1055): with matching
*     function f = mu*theta^(1-gamma), the benefit-induced change in u (via tightness)
*       Du = (1-u)(1-gamma) * |tightness coef|                                -> 0.0528
*     tightness coef = 0.101 (tab:Benefits_on_JobCreation), gamma = 0.45, u = 0.05.
*
* (C) Perfect-foresight scenario, §baseline_results (~L776) + intro (~L247): if 26-week
*     durations had prevailed, u in 2010 / 2011 would have been 3.02 / 2.15 pp lower.
*     Computed as the discounted forward sum of the
*     national perfect-foresight log-benefit deviation, evaluated at the start (Q1) of
*     each year, times alpha, converted to a level pp change u*(1-exp(-effect)):
*       partial_sum_t = sum_{m>=0} [prod 0.99(1-s)] * (log(weeks_pf_{t+m}) - log(26))
*       effect_t      = alpha * partial_sum_t
*       pp_t          = u_act_t * (1 - exp(-effect_t))
*     Inputs: benefit_weeks.dta (pf_meanwks, perfect-foresight weeks) + jolts2013.dta (agg sep
*     rate), both public, in $maindirectory. Actual national annual u: 2010=9.6, 2011=8.9.
*
* (D) Discount-factor robustness (0.484 / 0.491 at beta=0.9975 / 0.98) is NOT reproduced
*     here: per the paper footnote it RE-ESTIMATES alpha under each beta (the quasi-
*     difference discount changes), so it needs two new factor-model runs, not a derived
*     calc. The beta=0.99 baseline 0.488 is the (A) multiplier above.
* ---------------------------------------------------------------------------

do "config.do"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"
set more off, perm

* ---- shared parameters ----
scalar alpha = 0.0532          // benchmark effect of benefits on unemployment (Col 1)
scalar beta  = 0.99
scalar s     = 0.10            // avg quarterly JOLTS separation rate
scalar u0    = 0.05            // equilibrium u with 26 weeks
scalar w1    = 26
scalar w2    = 99

* ===== (A) permanent 26->99 extension =====
scalar perm_mult   = alpha/(1-beta*(1-s))
scalar perm_logeff = perm_mult*(ln(w2)-ln(w1))
scalar u_perm      = u0*exp(perm_logeff)
scalar emp_base    = 1-u0
scalar emp_perm    = 1-u_perm

* ===== (B) tightness -> unemployment decomposition =====
scalar tight_coef = 0.101
scalar gamma      = 0.45
scalar du_tight   = (1-u0)*(1-gamma)*tight_coef

* ===== (C) perfect-foresight scenario (2010/2011) =====
use "${rawdata}/jolts2013.dta", clear
collapse jolts_agg_seprate_q, by(year quarter)
* perfect-foresight weeks now live in the consolidated benefit_weeks input
* (pf_meanwks, quarter-constant; one row per state-quarter kept, so the
* cross-state mean below is over exactly the same 51 state values as before)
preserve
use fipsstate year quarter pf_meanwks using "${rawdata}/benefit_weeks.dta", clear
bys fipsstate year quarter: keep if _n==1
rename pf_meanwks meanwks_pf
tempfile pfq
save `pfq'
restore
merge 1:m year quarter using `pfq'
keep if _merge==3
collapse meanwks_pf jolts_agg_seprate_q, by(year quarter)
drop if missing(meanwks_pf)
sort year quarter
gen tq = yq(year,quarter)
* pad the tail to 2019q4 with benefits back at 26 (log-deviation 0) so the forward sum
* converges (the perfect-foresight measure has returned to ~26 weeks by 2013q4-2014)
local lasts  = jolts_agg_seprate_q[_N]
local lasttq = tq[_N]
local nadd   = yq(2019,4)-`lasttq'
set obs `=_N+`nadd''
forvalues k=1/`nadd'{
	replace tq                  = `lasttq'+`k' if _n==_N-`nadd'+`k'
	replace meanwks_pf          = 26            if _n==_N-`nadd'+`k'
	replace jolts_agg_seprate_q = `lasts'       if _n==_N-`nadd'+`k'
}
replace year    = year(dofq(tq))
replace quarter = quarter(dofq(tq))
sort tq
replace meanwks_pf = ln(meanwks_pf)-ln(26)
gen cum_sep_0     = 0.99*(1-jolts_agg_seprate_q)
gen partial_sum_0 = meanwks_pf*cum_sep_0
forvalues tt=1/28{
	local y=`tt'-1
	gen cum_sep_`tt'     = 0.99*(1-jolts_agg_seprate_q[_n+`tt'])*cum_sep_`y'
	gen partial_sum_`tt' = partial_sum_`y'+meanwks_pf[_n+`tt']*cum_sep_`tt'
}
gen effect = alpha*partial_sum_28
gen uact   = .
replace uact = 9.6 if year==2010
replace uact = 8.9 if year==2011
gen pp = uact*(1-exp(-effect))
qui sum pp if year==2010 & quarter==1
scalar pp_2010 = r(mean)
qui sum pp if year==2011 & quarter==1
scalar pp_2011 = r(mean)

* ===== report + write CSV =====
di as txt "================ Derived policy-scenario calcs ================"
di as txt "(A) permanent 26->99:  mult="     as res %6.4f perm_mult   as txt " (paper 0.488)"
di as txt "    perm log-effect="              as res %6.4f perm_logeff as txt " ; long-run u=" as res %5.3f u_perm as txt " (paper 9.6%)"
di as txt "    employment "                   as res %5.3f emp_base   as txt " -> " as res %5.3f emp_perm as txt " (paper 95% -> 90.4%, 4.6pp)"
di as txt "(B) tightness->u:      Du="        as res %6.4f du_tight   as txt " (paper 0.0528)"
di as txt "(C) perfect foresight: 2010="      as res %5.3f pp_2010    as txt " pp ; 2011=" as res %5.3f pp_2011 as txt " pp (paper 3.02 / 2.15)"
di as txt "==============================================================="

file open f using "${latexdir}Derived_Policy_Calcs.csv", write replace
file write f "label,value,published" _n
file write f "permanent_multiplier,"        (perm_mult)        ",0.488" _n
file write f "permanent_log_effect,"        (perm_logeff)      ",0.65"  _n
file write f "permanent_u_pct,"             (100*u_perm)       ",9.6"   _n
file write f "permanent_emp_base_pct,"      (100*emp_base)     ",95"    _n
file write f "permanent_emp_pct,"           (100*emp_perm)     ",90.4"  _n
file write f "tightness_du,"                (du_tight)         ",0.0528" _n
file write f "perfect_foresight_2010_pp,"   (pp_2010)          ",3.02"  _n
file write f "perfect_foresight_2011_pp,"   (pp_2011)          ",2.15"  _n
file close f
