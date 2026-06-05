library(haven)
library(ggplot2)

df <- read_dta("data/census_microdata_restricted.dta")

p <- ggplot(df, aes(x = age, y = earnings)) + geom_point()
ggsave("figures/fig1.pdf", plot = p)
