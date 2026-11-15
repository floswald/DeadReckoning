"""
Mixed-language compilation risk detection — mixed_language_check.py.

Rcpp, Cython, MEX, and similar setups where one language's build
machinery silently depends on another's compiler toolchain — a common
source of "worked when I wrote it, breaks for the replicator" failures,
since the embedding language usually auto-compiles with system-default
flags rather than failing outright, so nothing in a native run catches a
missing custom flag (OpenMP, an include path, a C++ standard version).
"""

from __future__ import annotations

from deadreckoning.mixed_language_check import check_mixed_language_compilation


# ---------------------------------------------------------------------------
# Rcpp
# ---------------------------------------------------------------------------


def test_rcpp_sourcecpp_with_no_makevars_flagged(tmp_path):
    """The exact scenario asked for: Rcpp code present, no src/Makevars,
    no src/Makevars.win, and no documented flags anywhere."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.R").write_text(
        'library(Rcpp)\n'
        'sourceCpp("code/fastloop.cpp")\n'
    )
    (tmp_path / "code" / "fastloop.cpp").write_text(
        "#include <Rcpp.h>\n"
        "// [[Rcpp::export]]\n"
        "double fastSum(Rcpp::NumericVector x) {\n"
        "    return Rcpp::sum(x);\n"
        "}\n"
    )
    result = check_mixed_language_compilation(tmp_path)
    assert any(f.language == "Rcpp" for f in result.findings)
    rcpp_finding = next(f for f in result.findings if f.language == "Rcpp")
    assert "Makevars" in rcpp_finding.note


def test_rcpp_with_makevars_present_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "code" / "run.R").write_text(
        'library(Rcpp)\nsourceCpp("code/fastloop.cpp")\n'
    )
    (tmp_path / "code" / "fastloop.cpp").write_text("#include <Rcpp.h>\n")
    (tmp_path / "src" / "Makevars").write_text("PKG_CXXFLAGS = -fopenmp\n")
    result = check_mixed_language_compilation(tmp_path)
    assert not any(f.language == "Rcpp" for f in result.findings)


def test_rcpp_detected_via_description_linkingto(tmp_path):
    """Rcpp usage declared in an R package's DESCRIPTION, not sourceCpp()."""
    (tmp_path / "DESCRIPTION").write_text(
        "Package: mypkg\nLinkingTo: Rcpp, RcppArmadillo\nImports: Rcpp\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core.cpp").write_text("#include <Rcpp.h>\n")
    result = check_mixed_language_compilation(tmp_path)
    assert any(f.language == "Rcpp" for f in result.findings)


def test_no_rcpp_usage_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.R").write_text('library(ggplot2)\nx <- 1\n')
    result = check_mixed_language_compilation(tmp_path)
    assert not any(f.language == "Rcpp" for f in result.findings)


# ---------------------------------------------------------------------------
# Cython
# ---------------------------------------------------------------------------


def test_cython_pyx_with_no_setup_py_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "fastloop.pyx").write_text(
        "def fast_sum(double[:] x):\n    return x.sum()\n"
    )
    result = check_mixed_language_compilation(tmp_path)
    assert any(f.language == "Cython" for f in result.findings)


def test_cython_with_setup_py_cythonize_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "fastloop.pyx").write_text("def f(): pass\n")
    (tmp_path / "setup.py").write_text(
        "from Cython.Build import cythonize\n"
        "from setuptools import setup\n"
        "setup(ext_modules=cythonize('code/fastloop.pyx'))\n"
    )
    result = check_mixed_language_compilation(tmp_path)
    assert not any(f.language == "Cython" for f in result.findings)


def test_pyximport_usage_without_build_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.py").write_text(
        "import pyximport\npyximport.install()\nimport fastloop\n"
    )
    result = check_mixed_language_compilation(tmp_path)
    assert any(f.language == "Cython" for f in result.findings)


# ---------------------------------------------------------------------------
# MEX
# ---------------------------------------------------------------------------


def test_mex_gateway_with_no_mex_build_call_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "fastloop.c").write_text(
        "#include \"mex.h\"\n"
        "void mexFunction(int nlhs, mxArray *plhs[], int nrhs, const mxArray *prhs[]) {\n"
        "}\n"
    )
    result = check_mixed_language_compilation(tmp_path)
    assert any(f.language == "MEX" for f in result.findings)


def test_mex_gateway_with_mex_build_call_not_flagged(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "fastloop.c").write_text(
        "#include \"mex.h\"\n"
        "void mexFunction(int nlhs, mxArray *plhs[], int nrhs, const mxArray *prhs[]) {\n"
        "}\n"
    )
    (tmp_path / "code" / "build.m").write_text("mex('code/fastloop.c');\n")
    result = check_mixed_language_compilation(tmp_path)
    assert not any(f.language == "MEX" for f in result.findings)


# ---------------------------------------------------------------------------
# Multiple findings at once
# ---------------------------------------------------------------------------


def test_rcpp_and_cython_both_flagged_independently(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.R").write_text(
        'library(Rcpp)\nsourceCpp("code/fastloop.cpp")\n'
    )
    (tmp_path / "code" / "fastloop.cpp").write_text("#include <Rcpp.h>\n")
    (tmp_path / "code" / "fastloop.pyx").write_text("def f(): pass\n")
    result = check_mixed_language_compilation(tmp_path)
    languages = {f.language for f in result.findings}
    assert languages == {"Rcpp", "Cython"}


def test_clean_project_no_findings(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.R").write_text("x <- 1 + 1\n")
    result = check_mixed_language_compilation(tmp_path)
    assert result.findings == []
    assert not result.has_findings
