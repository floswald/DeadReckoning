import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
import numpy as np

# Load data — absolute path (bad practice, left over from author's machine)
df = pd.read_csv("/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.csv")

df = df[df["wage"].notna()].copy()

# Fit model
X = df[["age"]].values
y = df["wage"].values
model = LinearRegression().fit(X, y)

# Plot
fig, ax = plt.subplots()
ax.scatter(df["age"], df["wage"], alpha=0.3)
ax.plot(df["age"], model.predict(X), color="red")
ax.set_xlabel("Age")
ax.set_ylabel("Wage")

# Writes to working directory, not the figures/ folder LaTeX expects
plt.savefig("fig1.pdf")
