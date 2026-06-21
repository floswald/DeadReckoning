**********************************************************************************************
* RunBuild.do  --  one-command orchestrator for the entire data build.
*
* Run from the code/ directory:
*     do "RunBuild.do"                 (interactive)
*     stata-mp -b do RunBuild.do       (batch)
*
* config.do is sourced ONCE here. Its globals (${rawdata} ${code} ${processed} ${vacfile} ...)
* survive the `clear all' at the top of each child script, so no child needs to re-set paths.
* `cd "${code}"' is reissued before each child because several producers cd into working dirs.
*
* ---------------------------------------------------------------------------------------------
* STAGE 1 (default ON) -- build every from-raw input in data/raw/ from primary sources, via the
*   producers in build/RawDataScripts/.  The archive ships NO pre-built intermediates, so this
*   stage runs by default (`rebuild_from_raw' = 1).  Each source's raw inputs and build steps are
*   documented in build/RawDataScripts/<source>/SOURCE_NOTES.md.
*
*   NOT built by Stage 1 (shipped as PROVIDED inputs -- no in-kit producer):
*     benefit weeks       benefit_weeks (the ONE consolidated weeks input the build
*                         merges), plus Fullbenefits_MeanWks_Update (consumed only by
*                         the LAUS Stage-1 chain, step 2)
*     external downloads  LatLongData, cbsacode_xwalk
*     archived/published  population_age (Census county pop, pre-rebase vintage),
*                         cpssep (Shimer 2012 separation series)
*
*   One Stage-1 step is MATLAB, which Stata cannot call: JobFinding/step1_backoutf_fp.m. Run it in
*   MATLAB first (do_replication.sh does this); it writes jobfindingfp_v12.txt that steps 2-3 consume.
*
* STAGE 2 (always) -- build the three master datasets in data/processed/ via UIMacro_BuildData.do:
*   UIMacro_RevisionData, UIMacro_DataControls, ProcessedWages.
*
* HWOL county/state vacancies are proprietary; the kit ships a synthetic stand-in and the build
* reads it through ${vacfile}/${statefile} (config), so only public/synthetic data is used. The
* Data Editor swaps in licensed HWOL via those switches to reproduce published vacancy numbers.
**********************************************************************************************

clear all
do "config.do"

local rebuild_from_raw = 1      // <- 1 = full from-primary rebuild (the shipped default). Set 0 ONLY to
                                //    re-run Stage 2 after a prior full build; the archive ships no
                                //    pre-built data/raw intermediates, so 0 on a fresh archive will fail.

*---------------------------------------------------------------------------------------------
* STAGE 1 -- producers (from-raw inputs)
*---------------------------------------------------------------------------------------------
if `rebuild_from_raw' {

    * UI tax base first (feeds the QWI and QCEW tax-rate steps below)
    cd "${code}"
    do "build/RawDataScripts/BuildUITax.do"

    * single-output producers (order-independent)
    foreach p in                                                ///
            JOLTS/MakeJolts                                     ///
            FHFA/MakeFHFA_HPI                                   ///
            IRSEquifax/Make_IRSEquifax                          ///
            CountyDebt/MakeCountyDebt                           ///
            Saiz/Make_Saiz_Elasticity                           ///
            SNAP/Process_SNAP_Policy_Database                   ///
            StatePolicies/Make_StatePolicies_Indices            ///
            StatePolicies/Make_StatePolicies_Taxes              ///
            BEA_Industry/Make_IndustryShares                    ///
            BEA_GDP/Make_BEA_GDP_State_Q                        ///
            Spending/Make_SpendingData                          ///
            BLS_State/Make_StateEmp                             ///
            LAUS_Additivity/Script/construct_laus_additivity {
        cd "${code}"
        do "build/RawDataScripts/`p'.do"
    }

    * core LAUS border-county-pair panel (steps 1-3) + state SA employment (steps 4-5)
    * + the state monthly rate panels for the placebo (steps 6-7, Dec-2015 revised raws)
    * + state quarterly unemployment for TableA2 (step 8); 4-8 are independent
    * sub-chains off the same download batches (see LAUS/SOURCE_NOTES.md)
    foreach p in 1_construct_laus_2014 2_MakeNewLAUSDataSet                     ///
            3_MakeNewLAUSBorderDataSet24Nov16                                   ///
            4_construct_laus_state_sa_pre 5_Make_StateEmp2014rev                ///
            6_construct_laus_state_sa 7_construct_laus_state_u                  ///
            8_Make_StateQuarterlyU {
        cd "${code}"
        do "build/RawDataScripts/LAUS/`p'.do"
    }

    * QCEW county employment (1990-2015 allhlcn + 1975-89 history + 2014 refresh + merges + tax)
    foreach p in 1_construct_qcew_2015 1b_QCEW_Historical_1975_1989 1c_QCEW_County_2014 2_MergeFullQCEW 3_MergeFullQCEW_2014_Q4 4_MakeQCEWTaxRate {
        cd "${code}"
        do "build/RawDataScripts/QCEW/`p'.do"
    }

    * QWI worker flows / wages (3-step chain)
    foreach p in 1_BuildQWI 2_MakeQWI_2018_09_18 3_MakeQWITaxRate {
        cd "${code}"
        do "build/RawDataScripts/QWI/`p'.do"
    }

    * job-finding rate: step 1 (step1_backoutf_fp.m) is MATLAB -- run it first; steps 2-3 are Stata
    foreach p in 2_makejobfind 3_MakeQuarterlyF {
        cd "${code}"
        do "build/RawDataScripts/JobFinding/`p'.do"
    }

    * commuter shares (LODES): aggregate, then match-to-pairs (which internally runs TransposePairs)
    foreach p in 1_make_aggregate_byresidence LODES_match_to_pairs_v6 {
        cd "${code}"
        do "build/RawDataScripts/LODES/`p'.do"
    }

    * Bartik shocks (needs QWI_2018_09_18 + the LAUS border panel)
    cd "${code}"
    do "build/RawDataScripts/Bartik/MakeBartikShocks.do"

    * NOTE: the synthetic HWOL stand-ins are PROVIDED in synthetic-data/ and are NOT
    * regenerated here. build/Make_Synthetic_Vacancies.do (county; seeded Beveridge model
    * on public JOLTS/LAUS) reads the BUILT UIMacro_RevisionData, so it can only be re-run
    * AFTER a full Stage-2 build (run it, then rebuild, to demonstrate the recipe).
    * build/Make_Synthetic_StateBorderData.do (the STATE-level synthetic generator)
    * is NOT run here -- it anonymizes the licensed HWOL state panel, which is not in this
    * archive. Its output ships as synthetic-data/StateMonthlyBorderData_synthetic.dta;
    * only the Data Editor (with the licensed panel) can regenerate it.

    * placebo benefit-weeks panel
    cd "${code}"
    do "build/Make_PlaceboWeeksData.do"
}

*---------------------------------------------------------------------------------------------
* STAGE 2 -- master datasets (always)
*---------------------------------------------------------------------------------------------
cd "${code}"
do "build/UIMacro_BuildData.do"

di as result _n "==== RunBuild.do complete ===="
