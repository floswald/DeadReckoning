library(ggplot2)
p <- ggplot(mtcars, aes(x = wt, y = mpg)) +
  geom_point() +
  labs(x = "Weight (1000 lbs)", y = "MPG")
ggsave("figures/fig1.pdf", plot = p, width = 6, height = 4)
