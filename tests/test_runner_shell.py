"""
Runner dispatch tests for shell-script masters (run_all.sh-style
multi-language orchestrators).

Regression context: `_detect_master_script` (orchestrator.py) prefers
`code/run_all.sh` above any single-language script, but `run_natively` had
no .sh case at all — any real package using this extremely common
convention would fail immediately with "Unsupported script extension",
before Stata/R/Julia ever ran. Found by actually tracing what would happen
running a real published package, not by reasoning about GRAPH's gap
report in isolation.

A second, subtler bug this also tests: a shell master's relative paths
(including ones it hands to whatever it invokes) are written assuming
cwd = the script's OWN directory, not project_root — confirmed against a
real package where `code/run_all.sh` calls
`stata-mp -b stata/replication_aggregate_main.do`, only valid with
cwd=code/.
"""

from __future__ import annotations

from pathlib import Path

from deadreckoning.runner import run_natively


def test_sh_extension_does_not_fall_through_to_unsupported(tmp_path):
    (tmp_path / "code").mkdir()
    script = tmp_path / "code" / "run_all.sh"
    script.write_text("#!/bin/bash\nexit 0\n")
    result = run_natively(tmp_path, master_script="code/run_all.sh")
    assert "Unsupported" not in result.stderr
    assert result.success


def test_sh_runs_with_cwd_set_to_scripts_own_directory(tmp_path):
    """
    The real-world failure mode: run_all.sh sources/invokes a sibling file
    by a path relative to ITS OWN directory, not project_root. With the
    wrong cwd, this fails immediately — exactly how a real package's first
    `stata-mp -b stata/...` line would fail if cwd were project_root
    instead of the script's own directory.
    """
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "helper.sh").write_text('MSG="hello from helper"\n')
    (tmp_path / "code" / "run_all.sh").write_text(
        "#!/bin/bash\nset -e\nsource \"helper.sh\"\necho \"$MSG\"\n"
    )
    result = run_natively(tmp_path, master_script="code/run_all.sh")
    assert result.success, f"shell master failed with cwd bug:\n{result.stderr}"
    assert "hello from helper" in result.stdout


def test_sh_relative_output_path_resolves_against_script_directory(tmp_path):
    """A `../output/x` write inside the shell script must land at
    project_root/output/x (one level above the script's own directory),
    the convention a real run_all.sh/code/ layout depends on."""
    (tmp_path / "code").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "code" / "run_all.sh").write_text(
        "#!/bin/bash\nset -e\necho done > ../output/marker.txt\n"
    )
    result = run_natively(tmp_path, master_script="code/run_all.sh")
    assert result.success, f"shell master failed:\n{result.stderr}"
    assert (tmp_path / "output" / "marker.txt").exists()


def test_sh_nonzero_exit_propagates(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run_all.sh").write_text("#!/bin/bash\nexit 3\n")
    result = run_natively(tmp_path, master_script="code/run_all.sh")
    assert not result.success
    assert result.returncode == 3
