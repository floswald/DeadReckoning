#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Make_CountyMap.py  ->  countymap2.png  (paper fig:Counties_Map)
#
# "Map of U.S.A. with state and county outlines" -- the appendix locator map.
# Plain county boundaries (thin) + state boundaries (thick), white fill, with
# Alaska and Hawaii as insets. No data, just geography.
#
# The original was a one-off GIS export (not recovered); this regenerates it
# from the Census county shapefile already used by Make_BenefitMaps.py.
#
# Run with a Python that has geopandas + matplotlib:
#   python3 code/analysis/Make_CountyMap.py
# Output: output/figures/countymap2.png
# ---------------------------------------------------------------------------

import os, zipfile
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..","..","data","raw")+os.sep
SHP  = DATA + "cb_2025_us_county_20m/cb_2025_us_county_20m.shp"
OUT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..","..","output","figures")+os.sep

# the Census county shapefile ships zipped; extract it on first use
if not os.path.exists(SHP):
    with zipfile.ZipFile(DATA + "cb_2025_us_county_20m.zip") as _z:
        _z.extractall(DATA + "cb_2025_us_county_20m/")

CTY_EDGE, CTY_LW = "0.45", 0.12     # county outlines: thin grey
ST_EDGE,  ST_LW  = "black", 0.6     # state outlines: thicker black

gdf = gpd.read_file(SHP)
gdf["sf"] = gdf["STATEFP"].astype(int)
gdf = gdf[~gdf["sf"].isin({72, 60, 66, 69, 78})].copy()  # drop territories

# CONUS (Albers 5070), Alaska (Albers 3338), Hawaii (lat/lon)
conus = gdf[~gdf["sf"].isin({2, 15})].to_crs(5070)
ak    = gdf[gdf["sf"] == 2].to_crs(3338)
hi    = gdf[gdf["sf"] == 15].to_crs(4269)

def draw(g, ax):
    g.plot(ax=ax, facecolor="white", edgecolor=CTY_EDGE, linewidth=CTY_LW)
    g.dissolve(by="sf").boundary.plot(ax=ax, color=ST_EDGE, linewidth=ST_LW)
    ax.set_aspect("equal")
    ax.axis("off")

fig = plt.figure(figsize=(10, 6.3), facecolor="white")
ax_main = fig.add_axes([0.0, 0.0, 1.0, 1.0]);  draw(conus, ax_main)
ax_ak   = fig.add_axes([0.005, 0.01, 0.22, 0.28]); draw(ak, ax_ak)
ax_hi   = fig.add_axes([0.23, 0.01, 0.11, 0.17]); draw(hi, ax_hi)

fig.savefig(OUT + "countymap2.png", dpi=220, bbox_inches="tight", pad_inches=0.02)
plt.close(fig)
print("wrote countymap2.png")
