library(dplyr)
library(stargazer)

df <- read.csv("data/raw/survey.csv")
stargazer(df, out = "tables/tab1.tex", type = "latex")
