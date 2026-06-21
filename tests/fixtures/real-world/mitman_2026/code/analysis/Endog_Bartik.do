* ---------------------------------------------------------------------------
* Endog_Bartik.do  ->  output/factor_results/Endog_Bartik_real.csv
*
* Appendix §app:endogeneity_test_unemp (eq:endogenousFE_Bartik, ~L2161-2165), REAL
* sample. Second implementation of the Section-\ref{sec:endogeneity_test} endogeneity
* test: add the difference in the CHANGE in state unemployment -- instrumented with
* Bartik shocks -- as a second regressor (chi) alongside benefit weeks (alpha) in the
* additive-FE (pair fixed effects) specification. A near-zero, insignificant chi means
* the benchmark estimate of alpha is not contaminated by state-level conditions.
* Paper: chi (instrumented state unemployment) = -0.073, p-value 0.78; alpha (benefits)
* size/significance unaffected.
*
* did_stateu = time-diff of the cross-pair difference in log state unemployment
*              (a difference-in-differences of state unemployment, the endogenous Z).
* did_bartik = time-diff of the cross-pair difference in the Bartik state shock
*              (the excluded instrument). Both built on the fly; diff_logxstate_unemp
*              and diff_bartik_state are already in DataControls.
*
* Inference: residual cluster bootstrap over border segments (200 reps), holding the
* design fixed and resampling the FE-IV residuals by cluster (as in the original). The
* reported p is the NORMAL-based TWO-SIDED p (Stata estat bootstrap convention): this is
* a two-sided "is chi != 0" test, NOT the kit's one-sided directional convention used
* for the benefit coefficient elsewhere -- hence 0.78 (> 0.5) is expected.
*
* Output Endog_Bartik_real.csv: one row per coefficient
*   [name, observed_coef, boot_se, z, p_twosided], for benefits (alpha) and did_stateu (chi).
* ---------------------------------------------------------------------------

do "config.do"
global maindirectory "${processed}/"
global DataControls "UIMacro_DataControls"
global latexdir "${factor_csv}/"

set more off, perm
set seed 20180802

cd "$maindirectory"
use ${DataControls}.dta, clear

sort pair_id_numeric quarter_index
by pair_id_numeric: gen did_stateu = diff_logxstate_unemp[_n] - diff_logxstate_unemp[_n-1]
by pair_id_numeric: gen did_bartik = diff_bartik_state[_n]   - diff_bartik_state[_n-1]
keep if year>2004 & year<2013

xtset pair_id_numeric quarter_index

* ---- observed coefficients (FE-IV: instrument did_stateu with did_bartik) ----
xtivreg qdk1_logunemp_rate_laus diff_logmeanwks (did_stateu = did_bartik), fe
scalar obs_wks   = _b[diff_logmeanwks]
scalar obs_state = _b[did_stateu]
di as txt "OBSERVED: benefits(alpha)=" as res obs_wks as txt "  did_stateu(chi)=" as res obs_state

* residual + linear index for the residual bootstrap (design held fixed)
predict ehat,    ue
predict predvar, xb
keep bordersegment qdk1_logunemp_rate_laus diff_logmeanwks did_stateu did_bartik ///
     pair_id_numeric quarter_index ehat predvar
sort pair_id_numeric quarter_index
gen unique_id = _n
tempfile design
save "`design'"

* ---- residual cluster bootstrap over border segments (200 reps) ----
* pass the design tempfile path into the program via a global (tempfiles don't
* survive into a program's local scope)
global DESIGN "`design'"
capture program drop myboot
program define myboot, rclass
    preserve
    use "${DESIGN}", clear
    quietly {
        bsample, cluster(bordersegment) idcluster(newborder)
        sort newborder pair_id_numeric quarter_index
        replace unique_id = _n
        keep unique_id ehat newborder pair_id_numeric quarter_index
        rename ehat ehatresamp
        merge 1:1 unique_id using "${DESIGN}", keepusing(predvar diff_logmeanwks did_stateu did_bartik bordersegment)
        keep if _merge==3
        gen newid = newborder*100000 + pair_id_numeric
        gen LHSvar = predvar + ehatresamp
        xtset newid quarter_index
        capture xtivreg LHSvar diff_logmeanwks (did_stateu = did_bartik), fe
    }
    return scalar wkscoef   = _b[diff_logmeanwks]
    return scalar statecoef = _b[did_stateu]
    restore
end

simulate wkscoef=r(wkscoef) statecoef=r(statecoef), reps(200) seed(20180802): myboot

* ---- bootstrap SEs and two-sided normal p-values (estat-bootstrap convention) ----
quietly sum wkscoef
scalar se_wks = r(sd)
quietly sum statecoef
scalar se_state = r(sd)

scalar z_wks   = obs_wks   / se_wks
scalar z_state = obs_state / se_state
scalar p_wks   = 2*(1-normal(abs(z_wks)))
scalar p_state = 2*(1-normal(abs(z_state)))

di as txt "=============================================================="
di as txt "benefits (alpha):     coef=" as res %7.4f obs_wks   as txt "  se=" as res %7.4f se_wks   as txt "  p2=" as res %6.3f p_wks
di as txt "did_stateu (chi):     coef=" as res %7.4f obs_state as txt "  se=" as res %7.4f se_state as txt "  p2=" as res %6.3f p_state
di as txt "  (target: chi = -0.073, p = 0.78)"
di as txt "=============================================================="

* ---- write CSV ----
file open f using "${latexdir}Endog_Bartik_real.csv", write replace
file write f "name,coef,boot_se,z,p_twosided" _n
file write f "benefits,"   (obs_wks)   "," (se_wks)   "," (z_wks)   "," (p_wks)   _n
file write f "did_stateu," (obs_state) "," (se_state) "," (z_state) "," (p_state) _n
file close f
