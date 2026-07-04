"""
FIX loop: injectable dispatcher + deterministic fixes for script-write-path gaps.

Convergence = dispatcher returns None (no more applicable fixes), not validate success.
All mutations on working copy only — original never touched.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from .models import DependencyGraph, EnvSpec, Gap, GapKind, PackageSpec


# ---------------------------------------------------------------------------
# Fix actions
# ---------------------------------------------------------------------------


class FixAction(BaseModel):
    kind: str  # "install_package" | "rewrite_path" | "fix_write_path" | "add_missing_script_output"
    package_name: Optional[str] = None
    package_version: Optional[str] = None
    script: Optional[Path] = None
    old_path: Optional[str] = None
    new_path: Optional[str] = None
    exhibit_path: Optional[str] = None
    write_call: Optional[str] = None  # LLM-generated code snippet for add_missing_script_output


# ---------------------------------------------------------------------------
# Fix context
# ---------------------------------------------------------------------------


class FixContext(BaseModel):
    working_copy: Path
    graph: DependencyGraph
    env_spec: Optional[EnvSpec] = None
    iteration: int = 0
    applied_fixes: list[FixAction] = Field(default_factory=list)
    last_stderr: Optional[str] = None  # stderr from most recent script execution

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Dispatcher protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Dispatcher(Protocol):
    def next_fix(self, gaps: list[Gap], context: FixContext) -> Optional[FixAction]: ...


# ---------------------------------------------------------------------------
# Fix tools (pure functions — mutate files on working_copy)
# ---------------------------------------------------------------------------


def _rewrite_quoted(text: str, old: str, new: str) -> tuple[str, int]:
    """Replace quoted old with quoted new; return (new_text, count)."""
    pattern = re.compile(r'(["\'])' + re.escape(old) + r'\1')
    count = len(pattern.findall(text))
    new_text = pattern.sub(lambda m: m.group(1) + new + m.group(1), text)
    return new_text, count


def _script_abs(working_copy: Path, script: Path) -> Path:
    if script.is_absolute():
        return script
    return working_copy / script


def fix_write_path(working_copy: Path, action: FixAction) -> bool:
    """Correct output path in a script write call."""
    if not action.script or not action.old_path or not action.new_path:
        return False
    path = _script_abs(working_copy, action.script)
    if not path.exists():
        return False
    text = path.read_text(errors="replace")
    new_text, count = _rewrite_quoted(text, action.old_path, action.new_path)
    if not count:
        return False
    path.write_text(new_text)
    return True


def install_package(env_spec: Optional[EnvSpec], action: FixAction) -> bool:
    """Add package to env_spec (in-memory mutation)."""
    if env_spec is None or not action.package_name:
        return False
    if any(p.name == action.package_name for p in env_spec.packages):
        return True
    from .models import PinMethod
    env_spec.packages.append(PackageSpec(
        name=action.package_name,
        version=action.package_version,
        pin_method=PinMethod.unknown,
    ))
    return True


def rewrite_path(working_copy: Path, action: FixAction) -> bool:
    """Rewrite one quoted path string in a script."""
    if not action.script or not action.old_path or not action.new_path:
        return False
    path = _script_abs(working_copy, action.script)
    if not path.exists():
        return False
    text = path.read_text(errors="replace")
    new_text, count = _rewrite_quoted(text, action.old_path, action.new_path)
    if not count:
        return False
    path.write_text(new_text)
    return True


def add_missing_script_output(working_copy: Path, action: FixAction) -> bool:
    """Append LLM-generated write call to end of script file."""
    if not action.script or not action.write_call:
        return False
    path = _script_abs(working_copy, action.script)
    if not path.exists():
        return False
    existing = path.read_text(errors="replace")
    if action.write_call.strip() in existing:
        return False  # already present
    with path.open("a") as f:
        f.write("\n" + action.write_call.rstrip() + "\n")
    return True


def apply_fix(
    working_copy: Path,
    action: FixAction,
    env_spec: Optional[EnvSpec] = None,
) -> bool:
    dispatch = {
        "fix_write_path":            lambda: fix_write_path(working_copy, action),
        "install_package":           lambda: install_package(env_spec, action),
        "rewrite_path":              lambda: rewrite_path(working_copy, action),
        "add_missing_script_output": lambda: add_missing_script_output(working_copy, action),
    }
    fn = dispatch.get(action.kind)
    return fn() if fn else False


# ---------------------------------------------------------------------------
# Deterministic dispatcher
# ---------------------------------------------------------------------------


class DeterministicDispatcher:
    """
    Handles gaps fixable without LLM:
      - script_writes_wrong_path → fix_write_path
    """

    def __init__(self) -> None:
        self._handled: set[str] = set()

    def next_fix(self, gaps: list[Gap], context: FixContext) -> Optional[FixAction]:
        for gap in gaps:
            if gap.kind != GapKind.script_writes_wrong_path:
                continue
            if gap.exhibit is None:
                continue
            key = str(gap.exhibit)
            if key in self._handled:
                continue

            exhibit_rec = next(
                (e for e in context.graph.exhibits
                 if e.tex_path == gap.exhibit and e.source is not None),
                None,
            )
            if exhibit_rec is None:
                continue

            src = exhibit_rec.source
            try:
                script_rel = src.script.relative_to(context.working_copy)
            except ValueError:
                script_rel = src.script

            self._handled.add(key)
            return FixAction(
                kind="fix_write_path",
                script=script_rel,
                old_path=str(src.written_path),
                new_path=str(gap.exhibit),
            )

        return None  # converged


# ---------------------------------------------------------------------------
# Fix loop result
# ---------------------------------------------------------------------------


class FixLoopResult(BaseModel):
    iterations: int = 0
    fixes_applied: list[FixAction] = Field(default_factory=list)
    converged: bool = False
    final_gaps: list[Gap] = Field(default_factory=list)
    error: Optional[str] = None
    llm_reasoning: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_fix_loop(
    working_copy: Path,
    graph: DependencyGraph,
    env_spec: Optional[EnvSpec] = None,
    dispatcher: Optional[Dispatcher] = None,
    max_iterations: int = 10,
) -> tuple[FixLoopResult, DependencyGraph]:
    """
    Run FIX convergence loop. Returns (result, updated_graph).
    Mutates working_copy scripts only.
    """
    from .graph import build_graph

    if dispatcher is None:
        dispatcher = DeterministicDispatcher()

    result = FixLoopResult()
    current_graph = graph

    for iteration in range(max_iterations):
        result.iterations = iteration + 1
        context = FixContext(
            working_copy=working_copy,
            graph=current_graph,
            env_spec=env_spec,
            iteration=iteration,
            applied_fixes=list(result.fixes_applied),
        )

        action = dispatcher.next_fix(current_graph.gaps, context)
        if action is None:
            result.converged = True
            break

        applied = apply_fix(working_copy, action, env_spec)
        if applied:
            result.fixes_applied.append(action)
            current_graph = build_graph(working_copy)
        else:
            # Can't apply — don't loop forever
            result.converged = True
            break
    else:
        result.error = f"Did not converge after {max_iterations} iterations"

    result.final_gaps = list(current_graph.gaps)
    return result, current_graph


# ---------------------------------------------------------------------------
# LLM fix loop — re-runs scripts to capture stderr for the dispatcher
# ---------------------------------------------------------------------------


def run_llm_fix_loop(
    working_copy: Path,
    graph: DependencyGraph,
    env_spec: Optional[EnvSpec] = None,
    dispatcher: Optional[Dispatcher] = None,
    master_script: str = "code/run.R",
    max_iterations: int = 5,
    initial_stderr: Optional[str] = None,
) -> tuple[FixLoopResult, DependencyGraph]:
    """
    Run FIX loop with actual script re-execution after each fix.
    Uses LLMDispatcher by default; falls back gracefully if no API key.
    `initial_stderr` should be the stderr from the run that triggered this loop —
    without it, iteration 0 has no gaps and no stderr, so the dispatcher never
    even sees the original failure.
    Returns (result, updated_graph).
    """
    from .graph import build_graph
    from .runner import run_natively

    if dispatcher is None:
        from .llm_dispatcher import LLMDispatcher
        dispatcher = LLMDispatcher()

    result = FixLoopResult()
    current_graph = graph
    last_stderr: Optional[str] = initial_stderr

    for iteration in range(max_iterations):
        result.iterations = iteration + 1
        context = FixContext(
            working_copy=working_copy,
            graph=current_graph,
            env_spec=env_spec,
            iteration=iteration,
            applied_fixes=list(result.fixes_applied),
            last_stderr=last_stderr,
        )

        action = dispatcher.next_fix(current_graph.gaps, context)
        if action is None:
            result.converged = True
            break

        applied = apply_fix(working_copy, action, env_spec)
        if not applied:
            result.converged = True
            break

        result.fixes_applied.append(action)
        current_graph = build_graph(working_copy)

        run = run_natively(working_copy, master_script=master_script)
        last_stderr = run.stderr

        if hasattr(dispatcher, "reasoning") and dispatcher.reasoning:
            result.llm_reasoning.extend(dispatcher.reasoning)
            dispatcher.reasoning.clear()

        if run.success:
            result.converged = True
            break
    else:
        result.error = f"Did not converge after {max_iterations} iterations"

    result.final_gaps = list(current_graph.gaps)
    return result, current_graph


# ---------------------------------------------------------------------------
# AGENT_REPORT.md — append-only FIX section
# ---------------------------------------------------------------------------


def append_fix_report(working_copy: Path, fix_result: FixLoopResult) -> None:
    """Append FIX loop summary to AGENT_REPORT.md (creates file if absent)."""
    report = working_copy / "AGENT_REPORT.md"
    lines = [
        "\n## FIX loop\n",
        f"Iterations: {fix_result.iterations}  "
        f"| Converged: {'yes' if fix_result.converged else 'no'}  "
        f"| Fixes applied: {len(fix_result.fixes_applied)}\n",
    ]

    if fix_result.fixes_applied:
        lines.append("| # | Kind | Script | Old path | New path |")
        lines.append("|---|------|--------|----------|----------|")
        for i, fa in enumerate(fix_result.fixes_applied, 1):
            lines.append(
                f"| {i} | {fa.kind} | `{fa.script or '—'}` "
                f"| `{fa.old_path or '—'}` | `{fa.new_path or '—'}` |"
            )
    else:
        lines.append("_No fixes needed._")

    if fix_result.error:
        lines.append(f"\n**Warning:** {fix_result.error}")

    if fix_result.final_gaps:
        lines.append(f"\nRemaining gaps after FIX ({len(fix_result.final_gaps)}):")
        for g in fix_result.final_gaps:
            lines.append(f"- `{g.kind.value}`: {g.exhibit or g.location or '—'}")

    with report.open("a") as f:
        f.write("\n".join(lines) + "\n")
