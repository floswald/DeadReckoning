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


class Exhibit(BaseModel):
    tex_path: Path                        # path as referenced in .tex (may be relative)
    exists_on_disk: bool
    source: Optional[ScriptWritesExhibit] = None   # None → gap
    path_mismatch: bool = False           # script writes elsewhere, file was moved


class DataFile(BaseModel):
    path: Path
    exists_on_disk: bool
    referenced_by: list[Path] = Field(default_factory=list)
    is_external: bool = False             # outside project root
    external_kind: Optional[str] = None  # "dropbox", "url", "network_share", "hpc", "coauthor"
    url: Optional[str] = None


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
    last_run_date: Optional[str] = None         # §3 item 5 — free text, e.g. "March 2023"
    languages_claimed: list[str] = Field(default_factory=list)   # §3 item 6
    has_stata_license: Optional[bool] = None    # §3 item 6
    has_matlab_license: Optional[bool] = None   # §3 item 6
    restricted_data: Optional[bool] = None      # §4.1 — asked before any file opened
    runtime_estimate: Optional[str] = None      # §3 item 8 — "minutes/hours/days"
    target_journal: Optional[str] = None        # §3 item 9


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
