"""Mean household income from a confidential household survey."""

import csv


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    rows = read_csv("data/survey_confidential.csv")
    # BUG: the column is actually named "income", not "household_income" —
    # a renamed-column slip. A normal (non-restricted) run would get this
    # fixed live by Claude; see run_demo_restricted.py.
    incomes = [float(r["household_income"]) for r in rows]
    mean_income = sum(incomes) / len(incomes)

    with open("output/table1.tex", "w") as f:
        f.write("\\begin{tabular}{lr}\n")
        f.write("\\toprule\n")
        f.write("Statistic & Value \\\\\n")
        f.write("\\midrule\n")
        f.write(f"Mean household income & {mean_income:.2f} \\\\\n")
        f.write(f"N & {len(rows)} \\\\\n")
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")


if __name__ == "__main__":
    main()
