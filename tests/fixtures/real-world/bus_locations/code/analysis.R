library(sf)
library(ggplot2)
library(data.table)
library(mlogit)
library(stargazer)
library(xml2)
library(here)

# Load spatial data
garages <- st_read(here("data", "garages.gpkg"))
routes   <- st_read(here("data", "routes.gpkg"))

# Merge and summarise
dt <- as.data.table(garages)
dt[, n_routes := .N, by = garage_id]

# Model
ml <- mlogit(choice ~ price + distance | 1, data = dt)

# Output
ggsave(here("figures", "garage-map.pdf"), width = 10, height = 8)
stargazer(ml, out = here("tables", "logit-results.tex"), type = "latex")
