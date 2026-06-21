import statistics

x = list(range(1, 21))

with open("tables/summary.tex", "w") as f:
    f.write("\\begin{tabular}{lr}\n")
    f.write("\\toprule\n")
    f.write("Statistic & Value \\\\\n")
    f.write("\\midrule\n")
    f.write(f"Mean & {statistics.mean(x):.2f} \\\\\n")
    f.write(f"Std & {statistics.stdev(x):.2f} \\\\\n")
    f.write("\\bottomrule\n")
    f.write("\\end{tabular}\n")
