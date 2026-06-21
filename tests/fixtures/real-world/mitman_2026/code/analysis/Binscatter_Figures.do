* ---------------------------------------------------------------------------
* Binscatter_Figures.do
*
* §4.2 "Under the Hood of the Quasi-Difference" binscatters:
*   fig:binscatter_du  -> DiffWks.pdf  (paper: figures/Binscatter/DiffWks.pdf)
*   fig:binscatter_qdu -> QDWks.pdf    (paper: figures/Binscatter/QDWks.pdf)
*
* DiffWks shows raw differenced unemployment -- contemporaneous
* (diff_logunemp_rate_laus) and one-quarter-ahead (f1_logunemp_rate_laus) --
* against the benefit difference, illustrating that current benefits predict
* both current and future unemployment. QDWks shows the quasi-differenced
* unemployment (qdk1_logunemp_rate_laus) against the same benefit difference,
* which collapses the forward-looking relationship into a single clean slope.
*
* They are drawn with an explicit twoway rather than the `binscatter` command
* because binscatter only exposes lcolor() on its fit lines (no line width or
* pattern). The binning replicates binscatter exactly -- 20
* `xtile` quantile bins of the x-variable over the common non-missing sample,
* plotting per-bin means, with an OLS fit line -- then style:
*   - fit lines twice as thick (lwidth(thick));
*   - QDWks markers AND fit line the same navy (so it reads in one colour);
*   - DiffWks "Lagged Benefits" fit line dashed so it survives B&W printing.
* All series are already border-pair differences, so no FE absorption is
* needed. Sample: 2005-2012, matching Check_UFU.do and the estimation window.
*
* Outputs are written with bare basenames directly into output/figures/ per the
* flat-folder submission convention; the paper \includegraphics path should
* become \includegraphics{DiffWks.pdf} / {QDWks.pdf} (drop figures/Binscatter/).
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/analysis/"
global DataControls "UIMacro_DataControls"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"

set more off, perm
cap log close


* ========================== Panel (a): DiffWks ==========================
cd "${maindirectory}"
use ${DataControls}, clear

* Common binscatter sample: all three variables non-missing, 2005-2012.
gen byte touse = inrange(year,2005,2012) ///
    & !missing(diff_logmeanwks, diff_logunemp_rate_laus, f1_logunemp_rate_laus)

* 20 quantile bins of the x-variable (matches binscatter's default).
xtile xbin = diff_logmeanwks if touse, nq(20)
bysort xbin: egen xbar  = mean(diff_logmeanwks)         if !missing(xbin)
bysort xbin: egen y1bar = mean(diff_logunemp_rate_laus) if !missing(xbin)
bysort xbin: egen y2bar = mean(f1_logunemp_rate_laus)   if !missing(xbin)
bysort xbin: gen byte binpt = (_n==1) if !missing(xbin)

* Clip the fit lines to the span of the binned points (binscatter convention).
summarize xbar if binpt
local lo = r(min)
local hi = r(max)

twoway (scatter y1bar xbar if binpt, mcolor(navy)   msymbol(O)) ///
       (scatter y2bar xbar if binpt, mcolor(maroon) msymbol(O)) ///
       (lfit diff_logunemp_rate_laus diff_logmeanwks if touse, ///
            range(`lo' `hi') lcolor(navy)   lwidth(thick)) ///
       (lfit f1_logunemp_rate_laus   diff_logmeanwks if touse, ///
            range(`lo' `hi') lcolor(maroon) lwidth(thick) lpattern(dash)), ///
       graphregion(fcolor(white)) xtitle(Difference in Weeks) ///
       ytitle(Difference in Unemployment) ///
       legend(order(1 "Contemporaneous Benefits" 2 "Lagged Benefits") ///
              bplace(nwest) ring(0))
graph export "${figures}/DiffWks.pdf", replace


* ========================== Panel (b): QDWks ===========================
use ${DataControls}, clear

gen byte touse = inrange(year,2005,2012) ///
    & !missing(diff_logmeanwks, qdk1_logunemp_rate_laus)

xtile xbin = diff_logmeanwks if touse, nq(20)
bysort xbin: egen xbar = mean(diff_logmeanwks)          if !missing(xbin)
bysort xbin: egen ybar = mean(qdk1_logunemp_rate_laus)  if !missing(xbin)
bysort xbin: gen byte binpt = (_n==1) if !missing(xbin)

summarize xbar if binpt
local lo = r(min)
local hi = r(max)

* Markers and fit line both navy (one colour, per request).
twoway (scatter ybar xbar if binpt, mcolor(navy) msymbol(O)) ///
       (lfit qdk1_logunemp_rate_laus diff_logmeanwks if touse, ///
            range(`lo' `hi') lcolor(navy) lwidth(thick)), ///
       graphregion(fcolor(white)) xtitle(Difference in Weeks) ///
       ytitle(Difference in Quasi-Differenced Unemployment) ///
       legend(off)
graph export "${figures}/QDWks.pdf", replace

cd "${CodeDirec}"
