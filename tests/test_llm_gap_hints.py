"""
Tests for GapHintDispatcher (llm_gap_hints.py).

Unit tests use a mock Anthropic client — no network, no API key needed.
Mirrors tests/test_llm_dispatcher.py's conventions.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from deadreckoning.llm_gap_hints import GapHintDispatcher
from deadreckoning.models import DependencyGraph, Exhibit, Gap, GapKind, ScriptCopiesFile, ScriptWritesExhibit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_block(text: str) -> Any:
    block = SimpleNamespace()
    block.type = "text"
    block.text = text
    return block


def _mock_response(*blocks: Any) -> Any:
    resp = MagicMock()
    resp.content = list(blocks)
    return resp


def _make_dispatcher(response: Any) -> tuple[GapHintDispatcher, MagicMock]:
    client = MagicMock()
    client.messages.create.return_value = response
    return GapHintDispatcher(client=client), client


# ---------------------------------------------------------------------------
# No API key — must no-op, never call the network
# ---------------------------------------------------------------------------


def test_returns_none_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = GapHintDispatcher()  # no injected client
    gap = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"), candidate_scripts=[])
    graph = DependencyGraph(project_root=Path("/tmp/proj"), gaps=[gap])
    assert d.propose_hint(gap, graph, Path("/tmp/proj")) is None


# ---------------------------------------------------------------------------
# Gap kinds this module doesn't handle — must no-op without calling the client
# ---------------------------------------------------------------------------


def test_irrelevant_gap_kind_skipped_without_api_call() -> None:
    client = MagicMock()
    d = GapHintDispatcher(client=client)
    gap = Gap(kind=GapKind.inline_table)
    graph = DependencyGraph(project_root=Path("/tmp/proj"), gaps=[gap])
    assert d.propose_hint(gap, graph, Path("/tmp/proj")) is None
    client.messages.create.assert_not_called()


def test_no_source_script_with_no_candidates_skipped_without_api_call() -> None:
    """Nothing useful to show the model — don't spend an API call."""
    client = MagicMock()
    d = GapHintDispatcher(client=client)
    gap = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"), candidate_scripts=[])
    graph = DependencyGraph(project_root=Path("/tmp/proj"), gaps=[gap])
    assert d.propose_hint(gap, graph, Path("/tmp/proj")) is None
    client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# exhibit_no_source_script — candidate scripts get sent, hint comes back
# ---------------------------------------------------------------------------


def test_no_source_script_sends_candidate_contents(tmp_path: Path) -> None:
    script = tmp_path / "figures.R"
    script.write_text('ggsave("output/fig1_v2.pdf")\n')

    resp = _mock_response(_text_block("fig1.pdf is likely produced by figures.R (medium confidence)."))
    d, client = _make_dispatcher(resp)

    gap = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"), candidate_scripts=[script])
    graph = DependencyGraph(project_root=tmp_path, gaps=[gap])

    hint = d.propose_hint(gap, graph, tmp_path)
    assert hint == "fig1.pdf is likely produced by figures.R (medium confidence)."

    sent = client.messages.create.call_args.kwargs
    user_msg = sent["messages"][0]["content"]
    assert "ggsave" in user_msg  # script content was actually included
    assert "fig1.pdf" in user_msg


# ---------------------------------------------------------------------------
# exhibit_copied_but_no_source_script — uses the copy edge's script + siblings
# ---------------------------------------------------------------------------


def test_copied_but_no_source_sends_rename_script_and_siblings(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    rename_script = src_dir / "param.jl"
    rename_script.write_text(
        'register = [pf_base("mod_data_x.pdf") => joinpath(dbplots(), "figure8a.pdf")]\n'
    )
    (src_dir / "plotter.jl").write_text('dd[:mod_data_x] = plot(x, y)\n')

    resp = _mock_response(_text_block(
        "Likely plotter.jl:1 (`dd[:mod_data_x] = plot(x, y)`), medium confidence."
    ))
    d, client = _make_dispatcher(resp)

    edge = ScriptCopiesFile(
        script=rename_script, copy_call="=>", line=1,
        src_path=Path("mod_data_x.pdf"), dst_path=Path("figure8a.pdf"),
    )
    exhibit = Exhibit(
        tex_path=Path("output/figure8a.pdf"), exists_on_disk=True,
        source=None, copied_via=edge,
    )
    gap = Gap(
        kind=GapKind.exhibit_copied_but_no_source_script,
        exhibit=Path("output/figure8a.pdf"),
        note=f"{rename_script.name}:1 copies mod_data_x.pdf to this exhibit, but no script writes mod_data_x.pdf",
    )
    graph = DependencyGraph(project_root=tmp_path, gaps=[gap], exhibits=[exhibit])

    hint = d.propose_hint(gap, graph, tmp_path)
    assert hint is not None
    assert "plotter.jl" in hint

    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "register" in user_msg  # rename script's own content included
    assert "plotter.jl" in user_msg  # sibling file listed


def test_copied_but_no_source_without_exhibit_lookup_skips_api_call() -> None:
    """Gap references an exhibit not present in graph.exhibits (shouldn't
    happen in practice, but must fail safe, not crash or guess)."""
    client = MagicMock()
    d = GapHintDispatcher(client=client)
    gap = Gap(kind=GapKind.exhibit_copied_but_no_source_script, exhibit=Path("ghost.pdf"))
    graph = DependencyGraph(project_root=Path("/tmp/proj"), gaps=[gap], exhibits=[])
    assert d.propose_hint(gap, graph, Path("/tmp/proj")) is None
    client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling — must never raise
# ---------------------------------------------------------------------------


def test_api_error_returns_none_not_raise(tmp_path: Path) -> None:
    script = tmp_path / "figures.R"
    script.write_text('ggsave("fig1.pdf")\n')
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("network blew up")
    d = GapHintDispatcher(client=client)
    gap = Gap(kind=GapKind.exhibit_no_source_script, exhibit=Path("fig1.pdf"), candidate_scripts=[script])
    graph = DependencyGraph(project_root=tmp_path, gaps=[gap])
    assert d.propose_hint(gap, graph, tmp_path) is None


def test_empty_response_returns_none() -> None:
    resp = _mock_response()  # no content blocks at all
    d, _ = _make_dispatcher(resp)
    script_gap = Gap(kind=GapKind.inline_table)  # irrelevant kind forces early None anyway
    graph = DependencyGraph(project_root=Path("/tmp/proj"), gaps=[])
    assert d.propose_hint(script_gap, graph, Path("/tmp/proj")) is None
