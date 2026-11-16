# Reads the per-region anchor incomes code/stata/prep_survey.do picked,
# and simulates region-level income shocks via a compiled Rcpp routine
# (src/shocks.cpp), producing the paper's Table 1 and Figure 1.
library(Rcpp)
sourceCpp("src/shocks.cpp")

anchors <- haven::read_dta("data/survey_prepped.dta")

n_draws <- 2000
shocks <- simulate_shocks(n_draws, anchors$anchor_income)

mean_shock <- mean(shocks)
sd_shock <- sd(shocks)

tex <- sprintf(
  paste0(
    "\\begin{tabular}{lc}\n\\toprule\n",
    "Simulated mean income shock & %.4f \\\\\n",
    "Simulated SD income shock & %.4f \\\\\n",
    "\\bottomrule\n\\end{tabular}\n"
  ),
  mean_shock, sd_shock
)
writeLines(tex, "output/Table1.tex")

pdf("output/fig1.pdf", width = 5, height = 4)
hist(shocks, main = "Simulated income shocks", xlab = "shock")
dev.off()
