# Combines author 1's revenue panel with author 2's region weights to
# produce Table 3's weighted-average-revenue statistic.
using CSV, DataFrames

panel = CSV.read("data/panel.csv", DataFrame)
weights = CSV.read("data/input_data_from_2.csv", DataFrame)
merged = innerjoin(panel, weights, on = :region_id)

weighted_avg = sum(merged.weight .* merged.revenue) / sum(merged.weight)

open("output/Table3.tex", "w") do io
    write(io, "\\begin{tabular}{lc}\n")
    write(io, "\\toprule\n")
    write(io, "Average regional revenue (weighted, \\\$ thousands) & $(round(weighted_avg, digits=2)) \\\\\n")
    write(io, "\\bottomrule\n")
    write(io, "\\end{tabular}\n")
end
