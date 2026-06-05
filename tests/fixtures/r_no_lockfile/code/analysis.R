library(ggplot2)
library(dplyr)
library(haven)

# Load data — absolute path (bad practice, left over from author's machine)
df <- read_dta("/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.dta")

df_clean <- df %>% filter(!is.na(wage))

p <- ggplot(df_clean, aes(x = age, y = wage)) +
  geom_point() +
  theme_minimal()

# Writes to working directory, not the figures/ folder LaTeX expects
ggsave("fig1.pdf", plot = p, width = 8, height = 5)
