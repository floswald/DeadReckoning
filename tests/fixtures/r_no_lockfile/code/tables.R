library(dplyr)
library(stargazer)

df <- readRDS("/Users/jsmith/Dropbox/JPE_paper/data/model_results.rds")

# Writes table to correct path
stargazer(df, out = "tables/tab1.tex", type = "latex")
