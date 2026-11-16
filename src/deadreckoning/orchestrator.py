"""
Sequential pipeline orchestrator — no LLM, deterministic.

Phase 2 walking skeleton: wire all steps in order, prove connectivity.
LLM orchestration (FIX loop) is Phase 4.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .ask import run_ask_step
from .capture import capture_env
from .clean import run_clean_step
from .compile_check import check_compiled_language_build
from .confidentiality import check_restricted
from .data_profile import profile_data_files, render_data_structure_summary, write_data_structure_summary
from .deliver import run_deliver_step
from .docker import BuildResult, ContainerRunResult, DockerFixResult, build_image, generate_dockerfile, run_docker_fix_loop, run_in_container
from .fidelity_check import FidelityCheckResult, run_fidelity_check_step
from .fix_loop import FixLoopResult, append_fix_report, run_fix_loop, run_llm_fix_loop
from .graph import build_graph
from .llm_dispatcher import LLMDispatcher
from .llm_gap_hints import GapHintDispatcher
from .models import AuthorQA, CleanResult, DataProfileResult, DeliverResult, DependencyGraph, EnvSpec, GapKind, IntakeResult, PackageSpec, PinMethod, RestrictedStatus
from .provenance import render_data_exhibit_map, trace_exhibit_inputs, write_data_exhibit_map
from .mixed_language_check import MixedLanguageCheckResult, run_mixed_language_check_step
from .resolve import ResolveResult, resolve_paths
from .rng_check import RngCheckResult, run_rng_check_step
from .runner import RunResult, ValidationResult, run_natively, validate_outputs
from .scan import ScanResult, scan_scripts
from .sort_check import SortCheckResult, run_sort_check_step


@dataclass
class PipelineResult:
    project_root: Path
    working_copy: Path
    restricted: RestrictedStatus
    graph: DependencyGraph | None = None
    data_profile: DataProfileResult | None = None
    provenance: dict[Path, list[Path]] | None = None
    env_spec: EnvSpec | None = None
    scan: ScanResult | None = None
    resolve: ResolveResult | None = None
    intake: IntakeResult | None = None
    ask: AuthorQA | None = None
    needs_author_input: bool = False
    clean: CleanResult | None = None
    rng_check: RngCheckResult | None = None
    mixed_language_check: MixedLanguageCheckResult | None = None
    sort_check: SortCheckResult | None = None
    fidelity_check: FidelityCheckResult | None = None
    deliver: DeliverResult | None = None
    fix_loop: FixLoopResult | None = None
    llm_fix_loop: FixLoopResult | None = None
    docker_fix: DockerFixResult | None = None
    native_run: RunResult | None = None
    native_validation: ValidationResult | None = None
    dockerfile: str | None = None
    docker_build: BuildResult | None = None
    container_validation: ContainerRunResult | None = None
    error: str | None = None

    @property
    def native_ok(self) -> bool:
        return self.native_run is not None and self.native_run.success

    @property
    def container_ok(self) -> bool:
        return (
            self.container_validation is not None
            and self.container_validation.run.success
            and self.container_validation.outputs.success
        )



def _detect_master_script(project_root: Path) -> str:
    """Guess master script if not supplied."""
    for candidate in (
        "code/run_all.sh", "run_all.sh",
        "code/run.R", "run.R",
        "code/master.do", "master.do",
    ):
        if (project_root / candidate).exists():
            return candidate
    # No named convention matched — fall back to the sole script of a
    # recognized type in code/, if there's exactly one (author didn't
    # answer the intake master-script question and no convention fit).
    for pattern in ("*.do", "*.R", "*.r", "*.py", "*.jl"):
        matches = sorted((project_root / "code").glob(pattern)) if (project_root / "code").exists() else []
        if len(matches) == 1:
            return str(matches[0].relative_to(project_root))
    return "code/run.R"


# Step names accepted by `stop_after`, in pipeline order — used to halt
# early for step-by-step demos/narration without a separate driver script.
STOP_AFTER_STEPS = (
    "detect", "graph", "capture", "scan", "resolve",
    "ask", "fix", "llm-fix", "run", "validate",
)


def run_pipeline(
    project_root: Path,
    master_script: str | None = None,
    docker_tag: str | None = None,
    skip_docker: bool = False,
    skip_run: bool = False,
    intake: IntakeResult | None = None,
    stata_license: Path | None = None,
    stata_image: str | None = None,
    stop_after: str | None = None,
) -> PipelineResult:
    """
    Run the full DeadReckoning pipeline on a copy of project_root.

    Steps:
    1. DETECT   — confidentiality gate (abort on restricted data)
    2. GRAPH    — build dependency graph
    3. CAPTURE  — parse env spec from lockfile
    4. SCAN     — extract packages, external paths, secrets
    5. RESOLVE  — rewrite paths, generate data-manifest + AGENT_REPORT
    6. RUN      — execute master_script natively
    7. VALIDATE (native) — all sourced exhibits present
    8. GENERATE — produce Dockerfile
    9. BUILD    — docker build
    10. VALIDATE (container) — all exhibits regenerate inside container

    `stop_after` (one of STOP_AFTER_STEPS) halts the pipeline right after
    that step, for narrating steps one at a time (e.g. in a recorded demo)
    without writing a separate driver script.
    """
    if stop_after is not None and stop_after not in STOP_AFTER_STEPS:
        raise ValueError(f"stop_after must be one of {STOP_AFTER_STEPS!r}, got {stop_after!r}")
    # Priority: explicit --master-script flag > author's intake answer > auto-detect.
    if master_script is None:
        master_script = (intake.master_script if intake else None) or _detect_master_script(project_root)

    # Step 1: confidentiality gate. Restricted data no longer aborts the
    # pipeline (see #27) — GRAPH/CAPTURE/SCAN/RESOLVE/RUN/VALIDATE/Docker
    # are all 100%-local already, restricted or not. Instead,
    # `restricted.is_restricted` is threaded through as the single source
    # of truth for "LLM off for the rest of this run" — no new boolean
    # field, so nothing can drift out of sync with the audit trail below.
    #
    # The author's own answer takes priority over the filename heuristic —
    # ask before opening anything means "believe them," not "double-check first."
    if intake is not None and intake.restricted_data:
        restricted = RestrictedStatus(
            is_restricted=True,
            reason="Author confirmed restricted/confidential data during intake questionnaire",
        )
    else:
        # check_restricted reads filenames only, no file contents opened.
        restricted = check_restricted(project_root)
        if restricted.is_restricted:
            # §4.2 — a filename match (census, psid, nda, ...) is a lead, not
            # proof: legitimate public-use extracts are named this way too.
            # Stay restricted unless the author was specifically re-asked
            # about this hit and confirmed it's a false positive
            # (restricted_override_safe) — the fail-safe default
            # (None/unset) is to stay restricted.
            if intake is not None and intake.restricted_override_safe:
                # Overridden: author re-confirmed this specific hit is a
                # false positive. Record that in the audit trail, but
                # report DETECT as cleared, not restricted.
                restricted = RestrictedStatus(
                    is_restricted=False,
                    reason=f"Filename heuristic hit ({restricted.reason}) — "
                           f"author confirmed false positive, see §4.2",
                    trigger_path=restricted.trigger_path,
                )

    # Always work on a copy — original is never touched
    tmpdir = Path(tempfile.mkdtemp(prefix="dr_"))
    working_copy = tmpdir / project_root.name
    shutil.copytree(project_root, working_copy)

    if docker_tag is None:
        docker_tag = f"deadreckoning-{project_root.name}:latest"

    result = PipelineResult(
        project_root=project_root,
        working_copy=working_copy,
        restricted=restricted,
        intake=intake,
    )

    if stop_after == "detect":
        return result

    # Step 2: graph
    result.graph = build_graph(working_copy)

    # Step 2a: compiled-language (Fortran/C/C++) build-step detection — a
    # blocking gap if such source exists with no build script anywhere
    # (see compile_check.py / Action Point 4 in compare.md). Appended into
    # graph.gaps so ASK picks it up via the existing blocking-gap machinery.
    compile_gap = check_compiled_language_build(working_copy)
    if compile_gap is not None:
        result.graph.gaps.append(compile_gap)

    # Step 2b: trace exhibit <- data-input provenance; write DATA-EXHIBIT-MAP.md
    result.provenance = trace_exhibit_inputs(result.graph)
    write_data_exhibit_map(working_copy, render_data_exhibit_map(result.provenance))

    # Step 2c: local-only data-structure profile (row counts/columns, never
    # cell values, never transmitted) — only load-bearing for restricted
    # projects, so only generated for them.
    if result.restricted.is_restricted:
        result.data_profile = profile_data_files(working_copy, result.graph)
        write_data_structure_summary(working_copy, render_data_structure_summary(result.data_profile))

    if stop_after == "graph":
        return result

    # Step 3: capture env
    result.env_spec = capture_env(working_copy)
    # stata_image cannot be inferred from disk (proprietary, no lockfile) — author-supplied
    if stata_image and result.env_spec.language.upper() == "STATA":
        result.env_spec.stata_image = stata_image

    if stop_after == "capture":
        return result

    # Step 4: scan all scripts (multi-language)
    result.scan = scan_scripts(working_copy)

    if stop_after == "scan":
        return result

    # Step 5: resolve paths (mutates working copy only)
    result.resolve = resolve_paths(working_copy, result.scan)

    # RESOLVE's here::here() adoption (R) introduces a new dependency on the
    # `here` package — env_spec was captured in Step 3, before this rewrite,
    # so it never sees it unless we add it back here.
    if (
        result.resolve.here_adoptions > 0
        and result.env_spec.language.upper() == "R"
        and not any(p.name == "here" for p in result.env_spec.packages)
    ):
        result.env_spec.packages.append(PackageSpec(name="here", pin_method=PinMethod.unknown))

    if result.restricted.is_restricted:
        # AGENT_REPORT.md already exists after resolve_paths — append here so
        # the note lands even if ASK below ends the run early for author input.
        with (working_copy / "AGENT_REPORT.md").open("a") as f:
            f.write(
                "\n## Restricted mode\n\n"
                "Restricted mode: LLM-FIX and ASK hints were disabled for this run "
                "(confidential/restricted data detected). "
                "See `DATA-STRUCTURE-SUMMARY.md`.\n"
            )

    if stop_after == "resolve":
        return result

    # Step 5b: ASK — surface gaps that require author input
    result.ask, result.needs_author_input, result.graph, result.env_spec = run_ask_step(
        working_copy, result.graph, result.env_spec, result.scan, intake=intake,
        hint_dispatcher=GapHintDispatcher(restricted=result.restricted.is_restricted),
    )
    if result.needs_author_input:
        result.error = "Author input required: see QUESTIONS.md in working copy"
        return result

    if stop_after == "ask":
        return result

    # Step 6: FIX loop — deterministic fixes (e.g. wrong output paths)
    fix_result, result.graph = run_fix_loop(working_copy, result.graph, result.env_spec)
    result.fix_loop = fix_result
    append_fix_report(working_copy, fix_result)

    if skip_run or stop_after == "fix":
        return result

    # Step 7+8: native run + validate
    result.native_run = run_natively(
        working_copy, master_script=master_script,
        compile_command=result.env_spec.compile_command if result.env_spec else None,
    )
    if not result.native_run.success:
        # Step 7b: LLM fix loop — re-run with Claude-proposed fixes
        llm_result, result.graph = run_llm_fix_loop(
            working_copy,
            result.graph,
            result.env_spec,
            dispatcher=LLMDispatcher(restricted=result.restricted.is_restricted),
            master_script=master_script,
            initial_stderr=result.native_run.stderr,
        )
        result.llm_fix_loop = llm_result
        append_fix_report(working_copy, llm_result)

        if stop_after == "llm-fix":
            return result

        # Re-run after LLM fixes
        result.native_run = run_natively(
        working_copy, master_script=master_script,
        compile_command=result.env_spec.compile_command if result.env_spec else None,
    )
        if not result.native_run.success:
            result.error = f"Native run failed (rc={result.native_run.returncode})"
            return result

    if stop_after == "run":
        return result

    result.native_validation = validate_outputs(working_copy, result.graph)

    if stop_after == "validate":
        return result

    # CLEAN: identify unreachable files; write CLEANUP.md (non-blocking)
    result.clean, _needs_review = run_clean_step(working_copy, result.graph)

    # RNG-CHECK: flag stochastic calls with no seed upstream; write
    # RNG-WARNINGS.md (non-blocking) — see Action Point 2 in compare.md
    result.rng_check = run_rng_check_step(working_copy, result.graph)

    # MIXED-LANGUAGE-CHECK: flag Rcpp/Cython/MEX with no declared build
    # step for the compiled part; write MIXED-LANGUAGE-WARNINGS.md
    # (non-blocking)
    result.mixed_language_check = run_mixed_language_check_step(working_copy)

    # SORT-CHECK: flag a Stata sort/gsort with no , stable and no
    # set sortseed feeding a tie-sensitive by ... : ... _n==1/_n==_N
    # operation; write SORT-WARNINGS.md (non-blocking)
    result.sort_check = run_sort_check_step(working_copy)

    # FIDELITY: compare regenerated exhibits against author-supplied
    # reference directories, if any were given at intake; write
    # FIDELITY-REPORT.md (non-blocking). See README §11.
    result.fidelity_check = run_fidelity_check_step(working_copy, result.intake)

    if skip_docker:
        return result

    # Step 6+7+8: Docker — build + run with auto-fix loop
    result.docker_fix = run_docker_fix_loop(
        working_copy,
        result.graph,
        result.env_spec,
        image_tag=docker_tag,
        master_script=master_script,
        stata_license=stata_license,
        restricted=result.restricted.is_restricted,
    )
    if result.docker_fix.final_build is not None:
        result.dockerfile = result.docker_fix.final_build.dockerfile_text
        result.docker_build = result.docker_fix.final_build
    if result.docker_fix.final_run is not None:
        result.container_validation = result.docker_fix.final_run
    if not result.docker_fix.converged:
        result.error = result.docker_fix.error
        return result

    # DELIVER: write README.md template + DELIVERY_REPORT.md
    result.deliver = run_deliver_step(
        working_copy,
        result.graph,
        result.env_spec,
        qa=result.ask,
        clean=result.clean,
        resolve=result.resolve,
        native_ok=result.native_ok,
        container_ok=result.container_ok,
        fidelity_check=result.fidelity_check,
    )

    return result
