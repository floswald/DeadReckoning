* ---------------------------------------------------------------------------
* Impute_to_Stata.do  ->  packages the Matlab imputation output into
*                         ImputedDataBorder.dta (the input to Imputed_Results.do)
*
* Reads the Matlab driver output Impute_Results.txt (written by
* Run_Impute_Border.m) and saves it keyed by bordersegment fipsstate year quarter,
* matching the schema of the original imputed border dataset:
*   f x thet_corr phi utilde meanx val mu_t alpha_c.
*
* *** VACANCY-GATED *** (the imputation embeds proprietary vacancies). The
* synthetic-vacancy path replaces the vacancy inputs.
* ---------------------------------------------------------------------------

do "config.do"
global CodeDirec ="${code}/analysis/"
global maindirectory "${processed}/"
global latexdir "${factor_csv}/"
* Output: ImputedDataBorder.dta in data/processed/ -- a BUILT intermediate, NOT shipped
* (the replicator regenerates it here). Synthetic by default (the kit's ${vacfile}); the
* Data Editor's real-HWOL run writes the real version to the same path. Matches the schema
* of the original imputed border dataset.
if "${ImputedOut}"=="" global ImputedOut "${processed}/ImputedDataBorder.dta"

set more off, perm

insheet bordersegment fipsstate year quarter f x thet_corr phi utilde meanx val mu_t alpha_c ///
    using "${latexdir}Impute_Results.txt", comma clear

sort bordersegment fipsstate year quarter
save "${ImputedOut}", replace

cd "${CodeDirec}"
