#!/usr/bin/env python3
"""Generate paper tables from the per-experiment CSV outputs.

Reads the canonical per-pairing CSVs in this directory and writes
\\input-able .tex files alongside, one per appendix table.

Run from anywhere:
    python3 code/tex/make_tables.py
"""

import csv
import math
import pathlib
import statistics

HERE = pathlib.Path(__file__).resolve().parent
IN_DIR  = HERE.parent.parent / "output" / "factor_results"   # CSV inputs (analysis/Matlab results)
OUT_DIR = HERE.parent.parent / "output" / "tables"           # generated .tex (paper \input)
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------- CSV helpers ----------

def read_matrix(name):
    """Return a list-of-lists of floats from a comma-separated file.

    Empty cells and Stata's `.` missing marker parse as NaN; the OLS
    generator only consumes the cells that are guaranteed populated by
    the producing script, so NaN in unused positions is harmless.
    """
    def _parse(x):
        x = x.strip()
        if x == "" or x == ".":
            return float("nan")
        return float(x)
    with (IN_DIR / name).open() as f:
        return [[_parse(x) for x in row] for row in csv.reader(f) if row]


# Per the experiment-pairing convention (see csv-summary-conventions memory):
#   SenseResults<SepMethod>.csv  — 8 rows x N sub-experiments
#     row 1: benefits coef (point estimate)
#     row 2: %>0 in the bootstrap (the "p-value" raw input)
#     row 3: 2.5% bootstrap percentile
#     row 4: 97.5% bootstrap percentile
#     row 5: bootstrap std
#     row 6: numfactors
#     row 7: R-squared
#     row 8: Nobs
#   <SepMethod>_*_summary.csv    — N rows x 5 cols (one row per regressor)
#     cols: [coef, %>0, 2.5%, 97.5%, std]


# ---------- formatting ----------

def pvalue(pct_gt_0):
    """One-sided bootstrap p-value derived from the %>0 statistic.

    Directional test in the direction the point estimate points (the smaller
    bootstrap tail). This is the paper's standing convention; the two-sided
    value would be 2x this.
    """
    return min(pct_gt_0, 100.0 - pct_gt_0) / 100.0


# Coefficient decimal places, matched per table to the original paper's convention
# (any changed number must be flagged, including a changed decimal count). Set CDEC
# at the top of each table block; the coefficient formatters fall back to it when no
# explicit `decimals` is passed. Original conventions: Table 1 / OLS / Distance / beg
# = 3; Forward_Spec = 2; the policy-control, wage, Mobility, and A-1 tables = 4.
CDEC = 3


def fmt_coef(coef, pct_gt_0, decimals=None, bold_thresh=0.05):
    if decimals is None:
        decimals = CDEC
    s = f"{coef:.{decimals}f}"
    return f"\\bf{{{s}}}" if pvalue(pct_gt_0) < bold_thresh else s


def fmt_pval(pct_gt_0, decimals=3):
    return f"({pvalue(pct_gt_0):.{decimals}f})"


def fmt_obs(n):
    return f"{int(round(n)):,}"


def fmt_rsq(r, decimals=3):
    return f"{r:.{decimals}f}"


def fmt_int(n):
    return f"{int(round(n))}"


def fmt_nolead(x, decimals=3):
    """Fixed-decimal format with the leading zero stripped (.108, -.045), as in
    tab:MO_V_U."""
    s = f"{x:.{decimals}f}"
    if s.startswith("0."):
        return s[1:]
    if s.startswith("-0."):
        return "-" + s[2:]
    return s


# ---------- analytic-SE formatting (for OLS tables) ----------

def pval_normal(coef, se):
    """One-sided p-value from a normal approximation given coef and clustered SE.

    Directional test in the direction of the estimate (1 - Phi(|z|)), matching
    the one-sided bootstrap convention used elsewhere in the kit. Two-sided
    would be 2x this.
    """
    if se == 0 or se != se:  # nan-safe
        return 1.0
    z = abs(coef / se)
    # 1 - Phi(z) where Phi is the standard normal CDF
    return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def fmt_coef_se(coef, se, decimals=None, bold_thresh=0.01):
    """Format a coefficient with bolding determined by an analytic p-value."""
    if decimals is None:
        decimals = CDEC
    s = f"{coef:.{decimals}f}"
    return f"\\bf{{{s}}}" if pval_normal(coef, se) < bold_thresh else s


def fmt_pval_se(coef, se, decimals=3):
    return f"({pval_normal(coef, se):.{decimals}f})"


def fmt_se(se, decimals=3):
    """Format a standard error in parentheses (for tables that report SEs, not p-values)."""
    return f"({se:.{decimals}f})"


# ---------- data accessors ----------

def benefits(matrix, col_index):
    """Return (coef, pct_gt_0, numfactors, Rsq, Nobs) for the 1-indexed sub-experiment."""
    j = col_index - 1
    return matrix[0][j], matrix[1][j], matrix[5][j], matrix[6][j], matrix[7][j]


def control(summary, iiii):
    """Return (coef, pct_gt_0) for the 1-indexed OnebyOne iteration."""
    row = summary[iiii - 1]
    return row[0], row[1]


# ---------- read inputs ----------

bench = read_matrix("SenseResultsBench.csv")
obo = read_matrix("SenseResultsControlsOnebyOne.csv")
obo_ctrl = read_matrix("Controls_OnebyOne_controls_summary.csv")
lev_obo = read_matrix("SenseResultsControlsLevOnebyOne.csv")
lev_ctrl = read_matrix("Controls_LevOnebyOne_controls_summary.csv")

# Baseline = Bench Col 1 (the first sub-experiment of the Bench pairing).
b_coef, b_pct, b_nf, b_rsq, b_n = benefits(bench, 1)


# ---------- tab:Benefits_on_unemp_SNAP_Mortgage ----------
# Col 1 = baseline (Bench)
# Col 2 = OnebyOne iiii=9 (diff_bbce_asset2018, "SNAP Broad Eligibility")
# Col 3 = OnebyOne iiii=8 (diff_judicial,        "Foreclosure Policy")

snap_c, snap_p = control(obo_ctrl, 9)
fc_c,   fc_p   = control(obo_ctrl, 8)
c2 = benefits(obo, 9)
c3 = benefits(obo, 8)

CDEC = 4   # policy-control table: 4-decimal coefficients (original)
snap_mortgage = rf"""\begin{{tabular}}{{lcccc}} \hline
VARIABLES                & &  (1)            & (2)            & (3)            \\ \hline \noalign{{\vskip 1mm}}
Weeks of Benefits        & &  {fmt_coef(b_coef, b_pct)}  & {fmt_coef(c2[0], c2[1])}  & {fmt_coef(c3[0], c3[1])}  \\
                         & &  {fmt_pval(b_pct)}      & {fmt_pval(c2[1])}      & {fmt_pval(c3[1])}      \\ \noalign{{\vskip 2mm}}

SNAP Broad Eligibility   & &                  & {fmt_coef(snap_c, snap_p)}  &                \\
                         & &                  & {fmt_pval(snap_p)}      &                \\ \noalign{{\vskip 2mm}}

Foreclosure Policy       & &                  &                & {fmt_coef(fc_c, fc_p)}  \\
                         & &                  &                & {fmt_pval(fc_p)}      \\ \noalign{{\vskip 2mm}}

Number of Factors        & &  {fmt_int(b_nf)}              & {fmt_int(c2[2])}              & {fmt_int(c3[2])}              \\
Observations             & &  {fmt_obs(b_n)}        & {fmt_obs(c2[4])}        & {fmt_obs(c3[4])}        \\
R-squared                & &  {fmt_rsq(b_rsq)}             & {fmt_rsq(c2[3])}             & {fmt_rsq(c3[3])}             \\ \hline
\multicolumn{{5}}{{l}}{{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap.}} \\
\multicolumn{{5}}{{l}}{{\footnotesize Bold indicates $p<0.05$.}} \\
\end{{tabular}}
"""

(OUT_DIR / "Benefits_on_unemp_SNAP_Mortgage.tex").write_text(snap_mortgage)


# ---------- tab:Benefits_on_unemp_other_policies ----------
# Col 1 = baseline (Bench)
# Col 2 = OnebyOne iiii=2 (diff_sbsi, "SBSI")
# Col 3 = OnebyOne iiii=3 (diff_sbtc, "SBTC")
# Col 4 = OnebyOne iiii=4 (diff_bhi,  "BHI")

sbsi_c, sbsi_p = control(obo_ctrl, 2)
sbtc_c, sbtc_p = control(obo_ctrl, 3)
bhi_c,  bhi_p  = control(obo_ctrl, 4)
op2 = benefits(obo, 2)
op3 = benefits(obo, 3)
op4 = benefits(obo, 4)

CDEC = 4   # policy-control table: 4-decimal coefficients (original)
other_policies = rf"""\begin{{tabular}}{{lcccc}} \hline
VARIABLES         & (1)            & (2)            & (3)            & (4)            \\ \hline \noalign{{\vskip 1mm}}
Weeks of Benefits & {fmt_coef(b_coef, b_pct)}  & {fmt_coef(op2[0], op2[1])}  & {fmt_coef(op3[0], op3[1])}  & {fmt_coef(op4[0], op4[1])}  \\
                  & {fmt_pval(b_pct)}      & {fmt_pval(op2[1])}      & {fmt_pval(op3[1])}      & {fmt_pval(op4[1])}      \\ \noalign{{\vskip 2mm}}

SBSI              &                & {fmt_coef(sbsi_c, sbsi_p)}  &                &                \\
                  &                & {fmt_pval(sbsi_p)}      &                &                \\ \noalign{{\vskip 2mm}}

SBTC              &                &                & {fmt_coef(sbtc_c, sbtc_p)}  &                \\
                  &                &                & {fmt_pval(sbtc_p)}      &                \\ \noalign{{\vskip 2mm}}

BHI               &                &                &                & {fmt_coef(bhi_c, bhi_p)}  \\
                  &                &                &                & {fmt_pval(bhi_p)}      \\ \noalign{{\vskip 2mm}}

Number of Factors & {fmt_int(b_nf)}              & {fmt_int(op2[2])}              & {fmt_int(op3[2])}              & {fmt_int(op4[2])}              \\
Observations      & {fmt_obs(b_n)}        & {fmt_obs(op2[4])}        & {fmt_obs(op3[4])}        & {fmt_obs(op4[4])}        \\
R-squared         & {fmt_rsq(b_rsq)}             & {fmt_rsq(op2[3])}             & {fmt_rsq(op3[3])}             & {fmt_rsq(op4[3])}             \\ \hline
\multicolumn{{5}}{{l}}{{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap.}} \\
\multicolumn{{5}}{{l}}{{\footnotesize Bold indicates $p<0.05$.}} \\
\end{{tabular}}
"""

(OUT_DIR / "Benefits_on_unemp_other_policies.tex").write_text(other_policies)


# ---------- tab:Benefits_on_unemp_stimulus_taxes ----------
# 9 numbered columns + 1 spacer between Levels half (Cols 2-5) and GDP half (Cols 6-9).
# Col 1 = baseline (Bench).
# Levels half (from Levels OnebyOne pairing):
#   Col 2 (Stimulus, Levels)         = Lev iiii=1 (diff_logawardamount)
#   Col 3 (Total Tax, Levels)        = Lev iiii=2 (diff_logtotal)
#   Col 4 (Sales Tax, Levels)        = Lev iiii=4 (diff_loggeneral_sales)
#   Col 5 (Income Tax, Levels)       = Lev iiii=3 (diff_logincome)
# GDP half (from GDP OnebyOne pairing):
#   Col 6 (Stimulus, GDP)            = GDP iiii=1 (diff_logawardamount_gdp)
#   Col 7 (Total Tax, GDP)           = GDP iiii=5 (diff_logtotal_gdp)
#   Col 8 (Sales Tax, GDP)           = GDP iiii=7 (diff_loggeneral_sales_gdp)
#   Col 9 (Income Tax, GDP)          = GDP iiii=6 (diff_logincome_gdp)

stim_l_c, stim_l_p = control(lev_ctrl, 1);  stim_l = benefits(lev_obo, 1)
tot_l_c,  tot_l_p  = control(lev_ctrl, 2);  tot_l  = benefits(lev_obo, 2)
sal_l_c,  sal_l_p  = control(lev_ctrl, 4);  sal_l  = benefits(lev_obo, 4)
inc_l_c,  inc_l_p  = control(lev_ctrl, 3);  inc_l  = benefits(lev_obo, 3)

stim_g_c, stim_g_p = control(obo_ctrl, 1);  stim_g = benefits(obo, 1)
tot_g_c,  tot_g_p  = control(obo_ctrl, 5);  tot_g  = benefits(obo, 5)
sal_g_c,  sal_g_p  = control(obo_ctrl, 7);  sal_g  = benefits(obo, 7)
inc_g_c,  inc_g_p  = control(obo_ctrl, 6);  inc_g  = benefits(obo, 6)

CDEC = 4   # policy-control table: 4-decimal coefficients (original)
stimulus_taxes = rf"""\begin{{tabular}}{{lcccccccccc}} \hline
VARIABLE          & (1) &  (2)   & (3) & (4) & (5) && (6) & (7) & (8) & (9)\\ \hline \noalign{{\vskip 1mm}}

Weeks of          & {fmt_coef(b_coef, b_pct)} & {fmt_coef(stim_l[0], stim_l[1])} & {fmt_coef(tot_l[0], tot_l[1])} & {fmt_coef(sal_l[0], sal_l[1])} & {fmt_coef(inc_l[0], inc_l[1])} && {fmt_coef(stim_g[0], stim_g[1])} & {fmt_coef(tot_g[0], tot_g[1])} & {fmt_coef(sal_g[0], sal_g[1])} & {fmt_coef(inc_g[0], inc_g[1])}\\
Benefits          & {fmt_pval(b_pct)}      & {fmt_pval(stim_l[1])}      & {fmt_pval(tot_l[1])}      & {fmt_pval(sal_l[1])}      & {fmt_pval(inc_l[1])}      && {fmt_pval(stim_g[1])}      & {fmt_pval(tot_g[1])}      & {fmt_pval(sal_g[1])}      & {fmt_pval(inc_g[1])}     \\ \noalign{{\vskip 1mm}}

& & \multicolumn{{4}}{{c}}{{ Variable in Levels}} && \multicolumn{{4}}{{c}}{{ Variable Relative to GDP}}\\ \cline{{3-6}} \cline{{8-11}}  \noalign{{\vskip 2mm}}

Stimulus          & & {fmt_coef(stim_l_c, stim_l_p)} & & & && {fmt_coef(stim_g_c, stim_g_p)} & & & \\
Spending          & & {fmt_pval(stim_l_p)}      & & & && {fmt_pval(stim_g_p)}      & & & \\ \\

Total Tax         & & & {fmt_coef(tot_l_c, tot_l_p)} & & && & {fmt_coef(tot_g_c, tot_g_p)} & & \\
Revenue           & & & {fmt_pval(tot_l_p)}      & & && & {fmt_pval(tot_g_p)}      & & \\ \\

Sales Tax         & & & & {fmt_coef(sal_l_c, sal_l_p)} & && & & {fmt_coef(sal_g_c, sal_g_p)}  & \\
Revenue           & & & & {fmt_pval(sal_l_p)}      & && & & {fmt_pval(sal_g_p)}      & \\ \\

Income Tax        & & & & & {fmt_coef(inc_l_c, inc_l_p)} && & & & {fmt_coef(inc_g_c, inc_g_p)} \\
Revenue           & & & & & {fmt_pval(inc_l_p)}      && & & & {fmt_pval(inc_g_p)}      \\  \noalign{{\vskip 2mm}}

\# Factors        & {fmt_int(b_nf)} & {fmt_int(stim_l[2])} & {fmt_int(tot_l[2])} & {fmt_int(sal_l[2])} & {fmt_int(inc_l[2])} && {fmt_int(stim_g[2])} & {fmt_int(tot_g[2])} & {fmt_int(sal_g[2])} & {fmt_int(inc_g[2])} \\
Obs.              & {fmt_obs(b_n)} & {fmt_obs(stim_l[4])} & {fmt_obs(tot_l[4])} & {fmt_obs(sal_l[4])} & {fmt_obs(inc_l[4])} && {fmt_obs(stim_g[4])} & {fmt_obs(tot_g[4])} & {fmt_obs(sal_g[4])} & {fmt_obs(inc_g[4])} \\
R-squared         & {fmt_rsq(b_rsq)} & {fmt_rsq(stim_l[3])} & {fmt_rsq(tot_l[3])} & {fmt_rsq(sal_l[3])} & {fmt_rsq(inc_l[3])} && {fmt_rsq(stim_g[3])} & {fmt_rsq(tot_g[3])} & {fmt_rsq(sal_g[3])} & {fmt_rsq(inc_g[3])} \\ \hline
\end{{tabular}}
"""

(OUT_DIR / "Benefits_on_unemp_stimulus_taxes.tex").write_text(stimulus_taxes)


# ---------- tab:Benefits_on_unemp_OLS ----------
# 10-column OLS / additive-effects appendix table. Sources:
#   - Table1_OLS_reghdfe.csv (8 rows from code/analysis/Table1_OLS.do):
#       row 1 -> Col 1 baseline
#       row 2 -> Col 2 (+ State GDP per Worker, diff_logprod_all_old)
#       row 3 -> Col 5 (emp_share<0.15)
#       row 4 -> not in paper OLS table (alt unemp measure); SKIP
#       row 5 -> Col 6 (industry)
#       row 6 -> Col 7 (dist<30)
#       row 7 -> Col 8 (samecbsa==1)
#       row 8 -> Col 9 (perfect-foresight benefits)
#     Cols within each row: [coef, se, control_coef, control_se, N, R^2]
#   - Scrambles_OLS_baseline.csv  (200 x 4)  -> Col 3
#   - Scrambles_OLS_prodall.csv   (200 x 6)  -> Col 4
#       Coef = mean across scrambles; SE = std across scrambles (per paper convention)
#   - Table1_OLS_Controls.csv     (1 x 4)    -> Col 10

_ols_inputs = [
    "Table1_OLS_reghdfe.csv",
    "Scrambles_OLS_baseline.csv",
    "Scrambles_OLS_prodall.csv",
    "Table1_OLS_Controls.csv",
]
_ols_missing = [f for f in _ols_inputs if not (IN_DIR / f).exists()]
if _ols_missing:
    print("Skipping Benefits_on_unemp_OLS.tex — missing inputs:")
    for f in _ols_missing:
        print(f"  {f}")
    print("Generate them by re-running code/analysis/Table1_OLS.do and "
          "code/analysis/Table1_OLS_Controls.do, then re-running this script.")
else:
    t1o = read_matrix("Table1_OLS_reghdfe.csv")
    scr_b = read_matrix("Scrambles_OLS_baseline.csv")
    scr_p = read_matrix("Scrambles_OLS_prodall.csv")
    t1o_ctrl = read_matrix("Table1_OLS_Controls.csv")


    def ols_cell(row):
        """Pack one row of Table1_OLS_reghdfe.csv as (coef, se, gdp_coef, gdp_se, N, Rsq)."""
        return row[0], row[1], row[2], row[3], row[4], row[5]

    def scramble_cell(matrix, coef_col):
        """Mean coef + std across scrambles."""
        coefs = [r[coef_col] for r in matrix]
        return statistics.mean(coefs), statistics.stdev(coefs)

    # Paper Col 1 - baseline
    c1_b, c1_se, _, _, c1_n, c1_r = ols_cell(t1o[0])
    # Paper Col 2 - + State GDP
    c2_b, c2_se, c2_g, c2_gse, c2_n, c2_r = ols_cell(t1o[1])
    # Paper Col 3 - Scrambled (mean over 200 scrambles)
    c3_b, c3_se = scramble_cell(scr_b, 0)
    c3_n = statistics.mean(r[2] for r in scr_b)
    c3_r = statistics.mean(r[3] for r in scr_b)
    # Paper Col 4 - Scrambled + State GDP
    c4_b, c4_se = scramble_cell(scr_p, 0)
    c4_g, c4_gse = scramble_cell(scr_p, 2)
    c4_n = statistics.mean(r[4] for r in scr_p)
    c4_r = statistics.mean(r[5] for r in scr_p)
    # Paper Col 5 - emp_share<0.15
    c5_b, c5_se, _, _, c5_n, c5_r = ols_cell(t1o[2])
    # Paper Col 6 - industry
    c6_b, c6_se, _, _, c6_n, c6_r = ols_cell(t1o[3])
    # Paper Col 7 - dist<30
    c7_b, c7_se, _, _, c7_n, c7_r = ols_cell(t1o[4])
    # Paper Col 8 - same CBSA
    c8_b, c8_se, _, _, c8_n, c8_r = ols_cell(t1o[5])
    # Paper Col 9 - perfect-foresight benefits
    c9_b, c9_se, _, _, c9_n, c9_r = ols_cell(t1o[6])
    # Paper Col 10 - all state-policy controls
    c10_b, c10_se, c10_n, c10_r = t1o_ctrl[0]

    # Paper convention for tab:Benefits_on_unemp_OLS: clustered standard errors
    # in parentheses (not p-values), bold if p<0.01.
    CDEC = 3   # OLS table: 3-decimal coefficients (original)
    ols_table = rf"""\begin{{tabular}}{{lcccccccccc}} \hline
VAR.       & (1) & (2) & (3) & (4) & (5) & (6) & (7) & (8) & (9) & (10)\\ \hline \noalign{{\vskip 2mm}}
Weeks of   & {fmt_coef_se(c1_b, c1_se)} & {fmt_coef_se(c2_b, c2_se)} & {fmt_coef_se(c3_b, c3_se)} & {fmt_coef_se(c4_b, c4_se)} & {fmt_coef_se(c5_b, c5_se)} & {fmt_coef_se(c6_b, c6_se)} & {fmt_coef_se(c7_b, c7_se)} & {fmt_coef_se(c8_b, c8_se)} & {fmt_coef_se(c9_b, c9_se)} & {fmt_coef_se(c10_b, c10_se)}\\
Benefits   & {fmt_se(c1_se)} & {fmt_se(c2_se)} & {fmt_se(c3_se)} & {fmt_se(c4_se)} & {fmt_se(c5_se)} & {fmt_se(c6_se)} & {fmt_se(c7_se)} & {fmt_se(c8_se)} & {fmt_se(c9_se)} & {fmt_se(c10_se)}\\ \noalign{{\vskip 4mm}}

State GDP  &  & {fmt_coef_se(c2_g, c2_gse)} &  & {fmt_coef_se(c4_g, c4_gse)} &  &  &  &  &  & \\
per Worker &  & {fmt_se(c2_gse)} &  & {fmt_se(c4_gse)} &  &  &  &  &  & \\ \noalign{{\vskip 4mm}}

Obs.       & {fmt_obs(c1_n)} & {fmt_obs(c2_n)} & {fmt_obs(c3_n)} & {fmt_obs(c4_n)} & {fmt_obs(c5_n)} & {fmt_obs(c6_n)} & {fmt_obs(c7_n)} & {fmt_obs(c8_n)} & {fmt_obs(c9_n)} & {fmt_obs(c10_n)}\\
R-squared  & {fmt_rsq(c1_r)} & {fmt_rsq(c2_r)} & {fmt_rsq(c3_r)} & {fmt_rsq(c4_r)} & {fmt_rsq(c5_r)} & {fmt_rsq(c6_r)} & {fmt_rsq(c7_r)} & {fmt_rsq(c8_r)} & {fmt_rsq(c9_r)} & {fmt_rsq(c10_r)}\\ \hline
\end{{tabular}}
"""

    (OUT_DIR / "Benefits_on_unemp_OLS.tex").write_text(ols_table)


# ---------- tab:Benefits_on_unemp (main Table 1, 11 columns) ----------
# The headline IFE table. Non-beg twin of tab:Benefits_on_unemp_beg; bolds at
# p<0.01 (stricter than the appendix tables). Column -> producer CSV map:
#   Col 1  Baseline                 SenseResultsBench.csv         sub-exp 1
#   Col 2  Baseline + State GDP/Wkr SenseResultsBench.csv         sub-exp 2
#          (GDP control coef/%>0 from Bench_qd1_unemp_prodall_summary.csv row 2)
#   Col 3  Scrambled baseline       Scrambles_coefs.csv col 1 (mean +/- std)
#   Col 4  Scrambled + State GDP    Scrambles_coefs.csv col 2 (benefit), col 3 (GDP)
#   Col 5  Emp share <15%           SenseResultsEmpShare.csv
#   Col 6  Similar industry         SenseResultsIndustry.csv
#   Col 7  Pop centers <30mi        SenseResultsDist30.csv
#   Col 8  Same CBSA                SenseResultsCBSA.csv
#   Col 9  Perfect foresight        SenseResultsBench.csv         sub-exp 3
#   Col 10 All other policies       SenseResultsControls.csv
#   Col 11 Unemp corr >0.5 (Uhlig)  Uhlig_qd1_unemp_drop60_trunc8_se.csv
# The Scrambled columns (3-4) report the dispersion across the 200 random
# pairings as the inference object (one-sided analytic-normal p from mean/std,
# not a per-run bootstrap). Their N.factors / Obs / R^2 are not meaningful when
# aggregated across pairings, so they print "--" pending the reporting-
# convention -- mirrors the beg table's treatment.

_t1_inputs = [
    "SenseResultsBench.csv",
    "Bench_qd1_unemp_prodall_summary.csv",
    "SenseResultsEmpShare.csv",
    "SenseResultsIndustry.csv",
    "SenseResultsDist30.csv",
    "SenseResultsCBSA.csv",
    "SenseResultsControls.csv",
    "Uhlig_qd1_unemp_drop60_trunc8_se.csv",
    "Scrambles_coefs.csv",
]
_t1_missing = [f for f in _t1_inputs if not (IN_DIR / f).exists()]
if _t1_missing:
    print("Skipping Benefits_on_unemp.tex — missing inputs:")
    for f in _t1_missing:
        print(f"  {f}")
    _t1_done = False
else:
    t1_bench = read_matrix("SenseResultsBench.csv")
    t1_prodall = read_matrix("Bench_qd1_unemp_prodall_summary.csv")
    t1_emp = read_matrix("SenseResultsEmpShare.csv")
    t1_ind = read_matrix("SenseResultsIndustry.csv")
    t1_d30 = read_matrix("SenseResultsDist30.csv")
    t1_cbsa = read_matrix("SenseResultsCBSA.csv")
    t1_ctrl = read_matrix("SenseResultsControls.csv")
    t1_uhlig = read_matrix("Uhlig_qd1_unemp_drop60_trunc8_se.csv")
    t1_scr = read_matrix("Scrambles_coefs.csv")

    BT = 0.01  # Table 1 bolding threshold

    # Cols 1, 2, 9 from Bench sub-experiments 1, 2, 3.
    a1_b, a1_p, a1_nf, a1_rsq, a1_n = benefits(t1_bench, 1)
    a2_b, a2_p, a2_nf, a2_rsq, a2_n = benefits(t1_bench, 2)
    a2_g, a2_g_pct = t1_prodall[1][0], t1_prodall[1][1]   # State GDP per Worker control
    a9_b, a9_p, a9_nf, a9_rsq, a9_n = benefits(t1_bench, 3)

    # Cols 5-8, 10 from single-experiment runs.
    a5_b, a5_p, a5_nf, a5_rsq, a5_n = benefits(t1_emp, 1)
    a6_b, a6_p, a6_nf, a6_rsq, a6_n = benefits(t1_ind, 1)
    a7_b, a7_p, a7_nf, a7_rsq, a7_n = benefits(t1_d30, 1)
    a8_b, a8_p, a8_nf, a8_rsq, a8_n = benefits(t1_cbsa, 1)
    a10_b, a10_p, a10_nf, a10_rsq, a10_n = benefits(t1_ctrl, 1)

    # Col 11 (Uhlig) from the single-column _se file (8-row layout, one value each).
    a11_b, a11_p = t1_uhlig[0][0], t1_uhlig[1][0]
    a11_nf, a11_rsq, a11_n = t1_uhlig[5][0], t1_uhlig[6][0], t1_uhlig[7][0]

    # Cols 3-4 (Scrambled): mean coef +/- std across the 200 random pairings.
    col3 = [r[0] for r in t1_scr]
    col4 = [r[1] for r in t1_scr]
    col4g = [r[2] for r in t1_scr]
    a3_b, a3_se = statistics.mean(col3), statistics.stdev(col3)
    a4_b, a4_se = statistics.mean(col4), statistics.stdev(col4)
    a4_g, a4_g_se = statistics.mean(col4g), statistics.stdev(col4g)
    # N.factors / Obs / R^2 for the scrambled columns (3,4): MEDIAN across the 200
    # random pairings (median convention). Falls back to "--" if the per-scramble
    # meta file is absent (e.g. an older Scrambles run that did not emit it).
    if (IN_DIR / "Scrambles_meta.csv").exists():
        _sm = list(zip(*read_matrix("Scrambles_meta.csv")))  # 6 cols: c3[nf,n,r2] c4[nf,n,r2]
        _med = [statistics.median(c) for c in _sm]
        scr3_nf, scr3_n, scr3_rsq = fmt_int(_med[0]), fmt_obs(_med[1]), fmt_rsq(_med[2])
        scr4_nf, scr4_n, scr4_rsq = fmt_int(_med[3]), fmt_obs(_med[4]), fmt_rsq(_med[5])
    else:
        scr3_nf = scr3_n = scr3_rsq = scr4_nf = scr4_n = scr4_rsq = "--"

    CDEC = 3   # Table 1: 3-decimal coefficients (original)
    table1 = rf"""\begin{{tabular}}{{lccccccccccc}} \hline
VAR. & (1) & (2) & (3) & (4) & (5) & (6) & (7) & (8) & (9) & (10) & (11)\\ \hline \noalign{{\vskip 2mm}}
Weeks of  & {fmt_coef(a1_b, a1_p, bold_thresh=BT)} & {fmt_coef(a2_b, a2_p, bold_thresh=BT)} & {fmt_coef_se(a3_b, a3_se, bold_thresh=BT)} & {fmt_coef_se(a4_b, a4_se, bold_thresh=BT)} & {fmt_coef(a5_b, a5_p, bold_thresh=BT)} & {fmt_coef(a6_b, a6_p, bold_thresh=BT)} & {fmt_coef(a7_b, a7_p, bold_thresh=BT)} & {fmt_coef(a8_b, a8_p, bold_thresh=BT)} & {fmt_coef(a9_b, a9_p, bold_thresh=BT)} & {fmt_coef(a10_b, a10_p, bold_thresh=BT)} & {fmt_coef(a11_b, a11_p, bold_thresh=BT)}\\
Benefits  & {fmt_pval(a1_p)} & {fmt_pval(a2_p)} & {fmt_pval_se(a3_b, a3_se)} & {fmt_pval_se(a4_b, a4_se)} & {fmt_pval(a5_p)} & {fmt_pval(a6_p)} & {fmt_pval(a7_p)} & {fmt_pval(a8_p)} & {fmt_pval(a9_p)} & {fmt_pval(a10_p)} & {fmt_pval(a11_p)}\\ \noalign{{\vskip 4mm}}

State GDP  & & {fmt_coef(a2_g, a2_g_pct, bold_thresh=BT)} & & {fmt_coef_se(a4_g, a4_g_se, bold_thresh=BT)} & & & & & & & \\
per Worker & & {fmt_pval(a2_g_pct)} & & {fmt_pval_se(a4_g, a4_g_se)} & & & & & & & \\ \noalign{{\vskip 4mm}}

N. factors & {fmt_int(a1_nf)} & {fmt_int(a2_nf)} & {scr3_nf} & {scr4_nf} & {fmt_int(a5_nf)} & {fmt_int(a6_nf)} & {fmt_int(a7_nf)} & {fmt_int(a8_nf)} & {fmt_int(a9_nf)} & {fmt_int(a10_nf)} & {fmt_int(a11_nf)}\\
Obs. & {fmt_obs(a1_n)} & {fmt_obs(a2_n)} & {scr3_n} & {scr4_n} & {fmt_obs(a5_n)} & {fmt_obs(a6_n)} & {fmt_obs(a7_n)} & {fmt_obs(a8_n)} & {fmt_obs(a9_n)} & {fmt_obs(a10_n)} & {fmt_obs(a11_n)}\\
R-squared & {fmt_rsq(a1_rsq)} & {fmt_rsq(a2_rsq)} & {scr3_rsq} & {scr4_rsq} & {fmt_rsq(a5_rsq)} & {fmt_rsq(a6_rsq)} & {fmt_rsq(a7_rsq)} & {fmt_rsq(a8_rsq)} & {fmt_rsq(a9_rsq)} & {fmt_rsq(a10_rsq)} & {fmt_rsq(a11_rsq)}\\ \hline
\end{{tabular}}
"""
    (OUT_DIR / "Benefits_on_unemp.tex").write_text(table1)
    _t1_done = True


# ---------- tab:Benefits_on_unemp_beg ----------
# 10-column qdsbk1 (QWI beginning-of-quarter separations) counterpart of Table 1.
# Same structure, same RHS, same controls -- LHS changes to qdsbk1_logunemp_rate_laus.
# Sources:
#   SenseResultsBenchBeg.csv      cols 1,2,3   -> paper Cols 1, 2, 9
#   BenchBeg_qdsbk1_unemp_prodall_summary.csv  -> row 2 = State GDP coef in Col 2
#   SenseResultsEmpShareBeg.csv   col 1        -> Col 5
#   SenseResultsIndustryBeg.csv   col 1        -> Col 6
#   SenseResultsDist30Beg.csv     col 1        -> Col 7
#   SenseResultsCBSABeg.csv       col 1        -> Col 8
#   SenseResultsControlsBeg.csv   col 1        -> Col 10
# Cols 3-4 (Scrambled Beg) are deferred -- emit blank cells with a TBD marker.

_beg_inputs = [
    "SenseResultsBenchBeg.csv",
    "BenchBeg_qdsbk1_unemp_prodall_summary.csv",
    "SenseResultsEmpShareBeg.csv",
    "SenseResultsIndustryBeg.csv",
    "SenseResultsDist30Beg.csv",
    "SenseResultsCBSABeg.csv",
    "SenseResultsControlsBeg.csv",
]
_beg_missing = [f for f in _beg_inputs if not (IN_DIR / f).exists()]
_beg_scrambles_present = (IN_DIR / "Scrambles_Beg_coefs.csv").exists()
if _beg_missing:
    print("Skipping Benefits_on_unemp_beg.tex — missing inputs:")
    for f in _beg_missing:
        print(f"  {f}")
    print("Generate them by re-running the Stata exporters and the new "
          "Factor_FrontEnd_*Beg.m front-ends.")
else:
    bench_beg = read_matrix("SenseResultsBenchBeg.csv")
    bench_beg_prodall = read_matrix("BenchBeg_qdsbk1_unemp_prodall_summary.csv")
    empshare_beg = read_matrix("SenseResultsEmpShareBeg.csv")
    industry_beg = read_matrix("SenseResultsIndustryBeg.csv")
    dist30_beg = read_matrix("SenseResultsDist30Beg.csv")
    cbsa_beg = read_matrix("SenseResultsCBSABeg.csv")
    controls_beg = read_matrix("SenseResultsControlsBeg.csv")

    # Paper Cols 1, 2, 9 from BenchBeg sub-experiments 1, 2, 3.
    b1_b, b1_p, b1_nf, b1_rsq, b1_n = benefits(bench_beg, 1)
    b2_b, b2_p, b2_nf, b2_rsq, b2_n = benefits(bench_beg, 2)
    # Col 2 State GDP coefficient and %>0 from the per-regressor summary
    # (row 2 = control, the diff_logprod_all term).
    b2_g, b2_g_pct = bench_beg_prodall[1][0], bench_beg_prodall[1][1]
    b9_b, b9_p, b9_nf, b9_rsq, b9_n = benefits(bench_beg, 3)

    # Paper Cols 5-8 from the filtered single-experiment runs.
    b5_b, b5_p, b5_nf, b5_rsq, b5_n = benefits(empshare_beg, 1)
    b6_b, b6_p, b6_nf, b6_rsq, b6_n = benefits(industry_beg, 1)
    b7_b, b7_p, b7_nf, b7_rsq, b7_n = benefits(dist30_beg, 1)
    b8_b, b8_p, b8_nf, b8_rsq, b8 = benefits(cbsa_beg, 1)
    b8_n = b8  # keep naming consistent with the other cells

    # Paper Col 10 from ControlsBeg.
    b10_b, b10_p, b10_nf, b10_rsq, b10_n = benefits(controls_beg, 1)

    # Paper Cols 3-4 (Scrambled Beg) — populate from Scrambles_Beg_coefs.csv
    # if available, otherwise leave blank with a deferred-Scrambles note.
    if _beg_scrambles_present:
        scr_beg = read_matrix("Scrambles_Beg_coefs.csv")
        col3_coefs = [r[0] for r in scr_beg]
        col4_coefs = [r[1] for r in scr_beg]
        col4_g_coefs = [r[2] for r in scr_beg]
        # Mean coef + std-across-scrambles as the SE; one-sided p from coef sign.
        # Use the analytic-normal p-value so the bold rule keys off coef/SE.
        b3_b = statistics.mean(col3_coefs)
        b3_se = statistics.stdev(col3_coefs)
        b3_p = 0.0 if pval_normal(b3_b, b3_se) < 1e-4 else pval_normal(b3_b, b3_se)
        b4_b = statistics.mean(col4_coefs)
        b4_se = statistics.stdev(col4_coefs)
        b4_g = statistics.mean(col4_g_coefs)
        b4_g_se = statistics.stdev(col4_g_coefs)
        # Per-scramble outputs include numfactors/N/Rsq via the standard
        # RunFactorModel writes but the aggregated summary only carries coefs.
        # Use the BenchBeg shared stats as a placeholder for the meta fields
        # (paper reports per-Col N and R^2; we punt those to the user via the
        # _summary CSV and leave the table to display "—" if not aggregated).
        col3_4_cells = True
        # SE-driven cells: use fmt_coef_se for bolding by analytic p<0.05 and
        # fmt_se for the SE in parentheses (paper for Beg table is p-values
        # in parens, so use fmt_pval_se via std-as-se).
        c3_cell_coef = fmt_coef_se(b3_b, b3_se, decimals=3, bold_thresh=0.05)
        c3_cell_pval = fmt_pval_se(b3_b, b3_se)
        c4_cell_coef = fmt_coef_se(b4_b, b4_se, decimals=3, bold_thresh=0.05)
        c4_cell_pval = fmt_pval_se(b4_b, b4_se)
        c4_g_cell_coef = fmt_coef_se(b4_g, b4_g_se, decimals=3, bold_thresh=0.05)
        c4_g_cell_pval = fmt_pval_se(b4_g, b4_g_se)
        # N, R^2, # factors are per-scramble and we don't aggregate here; use a dash
        c3_meta = c4_meta = "--"
    else:
        col3_4_cells = False
        c3_cell_coef = c3_cell_pval = ""
        c4_cell_coef = c4_cell_pval = ""
        c4_g_cell_coef = c4_g_cell_pval = ""
        c3_meta = c4_meta = ""

    footer_extra = ""
    if not col3_4_cells:
        footer_extra = "\n\\multicolumn{11}{l}{\\footnotesize Cols (3) and (4) are deferred (Scrambled Beg).} \\\\"

    CDEC = 3   # QWI-separation (beg) table: 3-decimal coefficients (original)
    beg_table = rf"""\begin{{tabular}}{{lccccccccccc}} \hline
VAR.       & (1) & (2) & (3) & (4) & (5) & (6) & (7) & (8) & (9) & (10)\\ \hline \noalign{{\vskip 2mm}}
Weeks of   & {fmt_coef(b1_b, b1_p)} & {fmt_coef(b2_b, b2_p)} & {c3_cell_coef} & {c4_cell_coef} & {fmt_coef(b5_b, b5_p)} & {fmt_coef(b6_b, b6_p)} & {fmt_coef(b7_b, b7_p)} & {fmt_coef(b8_b, b8_p)} & {fmt_coef(b9_b, b9_p)} & {fmt_coef(b10_b, b10_p)}\\
Benefits   & {fmt_pval(b1_p)} & {fmt_pval(b2_p)} & {c3_cell_pval} & {c4_cell_pval} & {fmt_pval(b5_p)} & {fmt_pval(b6_p)} & {fmt_pval(b7_p)} & {fmt_pval(b8_p)} & {fmt_pval(b9_p)} & {fmt_pval(b10_p)}\\ \noalign{{\vskip 4mm}}

State GDP  &  & {fmt_coef(b2_g, b2_g_pct)} &  & {c4_g_cell_coef} &  &  &  &  &  & \\
per Worker &  & {fmt_pval(b2_g_pct)} &  & {c4_g_cell_pval} &  &  &  &  &  & \\ \noalign{{\vskip 4mm}}

N. factors & {fmt_int(b1_nf)} & {fmt_int(b2_nf)} & {c3_meta} & {c4_meta} & {fmt_int(b5_nf)} & {fmt_int(b6_nf)} & {fmt_int(b7_nf)} & {fmt_int(b8_nf)} & {fmt_int(b9_nf)} & {fmt_int(b10_nf)}\\
Obs.       & {fmt_obs(b1_n)} & {fmt_obs(b2_n)} & {c3_meta} & {c4_meta} & {fmt_obs(b5_n)} & {fmt_obs(b6_n)} & {fmt_obs(b7_n)} & {fmt_obs(b8_n)} & {fmt_obs(b9_n)} & {fmt_obs(b10_n)}\\
R-squared  & {fmt_rsq(b1_rsq)} & {fmt_rsq(b2_rsq)} & {c3_meta} & {c4_meta} & {fmt_rsq(b5_rsq)} & {fmt_rsq(b6_rsq)} & {fmt_rsq(b7_rsq)} & {fmt_rsq(b8_rsq)} & {fmt_rsq(b9_rsq)} & {fmt_rsq(b10_rsq)}\\ \hline
{footer_extra}
\end{{tabular}}
"""

    (OUT_DIR / "Benefits_on_unemp_beg.tex").write_text(beg_table)


# ---------- tab:Effect_of_Distance ----------
# 8-column appendix table: dist< and dist> at 20/30/40/50 miles.
# SenseResultsDistance.csv has 9 rows per column:
#   1 coef, 2 %>0, 3 ci_lo, 4 ci_hi, 5 std, 6 numfactors, 7 R^2, 8 Nobs, 9 npairs
# Column order matches sep_methods in Factor_FrontEnd_Distance.m:
#   Dist20Lt, Dist20Gt, Dist30Lt, Dist30Gt, Dist40Lt, Dist40Gt, Dist50Lt, Dist50Gt

_dist_input = "SenseResultsDistance.csv"
if not (IN_DIR / _dist_input).exists():
    print(f"Skipping Effect_of_Distance.tex — missing input: {_dist_input}")
    print("Generate it by running code/exporters/OutputDataSetsUIMacro_Distance.do "
          "and code/matlab/Factor_FrontEnd_Distance.m.")
    _dist_done = False
else:
    dist = read_matrix("SenseResultsDistance.csv")
    # Helper to pull (coef, pct_gt_0, numfactors, Rsq, npairs) per column.
    def dist_cell(col_index):
        j = col_index - 1
        return dist[0][j], dist[1][j], dist[5][j], dist[6][j], dist[8][j]

    d1 = dist_cell(1)   # dist<20
    d2 = dist_cell(2)   # dist>20
    d3 = dist_cell(3)   # dist<30
    d4 = dist_cell(4)   # dist>30
    d5 = dist_cell(5)   # dist<40
    d6 = dist_cell(6)   # dist>40
    d7 = dist_cell(7)   # dist<50
    d8 = dist_cell(8)   # dist>50

    def fmt_dist_coef(d):
        return fmt_coef(d[0], d[1])

    def fmt_dist_pval(d):
        return fmt_pval(d[1])

    CDEC = 3   # Effect-of-Distance table: 3-decimal coefficients (original)
    distance_table = rf"""\begin{{tabular}}{{lccccccccccc}} \hline
Distance:    & \multicolumn{{2}}{{c}}{{20 Miles}} && \multicolumn{{2}}{{c}}{{30 Miles}} && \multicolumn{{2}}{{c}}{{40 Miles}} && \multicolumn{{2}}{{c}}{{50 Miles}}\\ \cline{{2-3}} \cline{{5-6}} \cline{{8-9}} \cline{{11-12}}
Less or More & $<$ & $>$ && $<$ & $>$ && $<$ & $>$ && $<$ & $>$\\
             & (1) & (2) && (3) & (4) && (5) & (6) && (7) & (8)\\ \hline \noalign{{\vskip 1mm}}
Weeks of Benefits & {fmt_dist_coef(d1)} & {fmt_dist_coef(d2)} && {fmt_dist_coef(d3)} & {fmt_dist_coef(d4)} && {fmt_dist_coef(d5)} & {fmt_dist_coef(d6)} && {fmt_dist_coef(d7)} & {fmt_dist_coef(d8)}\\
                  & {fmt_dist_pval(d1)} & {fmt_dist_pval(d2)} && {fmt_dist_pval(d3)} & {fmt_dist_pval(d4)} && {fmt_dist_pval(d5)} & {fmt_dist_pval(d6)} && {fmt_dist_pval(d7)} & {fmt_dist_pval(d8)}\\ \noalign{{\vskip 1mm}}

N. factors   & {fmt_int(d1[2])} & {fmt_int(d2[2])} && {fmt_int(d3[2])} & {fmt_int(d4[2])} && {fmt_int(d5[2])} & {fmt_int(d6[2])} && {fmt_int(d7[2])} & {fmt_int(d8[2])}\\
N. of pairs  & {fmt_int(d1[4])} & {fmt_int(d2[4])} && {fmt_int(d3[4])} & {fmt_int(d4[4])} && {fmt_int(d5[4])} & {fmt_int(d6[4])} && {fmt_int(d7[4])} & {fmt_int(d8[4])}\\
R-squared    & {fmt_rsq(d1[3])} & {fmt_rsq(d2[3])} && {fmt_rsq(d3[3])} & {fmt_rsq(d4[3])} && {fmt_rsq(d5[3])} & {fmt_rsq(d6[3])} && {fmt_rsq(d7[3])} & {fmt_rsq(d8[3])}\\ \hline
\multicolumn{{12}}{{c}}{{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap. Bold indicates $p<0.01$.}}\\
\end{{tabular}}
"""
    (OUT_DIR / "Effect_of_Distance.tex").write_text(distance_table)
    _dist_done = True


# ---------- tab:Forward_Spec ----------
# 4-column table: k, N. Observations, Permanent Effect, Implied Unemployment Rate
# Source: Forward_Spec_summary.csv (8 rows x 6 cols) produced by ProcessQDK.m.
#   cols = [k, Nobs, point_perm, point_u_pct, ci_perm_lo, ci_perm_hi]
# Paper also reports a mean row at the bottom (mean perm + mean impl_u across k).

_fwd_input = "Forward_Spec_summary.csv"
if not (IN_DIR / _fwd_input).exists():
    print(f"Skipping Forward_Spec.tex — missing input: {_fwd_input}")
    print("Generate it by running code/exporters/OutputDataSetsUIMacro_QDK.do, "
          "code/matlab/Factor_FrontEnd_QDK.m, and code/matlab/ProcessQDK.m in order.")
    _fwd_done = False
else:
    fwd = read_matrix("Forward_Spec_summary.csv")

    def fmt_perm(x):
        return f"{x:.2f}"

    rows = []
    for r in fwd:
        k_val, nobs, perm, impl_u, _, _ = r
        rows.append(rf"{fmt_int(k_val)} & {fmt_obs(nobs)} & {fmt_perm(perm)} & {fmt_perm(impl_u)} \\")

    mean_perm = statistics.mean(r[2] for r in fwd)
    mean_u = statistics.mean(r[3] for r in fwd)

    forward_table = (
        r"""\begin{tabular}{cccc}
\hline
$k$ & N. Observations & Permanent Effect & Implied Unemployment Rate\\
(1) & (2) & (3) & (4) \\ \hline \noalign{\vskip 1mm}
"""
        + "\n".join(rows)
        + rf"""
\noalign{{\vskip 1mm}}
\hline \noalign{{\vskip 1mm}}
Mean & & {fmt_perm(mean_perm)} & {fmt_perm(mean_u)}\\ \noalign{{\vskip 1mm}}
\hline
\end{{tabular}}
"""
    )
    (OUT_DIR / "Forward_Spec.tex").write_text(forward_table)
    _fwd_done = True


# ---------- §4.2 inline coefficients (Check_UFU) ----------
# Source: Check_UFU.csv produced by code/analysis/Check_UFU.do.
#   row 1 = u_t  (LHS = diff_logunemp_rate_laus)
#   row 2 = u_{t+1} (LHS = f1_logunemp_rate_laus)
# Each row: [coef, clustered_se, two_sided_p, N]
# Writes Check_UFU.tex defining \UFUDiffCoef, \UFUDiffPval, \UFULeadCoef,
# \UFULeadPval so the §4.2 paragraph can \providecommand-link these in.

_ufu_input = "Check_UFU.csv"
_ufu_done = False
if not (IN_DIR / _ufu_input).exists():
    print(f"Skipping Check_UFU.tex — missing input: {_ufu_input}")
    print("Generate it by running code/analysis/Check_UFU.do.")
else:
    ufu = read_matrix("Check_UFU.csv")
    diff_b, diff_se, diff_p, diff_n = ufu[0]
    lead_b, lead_se, lead_p, lead_n = ufu[1]

    def _pfmt(p):
        return "0.000" if p < 5e-4 else f"{p:.3f}"

    ufu_tex = (
        rf"\providecommand{{\UFUDiffCoef}}{{{diff_b:.3f}}}" + "\n" +
        rf"\providecommand{{\UFUDiffPval}}{{{_pfmt(diff_p)}}}" + "\n" +
        rf"\providecommand{{\UFULeadCoef}}{{{lead_b:.3f}}}" + "\n" +
        rf"\providecommand{{\UFULeadPval}}{{{_pfmt(lead_p)}}}" + "\n"
    )
    (OUT_DIR / "Check_UFU.tex").write_text(ufu_tex)
    _ufu_done = True


# ---------- §5.2 + wages appendix (Benefits_on_Wages) ----------
# Source: Benefits_on_Wages.csv produced by Factor_FrontEnd_QWIW.m.
#   One row per column, each the standard 8-stat _se layout:
#     [coef, %>0, 2.5pct, 97.5pct, std, N.factors, R^2, Nobs]
# Two layouts are accepted:
#   4 rows: New raw | New tax | All raw | All tax  (current — app cols 3-6;
#           the Job Stayers columns are produced by a separate front-end and
#           rendered blank here until that CSV exists)
#   6 rows: Stayers raw | Stayers tax | New raw | New tax | All raw | All tax
# Coefficients are reported to 4 decimals in both wage tables. Writes the main
# tab:Benefits_on_Wages (All-Workers columns) and the appendix
# tab:app_Benefits_on_Wages as \input-able tabular fragments.

_wage_input = "Benefits_on_Wages.csv"
_wage_done = False
if not (IN_DIR / _wage_input).exists():
    print(f"Skipping Benefits_on_Wages.tex / app_Benefits_on_Wages.tex — missing input: {_wage_input}")
    print("Generate it by running code/exporters/OutputDataSetsUIMacro_QWIW.do then code/matlab/Factor_FrontEnd_QWIW.m.")
elif len(read_matrix("Benefits_on_Wages.csv")) not in (4, 6):
    n = len(read_matrix("Benefits_on_Wages.csv"))
    print(f"Skipping wage tables — Benefits_on_Wages.csv has {n} rows, expected 4 or 6.")
else:
    wage = read_matrix("Benefits_on_Wages.csv")  # rows: coef,%>0,2.5,97.5,std,nfac,rsq,nobs
    if len(wage) == 6:
        st_r, st_t, nh_r, nh_t, al_r, al_t = wage
    else:  # 4 rows: New Hires + All Workers; stayers come from their own pairing
        st_r, st_t = None, None
        nh_r, nh_t, al_r, al_t = wage

    # Job Stayers are a separate pairing (OutputDataSetsUIMacro_QWIWStayers.do +
    # Factor_FrontEnd_QWIWStayers.m, LHS = wage2f_3 / RHS = ben_3). If that CSV
    # is present (2 rows: raw, tax) it populates the stayers columns; otherwise
    # they stay blank. NB: keep this and Benefits_on_Wages.csv on the SAME data
    # vintage for a single-vintage table.
    if (IN_DIR / "Benefits_on_Wages_Stayers.csv").exists():
        _st = read_matrix("Benefits_on_Wages_Stayers.csv")
        if len(_st) >= 2:
            st_r, st_t = _st[0], _st[1]

    # Column-cell formatters; a None column (not yet run) renders an empty cell.
    def _wc(row):   # 4-decimal coefficient, bolded by bootstrap p-value
        return fmt_coef(row[0], row[1], decimals=4) if row else ""

    def _wp(row):
        return fmt_pval(row[1]) if row else ""

    def _wf(row):
        return fmt_int(row[5]) if row else ""

    def _wo(row):
        return fmt_obs(row[7]) if row else ""

    def _wr(row):
        return fmt_rsq(row[6]) if row else ""

    # --- main text: All-Workers columns only ---
    main_wage = (
        r"""\begin{tabular}{lcc} \hline
    VARIABLES 	  & Raw Wages  & With Tax \\
    				  & (1) & (2)\\ \hline \noalign{\vskip 1mm}
"""
        + rf"Weeks of Benefits & {_wc(al_r)} & {_wc(al_t)}\\" + "\n"
        + rf"									 & {_wp(al_r)}	& {_wp(al_t)}\\ \noalign{{\vskip 1mm}}" + "\n\n"
        + rf"N. factors   & {_wf(al_r)} & {_wf(al_t)}  \\" + "\n"
        + rf"Observations & {_wo(al_r)} & {_wo(al_t)}  \\" + "\n"
        + rf"R-squared    & {_wr(al_r)} & {_wr(al_t)}  \\ \hline" + "\n"
        + r"""\multicolumn{3}{c}{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap.}\\
\multicolumn{3}{c}{Bold indicates $p<0.05$.} \\
\end{tabular}
"""
    )
    (OUT_DIR / "Benefits_on_Wages.tex").write_text(main_wage)

    # --- appendix: Job Stayers | New Hires | All Workers, raw and with tax ---
    app_wage = (
        r"""\begin{tabular}{lcccccccc} \hline
    VARIABLES & \multicolumn{2}{c}{Job Stayers} &&  \multicolumn{2}{c}{New Hires} &&  \multicolumn{2}{c}{All Workers}\\ \cline{2-3} \cline{5-6} \cline{8-9}
    				  & Raw    & With && Raw   & With && Raw   & With\\
    				  & Wages  & Tax  && Wages & Tax  && Wages & Tax\\
    				  & (1) & (2) && (3) & (4) && (1) & (2)\\ \hline \noalign{\vskip 1mm}
"""
        + rf"Weeks of  Benefits & {_wc(st_r)} & {_wc(st_t)} && {_wc(nh_r)} & {_wc(nh_t)} &&  {_wc(al_r)} & {_wc(al_t)}\\" + "\n"
        + rf"									 & {_wp(st_r)}	  & {_wp(st_t)}	 	 &&  {_wp(nh_r)}   	& {_wp(nh_t)}    && {_wp(al_r)}	& {_wp(al_t)}\\ \noalign{{\vskip 1mm}}" + "\n\n"
        + rf"N. factors   & {_wf(st_r)} & {_wf(st_t)} && {_wf(nh_r)} & {_wf(nh_t)} && {_wf(al_r)} & {_wf(al_t)}  \\" + "\n"
        + rf"Observations & {_wo(st_r)} & {_wo(st_t)} && {_wo(nh_r)} & {_wo(nh_t)} && {_wo(al_r)} & {_wo(al_t)}  \\" + "\n"
        + rf"R-squared    & {_wr(st_r)} & {_wr(st_t)} && {_wr(nh_r)} & {_wr(nh_t)} && {_wr(al_r)} & {_wr(al_t)}  \\  \hline" + "\n"
        + r"""\multicolumn{9}{c}{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap. Bold indicates $p<0.05$.} \\
\end{tabular}
"""
    )
    (OUT_DIR / "app_Benefits_on_Wages.tex").write_text(app_wage)
    _wage_done = True


# ---------- app_tab:A-1 (LAUS imputation / Hall test) ----------
# Source: LAUS_Imputation.csv produced by code/analysis/TableA2.do.
#   row 1 = county unemployment column, row 2 = county employment column
#   cols  = [b_other, se_other, b_state, se_state, N, R^2]
# Plain OLS with analytic SEs; the table prints SEs (not p-values) and bolds at
# p<0.01. (All coefficients here are hugely significant, so the one-sided vs
# two-sided pval_normal choice is immaterial to the bolding.)

_a1_input = "LAUS_Imputation.csv"
_a1_done = False
if not (IN_DIR / _a1_input).exists():
    print(f"Skipping LAUS_Imputation.tex — missing input: {_a1_input}")
    print("Generate it by running code/analysis/TableA2.do.")
else:
    a1 = read_matrix("LAUS_Imputation.csv")
    u_bo, u_so, u_bs, u_ss, u_n, u_r = a1[0]   # unemployment column
    e_bo, e_so, e_bs, e_ss, e_n, e_r = a1[1]   # employment column

    def _ac(b, se):
        return fmt_coef_se(b, se, decimals=4, bold_thresh=0.01)

    def _as(se):
        return fmt_se(se, decimals=4)

    a1_tex = (
        r"""\begin{tabular}{lcc} \hline
 & (1) & (2) \\
VARIABLES & county unemployment & county employment \\ \hline  \noalign{\vskip 2mm}
"""
        + rf"other county unemployment & {_ac(u_bo, u_so)} &  \\" + "\n"
        + rf" & {_as(u_so)} &  \\" + "\n"
        + rf"state unemployment & {_ac(u_bs, u_ss)} &  \\" + "\n"
        + rf" & {_as(u_ss)} &  \\" + "\n"
        + rf"other county employment &  & {_ac(e_bo, e_so)} \\" + "\n"
        + rf" &  & {_as(e_so)} \\" + "\n"
        + rf"state employment &  & {_ac(e_bs, e_ss)} \\" + "\n"
        + rf" &  & {_as(e_ss)} \\ \noalign{{\vskip 2mm}}" + "\n"
        + rf"Observations & {fmt_obs(u_n)} & {fmt_obs(e_n)} \\" + "\n"
        + rf" R-squared & {fmt_rsq(u_r)} & {fmt_rsq(e_r)} \\ \hline" + "\n"
        + r"""\multicolumn{3}{c}{ Standard errors in parentheses. Bold font indicates $p<0.01$.} \\
\end{tabular}
"""
    )
    (OUT_DIR / "LAUS_Imputation.tex").write_text(a1_tex)
    _a1_done = True


# ---------- tab:Endog_Vars (county HP / income / debt controls) ----------
# All three columns come from Endog_Vars.csv (code/analysis/Endog_Vars.do), estimated
#   in Stata: 3 rows [coef, se, N, R^2, n_factors] -- row 1 Factor Model (regife,
#   2 factors; R^2 = 1-SSR/SSY), row 2 OLS (reghdfe), row 3 IV-GLS (ivreg2). All
#   SEs analytic. Bold p<0.01; N.factors shown only for the factor column.

_ev_input = "Endog_Vars.csv"
_ev_done = False
if not (IN_DIR / _ev_input).exists():
    print(f"Skipping Endog_Vars.tex — missing input: {_ev_input}")
    print("Generate it by running code/analysis/Endog_Vars.do.")
else:
    ev = read_matrix("Endog_Vars.csv")
    o_b, o_se, o_n, o_r, _ = ev[1]   # OLS
    v_b, v_se, v_n, v_r, _ = ev[2]   # IV-GLS

    def _ec(b, se):
        return fmt_coef_se(b, se, decimals=3, bold_thresh=0.01)

    def _ep(b, se):
        return fmt_pval_se(b, se, decimals=3)

    # Col 1: Factor Model (regife interactive FE, analytic SE) -- Endog_Vars.csv row 1.
    f_b, f_se, f_n, f_r, f_nf = ev[0]
    col1_coef = _ec(f_b, f_se)
    col1_pval = _ep(f_b, f_se)

    ev_tex = (
        r"""\begin{tabular}{lccccc} \hline
    VARIABLES & Factor Model &&  OLS &&  IV-GLS \\ \cline{2-2} \cline{4-4} \cline{6-6}
    				  & (1) && (2) && (3) \\ \hline
"""
        + rf"Weeks of  Benefits & {col1_coef} && {_ec(o_b, o_se)} && {_ec(v_b, v_se)} \\" + "\n"
        + rf"									 & {col1_pval}	  && {_ep(o_b, o_se)}	 	 &&  {_ep(v_b, v_se)}\\" + "\n\n"
        + rf"N. factors   & {fmt_int(f_nf)} && -- && --   \\" + "\n"
        + rf"Observations & {fmt_obs(f_n)} && {fmt_obs(o_n)} && {fmt_obs(v_n)}  \\" + "\n"
        + rf"R-squared    & {fmt_rsq(f_r)} && {fmt_rsq(o_r)} && {fmt_rsq(v_r)}  \\ \hline" + "\n"
        + r"""\multicolumn{6}{c}{\footnotesize Note - $p$-values in parentheses. Bold indicates $p<0.01$.} \\
\end{tabular}
"""
    )
    (OUT_DIR / "Endog_Vars.tex").write_text(ev_tex)
    _ev_done = True


# ---------- tab:Mobility_LODES (LODES commuter counterfactual) ----------
# Source: Mobility_LODES.csv produced by code/analysis/Mobility_LODES.do.
#   1 row: [coef, bootstrap_se, n_factors, R^2, Nobs]. Parenthetical is the
#   bootstrap p (analytic from coef/bse, one-sided convention); bold p<0.01.
# NB: the draft renders the coefficient plain even though its p is 0.000 (a
# rendering oversight vs. its own "bold p<0.01" note); the generator applies the
# stated rule and bolds it.

_ml_input = "Mobility_LODES.csv"
_ml_done = False
if not (IN_DIR / _ml_input).exists():
    print(f"Skipping Mobility_LODES.tex — missing input: {_ml_input}")
    print("Generate it by running code/analysis/Mobility_LODES.do.")
else:
    ml = read_matrix("Mobility_LODES.csv")
    m_b, m_se, m_nf, m_r, m_n = ml[0]
    ml_tex = (
        r"""\begin{tabular}{lc} \hline
VARIABLES & Counterfactual Unemployment \\ \hline \noalign{\vskip 1mm}
"""
        + rf"Weeks of  Benefits& {fmt_coef_se(m_b, m_se, decimals=4, bold_thresh=0.01)} \\" + "\n"
        + rf" & {fmt_pval_se(m_b, m_se)} \\ \noalign{{\vskip 1mm}}" + "\n"
        + rf"Factors & {fmt_int(m_nf)} \\" + "\n"
        + rf"Observations & {fmt_obs(m_n)} \\" + "\n"
        + rf" R-squared & {fmt_rsq(m_r)} \\ \hline" + "\n"
        + r"""\multicolumn{2}{l}{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap. Bold indicates $p<0.01$.} \\
\end{tabular}
"""
    )
    (OUT_DIR / "Mobility_LODES.tex").write_text(ml_tex)
    _ml_done = True


# ---------- tab:Imputed_Results (imputed labor-market variables) ----------
# *** VACANCY-GATED *** Source: Imputed_Results.csv (code/analysis/Imputed_Results.do).
#   3 rows (Col 1 Out-of-State Search, Col 2 Imputed Tightness, Col 3 Imputed
#   Job-finding); cols = [coef, bootstrap_se, N, R^2, n_factors]. Bold p<0.01.
# Col 1's p reflects the one-sided convention (draft shows the two-sided 0.510);
# the conclusion -- search does not respond to benefits -- is unchanged.

_imp_input = "Imputed_Results.csv"
_imp_done = False
if not (IN_DIR / _imp_input).exists():
    print(f"Skipping Imputed_Results.tex — missing input: {_imp_input}")
    print("Generate it by running code/analysis/Imputed_Results.do (vacancy-gated).")
else:
    imp = read_matrix("Imputed_Results.csv")
    s_b, s_se, s_n, s_r, s_nf = imp[0]   # Out of State Search
    t_b, t_se, t_n, t_r, t_nf = imp[1]   # Imputed Tightness
    j_b, j_se, j_n, j_r, j_nf = imp[2]   # Imputed Job-finding

    def _ic(b, se):
        return fmt_coef_se(b, se, decimals=4, bold_thresh=0.01)

    def _ip(b, se):
        return fmt_pval_se(b, se)

    imp_tex = (
        r"""\begin{tabular}{lccc} \hline
VARIABLES & Out of State Search & Imputed Tightness  & Imputed Job-finding\\ \hline \noalign{\vskip 1mm}
"""
        + rf"Weeks of  Benefits& {_ic(s_b,s_se)} &  {_ic(t_b,t_se)}  & {_ic(j_b,j_se)}\\" + "\n"
        + rf" & {_ip(s_b,s_se)} &  {_ip(t_b,t_se)} & {_ip(j_b,j_se)}\\ \noalign{{\vskip 1mm}}" + "\n"
        + rf"Factors & {fmt_int(s_nf)} & {fmt_int(t_nf)} & {fmt_int(j_nf)}\\" + "\n"
        + rf"Observations & {fmt_obs(s_n)} & {fmt_obs(t_n)} & {fmt_obs(j_n)}\\" + "\n"
        + rf" R-squared & {fmt_rsq(s_r,4)} & {fmt_rsq(t_r,4)} & {fmt_rsq(j_r,4)}\\ \hline" + "\n"
        + r"""\multicolumn{4}{l}{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap. Bold indicates $p<0.01$.} \\
\end{tabular}
"""
    )
    (OUT_DIR / "Imputed_Results.tex").write_text(imp_tex)
    _imp_done = True


# ---------- tab:Benefits_on_JobCreation ----------
# Vacancies (qdk1_logvacrate2) + Tightness (qdk1_logtight2) from the HWOL pairing
# (SenseResultsHWOL.csv: col 1 Vac, col 2 Tight); Employment (qdk1_logqcew_emp)
# from the EmpQCEW pairing (SenseResultsEmpQCEW.csv, single col). Each CSV is the
# standard 8-row distresults layout [coef;%>0;2.5;97.5;std;nfac;R2;Nobs].
# Original precision: Vacancies/Tightness 3 decimals, Employment 4 decimals; bold p<0.01.
_jc_done = False
_jc_hwol = "SenseResultsHWOL.csv"
_jc_emp = "SenseResultsEmpQCEW.csv"
if not (IN_DIR / _jc_hwol).exists() or not (IN_DIR / _jc_emp).exists():
    miss = [f for f in (_jc_hwol, _jc_emp) if not (IN_DIR / f).exists()]
    print(f"Skipping Benefits_on_JobCreation.tex — missing input(s): {miss}")
    print("Generate via code/exporters/OutputDataSetsUIMacro_{HWOL,EmpQCEW}.do + "
          "code/matlab/Factor_FrontEnd_{HWOL,EmpQCEW}.m.")
else:
    hwol = read_matrix(_jc_hwol)
    empm = read_matrix(_jc_emp)
    vac = benefits(hwol, 1)   # (coef, pct_gt_0, numfactors, Rsq, Nobs)
    tig = benefits(hwol, 2)
    emp = benefits(empm, 1)
    jc_tex = rf"""\begin{{tabular}}{{lccc}} \hline
    VARIABLES & Vacancies & Tightness & Employment \\
    				  & (1) & (2) & (3) \\ \hline \noalign{{\vskip 1mm}}
Weeks of  Benefits & {fmt_coef(vac[0], vac[1], 3, 0.01)} & {fmt_coef(tig[0], tig[1], 3, 0.01)} & {fmt_coef(emp[0], emp[1], 4, 0.01)}  \\
	& {fmt_pval(vac[1])}	     & {fmt_pval(tig[1])}	 		&  {fmt_pval(emp[1])} \\ \noalign{{\vskip 1mm}}

N. factors & {fmt_int(vac[2])} & {fmt_int(tig[2])} & {fmt_int(emp[2])} \\
Observations & {fmt_obs(vac[4])} & {fmt_obs(tig[4])} & {fmt_obs(emp[4])} \\
 R-squared & {fmt_rsq(vac[3])} & {fmt_rsq(tig[3])} &  {fmt_rsq(emp[3])} \\ \hline
\multicolumn{{4}}{{l}}{{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap.}} \\
\multicolumn{{4}}{{l}}{{\footnotesize Bold indicates $p<0.01$.}} \\
\end{{tabular}}
"""
    (OUT_DIR / "Benefits_on_JobCreation.tex").write_text(jc_tex)
    _jc_done = True


# ---------- tab:macroeffects_beg ----------
# QWI-separation ("beg") analog of Benefits_on_JobCreation: same 3 columns, but the
# LHS are qdsbk1_ (QWI-beg separation) quasi-differences. SenseResultsHWOL_Beg.csv
# (col 1 Vac, col 2 Tight) + SenseResultsEmpQCEW_Beg.csv (Emp). Original precision:
# all 3 decimals; bold p<0.01.
_mb_done = False
_mb_hwol = "SenseResultsHWOL_Beg.csv"
_mb_emp = "SenseResultsEmpQCEW_Beg.csv"
if not (IN_DIR / _mb_hwol).exists() or not (IN_DIR / _mb_emp).exists():
    miss = [f for f in (_mb_hwol, _mb_emp) if not (IN_DIR / f).exists()]
    print(f"Skipping macroeffects_beg.tex — missing input(s): {miss}")
    print("Generate via code/exporters/OutputDataSetsUIMacro_{HWOL_Beg,EmpQCEW_Beg}.do + "
          "code/matlab/Factor_FrontEnd_{HWOL_Beg,EmpQCEW_Beg}.m.")
else:
    hwolb = read_matrix(_mb_hwol)
    empb = read_matrix(_mb_emp)
    vacb = benefits(hwolb, 1)
    tigb = benefits(hwolb, 2)
    empbr = benefits(empb, 1)
    mb_tex = rf"""\begin{{tabular}}{{lccc}} \hline
    VARIABLES & Vacancies & Tightness & Employment \\
    				  & (1) & (2) & (3) \\ \hline \noalign{{\vskip 1mm}}
Weeks of  Benefits & {fmt_coef(vacb[0], vacb[1], 3, 0.01)} & {fmt_coef(tigb[0], tigb[1], 3, 0.01)} & {fmt_coef(empbr[0], empbr[1], 3, 0.01)}  \\
	& {fmt_pval(vacb[1])}	     & {fmt_pval(tigb[1])}	 		&  {fmt_pval(empbr[1])} \\ \noalign{{\vskip 1mm}}

N. factors & {fmt_int(vacb[2])} & {fmt_int(tigb[2])} & {fmt_int(empbr[2])} \\
Observations & {fmt_obs(vacb[4])} & {fmt_obs(tigb[4])} & {fmt_obs(empbr[4])} \\
 R-squared & {fmt_rsq(vacb[3])} & {fmt_rsq(tigb[3])} &  {fmt_rsq(empbr[3])} \\ \hline
\multicolumn{{4}}{{l}}{{\footnotesize Note - $p$-values (in parentheses) calculated via bootstrap.}} \\
\multicolumn{{4}}{{l}}{{\footnotesize Bold indicates $p<0.01$.}} \\
\end{{tabular}}
"""
    (OUT_DIR / "macroeffects_beg.tex").write_text(mb_tex)
    _mb_done = True


# ---------- tab:MO_V_U ----------
# Per-Missouri-border jump in log V/U at the April-2011 cut, decomposed into the
# vacancy rise and the unemployment decline. MO_V_U.csv (from MO_Tightness_Figures.do)
# has one row per border: bordersegment, did_ltight (Tightness), did_lvac_sa
# (Vacancies), did_lunemp (Unemployment). Values are 3-decimal, leading zero stripped.
_movu_done = False
_movu_input = "MO_V_U.csv"
if not (IN_DIR / _movu_input).exists():
    print(f"Skipping MO_V_U.tex — missing input: {_movu_input}")
    print("Generate via code/analysis/MO_Tightness_Figures.do.")
else:
    movu = read_matrix(_movu_input)
    _mo_state = {11: "Arkansas", 46: "Illinois", 52: "Iowa", 56: "Kansas",
                 59: "Kentucky", 81: "Nebraska", 82: "Oklahoma", 83: "Tennessee"}
    _movu_rows = []
    for r in movu:
        seg = int(round(r[0]))
        name = _mo_state.get(seg, str(seg))
        _movu_rows.append(
            rf"{name}  && {fmt_nolead(r[1])}	&& {fmt_nolead(r[2])}	&& {fmt_nolead(r[3])} \\")
    movu_tex = (
        "\\begin{tabular}{lcccccc} \\hline\n"
        "Missouri Border && Change in	&& Change in && Change in \\\\\n"
        "with && Tightness	&& Vacancies	&& Unemployment \\\\ \\hline  \\noalign{\\vskip 1mm}\n"
        + "\n".join(_movu_rows)
        + "  \\noalign{\\vskip 1mm} \\hline\n"
        "\\multicolumn{5}{l}{ } \\\\\n"
        "\\end{tabular}\n"
    )
    (OUT_DIR / "MO_V_U.tex").write_text(movu_tex)
    _movu_done = True


print("Wrote:")
if _t1_done:
    print("  Benefits_on_unemp.tex")
print("  Benefits_on_unemp_SNAP_Mortgage.tex")
print("  Benefits_on_unemp_other_policies.tex")
print("  Benefits_on_unemp_stimulus_taxes.tex")
if not _ols_missing:
    print("  Benefits_on_unemp_OLS.tex")
if not _beg_missing:
    print("  Benefits_on_unemp_beg.tex")
if _dist_done:
    print("  Effect_of_Distance.tex")
if _fwd_done:
    print("  Forward_Spec.tex")
if _ufu_done:
    print("  Check_UFU.tex")
if _wage_done:
    print("  Benefits_on_Wages.tex")
    print("  app_Benefits_on_Wages.tex")
if _a1_done:
    print("  LAUS_Imputation.tex")
if _ev_done:
    print("  Endog_Vars.tex")
if _ml_done:
    print("  Mobility_LODES.tex")
if _imp_done:
    print("  Imputed_Results.tex")
if _jc_done:
    print("  Benefits_on_JobCreation.tex")
if _mb_done:
    print("  macroeffects_beg.tex")
if _movu_done:
    print("  MO_V_U.tex")


# ---------- tab:Monte-Carlo-Results (§monte_carlo) ----------
# Reads SenseResultsMonteCarlo.csv (code/matlab/RunMonteCarlo.m): 9 rows
# [panel, rho_t, rho_s, true, mean, median, delta]. Methodology check: the IFE
# estimator recovers the true 0.0532 across serial/spatial correlation structures
# (rho^t = 0.08 +/- 3 s.e. of 0.02; rho^s = 0.56 +/- 3 s.e. of 0.005).
import csv as _csv
_mc = HERE / "SenseResultsMonteCarlo.csv"
if _mc.exists():
    _rows = list(_csv.DictReader(open(_mc)))
    def _f4(x): return f"{float(x):.4f}"
    def _lab(v, base):
        fv = float(v)
        if abs(fv - base) < 1e-9:
            return f"${base:g}$"
        return f"${base:g} \\, {'+' if fv > base else '-'} \\, 3\\,\\textrm{{S.E.}}$"
    def _mcrow(r):
        return (f"{_lab(r['rho_t'],0.08)} & {_lab(r['rho_s'],0.56)} & "
                f"{_f4(r['true'])} & {_f4(r['mean'])} & {_f4(r['median'])} & {_f4(r['delta'])} \\\\")
    _byp = {}
    for r in _rows:
        _byp.setdefault(r['panel'], []).append(r)
    _titles = {'A': 'Panel A: Benchmark Specification',
               'B': 'Panel B: Changing Serial Correlation Only',
               'C': 'Panel C: Changing Spatial Correlation Only',
               'D': 'Panel D: Changing Serial and Spatial Correlation'}
    _body = []
    for _p in ['A', 'B', 'C', 'D']:
        _body.append(f"\\multicolumn{{6}}{{c}}{{\\underline{{{_titles[_p]}}}}}\\\\ \\noalign{{\\vskip 2mm}}")
        for r in _byp.get(_p, []):
            _body.append(_mcrow(r))
        _body.append("\\noalign{\\vskip 2mm}")
    mc_tex = ("\\begin{tabular}{cccccc} \\hline\\hline \\noalign{\\vskip 1mm}\n"
              "\\multicolumn{2}{c}{Parameterization} & & & & \\\\ \\cline{1-2} \\noalign{\\vskip 1mm}\n"
              "Serial, $\\rho^{t}$ & Spatial, $\\rho^{s}$ & True value & Mean & Median & $\\Delta$ \\\\ \\noalign{\\vskip 1mm} \\hline \\noalign{\\vskip 2mm}\n"
              + "\n".join(_body) +
              "\\hline\n\\end{tabular}\n")
    (OUT_DIR / "Monte_Carlo_Results.tex").write_text(mc_tex)
    print("Wrote Monte_Carlo_Results.tex")


# ---------- calib (Internally Calibrated Parameters) ----------
# Committed parameters (h, xi, gamma) of the 2D structural model. The Data
# column holds the calibration targets; the Model column holds what the calibrated
# model produces. Coefficient target = empirical Bench Col-1 QD coef (SenseResultsBench);
# coefficient Model = QD regression on the simulated panel (ModelCalibCoef.csv, from
# code/analysis/ModelPanelRegression.do). Mean-tightness / mean-job-finding targets (0.634 /
# 0.139) are external labor-market moments; their Model values are the baseline ergodic
# averages avgt0 / avgf0 from code/model/RunModel.m (ModelValidation.csv cols 5,6).
_calib_inputs = ["ModelCalibCoef.csv", "ModelValidation.csv"]
if not all((IN_DIR / f).exists() for f in _calib_inputs):
    miss = [f for f in _calib_inputs if not (IN_DIR / f).exists()]
    print(f"Skipping Model_Calibration.tex — missing input(s): {miss}")
    print("Generate via code/model/RunModel.m + code/analysis/ModelPanelRegression.do.")
else:
    _cc = read_matrix("ModelCalibCoef.csv")[0]      # [coef_u, coef_v, coef_t, Nobs]
    _mv = read_matrix("ModelValidation.csv")[0]      # [du dt dv avgu0 avgt0 avgf0 ...]
    coef_data  = bench[0][0]      # empirical Bench Col-1 QD coef (~0.0532)
    coef_model = _cc[0]           # model QD coef on the simulated panel (~0.0528)
    tight_model = _mv[4]          # baseline ergodic mean tightness
    jf_model    = _mv[5]          # baseline ergodic mean job-finding
    TIGHT_TGT, JF_TGT = 0.634, 0.139
    calib_tex = rf"""\begin{{tabular}}{{llclcc}}
\hline
\hline
 & Parameter & Value & Target & Data & Model \\ \hline  \noalign{{\vskip 1mm}}
$h$ & Value of non-market activity &  0.6095 & Regression Coefficient  & {coef_data:.3f} & {coef_model:.3f} \\
$\xi$ & Bargaining power & 0.0834 & Mean tightness & {TIGHT_TGT:.3f} & {tight_model:.3f} \\
$\gamma$ & Matching function parameter & 0.4022 & Mean job-finding rate & {JF_TGT:.3f} & {jf_model:.3f} \\  \noalign{{\vskip 1mm}}
\hline
\end{{tabular}}
"""
    (OUT_DIR / "Model_Calibration.tex").write_text(calib_tex)
    print("Wrote Model_Calibration.tex")


# ---------- valid (Estimated Permanent Effect: Model vs Data) ----------
# Data row = the estimator's PREDICTION: empirical QD coef x permanent multiplier
#   1/(1-0.9*0.99)=9.1743 x log(36/26) (a 10-week extension). u from Bench Col 1
#   (SenseResultsBench), v/theta from JobCreation (SenseResultsHWOL cols 1,2).
# Model row = the model's TRUE permanent effect (ergodic-average log-difference of the
#   +10-week EB-schedule-shift simulation) from code/model/RunModel.m (ModelValidation.csv:
#   col1 du=Unemp, col2 dt=Tightness, col3 dv=Vacancies -- note table order is u/v/theta).
_valid_inputs = ["ModelValidation.csv", "SenseResultsHWOL.csv"]
if not all((IN_DIR / f).exists() for f in _valid_inputs):
    miss = [f for f in _valid_inputs if not (IN_DIR / f).exists()]
    print(f"Skipping Model_Validation.tex — missing input(s): {miss}")
    print("Generate via code/model/RunModel.m (Model row) + the HWOL JobCreation pairing (Data v/theta).")
else:
    _fac = (1.0 / (1.0 - 0.9 * 0.99)) * math.log(36.0 / 26.0)   # permanent multiplier x log(36/26)
    _mv = read_matrix("ModelValidation.csv")[0]
    _hw = read_matrix("SenseResultsHWOL.csv")
    m_u, m_t, m_v = _mv[0], _mv[1], _mv[2]                       # Model: TRUE perm effects
    d_u = bench[0][0] * _fac                                     # Data: empirical coef x factor
    d_v = _hw[0][0] * _fac                                       # HWOL col 1 = Vacancies
    d_t = _hw[0][1] * _fac                                       # HWOL col 2 = Tightness
    valid_tex = rf"""\begin{{tabular}}{{lccc}}
\hline
VARIABLES & Unemp. & Vacancies & Tightness    \\
 & (1) & (2) & (3) \\ \hline  \noalign{{\vskip 1mm}}
Data  & {d_u:.3f} & {d_v:.3f} & {d_t:.3f} \\
Model & {m_u:.3f} & {m_v:.3f} & {m_t:.3f} \\ \hline
\end{{tabular}}
"""
    (OUT_DIR / "Model_Validation.tex").write_text(valid_tex)
    print("Wrote Model_Validation.tex")
