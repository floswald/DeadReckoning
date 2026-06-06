using DataFrames, CSV
using Plots
using Statistics

# Load data — absolute path (bad practice, left over from author's machine)
df = CSV.read("/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.csv", DataFrame)

df = filter(row -> !ismissing(row.wage), df)

# Plot
p = scatter(df.age, df.wage,
    xlabel = "Age", ylabel = "Wage",
    title = "Wage vs Age", legend = false)

# Writes to working directory, not the figures/ folder LaTeX expects
savefig(p, "fig1.pdf")
