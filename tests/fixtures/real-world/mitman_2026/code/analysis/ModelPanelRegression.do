* ---------------------------------------------------------------------------
* ModelPanelRegression.do  ->  model calibration coefficient (tab:calib check)
*
* The structural model is calibrated so that the SAME quasi-differenced (QD)
* benefit regression run on MODEL-generated data returns the data's unemployment
* coefficient (~0.0532). This script runs that regression on the simulated panel
* written by code/model/RunModel.m (output/factor_results/ModelPanel_Base.txt), confirming the
* committed calibration (tab:calib h/xi/chi) reproduces coef ~0.0528.
*
* Panel columns (17, from nested_state_county_simulate.m, fixed order):
*   pairid county time Fout Tout Vout Eout Uout Jout Zout AUout Aout Qout Pout Phiout Dout VVout
*   Uout = unemployment, Eout = benefit-duration weeks (the cross-county difference
*   in log(Eout) is the benefit regressor, the model analog of diff_logmeanwks).
*
* The QD transform mirrors the empirical spec: qd x = diff x - 0.9*0.99*lead(diff x),
* where diff is the cross-county (county1 - county2) difference within the pair.
* calibrate_model.m simulates ONE pair (cnum=1) as a long time series, so the
* calibration coefficient is the plain QD time-series regression of qd-unemployment
* on the cross-county benefit difference (no pair/IFE factors to remove -- there is
* only one pair). The original version of this script combined many-pair
* panels and ran the IFE (regife); on the single calibration panel the plain QD
* regression returns the same coefficient (0.0528).
*
* The model's v and theta QD coefficients are also reported for documentation, but
* note they are NOT the Table-valid Model row: that row is the TRUE permanent effect
* from RunModel.m's schedule-shift simulation (0.157/-0.279/-0.133), not these
* regression coefficients (see discoveries_lite.tex).
*
*
* Output: output/factor_results/ModelCalibCoef.csv  (one row: coef_u coef_v coef_t Nobs)
* ---------------------------------------------------------------------------

clear all
set matsize 11000
set maxvar 32767
set more off, perm

do "config.do"
global latexdir "${factor_csv}/"

infile pairid county time Fout Tout Vout Eout Uout Jout Zout AUout Aout Qout Pout Phiout Dout VVout ///
    using "${latexdir}ModelPanel_Base.txt", clear

gen logu = log(Uout)
gen logb = log(Eout)
gen logt = log(Tout)
gen logv = log(Vout)
sort pairid time county
by pairid time: gen diffu = logu[1]-logu[2]
by pairid time: gen diffb = logb[1]-logb[2]
by pairid time: gen difft = logt[1]-logt[2]
by pairid time: gen diffv = logv[1]-logv[2]

keep if county==1
sort pairid time
by pairid: gen fu = diffu[_n+1]
by pairid: gen ft = difft[_n+1]
by pairid: gen fv = diffv[_n+1]
gen qdu = diffu - 0.9*.99*fu
gen qdt = difft - 0.9*.99*ft
gen qdv = diffv - 0.9*.99*fv

reg qdu diffb
scalar coef_u = _b[diffb]
reg qdt diffb
scalar coef_t = _b[diffb]
reg qdv diffb
scalar coef_v = _b[diffb]

di as txt "==== Model QD regression coefficients on the calibration panel ===="
di as txt "  unemployment coef (calibration target ~0.0532; reported 0.0528) = " as res %7.5f coef_u
di as txt "  vacancy coef      = " as res %7.5f coef_v "   tightness coef = " as res %7.5f coef_t
di as txt "  (v/theta regression coefs are documentation only; Model row uses RunModel.m)"

* Headerless one-row matrix [coef_u coef_v coef_t Nobs] (kit CSV convention,
* read by code/tex/make_tables.py). coef_u is the calibration coefficient (~0.0528);
* coef_v/coef_t are documentation only (NOT the Table-valid Model row).
file open f using "${latexdir}ModelCalibCoef.csv", write replace
file write f (coef_u) "," (coef_v) "," (coef_t) "," (e(N)) _n
file close f
