"""
FIDELITY step: compare every regenerated exhibit against an author-supplied
reference — the output files (figures/tables) as they stood when the paper
was accepted — and report mismatches.

Why this needs an author-supplied reference at all: `check_exhibit_fidelity()`
(runner.py) compares exhibit *bytes*, and a fresh working copy has no "last
known good" copy of anything by construction — nothing to diff against
unless the author points at one. The compiled paper PDF is NOT a usable
reference here: it would need page extraction and a visual/text diff, a
different and much harder mechanism than the exact byte compare this module
does. The reference has to be the actual exhibit files (a `fig1.pdf`, a
`Table1.tex` fragment) as they existed at acceptance — a preserved
submission folder, an old Overleaf export, a zip, anything the author still
has lying around, however informal. If nothing like that exists anywhere,
this step says so plainly and does nothing further — there is no reference
to reconstruct one from.

Matching is by basename only, swept across every author-given directory
(not just the first match) — collisions (the same basename found in more
than one given directory) are recorded rather than silently resolved, since
a wrong silent match would report false confidence, which is worse than not
checking at all for a step whose whole point is to be trustworthy.

Non-blocking, like every other check in this module family — but unlike
RNG-CHECK/MIXED-LANGUAGE-CHECK/SORT-CHECK (passive scans that only speak up
when something's wrong), this one writes FIDELITY-REPORT.md whenever it
actually runs, clean pass or not: the author explicitly supplied a
reference to get an answer, so confirming "N/N matched" is itself part of
the answer, not silence.

Known limitation, not fixed here: if an author's reference directory lives
inside the working copy (e.g. a version-controlled `replication/reference/`
folder), CLEAN (which runs before this step and has no knowledge of
reference_exhibit_dirs) will list its files as orphans in CLEANUP.md even
though this report says they're the real reference — the same class of gap
already documented for the demo fixtures' own `reference/` directories.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .graph import build_graph
from .models import IntakeResult
from .runner import FidelityResult, check_exhibit_fidelity, group_fidelity_mismatches

_FIDELITY_REPORT_FILE = "FIDELITY-REPORT.md"


class FidelityCheckResult(BaseModel):
    attempted: bool = False
    reference_dirs: list[Path] = Field(default_factory=list)
    missing_reference_dirs: list[Path] = Field(default_factory=list)
    exhibits_checked: int = 0
    exhibits_without_reference: list[Path] = Field(default_factory=list)
    # basename -> every directory a hit was found in, when more than one
    basename_collisions: dict[str, list[Path]] = Field(default_factory=dict)
    mismatches: list[FidelityResult] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def has_findings(self) -> bool:
        return bool(
            self.missing_reference_dirs
            or self.exhibits_without_reference
            or self.basename_collisions
            or self.mismatches
        )


def _resolve_reference_dirs(
    working_copy: Path, raw_dirs: list[str]
) -> tuple[list[Path], list[Path]]:
    """Each given string resolved the same way ask.py resolves data_root:
    absolute as-is, relative joined to working_copy. Returns
    (existing_dirs, missing_dirs)."""
    existing: list[Path] = []
    missing: list[Path] = []
    for raw in raw_dirs:
        p = Path(raw)
        if not p.is_absolute():
            p = working_copy / raw
        if p.is_dir():
            existing.append(p)
        else:
            missing.append(p)
    return existing, missing


def _find_reference_files(basename: str, dirs: list[Path]) -> list[Path]:
    """Every hit for `basename` across every given directory, in directory
    order — a direct child first, then a recursive search within that
    directory. Does not stop at the first hit: the full sweep is what lets
    callers detect a collision (the same basename found under more than one
    given directory) instead of silently picking one."""
    hits: list[Path] = []
    for d in dirs:
        direct = d / basename
        if direct.is_file():
            hits.append(direct)
            continue
        for candidate in sorted(d.rglob(basename)):
            if candidate.is_file():
                hits.append(candidate)
                break
    return hits


def run_fidelity_check_step(
    working_copy: Path, intake: IntakeResult | None
) -> FidelityCheckResult:
    """
    Full FIDELITY step: if the author gave no reference_exhibit_dirs at
    intake, return immediately with attempted=False and write nothing —
    there is no reference to compare against. Otherwise rebuild the
    dependency graph fresh (not reusing an earlier graph — the mtime
    evidence _localize_divergence() reports needs current mtimes, which a
    graph built before the native run doesn't have), match every sourced
    exhibit to a reference file by basename, run check_exhibit_fidelity()
    for each match, and always write FIDELITY-REPORT.md.
    """
    if intake is None or not intake.reference_exhibit_dirs:
        return FidelityCheckResult(attempted=False)

    graph = build_graph(working_copy)
    resolved_dirs, missing_dirs = _resolve_reference_dirs(
        working_copy, intake.reference_exhibit_dirs
    )

    result = FidelityCheckResult(
        attempted=True,
        reference_dirs=resolved_dirs,
        missing_reference_dirs=missing_dirs,
    )

    for exhibit in graph.sourced_exhibits:
        hits = _find_reference_files(exhibit.tex_path.name, resolved_dirs)
        if not hits:
            result.exhibits_without_reference.append(exhibit.tex_path)
            continue
        if len(hits) > 1:
            result.basename_collisions[exhibit.tex_path.name] = hits

        result.exhibits_checked += 1
        fidelity = check_exhibit_fidelity(
            working_copy, graph, exhibit.tex_path, hits[0].read_bytes()
        )
        if not fidelity.matches_reference:
            result.mismatches.append(fidelity)

    write_fidelity_report_file(working_copy, result)
    return result


def write_fidelity_report_file(working_copy: Path, result: FidelityCheckResult) -> Path:
    lines = [
        "# DeadReckoning — Fidelity Report\n\n",
        "Compares every regenerated exhibit against the reference output "
        "files supplied at intake. This is advisory only; the pipeline is "
        "not blocked by it.\n\n",
    ]

    if result.missing_reference_dirs:
        lines.append("## Reference directories not found\n\n")
        for d in result.missing_reference_dirs:
            lines.append(f"- `{d}`\n")
        lines.append("\n")

    lines.append(
        f"Checked {result.exhibits_checked} exhibit(s) against "
        f"{len(result.reference_dirs)} reference directory/directories.\n\n"
    )

    if result.exhibits_without_reference:
        lines.append("## Exhibits with no matching reference file\n\n")
        lines.append(
            "No file with this exhibit's name was found in any reference "
            "directory given at intake — FIDELITY cannot say anything "
            "about these.\n\n"
        )
        for p in result.exhibits_without_reference:
            lines.append(f"- `{p}`\n")
        lines.append("\n")

    if result.basename_collisions:
        lines.append("## Basename collisions\n\n")
        lines.append(
            "The same filename was found in more than one reference "
            "directory — the first directory (in the order given at "
            "intake) was used for the comparison below; the others were "
            "not. Confirm these are not different exhibits that happen to "
            "share a name.\n\n"
        )
        for basename, paths in result.basename_collisions.items():
            joined = ", ".join(f"`{p}`" for p in paths)
            lines.append(f"- `{basename}`: {joined}\n")
        lines.append("\n")

    if result.mismatches:
        lines.append("## Mismatches\n\n")
        grouped = group_fidelity_mismatches(result.mismatches)
        for fidelity in result.mismatches:
            lines.append(f"### `{fidelity.exhibit}`\n\n")
            lines.append(
                f"- reference hash: `{fidelity.reference_hash}`\n"
                f"- regenerated hash: `{fidelity.regenerated_hash}`\n"
            )
            if fidelity.nondeterminism_note:
                lines.append(f"- {fidelity.nondeterminism_note}\n")
            for suspect in fidelity.suspects:
                lines.append(
                    f"- suspect: `{suspect.path}` [{suspect.evidence}, "
                    f"confidence={suspect.confidence}] — {suspect.detail}\n"
                )
            lines.append("\n")
        if grouped:
            lines.append("### Shared suspects across exhibits\n\n")
            for suspect_path, exhibits in grouped.items():
                exhibit_list = ", ".join(f"`{e}`" for e in exhibits)
                lines.append(f"- `{suspect_path}` implicated in: {exhibit_list}\n")
            lines.append("\n")
    else:
        lines.append(
            f"All {result.exhibits_checked} checked exhibit(s) match their "
            "reference.\n"
        )

    path = working_copy / _FIDELITY_REPORT_FILE
    path.write_text("".join(lines))
    return path
