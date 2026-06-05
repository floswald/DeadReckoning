lines <- c(
  "\\begin{tabular}{lrr}",
  "\\toprule",
  "Variable & Mean & Std Dev \\\\",
  "\\midrule",
  sprintf("MPG & %.1f & %.2f \\\\", mean(mtcars$mpg), sd(mtcars$mpg)),
  sprintf("Weight & %.2f & %.2f \\\\", mean(mtcars$wt), sd(mtcars$wt)),
  sprintf("HP & %.1f & %.2f \\\\", mean(mtcars$hp), sd(mtcars$hp)),
  "\\bottomrule",
  "\\end{tabular}"
)
writeLines(lines, "tables/summary.tex")
