import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("/Users/jsmith/Dropbox/python_project/data/lfs_2019.csv")
df = df[df['wage'].notna()].copy()

fig, ax = plt.subplots()
ax.scatter(df['age'], df['wage'], alpha=0.3)
ax.set_xlabel("Age"); ax.set_ylabel("Wage")
plt.savefig("fig1.pdf")
plt.savefig("fig2.pdf")
