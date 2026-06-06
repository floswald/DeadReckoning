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

from .capture import capture_env
from .confidentiality import check_restricted
from .docker import BuildResult, ContainerRunResult, build_image, generate_dockerfile, run_in_container
from .fix_loop import FixLoopResult, append_fix_report, run_fix_loop, run_llm_fix_loop
from .graph import build_graph
from .models import AuthorQA, AuthorQuestion, DependencyGraph, EnvSpec, GapKind, RestrictedStatus
from .resolve import ResolveResult, resolve_paths
from .runner import RunResult, ValidationResult, run_natively, validate_outputs
from .scan import ScanResult, scan_scripts


@dataclass
class PipelineResult:
    project_root: Path
    working_copy: Path
    restricted: RestrictedStatus
    graph: DependencyGraph | None = None
    env_spec: EnvSpec | None = None
    scan: ScanResult | None = None
    resolve: ResolveResult | None = None
    ask: AuthorQA | None = None
    needs_author_input: bool = False
    fix_loop: FixLoopResult | None = None
    llm_fix_loop: FixLoopResult | None = None
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


_AMBIGUOUS_KINDS = {
    GapKind.exhibit_missing_from_disk,
    GapKind.exhibit_no_source_script,
}

_QUESTIONS_FILE = "QUESTIONS.md"


def _identify_ambiguous_gaps(graph: DependencyGraph) -> list[AuthorQuestion]:
    questions = []
    for gap in graph.gaps:
        if gap.kind not in _AMBIGUOUS_KINDS:
            continue
        exhibit = str(gap.exhibit) if gap.exhibit else (gap.location or "unknown")
        if gap.kind == GapKind.exhibit_missing_from_disk:
            q = AuthorQuestion(
                gap_kind=gap.kind.value,
                exhibit=exhibit,
                question=(
                    f"The file `{exhibit}` is referenced in the paper but is not present on disk "
                    "and no script appears to produce it. "
                    "Is this file restricted data? If so, can you provide a path or description?"
                ),
                context=gap.note,
            )
        else:
            q = AuthorQuestion(
                gap_kind=gap.kind.value,
                exhibit=exhibit,
                question=(
                    f"No script was found that produces `{exhibit}`. "
                    "Which script creates this exhibit? Please edit this file with the script path."
                ),
                context=gap.note,
            )
        questions.append(q)
    return questions


def _write_questions_file(working_copy: Path, questions: list[AuthorQuestion]) -> Path:
    lines = [
        "# DeadReckoning — Author Questions\n",
        "Please answer the questions below and re-run `deadreckoning run`.\n",
        "Fill in the `> Answer:` lines.\n\n",
    ]
    for i, q in enumerate(questions, 1):
        lines.append(f"## Question {i}: {q.exhibit or q.gap_kind}\n\n")
        lines.append(f"**Gap kind:** `{q.gap_kind}`\n\n")
        if q.context:
            lines.append(f"**Context:** {q.context}\n\n")
        lines.append(f"{q.question}\n\n")
        lines.append("> Answer: \n\n")
    path = working_copy / _QUESTIONS_FILE
    path.write_text("".join(lines))
    return path


def _parse_author_responses(working_copy: Path) -> list:
    from .models import AuthorResponse
    path = working_copy / _QUESTIONS_FILE
    if not path.exists():
        return []
    text = path.read_text()
    responses = []
    for line in text.splitlines():
        if line.startswith("> Answer:"):
            answer = line[len("> Answer:"):].strip()
            if answer:
                responses.append(AuthorResponse(answer=answer))
    return responses


def _detect_master_script(project_root: Path) -> str:
    """Guess master script if not supplied."""
    for candidate in (
        "code/run_all.sh", "run_all.sh",
        "code/run.R", "run.R",
        "code/master.do", "master.do",
    ):
        if (project_root / candidate).exists():
            return candidate
    return "code/run.R"


def run_pipeline(
    project_root: Path,
    master_script: str | None = None,
    docker_tag: str | None = None,
    skip_docker: bool = False,
    skip_run: bool = False,
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
    """
    if master_script is None:
        master_script = _detect_master_script(project_root)

    # Always work on a copy — original is never touched
    tmpdir = Path(tempfile.mkdtemp(prefix="dr_"))
    working_copy = tmpdir / project_root.name
    shutil.copytree(project_root, working_copy)

    if docker_tag is None:
        docker_tag = f"deadreckoning-{project_root.name}:latest"

    result = PipelineResult(
        project_root=project_root,
        working_copy=working_copy,
        restricted=check_restricted(working_copy),
    )

    # Step 1: confidentiality gate
    if result.restricted.is_restricted:
        result.error = f"Restricted data detected: {result.restricted.reason}"
        return result

    # Step 2: graph
    result.graph = build_graph(working_copy)

    # Step 3: capture env
    result.env_spec = capture_env(working_copy)

    # Step 4: scan all scripts (multi-language)
    result.scan = scan_scripts(working_copy)

    # Step 5: resolve paths (mutates working copy only)
    result.resolve = resolve_paths(working_copy, result.scan)

    # Step 5b: ASK — surface ambiguous gaps to author before attempting to run
    ambiguous = _identify_ambiguous_gaps(result.graph)
    questions_path = working_copy / _QUESTIONS_FILE
    if ambiguous and not questions_path.exists():
        _write_questions_file(working_copy, ambiguous)
        result.ask = AuthorQA(questions=ambiguous)
        result.needs_author_input = True
        result.error = f"Author input required: see {_QUESTIONS_FILE} in working copy"
        return result
    elif questions_path.exists():
        responses = _parse_author_responses(working_copy)
        result.ask = AuthorQA(
            questions=ambiguous,
            responses=responses,
        )

    # Step 6: FIX loop — deterministic fixes (e.g. wrong output paths)
    fix_result, result.graph = run_fix_loop(working_copy, result.graph, result.env_spec)
    result.fix_loop = fix_result
    append_fix_report(working_copy, fix_result)

    if skip_run:
        return result

    # Step 7+8: native run + validate
    result.native_run = run_natively(working_copy, master_script=master_script)
    if not result.native_run.success:
        # Step 7b: LLM fix loop — re-run with Claude-proposed fixes
        llm_result, result.graph = run_llm_fix_loop(
            working_copy,
            result.graph,
            result.env_spec,
            master_script=master_script,
        )
        result.llm_fix_loop = llm_result
        append_fix_report(working_copy, llm_result)

        # Re-run after LLM fixes
        result.native_run = run_natively(working_copy, master_script=master_script)
        if not result.native_run.success:
            result.error = f"Native run failed (rc={result.native_run.returncode})"
            return result

    result.native_validation = validate_outputs(working_copy, result.graph)

    if skip_docker:
        return result

    # Step 6+7+8: Docker
    result.dockerfile = generate_dockerfile(result.env_spec)
    result.docker_build = build_image(working_copy, result.dockerfile, docker_tag)
    if not result.docker_build.success:
        result.error = "Docker build failed"
        return result
    result.container_validation = run_in_container(
        working_copy, docker_tag, result.graph, master_script=master_script
    )

    return result
