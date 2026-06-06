library(ggplot2)
library(haven)

df <- read_dta("/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.dta")
df <- df[!is.na(df$wage), ]

p <- ggplot(df, aes(x = age, y = wage)) + geom_point() + theme_minimal()
ggsave("fig_r.pdf", plot = p, width = 8, height = 5)
