"""Core pydantic models for DeadReckoning."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Confidentiality
# ---------------------------------------------------------------------------


class RestrictedStatus(BaseModel):
    is_restricted: bool
    reason: Optional[str] = None
    trigger_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------


class GapKind(str, Enum):
    exhibit_no_source_script = "exhibit_no_source_script"
    inline_table = "inline_table"
    inline_statistic = "inline_statistic"
    exhibit_missing_from_disk = "exhibit_missing_from_disk"
    script_writes_wrong_path = "script_writes_wrong_path"
    # A copy/rename edge (cp, file.rename, a `register`-style pair list, ...)
    # points at this exhibit, but the chain dead-ends — no write call produces
    # its source file either. Strictly more informative than
    # exhibit_no_source_script: we know ONE hop of provenance, just not the
    # root. Kept distinct so a report can show "found a lead" vs "nothing at all".
    exhibit_copied_but_no_source_script = "exhibit_copied_but_no_source_script"
    # A script reads an in-package (relative, non-external) data path that
    # does not exist on disk and that no script's write call produces either
    # — a genuinely missing input, not a restricted/external file (those are
    # surfaced separately by SCAN's external-path check). `exhibit` holds the
    # missing data path, reusing the same field other path-shaped gaps use.
    input_missing_from_disk = "input_missing_from_disk"
    # Fortran/C/C++ source is present but no Makefile/CMakeLists.txt/build
    # script, and no shell/batch script invoking a compiler, was found
    # anywhere in the project — DeadReckoning cannot guess the compile
    # command (the author may only have it in shell history). Blocking —
    # see compile_check.py / Action Point 4 in compare.md.
    compiled_language_no_build_script = "compiled_language_no_build_script"


class Gap(BaseModel):
    kind: GapKind
    exhibit: Optional[Path] = None       # path as referenced in .tex
    location: Optional[str] = None       # e.g. "paper.tex:412-441"
    snippet: Optional[str] = None        # the offending LaTeX fragment
    candidate_scripts: list[Path] = Field(default_factory=list)
    note: Optional[str] = None


class ScriptWritesExhibit(BaseModel):
    script: Path
    write_call: str        # e.g. "ggsave", "graph export", "savefig"
    line: int
    written_path: Path     # path the script actually writes to


class ScriptCopiesFile(BaseModel):
    """A copy/rename edge: `dst_path` is a copy or rename of `src_path`, found
    literally in a script (cp/mv/file.rename/file.copy/shutil.copy/copyfile/
    movefile/Stata `copy`, or a `src => dst`-style registration-table pair).
    Distinct from ScriptWritesExhibit: this isn't where content was produced,
    just where it was relocated/relabeled under a different name."""
    script: Path
    copy_call: str          # e.g. "cp", "file.rename", "=>" (register-table pair)
    line: int
    src_path: Path
    dst_path: Path


class Exhibit(BaseModel):
    tex_path: Path                        # path as referenced in .tex (may be relative)
    exists_on_disk: bool
    source: Optional[ScriptWritesExhibit] = None   # None → gap
    path_mismatch: bool = False           # script writes elsewhere, file was moved
    # Set when this exhibit's provenance runs through a copy/rename edge
    # rather than (or in addition to, for the final hop) a direct write call.
    # `source`, if also set, is the write call that produced the copy's
    # ORIGINAL (pre-rename) file — i.e. the full chain is: source writes
    # copied_via.src_path, which copied_via then copies/renames to
    # copied_via.dst_path (== this exhibit).
    copied_via: Optional[ScriptCopiesFile] = None


class DataFile(BaseModel):
    path: Path
    exists_on_disk: bool
    referenced_by: list[Path] = Field(default_factory=list)
    is_external: bool = False             # outside project root
    external_kind: Optional[str] = None  # "dropbox", "url", "network_share", "hpc", "coauthor"
    url: Optional[str] = None
    produced_by: Optional[Path] = None    # script whose write call matches this path, if any
    mtime: Optional[float] = None         # filesystem mtime at graph-build time


class OrphanFile(BaseModel):
    path: Path
    kind: str   # "script", "data", "output"


class DependencyGraph(BaseModel):
    project_root: Path
    tex_files: list[Path] = Field(default_factory=list)
    exhibits: list[Exhibit] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    data_files: list[DataFile] = Field(default_factory=list)
    orphan_files: list[OrphanFile] = Field(default_factory=list)
    script_order: list[Path] = Field(default_factory=list)  # topological order if resolvable
    script_writes: list[ScriptWritesExhibit] = Field(default_factory=list)  # every write call found, not just exhibit sources
    script_copies: list[ScriptCopiesFile] = Field(default_factory=list)  # every copy/rename edge found, not just exhibit sources

    @property
    def is_complete(self) -> bool:
        return len(self.gaps) == 0

    @property
    def exhibit_paths(self) -> set[Path]:
        return {e.tex_path for e in self.exhibits}

    @property
    def sourced_exhibits(self) -> list[Exhibit]:
        return [e for e in self.exhibits if e.source is not None]

    @property
    def unsourced_exhibits(self) -> list[Exhibit]:
        return [e for e in self.exhibits if e.source is None]


# ---------------------------------------------------------------------------
# Environment / version spec
# ---------------------------------------------------------------------------


class PinMethod(str, Enum):
    lockfile = "lockfile"
    live_session = "live_session"
    ppm_snapshot = "ppm_snapshot"       # R: Posit Package Manager dated snapshot
    conda_export = "conda_export"
    pip_freeze = "pip_freeze"
    manifest_toml = "manifest_toml"     # Julia
    pyproject = "pyproject"             # Python pyproject.toml
    inferred_from_date = "inferred_from_date"
    unknown = "unknown"


class PackageSpec(BaseModel):
    name: str
    version: Optional[str] = None
    pin_method: PinMethod = PinMethod.unknown


class EnvSpec(BaseModel):
    language: str
    language_version: Optional[str] = None
    packages: list[PackageSpec] = Field(default_factory=list)
    pin_method: PinMethod = PinMethod.unknown
    snapshot_date: Optional[str] = None    # ISO date used for PPM/conda channel
    snapshot_url: Optional[str] = None     # resolved PPM URL
    confidence: float = 0.0               # 0.0–1.0
    note: Optional[str] = None            # human-readable advice (e.g. MATLAB login)
    stata_image: Optional[str] = None     # pre-built private Stata base image tag
                                           # (e.g. "dataeditors/stata18_5-mp:2025-02-26")
                                           # — cannot be inferred from disk; author-supplied
    compile_command: Optional[str] = None  # Fortran/C/C++: exact compile (+ run) command
                                            # — cannot be inferred when no build script
                                            # exists; author-supplied, see compile_check.py


# ---------------------------------------------------------------------------
# Ground-truth manifest (for fixture testing)
# ---------------------------------------------------------------------------


class PathRewrite(BaseModel):
    original: str
    rewritten: str
    scripts_affected: list[Path] = Field(default_factory=list)


class ExpectedGap(BaseModel):
    kind: GapKind
    exhibit: Optional[str] = None
    location: Optional[str] = None
    note: Optional[str] = None


class ExpectedVersionPin(BaseModel):
    language: str
    method: PinMethod
    snapshot_date: Optional[str] = None


class AuthorQuestion(BaseModel):
    gap_kind: str
    exhibit: Optional[str] = None
    question: str
    context: Optional[str] = None


class AuthorResponse(BaseModel):
    exhibit: Optional[str] = None
    answer: str
    data_path: Optional[str] = None


class AuthorQA(BaseModel):
    questions: list[AuthorQuestion] = Field(default_factory=list)
    responses: list[AuthorResponse] = Field(default_factory=list)


class Manifest(BaseModel):
    """Ground-truth description of what a fixture contains and what the agent must do."""
    fixture_name: str
    gaps: list[ExpectedGap] = Field(default_factory=list)
    path_rewrites: list[PathRewrite] = Field(default_factory=list)
    version_pins: list[ExpectedVersionPin] = Field(default_factory=list)
    files_removed: list[str] = Field(default_factory=list)
    is_restricted: bool = False
    restricted_trigger: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Intake questionnaire (pre-pipeline, before disk read)
# ---------------------------------------------------------------------------


class IntakeResult(BaseModel):
    """Author-supplied context collected before the pipeline touches the disk."""
    paper_tex_path: Optional[str] = None        # §3 item 1 — relative or absolute
    code_root: Optional[str] = None             # §3 item 2
    data_root: Optional[str] = None             # §3 item 2
    master_script: Optional[str] = None         # entry point that runs the full analysis
    last_run_date: Optional[str] = None         # §3 item 5 — free text, e.g. "March 2023"
    languages_claimed: list[str] = Field(default_factory=list)   # §3 item 6
    has_stata_license: Optional[bool] = None    # §3 item 6
    has_matlab_license: Optional[bool] = None   # §3 item 6
    restricted_data: Optional[bool] = None      # §4.1 — asked before any file opened
    runtime_estimate: Optional[str] = None      # §3 item 8 — "minutes/hours/days"
    target_journal: Optional[str] = None        # §3 item 9

    # §4.2 — set only when a filename-heuristic hit (e.g. "census", "psid")
    # was re-confirmed with the author as a false positive. A filename
    # match alone is never enough to flip into restricted mode on its
    # own — legitimate public-use extracts are named this way too — so
    # this field records the author's answer to that follow-up question.
    # True  = author confirmed this specific match is NOT restricted data.
    # None  = no re-ask has happened yet (default; fails safe to restricted).
    restricted_override_safe: Optional[bool] = None


# ---------------------------------------------------------------------------
# CLEAN step models
# ---------------------------------------------------------------------------


class CleanChoice(BaseModel):
    path: Path
    kind: str                   # "script", "data", "output", "other"
    action: str = "keep"        # "delete", "archive", "keep"
    reason: Optional[str] = None


class CleanApplyResult(BaseModel):
    deleted: list[Path] = Field(default_factory=list)
    archived: list[Path] = Field(default_factory=list)
    kept: list[Path] = Field(default_factory=list)

    @property
    def total_cleaned(self) -> int:
        return len(self.deleted) + len(self.archived)


class CleanResult(BaseModel):
    orphans: list[OrphanFile] = Field(default_factory=list)
    choices: list[CleanChoice] = Field(default_factory=list)
    apply: Optional[CleanApplyResult] = None


# ---------------------------------------------------------------------------
# DELIVER step models
# ---------------------------------------------------------------------------


class DeliverResult(BaseModel):
    readme_path: Optional[Path] = None
    report_path: Optional[Path] = None
    package_path: Optional[Path] = None   # set only if zip assembled
    included_count: int = 0
    excluded_count: int = 0
