using DataFrames, CSV
using Plots

df = CSV.read("/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.csv", DataFrame)
df = filter(row -> !ismissing(row.wage), df)

p = scatter(df.age, df.wage, legend = false)
savefig(p, "fig_jl.pdf")
