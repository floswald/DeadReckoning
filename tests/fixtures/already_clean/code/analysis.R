library(ggplot2)
library(dplyr)

df <- read.csv("data/raw/survey.csv")

p <- ggplot(df, aes(x = age, y = income)) +
  geom_point() +
  theme_minimal()

ggsave("figures/fig1.pdf", plot = p, width = 8, height = 5)
