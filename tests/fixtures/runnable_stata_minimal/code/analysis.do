* analysis.do — scatter plot from built-in auto dataset
sysuse auto, clear
twoway scatter mpg price
graph export "figures/fig1.pdf", replace
