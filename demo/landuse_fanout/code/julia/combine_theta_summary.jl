# Combines generatethetas.do's rural TFP series (FRA_model.csv) with a
# coauthor-supplied decade weighting scheme (data/decade_weights.csv) to
# produce a single decade-weighted summary statistic — the chain-drift
# stage added to this fixture alongside the real two-script fan-out. See
# demo/landuse_fanout/README.md for how this stage was built and why.
using CSV, DataFrames, Statistics

thetas = CSV.read("data/processed/FRA_model.csv", DataFrame)
weights = CSV.read("data/decade_weights.csv", DataFrame)

thetas = thetas[.!ismissing.(thetas.theta_rural), :]
thetas.decade = 10 .* div.(thetas.year, 10)

by_decade = combine(groupby(thetas, :decade), :theta_rural => mean => :theta_rural)
merged = innerjoin(by_decade, weights, on = :decade)

weighted_avg = sum(merged.weight .* merged.theta_rural) / sum(merged.weight)

open("output/TableTheta.tex", "w") do io
    write(io, "\\begin{tabular}{lc}\n")
    write(io, "\\toprule\n")
    write(io, "Decade-weighted average rural TFP (1815=1) & $(round(weighted_avg, digits=4)) \\\\\n")
    write(io, "\\bottomrule\n")
    write(io, "\\end{tabular}\n")
end
