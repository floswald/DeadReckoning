"""
Loose oracle helpers for real-world replication package tests.

Usage in a real-world test file:
    from real_world_oracle import assert_graph_plausible, skip_if_absent

    FIXTURE = Path("tests/real_world/my_project")

    @skip_if_absent(FIXTURE)
    def test_graph_plausible():
        assert_graph_plausible(FIXTURE, min_exhibits=5)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind


def skip_if_absent(fixture_path: Path):
    """Decorator: skip test if fixture directory doesn't exist."""
    return pytest.mark.skipif(
        not fixture_path.exists(),
        reason=f"Real-world fixture absent: {fixture_path}. "
               f"Copy project to that path to run this test.",
    )


def assert_graph_plausible(
    project_root: Path,
    min_exhibits: int = 1,
    max_false_positive_gaps: int = 0,
    check_all_on_disk: bool = True,
    allowed_gap_kinds: Optional[set[GapKind]] = None,
) -> None:
    """
    Loose oracle assertions for a real-world project graph.

    Args:
        project_root: path to the project (may be in tests/real_world/ — not committed).
        min_exhibits: minimum plausible exhibit count.
        max_false_positive_gaps: how many exhibit_missing_from_disk gaps are acceptable
            (0 = all referenced exhibits must exist on disk).
        check_all_on_disk: if True, assert every exhibit exists on disk.
        allowed_gap_kinds: if given, only these gap kinds are permitted.
    """
    g = build_graph(project_root)

    assert len(g.exhibits) >= min_exhibits, (
        f"Too few exhibits ({len(g.exhibits)} < {min_exhibits}). "
        f"Macro expansion may have failed."
    )

    if check_all_on_disk:
        missing = [e for e in g.exhibits if not e.exists_on_disk]
        assert len(missing) <= max_false_positive_gaps, (
            f"{len(missing)} exhibits not found on disk "
            f"(allowed: {max_false_positive_gaps}):\n"
            + "\n".join(f"  {e.tex_path}" for e in missing)
        )

    if allowed_gap_kinds is not None:
        unexpected = [g for g in g.gaps if g.kind not in allowed_gap_kinds]
        assert not unexpected, (
            f"Unexpected gap kinds: {[g.kind for g in unexpected]}"
        )


def assert_no_raw_macros_in_paths(project_root: Path) -> None:
    """Assert no exhibit path contains unexpanded \\macroname."""
    g = build_graph(project_root)
    for e in g.exhibits:
        path_str = str(e.tex_path)
        assert not any(c == "\\" for c in path_str), (
            f"Unexpanded macro in path: {path_str}"
        )


def summarize_graph(project_root: Path) -> str:
    """Return a human-readable summary of the dependency graph (useful for debugging)."""
    g = build_graph(project_root)
    lines = [
        f"Project: {project_root.name}",
        f"  Exhibits: {len(g.exhibits)} "
        f"({sum(1 for e in g.exhibits if e.exists_on_disk)} on disk, "
        f"{sum(1 for e in g.exhibits if not e.exists_on_disk)} missing)",
        f"  Gaps: {len(g.gaps)}",
    ]
    gap_counts: dict[str, int] = {}
    for gap in g.gaps:
        gap_counts[gap.kind.value] = gap_counts.get(gap.kind.value, 0) + 1
    for kind, count in sorted(gap_counts.items()):
        lines.append(f"    {kind}: {count}")
    return "\n".join(lines)
