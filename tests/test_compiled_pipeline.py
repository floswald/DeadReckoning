"""
Full round-trip for Action Point 4 (compiled-language build-step
detection): a Fortran-only project with no Makefile/build script must
block at ASK with a QUESTIONS.md asking for the exact compile command;
once the author answers, a second run (pointed at the answered working
copy, the same "edit QUESTIONS.md and re-run" flow the CLI documents)
must actually compile and run it with real gfortran and validate.

Real gfortran invocation, not mocked — @pytest.mark.local, same posture
as the R/Stata/Julia end-to-end tests elsewhere in this suite.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deadreckoning.models import GapKind
from deadreckoning.orchestrator import run_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "runnable_fortran_minimal"

pytestmark = [
    pytest.mark.local,
    pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran not installed"),
]


def test_fortran_project_blocks_then_compiles_and_runs_after_answer():
    # First run: no Makefile/build script anywhere — must block at ASK.
    result1 = run_pipeline(FIXTURE, master_script="code/simulate.f90", skip_docker=True)
    assert result1.needs_author_input, "expected ASK to block on compiled_language_no_build_script"
    assert result1.ask is not None
    assert any(
        q.gap_kind == GapKind.compiled_language_no_build_script.value
        for q in result1.ask.questions
    )

    questions_path = result1.working_copy / "QUESTIONS.md"
    assert questions_path.exists()
    text = questions_path.read_text()
    answered = text.replace(
        "> Answer: \n",
        "> Answer: gfortran code/simulate.f90 -o code/simulate && ./code/simulate\n",
        1,
    )
    assert answered != text, "QUESTIONS.md did not contain the expected blank answer line"
    questions_path.write_text(answered)

    # Second run: pointed at the (now-answered) working copy from run 1 —
    # the same flow the CLI prints ("Edit QUESTIONS.md in the working copy
    # and re-run"). Must proceed past ASK and actually compile/run.
    result2 = run_pipeline(
        result1.working_copy, master_script="code/simulate.f90", skip_docker=True
    )
    assert not result2.needs_author_input, f"still blocked: {result2.error}"
    assert result2.error is None, f"pipeline error: {result2.error}"
    assert result2.native_ok, (
        f"native run failed:\n{result2.native_run.stderr if result2.native_run else 'no run'}"
    )
    assert (result2.working_copy / "result.txt").read_text().strip() == "55.00"
