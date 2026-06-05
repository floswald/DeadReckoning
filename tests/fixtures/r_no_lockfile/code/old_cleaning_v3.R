# Old cleaning script — not called by anything, not needed
library(dplyr)
df <- read.csv("data/raw_old.csv")
df_clean <- df %>% filter(year > 2010)
write.csv(df_clean, "data/cleaned_old.csv")
