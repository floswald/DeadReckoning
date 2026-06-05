* tables.do — summary stats table using file write (no external packages)
sysuse auto, clear

quietly summ mpg
local mpg_mean = r(mean)
local mpg_sd   = r(sd)
quietly summ price
local price_mean = r(mean)
local price_sd   = r(sd)
quietly summ weight
local weight_mean = r(mean)
local weight_sd   = r(sd)

file open fh using "tables/summary.tex", write replace
file write fh "\begin{tabular}{lrr}" _n
file write fh "\toprule" _n
file write fh "Variable & Mean & Std Dev \\" _n
file write fh "\midrule" _n
file write fh "MPG & " %5.1f (`mpg_mean') " & " %5.2f (`mpg_sd') " \\" _n
file write fh "Price & " %7.0f (`price_mean') " & " %7.0f (`price_sd') " \\" _n
file write fh "Weight & " %6.0f (`weight_mean') " & " %6.0f (`weight_sd') " \\" _n
file write fh "\bottomrule" _n
file write fh "\end{tabular}" _n
file close fh
