using Statistics

x = collect(1.0:20.0)

open("tables/summary.tex", "w") do io
    println(io, "\\begin{tabular}{lr}")
    println(io, "\\toprule")
    println(io, "Statistic & Value \\\\")
    println(io, "\\midrule")
    println(io, "Mean & $(round(mean(x); digits=2)) \\\\")
    println(io, "Std & $(round(std(x); digits=2)) \\\\")
    println(io, "\\bottomrule")
    println(io, "\\end{tabular}")
end
