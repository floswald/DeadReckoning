"""
LLM-backed gap hints — an optional, narrowly-scoped assist for ASK.

Separate from llm_dispatcher.py (LLM-FIX): this never proposes an action and
never touches the graph or the filesystem. It only ever produces a short,
clearly-labeled text suggestion attached to a question the author still has
to answer — the same "ask, don't silently decide" rule every other step in
this pipeline follows (spec §3, §5). If there's no API key, or nothing
useful to say, callers get None and ASK's deterministic question falls back
to exactly what it would say without this module.

Why this exists instead of just asking an LLM to build the whole graph:
GRAPH resolves ~85% of a real multi-language package's exhibits through
plain literal-text matching — nothing here needs a model. The residual is
either exhibits with a known copy/rename edge whose ORIGINAL write is
genuinely dynamic (a loop variable, a dict key, string interpolation — no
literal string exists anywhere for a regex, or an LLM reading the code
rather than running it, to find with certainty), or exhibits with no
producing code at all. Neither case is solved by "read more carefully" —
an LLM here is making the same kind of educated guess a human skimming the
code would make, which is why its output is a lead for the author to
confirm, never treated as a resolved fact.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .models import DependencyGraph, Exhibit, Gap, GapKind

_MAX_SNIPPET_CHARS = 4000  # per candidate script, keeps prompts small and cheap
_MAX_CANDIDATES = 5

_SYSTEM_PROMPT = """You are helping reconstruct provenance in a messy, real economics-paper \
replication package. You will be shown an exhibit (a figure or table file) that a \
deterministic scan could NOT trace to the script that produces it, plus whatever \
code the scan thinks might be relevant.

Answer in at most 3 sentences. If you can identify a plausible producing file \
and line (or function), name it and quote the relevant line. State your \
confidence as high/medium/low. If nothing in the provided code plausibly \
produces this file, say so plainly rather than guessing — a wrong confident \
guess is worse than an honest "I don't see it here."

You are not fixing anything and not asked to be certain. This is a lead for \
the paper's author to confirm, not a final answer."""


def _exhibit_for_gap(graph: DependencyGraph, gap: Gap) -> Optional[Exhibit]:
    if gap.exhibit is None:
        return None
    return next((e for e in graph.exhibits if e.tex_path == gap.exhibit), None)


def _read_snippet(path: Path) -> str:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return "(could not read file)"
    return text if len(text) <= _MAX_SNIPPET_CHARS else text[:_MAX_SNIPPET_CHARS] + "\n...(truncated)"


def _build_prompt(gap: Gap, graph: DependencyGraph, project_root: Path) -> Optional[str]:
    exhibit = _exhibit_for_gap(graph, gap)

    if gap.kind == GapKind.exhibit_copied_but_no_source_script and exhibit and exhibit.copied_via:
        edge = exhibit.copied_via
        sibling_names = sorted(
            p.name for p in edge.script.parent.glob("*")
            if p.is_file() and p.suffix.lower() in (".r", ".jl", ".py", ".do", ".m")
        )
        try:
            rel_script = edge.script.relative_to(project_root)
        except ValueError:
            rel_script = edge.script
        parts = [
            f"Exhibit `{gap.exhibit}` is produced by copying/renaming "
            f"`{edge.src_path}` to it (see {rel_script}:{edge.line}, "
            f"`{edge.copy_call}`). No script writes `{edge.src_path}` under "
            "that exact literal name — it's likely built dynamically (a loop "
            "variable, a dict/symbol key, string interpolation).",
            "",
            f"Full contents of {rel_script} (the file with the rename):",
            "```",
            _read_snippet(edge.script),
            "```",
        ]
        if sibling_names:
            parts += [
                "",
                f"Other code files in the same directory ({edge.script.parent.name}/): "
                + ", ".join(sibling_names[:30]),
            ]
        parts += [
            "",
            f"Which function/line most likely produces `{edge.src_path.name}`?",
        ]
        return "\n".join(parts)

    if gap.kind == GapKind.exhibit_no_source_script and gap.candidate_scripts:
        parts = [
            f"Exhibit `{gap.exhibit}` has no script that writes it under its "
            "exact literal path. Here are the scripts whose names most "
            "resemble it (a deterministic name-similarity heuristic, not a "
            "content match):",
        ]
        for script in gap.candidate_scripts[:_MAX_CANDIDATES]:
            try:
                rel = script.relative_to(project_root)
            except ValueError:
                rel = script
            parts += ["", f"--- {rel} ---", "```", _read_snippet(script), "```"]
        parts += [
            "",
            f"Does one of these plausibly produce `{gap.exhibit}`? If none do, "
            "say so.",
        ]
        return "\n".join(parts)

    return None  # nothing to usefully ask about — don't spend an API call


class GapHintDispatcher:
    """
    Proposes a one-shot, unverified text hint for a single unresolved gap.

    - No tool-calling, no iteration, no filesystem/graph side effects.
    - Returns None (and makes no API call at all) if there's no API key, or
      if the gap kind/context gives nothing useful to show the model.
    - Any API error is swallowed and returns None — this must never be able
      to break ASK, which has to keep working with zero network dependency.
    """

    def __init__(self, client: Any = None, model: str = "claude-sonnet-4-6") -> None:
        self._client = client
        self.model = model

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def propose_hint(self, gap: Gap, graph: DependencyGraph, project_root: Path) -> Optional[str]:
        if gap.kind not in (
            GapKind.exhibit_no_source_script,
            GapKind.exhibit_copied_but_no_source_script,
        ):
            return None

        client = self._get_client()
        if client is None:
            return None

        prompt = _build_prompt(gap, graph, project_root)
        if prompt is None:
            return None

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=300,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            return None

        text_blocks = [b.text.strip() for b in response.content if getattr(b, "type", None) == "text" and b.text.strip()]
        if not text_blocks:
            return None
        return " ".join(text_blocks)
