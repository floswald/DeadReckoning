"""
Compiled-language build-step detection tests — compile_check.py
(Action Point 4 in compare.md).
"""

from __future__ import annotations

from deadreckoning.compile_check import (
    check_compiled_language_build,
    find_build_script,
    find_compiled_sources,
)
from deadreckoning.models import GapKind


def test_no_compiled_sources_returns_none(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "analysis.R").write_text("x <- 1\n")
    assert check_compiled_language_build(tmp_path) is None


def test_fortran_source_with_no_build_flags_gap(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "simulate.f90").write_text("program p\nend program p\n")
    gap = check_compiled_language_build(tmp_path)
    assert gap is not None
    assert gap.kind == GapKind.compiled_language_no_build_script
    assert "simulate.f90" in (gap.note or "")


def test_c_source_with_no_build_flags_gap(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.c").write_text("int main() { return 0; }\n")
    gap = check_compiled_language_build(tmp_path)
    assert gap is not None
    assert gap.kind == GapKind.compiled_language_no_build_script


def test_cpp_source_with_no_build_flags_gap(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.cpp").write_text("int main() { return 0; }\n")
    gap = check_compiled_language_build(tmp_path)
    assert gap is not None


def test_makefile_at_root_satisfies_check(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.c").write_text("int main() { return 0; }\n")
    (tmp_path / "Makefile").write_text("all:\n\tgcc code/sim.c -o code/sim\n")
    assert check_compiled_language_build(tmp_path) is None


def test_makefile_in_code_dir_satisfies_check(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.f90").write_text("program p\nend program p\n")
    (tmp_path / "code" / "Makefile").write_text("all:\n\tgfortran sim.f90 -o sim\n")
    assert check_compiled_language_build(tmp_path) is None


def test_build_sh_detected_by_name(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.c").write_text("int main() { return 0; }\n")
    (tmp_path / "build.sh").write_text("#!/bin/sh\n# whatever is in here, the name alone counts\n")
    assert check_compiled_language_build(tmp_path) is None


def test_shell_script_sniffed_for_compiler_invocation_by_content(tmp_path):
    """A shell script that isn't named build.sh/compile.sh is still detected
    if its content invokes a compiler/build tool — the common run_all.sh
    pattern where the orchestrator itself compiles then runs."""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.f90").write_text("program p\nend program p\n")
    (tmp_path / "code" / "run_all.sh").write_text(
        "#!/bin/bash\ngfortran sim.f90 -o sim\n./sim\n"
    )
    assert check_compiled_language_build(tmp_path) is None


def test_unrelated_shell_script_does_not_satisfy_check(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.c").write_text("int main() { return 0; }\n")
    (tmp_path / "deploy.sh").write_text("#!/bin/sh\nscp out.csv server:/data\n")
    gap = check_compiled_language_build(tmp_path)
    assert gap is not None


def test_find_compiled_sources_covers_all_extensions(tmp_path):
    names = ["a.f90", "b.f95", "c.f", "d.for", "e.c", "f.cpp", "g.cc", "h.cxx"]
    for n in names:
        (tmp_path / n).write_text("")
    found = {p.name for p in find_compiled_sources(tmp_path)}
    assert found == set(names)


def test_find_build_script_returns_none_when_absent(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "sim.c").write_text("int main() { return 0; }\n")
    assert find_build_script(tmp_path) is None
