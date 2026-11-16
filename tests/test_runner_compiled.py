"""
_run_compiled() / run_natively() dispatch for Fortran/C/C++ master scripts
— Action Point 4 in compare.md.

Real compiler invocations (gfortran, gcc, g++) — not mocked. These require
the compilers to be installed locally, same posture as the R/Stata/Julia
`@pytest.mark.local` tests elsewhere in this suite.
"""

from __future__ import annotations

import shutil

import pytest

from deadreckoning.runner import run_natively

pytestmark = pytest.mark.local


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran not installed")
def test_real_gfortran_compile_and_run(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "simulate.f90").write_text(
        "program simulate\n"
        "  implicit none\n"
        "  integer :: i\n"
        "  real :: total\n"
        "  total = 0.0\n"
        "  do i = 1, 10\n"
        "     total = total + real(i)\n"
        "  end do\n"
        "  open(unit=10, file='result.txt', status='replace')\n"
        "  write(10, '(F6.2)') total\n"
        "  close(10)\n"
        "end program simulate\n"
    )
    result = run_natively(
        tmp_path,
        master_script="code/simulate.f90",
        compile_command="gfortran code/simulate.f90 -o code/simulate && ./code/simulate",
    )
    assert result.success, f"gfortran compile/run failed:\n{result.stderr}"
    assert (tmp_path / "result.txt").read_text().strip() == "55.00"


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_real_gcc_compile_and_run(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.c").write_text(
        "#include <stdio.h>\n"
        "int main() {\n"
        "    int total = 0;\n"
        "    for (int i = 1; i <= 10; i++) total += i;\n"
        "    FILE *f = fopen(\"result.txt\", \"w\");\n"
        "    fprintf(f, \"%d\", total);\n"
        "    fclose(f);\n"
        "    return 0;\n"
        "}\n"
    )
    result = run_natively(
        tmp_path,
        master_script="code/sim.c",
        compile_command="gcc code/sim.c -o code/sim && ./code/sim",
    )
    assert result.success, f"gcc compile/run failed:\n{result.stderr}"
    assert (tmp_path / "result.txt").read_text().strip() == "55"


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")
def test_real_gpp_compile_and_run(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.cpp").write_text(
        "#include <fstream>\n"
        "int main() {\n"
        "    int total = 0;\n"
        "    for (int i = 1; i <= 10; i++) total += i;\n"
        "    std::ofstream f(\"result.txt\");\n"
        "    f << total;\n"
        "    return 0;\n"
        "}\n"
    )
    result = run_natively(
        tmp_path,
        master_script="code/sim.cpp",
        compile_command="g++ code/sim.cpp -o code/sim && ./code/sim",
    )
    assert result.success, f"g++ compile/run failed:\n{result.stderr}"
    assert (tmp_path / "result.txt").read_text().strip() == "55"


def test_no_compile_command_reports_clear_error(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "simulate.f90").write_text("program p\nend program p\n")
    result = run_natively(tmp_path, master_script="code/simulate.f90", compile_command=None)
    assert not result.success
    assert "compile" in result.stderr.lower()


def test_compile_command_failure_propagates_returncode(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "broken.f90").write_text("this is not valid fortran\n")
    result = run_natively(
        tmp_path,
        master_script="code/broken.f90",
        compile_command="gfortran code/broken.f90 -o code/broken",
    )
    assert not result.success
