"""
find_nondeterministic_calls() — Action Point 3 in compare.md (ReproAI's C12).
"""

from __future__ import annotations

from deadreckoning.nondeterminism import find_nondeterministic_calls


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return p


def test_r_sys_time_detected(tmp_path):
    p = _write(tmp_path, "a.R", 'write.csv(Sys.time(), "out.csv")\n')
    assert find_nondeterministic_calls(p) == ["Sys.time("]


def test_r_clean_script_no_match(tmp_path):
    p = _write(tmp_path, "a.R", 'write.csv(data.frame(x=1), "out.csv")\n')
    assert find_nondeterministic_calls(p) == []


def test_python_datetime_now_detected(tmp_path):
    p = _write(tmp_path, "a.py", "f.write(str(datetime.now()))\n")
    assert find_nondeterministic_calls(p) == ["datetime.now("]


def test_python_getpid_detected(tmp_path):
    p = _write(tmp_path, "a.py", "f.write(str(os.getpid()))\n")
    assert find_nondeterministic_calls(p) == ["os.getpid("]


def test_stata_current_date_detected(tmp_path):
    p = _write(tmp_path, "a.do", 'file write myfile "`c(current_date)\'"\n')
    assert find_nondeterministic_calls(p) == ["c(current_date)"]


def test_julia_now_detected(tmp_path):
    p = _write(tmp_path, "a.jl", "write(io, string(now()))\n")
    assert find_nondeterministic_calls(p) == ["now("]


def test_matlab_datestr_detected(tmp_path):
    p = _write(tmp_path, "a.m", "fprintf(fid, datestr(now));\n")
    assert find_nondeterministic_calls(p) == ["datestr("]


def test_fortran_date_and_time_detected(tmp_path):
    p = _write(
        tmp_path, "a.f90",
        "program p\n  call date_and_time(date, time)\nend program p\n",
    )
    assert find_nondeterministic_calls(p) == ["call date_and_time("]


def test_c_getpid_detected(tmp_path):
    p = _write(tmp_path, "a.c", "int main() { int p = getpid(); return 0; }\n")
    assert find_nondeterministic_calls(p) == ["getpid("]


def test_cpp_chrono_now_detected(tmp_path):
    p = _write(
        tmp_path, "a.cpp",
        "auto t = std::chrono::system_clock::now();\n",
    )
    assert find_nondeterministic_calls(p) == ["std::chrono::system_clock::now("]


def test_unsupported_extension_returns_empty(tmp_path):
    p = _write(tmp_path, "a.txt", "Sys.time()\n")
    assert find_nondeterministic_calls(p) == []


def test_duplicate_calls_deduped_in_first_seen_order(tmp_path):
    p = _write(
        tmp_path, "a.R",
        'cat(Sys.time())\ncat(Sys.time())\ncat(tempdir())\n',
    )
    assert find_nondeterministic_calls(p) == ["Sys.time(", "tempdir("]
