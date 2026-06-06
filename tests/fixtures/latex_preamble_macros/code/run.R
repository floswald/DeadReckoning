library(ggplot2)
p <- ggplot(mtcars, aes(x=wt, y=mpg)) + geom_point()
ggsave("figures/fig1.pdf", plot=p)
