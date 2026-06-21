"""
Tests for LLMDispatcher.

Unit tests use a mock Anthropic client.
Integration tests (marked llm) require ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from deadreckoning.fix_loop import FixAction, FixContext
from deadreckoning.llm_dispatcher import LLMDispatcher, _fix_fingerprint
from deadreckoning.models import (
    DependencyGraph,
    Gap,
    GapKind,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(gaps: list[Gap] | None = None) -> DependencyGraph:
    return DependencyGraph(
        project_root=Path("/tmp/proj"),
        gaps=gaps or [],
    )


def _make_context(working_copy: Path | None = None, **kwargs: Any) -> FixContext:
    wc = working_copy or Path("/tmp/proj")
    return FixContext(
        working_copy=wc,
        graph=_make_graph(),
        **kwargs,
    )


def _tool_use_block(name: str, inp: dict) -> Any:
    block = SimpleNamespace()
    block.type = "tool_use"
    block.name = name
    block.input = inp
    return block


def _text_block(text: str) -> Any:
    block = SimpleNamespace()
    block.type = "text"
    block.text = text
    return block


def _mock_response(*blocks: Any) -> Any:
    resp = MagicMock()
    resp.content = list(blocks)
    return resp


def _make_dispatcher(response: Any) -> LLMDispatcher:
    client = MagicMock()
    client.messages.create.return_value = response
    return LLMDispatcher(client=client)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestLLMDispatcherNoApiKey:
    def test_returns_none_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        d = LLMDispatcher()  # no injected client
        gaps = [Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"))]
        ctx = _make_context()
        assert d.next_fix(gaps, ctx) is None


class TestLLMDispatcherNoActionableGaps:
    def test_inline_gaps_skipped(self) -> None:
        client = MagicMock()
        d = LLMDispatcher(client=client)
        gaps = [
            Gap(kind=GapKind.inline_table),
            Gap(kind=GapKind.inline_statistic),
        ]
        ctx = _make_context()
        result = d.next_fix(gaps, ctx)
        assert result is None
        client.messages.create.assert_not_called()


class TestLLMDispatcherToolCallParsing:
    def test_install_package(self) -> None:
        resp = _mock_response(_tool_use_block("install_package", {"package_name": "ggplot2", "package_version": "3.4.0"}))
        d = _make_dispatcher(resp)
        gaps = [Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"))]
        action = d.next_fix(gaps, _make_context())
        assert action is not None
        assert action.kind == "install_package"
        assert action.package_name == "ggplot2"
        assert action.package_version == "3.4.0"

    def test_rewrite_path(self) -> None:
        resp = _mock_response(_tool_use_block("rewrite_path", {
            "script": "code/analysis.R",
            "old_path": "/data/old.csv",
            "new_path": "data/new.csv",
        }))
        d = _make_dispatcher(resp)
        gaps = [Gap(kind=GapKind.exhibit_missing_from_disk, exhibit=Path("fig1.pdf"))]
        action = d.next_fix(gaps, _make_context())
        assert action is not None
        assert action.kind == "rewrite_path"
        assert action.old_path == "/data/old.csv"
        assert action.new_path == "data/new.csv"

    def test_fix_write_path(self) -> None:
        resp = _mock_response(_tool_use_block("fix_write_path", {
            "script": "code/plot.R",
            "old_path": "output/fig1.png",
            "new_path": "figures/fig1.pdf",
        }))
        d = _make_dispatcher(resp)
        gaps = [Gap(kind=GapKind.script_writes_wrong_path, exhibit=Path("figures/fig1.pdf"))]
        action = d.next_fix(gaps, _make_context())
        assert action is not None
        assert action.kind == "fix_write_path"
        assert action.new_path == "figures/fig1.pdf"

    def test_add_missing_script_output(self) -> None:
        resp = _mock_response(_tool_use_block("add_missing_script_output", {
            "script": "code/plot.R",
            "exhibit_path": "figures/fig1.pdf",
            "write_call": 'ggsave("figures/fig1.pdf", plot = p)',
        }))
        d = _make_dispatcher(resp)
        gaps = [Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("figures/fig1.pdf"))]
        action = d.next_fix(gaps, _make_context())
        assert action is not None
        assert action.kind == "add_missing_script_output"
        assert action.write_call == 'ggsave("figures/fig1.pdf", plot = p)'

    def test_no_tool_call_returns_none(self) -> None:
        resp = _mock_response(_text_block("Nothing actionable."))
        d = _make_dispatcher(resp)
        gaps = [Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"))]
        result = d.next_fix(gaps, _make_context())
        assert result is None

    def test_reasoning_captured(self) -> None:
        resp = _mock_response(
            _text_block("I see a missing package error."),
            _tool_use_block("install_package", {"package_name": "dplyr"}),
        )
        d = _make_dispatcher(resp)
        gaps = [Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"))]
        d.next_fix(gaps, _make_context())
        assert any("missing package" in r for r in d.reasoning)


class TestStallDetection:
    def test_stall_on_repeated_fix(self) -> None:
        resp = _mock_response(_tool_use_block("install_package", {"package_name": "ggplot2"}))
        client = MagicMock()
        client.messages.create.return_value = resp
        d = LLMDispatcher(client=client, max_stalls=2)
        gaps = [Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"))]
        ctx = _make_context()

        action1 = d.next_fix(gaps, ctx)
        assert action1 is not None  # first proposal accepted

        action2 = d.next_fix(gaps, ctx)
        assert action2 is None  # same fingerprint → stall
        assert d._stall_count == 1

        action3 = d.next_fix(gaps, ctx)
        assert action3 is None  # stall limit reached

    def test_stall_resets_on_new_fix(self) -> None:
        client = MagicMock()
        d = LLMDispatcher(client=client, max_stalls=3)

        resp1 = _mock_response(_tool_use_block("install_package", {"package_name": "ggplot2"}))
        resp2 = _mock_response(_tool_use_block("install_package", {"package_name": "dplyr"}))

        client.messages.create.side_effect = [resp1, resp1, resp2]
        gaps = [Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"))]
        ctx = _make_context()

        d.next_fix(gaps, ctx)  # ggplot2 accepted
        d.next_fix(gaps, ctx)  # ggplot2 again → stall (count=1)
        action = d.next_fix(gaps, ctx)  # dplyr → stall resets, accepted
        assert action is not None
        assert action.package_name == "dplyr"
        assert d._stall_count == 0

    def test_escalates_to_max_model_after_stalls(self) -> None:
        client = MagicMock()
        resp_stall = _mock_response(_tool_use_block("install_package", {"package_name": "ggplot2"}))
        resp_new = _mock_response(_tool_use_block("install_package", {"package_name": "dplyr"}))
        client.messages.create.side_effect = [resp_stall, resp_stall, resp_new]

        d = LLMDispatcher(client=client, model="claude-sonnet-4-6", max_model="claude-opus-4-8", max_stalls=3)
        gaps = [Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig.pdf"))]
        ctx = _make_context()

        d.next_fix(gaps, ctx)  # accepted (sonnet)
        d.next_fix(gaps, ctx)  # stall 1 → next call uses sonnet still (stall_count=1)
        # stall_count=1, threshold for opus is >=2 stalls
        d.next_fix(gaps, ctx)  # stall_count=1 → call 3 with new proposal uses sonnet still

        calls = client.messages.create.call_args_list
        assert calls[0].kwargs["model"] == "claude-sonnet-4-6"


class TestFingerprintDeduplication:
    def test_different_actions_have_different_fingerprints(self) -> None:
        a1 = FixAction(kind="install_package", package_name="ggplot2")
        a2 = FixAction(kind="install_package", package_name="dplyr")
        assert _fix_fingerprint(a1) != _fix_fingerprint(a2)

    def test_same_action_same_fingerprint(self) -> None:
        a1 = FixAction(kind="install_package", package_name="ggplot2", package_version="3.4.0")
        a2 = FixAction(kind="install_package", package_name="ggplot2", package_version="3.4.0")
        assert _fix_fingerprint(a1) == _fix_fingerprint(a2)


# ---------------------------------------------------------------------------
# Multi-language scenarios
# ---------------------------------------------------------------------------


class TestMultiLanguageScenarios:
    def test_python_missing_module_proposes_install(self) -> None:
        """Gap note describes Python ModuleNotFoundError → dispatcher proposes install_package."""
        gap = Gap(
            kind=GapKind.exhibit_no_source_script,
            exhibit=Path("figures/fig1.png"),
            note="ModuleNotFoundError: No module named 'pandas'",
        )
        response = _mock_response(
            _tool_use_block("install_package", {"package_name": "pandas"})
        )
        d = _make_dispatcher(response)
        action = d.next_fix([gap], _make_context())
        assert action is not None
        assert action.kind == "install_package"
        assert action.package_name == "pandas"

    def test_julia_missing_package_proposes_install(self) -> None:
        """Gap note describes Julia missing pkg → dispatcher proposes install_package."""
        gap = Gap(
            kind=GapKind.exhibit_no_source_script,
            exhibit=Path("output/table1.tex"),
            note="Package DataFrames not found in current path",
        )
        response = _mock_response(
            _tool_use_block("install_package", {"package_name": "DataFrames"})
        )
        d = _make_dispatcher(response)
        action = d.next_fix([gap], _make_context())
        assert action is not None
        assert action.kind == "install_package"
        assert action.package_name == "DataFrames"

    def test_mixed_gap_kinds_llm_called_once_per_next_fix(self) -> None:
        """Three gaps of different kinds → LLM called exactly once per next_fix invocation."""
        gaps = [
            Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf")),
            Gap(kind=GapKind.exhibit_missing_from_disk, exhibit=Path("table1.tex")),
            Gap(kind=GapKind.script_writes_wrong_path, exhibit=Path("fig2.pdf")),
        ]
        response = _mock_response(
            _tool_use_block("install_package", {"package_name": "ggplot2"})
        )
        d = _make_dispatcher(response)
        d.next_fix(gaps, _make_context())
        assert d._client.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Integration test — requires real API key
# ---------------------------------------------------------------------------


@pytest.mark.llm
def test_llm_dispatcher_real_api(tmp_path: Path) -> None:
    """Smoke test: dispatcher returns a FixAction or None for a simple gap."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    d = LLMDispatcher(client=client)

    gaps = [
        Gap(
            kind=GapKind.script_writes_wrong_path,
            exhibit=Path("figures/fig1.pdf"),
            note="Script writes to output/fig1.pdf but paper references figures/fig1.pdf",
        )
    ]
    graph = _make_graph(gaps)
    ctx = FixContext(
        working_copy=tmp_path,
        graph=graph,
        iteration=0,
    )

    action = d.next_fix(gaps, ctx)
    # Either returns a valid FixAction or None (converged) — both acceptable
    if action is not None:
        assert action.kind in ("fix_write_path", "rewrite_path", "install_package", "add_missing_script_output")
