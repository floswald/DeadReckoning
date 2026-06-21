#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Make_BenefitMaps.py  ->  AllMaps{42,48,...,96}.jpg  (paper fig:Benefit_Maps_*)
#
# County choropleths of TOTAL weeks of UI benefits available, at 10 snapshots:
# June and December of 2008-2012 (the EUC/EB era). Benefits are a state-level
# policy, so every county is colored by its state's value (uniform within state
# -- any apparent sub-state variation in the originals was a coding error).
#
# Snapshot -> AllMaps name (chronological, every 6 months):
#   Jun2008=42 Dec2008=48 Jun2009=54 Dec2009=60 Jun2010=66
#   Dec2010=72 Jun2011=78 Dec2011=84 Jun2012=90 Dec2012=96
#
# Inputs (in data/raw/):
#   FullFinal_AllYears-Daily.dta  - state x year x month x day x totalweeks_daily
#                                   x statefips (national, 51 = 50 states + DC).
#   cb_2025_us_county_20m/        - Census county cartographic boundary shapefile.
#
# The original 2013 ArcGIS producer was not recovered; this reproduces the maps from the
# kit's data. Run with a Python that has geopandas + matplotlib:
#   python3 code/analysis/Make_BenefitMaps.py
# Outputs: output/figures/AllMaps{NN}.jpg
# ---------------------------------------------------------------------------

import os, zipfile
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..","..","data","raw")+os.sep
SHP  = DATA + "cb_2025_us_county_20m/cb_2025_us_county_20m.shp"
OUT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..","..","output","figures")+os.sep

# --- snapshots: (year, month) chronological -> AllMaps NN (start 42, step 6) ---
snaps = [(y, m) for y in range(2008, 2013) for m in (6, 12)]
NNs   = list(range(42, 42 + 6 * len(snaps), 6))

# --- benefit weeks (state x month) ---
df = pd.read_stata(DATA + "FullFinal_AllYears-Daily.dta")

# --- county geometry, contiguous US only, Albers Equal-Area (EPSG:5070) ---
gdf = gpd.read_file(SHP)
gdf["sf"] = gdf["STATEFP"].astype(int)
gdf = gdf[~gdf["sf"].isin({2, 15, 72, 60, 66, 69, 78})].copy()  # drop AK/HI/PR/territories
gdf = gdf.to_crs(epsg=5070)
states = gdf.dissolve(by="sf")  # state outlines

# --- color scheme: 9 green bins matching the paper legend ---
#   [0,26] (26,39] (39,46] (46,60] (60,75] (75,85] (85,90] (90,95] >95
# weeks are integers, so .5-offset breaks assign each value cleanly to its bin.
bounds = [0, 26.5, 39.5, 46.5, 60.5, 75.5, 85.5, 90.5, 95.5, 1000]
labels = ["[0, 26]", "(26, 39]", "(39, 46]", "(46, 60]", "(60, 75]",
          "(75, 85]", "(85, 90]", "(90, 95]", "> 95"]
greens = plt.cm.Greens(np.linspace(0.06, 0.95, 9))
cmap = ListedColormap(greens)
norm = BoundaryNorm(bounds, cmap.N)
handles = [Patch(facecolor=greens[i], edgecolor="k", linewidth=0.4, label=labels[i])
           for i in range(9)]

for (y, m), nn in zip(snaps, NNs):
    sub = df[(df.year == y) & (df.month == m)]
    wk = sub.groupby("statefips").totalweeks_daily.median()
    g = gdf.copy()
    g["wk"] = g["sf"].map(wk)

    fig, ax = plt.subplots(figsize=(9, 5.6))
    g.plot(column="wk", cmap=cmap, norm=norm, ax=ax, edgecolor="0.55", linewidth=0.1)
    states.boundary.plot(ax=ax, color="black", linewidth=0.5)
    ax.axis("off")
    ax.legend(handles=handles, loc="lower right", fontsize=8,
              frameon=True, handlelength=1.2, handleheight=1.0, labelspacing=0.25)
    fig.savefig(OUT + f"AllMaps{nn}.jpg", dpi=200, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print(f"AllMaps{nn}.jpg  {y}-{m:02d}  states={wk.size}  wks {wk.min():.0f}-{wk.max():.0f}")

print("done")
