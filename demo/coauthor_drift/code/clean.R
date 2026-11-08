# Author 1's half of the pipeline. Cleans the administrative revenue
# panel that feeds Table 3, alongside author 2's weight file.
regions <- data.frame(
  region_id = 1:8,
  revenue   = c(820, 145, 610, 95, 430, 275, 690, 160)
)
write.csv(regions, "data/panel.csv", row.names = FALSE, quote = FALSE)
