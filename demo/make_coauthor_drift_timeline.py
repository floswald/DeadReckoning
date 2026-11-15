#!/usr/bin/env python3
"""
Generates demo/coauthor_drift_timeline.svg: a literal vertical timeline
for slides — a single arrow down the left border with tick marks at real
dates, and event boxes laid out in three columns (time | Author 1 |
Author 2) so it's immediately visible who did what. Joint/external
milestones (paper accepted, final PDF sent) span both author columns in
a neutral style. A visible axis break compresses the long forgotten
stretch between the silent re-export and the eventual rerun, so that gap
is the point of the picture, not an afterthought.

Hand-written SVG rather than Mermaid: Mermaid's flowchart layout engine
gives no control over an axis/tick visual, wraps node labels at a fixed
pixel width regardless of content, and has no notion of "column per
actor" (hit this building the Mermaid versions in demo/README.md) —
wrong tool for this specific ask.

Run: python3 demo/make_coauthor_drift_timeline.py
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Literal

Actor = Literal["A1", "A2", "BOTH"]

RED = "#7a2e2e"
RED_TEXT = "#ffffff"

A1_COLOR = "#2b4c7e"      # Author 1 — blue
A1_FILL = "#eaf1fb"
A2_COLOR = "#6b3fa0"      # Author 2 — purple
A2_FILL = "#f3ecfa"
NEUTRAL_STROKE = "#555555"
NEUTRAL_FILL = "#f0f0f0"

AXIS_COLOR = "#222222"
TEXT_COLOR = "#111111"
FONT = "Helvetica, Arial, sans-serif"

TICK_LEN = 14

# AXIS_X needs enough clearance to its left for a full right-anchored
# date label (e.g. "2025-05-20") to not run off the canvas edge.
AXIS_X = 95

A1_X = AXIS_X + 55                   # 150
COL_W = 265
GAP_COLS = 20
A2_X = A1_X + COL_W + GAP_COLS       # 435
NEUTRAL_X = A1_X
NEUTRAL_W = (A2_X + COL_W) - A1_X    # spans both columns, 550

WIDTH = A2_X + COL_W + 30            # 730

STRIPE_W = 6                         # actor-identity stripe on each box's left edge

HEADER_Y = 22
TOP_MARGIN = 55                      # first tick starts below the column headers

# Conservative chars-per-line estimate at font-size 12.5 Helvetica, so
# `wrap_lines` can safely re-wrap any phrase that would otherwise overflow
# its box — avoids hand-counting characters for every line of text below.
MAX_CHARS_COL = 30
MAX_CHARS_NEUTRAL = 62

# (date, lines, actor, is_red) — each line is a logical phrase; long ones
# are automatically re-wrapped to fit the box width at render time.
events: list[tuple[str, list[str], Actor, bool]] = [
    (
        "2024-01-08",
        ["clean.R run", "-> panel.csv"],
        "A1",
        False,
    ),
    (
        "2024-01-10",
        ["export.do run (Stata 12)", "-> input_data_from_2.csv (v1)"],
        "A2",
        False,
    ),
    (
        "2024-01-12",
        ["combine.jl run #1", "(reads panel.csv + csv v1)", "-> Table 3 (v1 numbers)"],
        "A1",
        False,
    ),
    (
        "2024-03-05",
        ["Upgrades Stata 12 -> 18, reruns export.do", "csv overwritten with v2 (full precision)", "combine.jl NOT rerun"],
        "A2",
        True,
    ),
    (
        "2025-05-20",
        ['"Final" PDF generated, sent to journal', "(still v1 Table 3)"],
        "BOTH",
        False,
    ),
    (
        "2025-06-01",
        ["Paper accepted", "(still carries v1 numbers)"],
        "BOTH",
        False,
    ),
    (
        "2026 (today)",
        ["Author 1 reruns the pipeline:", "combine.jl reads panel.csv + csv (v2)", "Table 3 regenerated -- no longer matches the PDF"],
        "A1",
        True,
    ),
]

# Everything from right after the silent re-export onward is the
# forgotten stretch — "paper accepted" and "final PDF sent" are just
# milestones that pass by inside it, not reasons to reset to normal
# spacing.
BREAK_AFTER_INDEX = 3

GAP_PAD_NORMAL = 34
GAP_PAD_BREAK = 16   # compressed — this is the ~2-year jump, deliberately tighter
BOTTOM_MARGIN = 30
AXIS_OVERSHOOT = 35  # axis extends this far past the last tick, so the arrowhead clears it

LINE_H = 16
BOX_V_PAD = 18


def box_geometry(actor: Actor) -> tuple[int, int]:
    """(x, width) of the box for a given actor/column."""
    if actor == "A1":
        return A1_X, COL_W
    if actor == "A2":
        return A2_X, COL_W
    return NEUTRAL_X, NEUTRAL_W


def wrap_lines(raw_lines: list[str], actor: Actor) -> list[str]:
    """Re-wrap any logical line that would overflow its column's box
    width, so source text can stay natural phrases instead of
    hand-counted characters-per-line."""
    max_chars = MAX_CHARS_NEUTRAL if actor == "BOTH" else MAX_CHARS_COL
    out: list[str] = []
    for line in raw_lines:
        out.extend(textwrap.wrap(line, width=max_chars) or [""])
    return out


def box_height(lines: list[str]) -> int:
    return len(lines) * LINE_H + BOX_V_PAD


def event_block(y_center: int, date: str, raw_lines: list[str], actor: Actor, is_red: bool) -> str:
    box_x, box_w = box_geometry(actor)
    lines = wrap_lines(raw_lines, actor)
    h = box_height(lines)

    if is_red:
        fill, stroke, text_fill = RED, RED, RED_TEXT
    elif actor == "A1":
        fill, stroke, text_fill = A1_FILL, A1_COLOR, TEXT_COLOR
    elif actor == "A2":
        fill, stroke, text_fill = A2_FILL, A2_COLOR, TEXT_COLOR
    else:
        fill, stroke, text_fill = NEUTRAL_FILL, NEUTRAL_STROKE, TEXT_COLOR

    svg = []

    # tick mark on the axis
    svg.append(
        f'<line x1="{AXIS_X - TICK_LEN / 2}" y1="{y_center}" '
        f'x2="{AXIS_X + TICK_LEN / 2}" y2="{y_center}" '
        f'stroke="{AXIS_COLOR}" stroke-width="2.5"/>'
    )
    # date label, left of axis
    svg.append(
        f'<text x="{AXIS_X - TICK_LEN}" y="{y_center + 4}" text-anchor="end" '
        f'font-family="{FONT}" font-size="12.5" font-weight="600" fill="{AXIS_COLOR}">{date}</text>'
    )
    # connector from axis to box
    svg.append(
        f'<line x1="{AXIS_X}" y1="{y_center}" x2="{box_x}" y2="{y_center}" '
        f'stroke="{AXIS_COLOR}" stroke-width="1.5" stroke-dasharray="3,3"/>'
    )

    # event box
    box_y = y_center - h / 2
    svg.append(
        f'<rect x="{box_x}" y="{box_y}" width="{box_w}" height="{h}" rx="6" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
    )

    # actor-identity stripe on the box's left edge — makes "who did this"
    # readable even at a glance, independent of the red/neutral fill.
    if actor == "BOTH":
        half = h / 2
        svg.append(
            f'<rect x="{box_x}" y="{box_y}" width="{STRIPE_W}" height="{half}" '
            f'fill="{A1_COLOR}"/>'
        )
        svg.append(
            f'<rect x="{box_x}" y="{box_y + half}" width="{STRIPE_W}" height="{half}" '
            f'fill="{A2_COLOR}"/>'
        )
    else:
        stripe_color = A1_COLOR if actor == "A1" else A2_COLOR
        svg.append(
            f'<rect x="{box_x}" y="{box_y}" width="{STRIPE_W}" height="{h}" fill="{stripe_color}"/>'
        )

    # text lines inside the box (indented past the stripe)
    n = len(lines)
    start_y = y_center - (n - 1) * LINE_H / 2 + 5
    for i, line in enumerate(lines):
        weight = "700" if i == 0 else "400"
        svg.append(
            f'<text x="{box_x + STRIPE_W + 10}" y="{start_y + i * LINE_H}" '
            f'font-family="{FONT}" font-size="12.5" font-weight="{weight}" fill="{text_fill}">{line}</text>'
        )
    return "\n".join(svg)


def merge_connector(
    src_edge: tuple[int, int], dst_edge: tuple[int, int], elbow_x: int, color: str, marker_id: str
) -> str:
    """Elbow connector (src edge -> elbow -> dst edge) with an arrowhead,
    used only for the two local merges into combine.jl's first run — not
    a general dependency graph, just enough to show that box merging
    both authors' files. The elbow sits in the empty gap between the two
    columns, so it never crosses through another box."""
    x1, y1 = src_edge
    x2, y2 = dst_edge
    return (
        f'<path d="M {x1} {y1} L {elbow_x} {y1} L {elbow_x} {y2} L {x2} {y2}" '
        f'fill="none" stroke="{color}" stroke-width="1.75" stroke-dasharray="4,3" '
        f'marker-end="url(#{marker_id})"/>'
    )


def column_header(x: int, w: int, label: str, color: str) -> str:
    cx = x + w / 2
    svg = [
        f'<text x="{cx}" y="{HEADER_Y}" text-anchor="middle" '
        f'font-family="{FONT}" font-size="15" font-weight="700" fill="{color}">{label}</text>',
        f'<rect x="{x}" y="{HEADER_Y + 8}" width="{w}" height="3" rx="1.5" fill="{color}"/>',
    ]
    return "\n".join(svg)


def break_mark(y: int) -> str:
    """Axis-break glyph: two short diagonal ticks crossing the axis line,
    the standard "scale is compressed here" convention."""
    svg = []
    for dx in (-7, 3):
        svg.append(
            f'<line x1="{AXIS_X + dx - 6}" y1="{y + 8}" x2="{AXIS_X + dx + 6}" y2="{y - 8}" '
            f'stroke="{AXIS_COLOR}" stroke-width="2.5"/>'
        )
    svg.append(
        f'<text x="{AXIS_X + 24}" y="{y + 5}" font-family="{FONT}" font-size="13" '
        f'font-style="italic" fill="{RED}">~1.5 years, forgotten</text>'
    )
    return "\n".join(svg)


# The break-mark glyph is attached to the beat right AFTER the gap, not
# the one before it — so clicking past the silent re-export first shows
# that box, then the NEXT click reveals both the axis break and whatever
# happened on the other side of it together ("time jumped to get here").
BREAK_MARK_BEAT = BREAK_AFTER_INDEX + 1

# combine.jl #1's beat is where its two inputs visibly converge.
MERGE_BEAT = 2


def build(*, fragments: bool = False) -> str:
    """
    fragments=False (default): the static picture, every event visible —
    used for demo/README.md and as a non-interactive fallback.

    fragments=True: each event is wrapped in a reveal.js
    ``<g class="fragment" data-fragment-index="i">`` so the slide can
    reveal one event per click. The axis and column headers are left
    unwrapped — they're the picture's beat 1, visible before the first
    advance. Meant to be inlined as raw HTML (not referenced via <img>,
    which reveal.js's fragment JS can't reach inside of).
    """
    heights = [box_height(wrap_lines(lines, actor)) for _, lines, actor, _ in events]

    y_positions: list[int] = []
    y = TOP_MARGIN + heights[0] / 2
    for i in range(len(events)):
        y_positions.append(int(y))
        if i < len(events) - 1:
            pad = GAP_PAD_BREAK if i >= BREAK_AFTER_INDEX else GAP_PAD_NORMAL
            y += heights[i] / 2 + pad + heights[i + 1] / 2

    total_height = y_positions[-1] + heights[-1] / 2 + BOTTOM_MARGIN

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{total_height}" '
        f'viewBox="0 0 {WIDTH} {total_height}" '
        f'style="max-width:100%;height:auto;display:block;margin:0 auto;">',
        f'<rect x="0" y="0" width="{WIDTH}" height="{total_height}" fill="white"/>',
        '<defs>',
        f'<marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{AXIS_COLOR}"/></marker>',
        f'<marker id="arrow-merge-a1" viewBox="0 0 10 10" refX="5" refY="5" '
        f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{A1_COLOR}"/></marker>',
        f'<marker id="arrow-merge-a2" viewBox="0 0 10 10" refX="5" refY="5" '
        f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{A2_COLOR}"/></marker>',
        '</defs>',
    ]

    # Beat 1 (always visible, no fragment wrapper): column headers + the
    # full-length time axis, arrowhead included.
    parts.append(column_header(A1_X, COL_W, "Author 1", A1_COLOR))
    parts.append(column_header(A2_X, COL_W, "Author 2", A2_COLOR))
    parts.append(
        f'<line x1="{AXIS_X}" y1="{y_positions[0] - 12}" x2="{AXIS_X}" y2="{y_positions[-1] + AXIS_OVERSHOOT}" '
        f'stroke="{AXIS_COLOR}" stroke-width="3" marker-end="url(#arrow)"/>'
    )

    # merge connectors: clean.R (0) and export.do v1 (1) both feed combine.jl #1 (2).
    # Elbow sits in the empty gap between the A1/A2 columns, so neither
    # segment ever crosses through another box.
    a1_x, a1_w = box_geometry("A1")
    a2_x, a2_w = box_geometry("A2")
    elbow_x = a1_x + a1_w + GAP_COLS / 2  # midpoint of the inter-column gap

    merge_svg = "\n".join([
        # clean.R (A1, directly above combine.jl in the same column) -> combine.jl #1
        merge_connector(
            src_edge=(a1_x + a1_w, y_positions[0]),
            dst_edge=(a1_x + a1_w, y_positions[2] - 6),
            elbow_x=elbow_x,
            color=A1_COLOR,
            marker_id="arrow-merge-a1",
        ),
        # export.do v1 (A2) -> combine.jl #1 (A1), crossing the column gap
        merge_connector(
            src_edge=(a2_x, y_positions[1]),
            dst_edge=(a1_x + a1_w, y_positions[2] + 6),
            elbow_x=elbow_x,
            color=A2_COLOR,
            marker_id="arrow-merge-a2",
        ),
    ])

    # Beats 2-8 (one event per click): tick, date, connector, box, and
    # anything else that belongs to that moment in the story.
    for i, ((date, lines, actor, is_red), y) in enumerate(zip(events, y_positions)):
        beat = [event_block(y, date, lines, actor, is_red)]
        if i == MERGE_BEAT:
            beat.append(merge_svg)
        if i == BREAK_MARK_BEAT:
            mid = (y_positions[i - 1] + y) / 2
            beat.append(break_mark(int(mid)))
        content = "\n".join(beat)
        if fragments:
            parts.append(f'<g class="fragment" data-fragment-index="{i}">\n{content}\n</g>')
        else:
            parts.append(content)

    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    demo_dir = Path(__file__).parent
    slides_img_dir = demo_dir.parent / "slides" / "img"

    static_out = demo_dir / "coauthor_drift_timeline.svg"
    static_out.write_text(build(fragments=False))
    print(f"wrote {static_out}")

    if slides_img_dir.is_dir():
        fragments_out = slides_img_dir / "coauthor_drift_timeline_fragments.html"
        fragments_out.write_text(
            "```{=html}\n" + build(fragments=True) + "\n```\n"
        )
        print(f"wrote {fragments_out}  (include via {{{{< include img/{fragments_out.name} >}}}})")
