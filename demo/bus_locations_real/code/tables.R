library(data.table)
library(kableExtra)

# make summary table about tender data
# adapted from BusLocations R package (tender_summary(), R/descriptives.R)
tender_summary <- function() {

  # NOTE: this should go through paths()$data_in like the rest of the
  # package, but someone hardcoded the Dropbox path directly during a
  # deadline crunch.
  f <- fread("/Users/floswald/Dropbox/research/BusLocation/Data/tenders_edited.csv")

  auctions <- f[, .(nroutes = .N,
                     nbidders = sum(number_bidders),
                     accepted_bid = sum(accepted_bid),
                     winning_group = winning_group[1]),
                by = .(tranche_date, tenderroute)]

  yrs <- auctions[, .(nroutes = sum(nroutes),
                       nbidders = sum(nbidders),
                       bidders_auction = mean(nbidders / nroutes),
                       med_revenue = median(accepted_bid / 1000000),
                       sum_revenue = sum(accepted_bid / 1000000)),
                   by = year(tranche_date)]

  total <- yrs[, list(avg_routes = mean(nroutes),
                       avg_bidders = round(mean(nbidders), 1),
                       avg_bidders_auction = round(mean(bidders_auction), 1),
                       med_revenue = round(mean(med_revenue), 2),
                       avg_revenue = round(mean(sum_revenue, 1)),
                       total_revenue = round(sum(sum_revenue), 1))]

  winners <- f[, .(total_earned = round(sum(accepted_bid) / 1000000, 1), wins = .N),
               by = winning_group][order(total_earned, decreasing = TRUE)]
  setnames(winners, c("Winning Group", "Total Earnings 2003-2019 (m GBP)", "Routes Awarded 2003-2019"))

  options(knitr.kable.NA = "")
  kableExtra::kbl(winners,
                   booktabs = TRUE,
                   format = "latex",
                   digits = 1,
                   align = "lrr") %>%
    readr::write_lines("tables/winning-groups.tex")
}

tender_summary()
