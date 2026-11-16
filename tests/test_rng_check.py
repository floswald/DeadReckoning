"""
RNG-CHECK step tests — rng_check.py

A stochastic call with no seed call anywhere upstream (same script or an
earlier one in graph.script_order) must be flagged. Covers all 8 languages
DeadReckoning targets (see Action Point 2 in compare.md).
"""

from __future__ import annotations

from pathlib import Path

from deadreckoning.graph import build_graph
from deadreckoning.rng_check import check_rng_seeding


def _check(tmp_path: Path):
    graph = build_graph(tmp_path)
    return check_rng_seeding(tmp_path, graph)


# ---------------------------------------------------------------------------
# R
# ---------------------------------------------------------------------------


def test_r_unseeded_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.R").write_text("x <- rnorm(10)\n")
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "R"


def test_r_seeded_same_script_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.R").write_text("set.seed(1)\nx <- rnorm(10)\n")
    result = _check(tmp_path)
    assert result.findings == []


def test_r_seed_after_draw_still_flagged(tmp_path):
    """A seed call that comes AFTER the stochastic call doesn't protect it."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.R").write_text("x <- rnorm(10)\nset.seed(1)\n")
    result = _check(tmp_path)
    assert len(result.findings) == 1


# ---------------------------------------------------------------------------
# Cross-script: an upstream seed call covers everything after it in run order
# ---------------------------------------------------------------------------


def test_upstream_seed_covers_downstream_script(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "01_seed.R").write_text("set.seed(42)\n")
    (tmp_path / "code" / "02_analysis.R").write_text("x <- rnorm(10)\n")
    result = _check(tmp_path)
    assert result.findings == []


def test_no_upstream_seed_flagged_even_in_second_script(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "01_prep.R").write_text("y <- 1 + 1\n")
    (tmp_path / "code" / "02_analysis.R").write_text("x <- rnorm(10)\n")
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].script == Path("code/02_analysis.R")


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def test_python_unseeded_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.py").write_text(
        "import numpy as np\nx = np.random.normal(size=10)\n"
    )
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "Python"


def test_python_seeded_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.py").write_text(
        "import numpy as np\nnp.random.seed(42)\nx = np.random.normal(size=10)\n"
    )
    result = _check(tmp_path)
    assert result.findings == []


# ---------------------------------------------------------------------------
# Stata
# ---------------------------------------------------------------------------


def test_stata_unseeded_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.do").write_text("bootstrap, reps(100): reg y x\n")
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "Stata"


def test_stata_seeded_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.do").write_text(
        "set seed 12345\nbootstrap, reps(100): reg y x\n"
    )
    result = _check(tmp_path)
    assert result.findings == []


# ---------------------------------------------------------------------------
# Julia
# ---------------------------------------------------------------------------


def test_julia_unseeded_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.jl").write_text("x = randn(10)\n")
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "Julia"


def test_julia_seeded_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.jl").write_text(
        "using Random\nRandom.seed!(1)\nx = randn(10)\n"
    )
    result = _check(tmp_path)
    assert result.findings == []


# ---------------------------------------------------------------------------
# MATLAB
# ---------------------------------------------------------------------------


def test_matlab_unseeded_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.m").write_text("x = randn(10,1);\n")
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "MATLAB"


def test_matlab_seeded_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.m").write_text("rng(1);\nx = randn(10,1);\n")
    result = _check(tmp_path)
    assert result.findings == []


# ---------------------------------------------------------------------------
# Fortran
# ---------------------------------------------------------------------------


def test_fortran_unseeded_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.f90").write_text(
        "program sim\n  real :: x\n  call random_number(x)\nend program sim\n"
    )
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "Fortran"


def test_fortran_seeded_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.f90").write_text(
        "program sim\n  real :: x\n  call random_seed(put=seed)\n"
        "  call random_number(x)\nend program sim\n"
    )
    result = _check(tmp_path)
    assert result.findings == []


# ---------------------------------------------------------------------------
# C
# ---------------------------------------------------------------------------


def test_c_unseeded_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.c").write_text(
        "int main() { int x = rand(); return 0; }\n"
    )
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "C"


def test_c_seeded_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.c").write_text(
        "int main() { srand(42); int x = rand(); return 0; }\n"
    )
    result = _check(tmp_path)
    assert result.findings == []


# ---------------------------------------------------------------------------
# C++
# ---------------------------------------------------------------------------


def test_cpp_unseeded_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.cpp").write_text(
        "int x = rand();\n"
    )
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "C++"


def test_cpp_seeded_engine_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.cpp").write_text(
        "std::mt19937 gen(42);\n"
        "int x = rand();\n"
    )
    result = _check(tmp_path)
    assert result.findings == []


def test_cpp_random_device_seeded_engine_still_flagged(tmp_path):
    """Seeding from entropy is deliberately non-reproducible — must not
    count as a seed."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.cpp").write_text(
        "std::mt19937 gen(std::random_device{}());\n"
        "int x = rand();\n"
    )
    result = _check(tmp_path)
    assert len(result.findings) == 1


# ---------------------------------------------------------------------------
# Rcpp — draws from R's own RNG stream, seeded upstream by R's set.seed()
# ---------------------------------------------------------------------------


def test_rcpp_rnorm_unseeded_flagged(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "shocks.cpp").write_text(
        "#include <Rcpp.h>\n"
        "// [[Rcpp::export]]\n"
        "double draw() { return Rcpp::rnorm(1)[0]; }\n"
    )
    result = _check(tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].language == "C++"


def test_rcpp_rnorm_covered_by_upstream_r_set_seed(tmp_path):
    """An Rcpp .cpp draws from R's own RNG stream — an upstream R script's
    set.seed() (itself a master script, so always walked first) covers
    the .cpp sourced from it."""
    (tmp_path / "code").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "code" / "simulate.R").write_text(
        "set.seed(1)\nRcpp::sourceCpp('src/shocks.cpp')\n"
    )
    (tmp_path / "src" / "shocks.cpp").write_text(
        "#include <Rcpp.h>\n"
        "// [[Rcpp::export]]\n"
        "double draw() { return Rcpp::rnorm(1)[0]; }\n"
    )
    result = _check(tmp_path)
    assert result.findings == []


def test_r_api_norm_rand_unseeded_flagged(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "shocks.cpp").write_text(
        "#include <Rcpp.h>\n// [[Rcpp::export]]\ndouble draw() { return norm_rand(); }\n"
    )
    result = _check(tmp_path)
    assert len(result.findings) == 1
