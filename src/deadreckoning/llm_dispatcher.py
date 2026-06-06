"""
LLM-backed dispatcher — uses Claude to propose fixes for reproducibility gaps.

Implements the Dispatcher protocol from fix_loop.py.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .fix_loop import FixAction, FixContext
from .models import Gap, GapKind


SYSTEM_PROMPT = """You are DeadReckoning, an automated reproducibility assistant for economics research papers.

Your job: inspect gaps in a computational replication package and propose one fix at a time using the provided tools.

## Gap taxonomy
- exhibit_no_source_script: a figure/table referenced in .tex has no script that produces it
- exhibit_missing_from_disk: exhibit file does not exist on disk and no script writes it
- script_writes_wrong_path: a script writes an output to a path that doesn't match the .tex reference
- inline_table / inline_statistic: number or table hard-coded in .tex (informational — no fix needed)

## Fix tools available
1. install_package(name, version): add a missing R/Python/Julia package
2. rewrite_path(script, old_path, new_path): fix a wrong input-data path in a script
3. fix_write_path(script, old_path, new_path): fix a wrong output-file path in a script write call
4. add_missing_script_output(script, exhibit_path, write_call): append a write call to a script that produces the exhibit but doesn't save it

## Rules
- Propose exactly ONE fix per call. If nothing can be fixed, call no tool.
- For add_missing_script_output, write_call must be valid code in the script's language (R/Python/Julia/Stata).
  - R: ggsave("path") or saveRDS(obj, "path") or write.csv(df, "path")
  - Python: fig.savefig("path") or df.to_csv("path")
  - Julia: CSV.write("path", df) or savefig("path")
  - Stata: graph export "path", replace
- Never propose a fix you've already proposed in this session.
- If the stderr shows a missing package error, propose install_package.
- If the stderr shows a file-not-found error, propose rewrite_path with the corrected path.
- Only fix gaps with clear evidence — do not guess when uncertain.
"""

TOOLS: list[dict[str, Any]] = [
    {
        "name": "install_package",
        "description": "Add a missing package to the environment spec.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package_name": {"type": "string", "description": "Package name"},
                "package_version": {"type": "string", "description": "Version string (optional)"},
            },
            "required": ["package_name"],
        },
    },
    {
        "name": "rewrite_path",
        "description": "Fix a wrong input-data path reference in a script.",
        "input_schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "Relative path to script file"},
                "old_path": {"type": "string", "description": "Current (wrong) path string in the script"},
                "new_path": {"type": "string", "description": "Correct path to use instead"},
            },
            "required": ["script", "old_path", "new_path"],
        },
    },
    {
        "name": "fix_write_path",
        "description": "Fix a wrong output-file path in a script write call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "Relative path to script file"},
                "old_path": {"type": "string", "description": "Current (wrong) path the script writes to"},
                "new_path": {"type": "string", "description": "Correct output path matching the .tex reference"},
            },
            "required": ["script", "old_path", "new_path"],
        },
    },
    {
        "name": "add_missing_script_output",
        "description": "Append a write/save call to a script that produces an exhibit but doesn't save it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "Relative path to script file"},
                "exhibit_path": {"type": "string", "description": "Path the exhibit should be written to"},
                "write_call": {"type": "string", "description": "Complete code snippet to append (e.g. ggsave(...))"},
            },
            "required": ["script", "exhibit_path", "write_call"],
        },
    },
]


def _gaps_summary(gaps: list[Gap]) -> str:
    lines = []
    for g in gaps:
        loc = str(g.exhibit or g.location or "—")
        note = f" — {g.note}" if g.note else ""
        lines.append(f"- {g.kind.value}: {loc}{note}")
    return "\n".join(lines) if lines else "(none)"


def _fix_fingerprint(action: FixAction) -> str:
    return json.dumps({
        "kind": action.kind,
        "package_name": action.package_name,
        "script": str(action.script) if action.script else None,
        "old_path": action.old_path,
        "new_path": action.new_path,
        "exhibit_path": action.exhibit_path,
    }, sort_keys=True)


class LLMDispatcher:
    """
    Calls Claude to propose one FixAction per invocation.

    - Uses claude-sonnet-4-6 by default; escalates to claude-opus-4-8 after stalls.
    - Returns None (converged) if: no API key, no tool call returned, or stall limit hit.
    - `reasoning` list accumulates per-turn text for AGENT_REPORT.
    """

    def __init__(
        self,
        client: Any = None,
        model: str = "claude-sonnet-4-6",
        max_model: str = "claude-opus-4-8",
        max_stalls: int = 3,
    ) -> None:
        self._client = client
        self.model = model
        self.max_model = max_model
        self._proposed: set[str] = set()
        self._stall_count: int = 0
        self._max_stalls = max_stalls
        self.reasoning: list[str] = []

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def next_fix(self, gaps: list[Gap], context: FixContext) -> Optional[FixAction]:
        client = self._get_client()
        if client is None:
            return None

        if self._stall_count >= self._max_stalls:
            return None

        actionable = [
            g for g in gaps
            if g.kind not in (GapKind.inline_table, GapKind.inline_statistic)
        ]
        if not actionable:
            return None

        current_model = self.max_model if self._stall_count >= 2 else self.model

        user_content = self._build_user_message(actionable, context)

        response = client.messages.create(
            model=current_model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": user_content}],
        )

        # Capture any text reasoning
        for block in response.content:
            if block.type == "text" and block.text.strip():
                self.reasoning.append(f"[iter {context.iteration}] {block.text.strip()}")

        # Find tool use block
        tool_block = next(
            (b for b in response.content if b.type == "tool_use"),
            None,
        )
        if tool_block is None:
            return None  # LLM chose not to call a tool → converged

        action = self._parse_tool_call(tool_block)
        if action is None:
            return None

        fp = _fix_fingerprint(action)
        if fp in self._proposed:
            self._stall_count += 1
            return None

        self._proposed.add(fp)
        self._stall_count = 0
        return action

    def _build_user_message(self, gaps: list[Gap], context: FixContext) -> str:
        parts = [
            f"## Project: {context.working_copy.name}",
            f"Iteration: {context.iteration + 1}",
            "",
            "## Open gaps",
            _gaps_summary(gaps),
        ]

        if context.last_stderr:
            stderr_snippet = context.last_stderr[-2000:] if len(context.last_stderr) > 2000 else context.last_stderr
            parts += ["", "## Last stderr", "```", stderr_snippet, "```"]

        if context.applied_fixes:
            parts += ["", "## Already applied fixes (do not repeat)"]
            for f in context.applied_fixes:
                parts.append(f"- {f.kind}: {f.script or f.package_name or '—'}")

        if context.env_spec:
            parts += ["", f"## Language: {context.env_spec.language}"]

        parts += ["", "Propose the single most impactful fix, or call no tool if nothing actionable remains."]
        return "\n".join(parts)

    def _parse_tool_call(self, block: Any) -> Optional[FixAction]:
        name = block.name
        inp = block.input or {}

        try:
            if name == "install_package":
                return FixAction(
                    kind="install_package",
                    package_name=inp["package_name"],
                    package_version=inp.get("package_version"),
                )
            elif name == "rewrite_path":
                from pathlib import Path as _Path
                return FixAction(
                    kind="rewrite_path",
                    script=_Path(inp["script"]),
                    old_path=inp["old_path"],
                    new_path=inp["new_path"],
                )
            elif name == "fix_write_path":
                from pathlib import Path as _Path
                return FixAction(
                    kind="fix_write_path",
                    script=_Path(inp["script"]),
                    old_path=inp["old_path"],
                    new_path=inp["new_path"],
                )
            elif name == "add_missing_script_output":
                from pathlib import Path as _Path
                return FixAction(
                    kind="add_missing_script_output",
                    script=_Path(inp["script"]),
                    exhibit_path=inp["exhibit_path"],
                    write_call=inp["write_call"],
                )
        except (KeyError, TypeError):
            return None

        return None
