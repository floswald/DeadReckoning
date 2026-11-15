// Compiled on the fly by R's sourceCpp() -- there is no src/Makevars
// shipped with this package. On the author's own machine, a personal
// ~/.R/Makevars sets:
//
//   PKG_CXXFLAGS = -O3
//
// That flag lives nowhere in this package -- not in a shipped
// src/Makevars, not in any sourceCpp() call with explicit flags -- so a
// replicator's machine compiles this file with R's own default
// toolchain flags instead, producing a different compiled binary than
// the one the author actually ran it with.
#include <Rcpp.h>
using namespace Rcpp;

// [[Rcpp::export]]
NumericVector simulate_shocks(int n, NumericVector anchors) {
  NumericVector shocks(n);
  int k = anchors.size();
  for (int i = 0; i < n; i++) {
    double base = anchors[i % k];
    // Draws from R's own RNG stream (the same stream set.seed() in the
    // calling R script controls) -- NOT C++'s own builtin generator.
    shocks[i] = base * 0.01 + Rcpp::rnorm(1, 0.0, 1.0)[0];
  }
  return shocks;
}
