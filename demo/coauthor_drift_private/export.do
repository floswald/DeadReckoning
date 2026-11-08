* Author 2's private export script — lives only on their own machine,
* never shared, never version-controlled, never part of the project
* repository. Illustrative only: the demo never executes this file.

* --- Original version, run under an older Stata release ---
* No display format was ever set on `weight`, so the default kicked in
* and `outsheet` truncated the exported value to 2 decimals.
*
*   outsheet region_id weight using "input_data_from_2.csv", comma replace

* --- After upgrading Stata, months later ---
* Author 2 modernized the script, swapping the old `outsheet` for the
* recommended `export delimited` — still with no display format set.
* `export delimited` does not apply the same implicit truncation, so the
* full double-precision weight now leaks into the csv. Same underlying
* number, same variable, same code logic otherwise — just a different
* export command with a different default.
*
*   export delimited region_id weight using "input_data_from_2.csv", replace
