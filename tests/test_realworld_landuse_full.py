"""Real-world test: LandUse full replication package (Oswald et al.).

Multi-language package: Stata (step 1) → R (steps 2/4) → Julia (step 3).

Requires env var R_LANDUSE pointing to the full package root, e.g.:
    R_LANDUSE=~/Dropbox/research/LandUse/replicationpackage-submit pytest tests/test_realworld_landuse_full.py -v

Skipped automatically in CI (env var absent).

Notes:
- Stata presence is checked structurally only (native run not yet in this test).
- renv.lock lives under code/LandUseR/ — Dropbox selective sync must include it
  for the R capture tests to pass.
- Graph runs against paper_production/ (manuscript + output siblings) — not
  package root, which scans too many binary/data files.
- Orchestrator static test copies only code/ + paper_production/ to tmp, skipping
  data/ (too large) and any Dropbox cloud-only files (SIGALRM probe per file).
"""

from __future__ import annotations

import os
import shutil
import signal
from pathlib import Path

import pytest

from deadreckoning.capture import capture_env
from deadreckoning.confidentiality import check_restricted
from deadreckoning.graph import build_graph
from deadreckoning.models import GapKind, PinMethod
from deadreckoning.orchestrator import run_pipeline

# ---------------------------------------------------------------------------
# Setup — skip entire module when env var absent
# ---------------------------------------------------------------------------

_LANDUSE_PATH = os.environ.get("R_LANDUSE", "")
_PKG_ROOT = Path(_LANDUSE_PATH).expanduser() if _LANDUSE_PATH else None

pytestmark = pytest.mark.skipif(
    not _LANDUSE_PATH or not (_PKG_ROOT and _PKG_ROOT.exists()),
    reason="R_LANDUSE not set or path does not exist (local only)",
)


def _root() -> Path:
    assert _PKG_ROOT is not None
    return _PKG_ROOT


# ---------------------------------------------------------------------------
# Confidentiality
# ---------------------------------------------------------------------------


def test_landuse_confidentiality_scan_runs():
    """check_restricted runs without error and does not false-positive on
    data/IGN-chef-lieux/ign_metropole_adminexpress_chefs_lieux_z.prj — public
    IGN administrative boundary data, not restricted microdata. (Previously a
    known false positive: bare 'admin' matched inside 'adminexpress'; the
    pattern now requires an adjacent data/records marker.)"""
    status = check_restricted(_root())
    assert not status.is_restricted, (
        f"Unexpected restricted-data trigger: {status.reason}\n"
        f"  path: {status.trigger_path}"
    )


# ---------------------------------------------------------------------------
# Structural — package layout
# ---------------------------------------------------------------------------


def test_master_script_exists():
    assert (_root() / "code" / "run_all.sh").exists()


def test_stata_scripts_present():
    stata_dir = _root() / "code" / "stata"
    do_files = list(stata_dir.glob("*.do"))
    assert len(do_files) >= 3, f"Expected ≥3 .do files, found {len(do_files)}"


def test_r_package_present():
    assert (_root() / "code" / "LandUseR" / "DESCRIPTION").exists()


def test_julia_package_present():
    assert (_root() / "code" / "LandUse.jl" / "Project.toml").exists()
    assert (_root() / "code" / "LandUse.jl" / "Manifest.toml").exists()


def test_julia_master_script_present():
    assert (_root() / "code" / "LandUse.jl" / "run.jl").exists()


# ---------------------------------------------------------------------------
# Graph — paper_production/ (manuscript + output siblings)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def landuse_graph():
    return build_graph(_root() / "paper_production")


def test_graph_exhibit_count_plausible(landuse_graph):
    """Full paper has many figures and tables; expect ≥30 exhibits."""
    assert len(landuse_graph.exhibits) >= 30, (
        f"Only {len(landuse_graph.exhibits)} exhibits — macro resolution may be broken"
    )


def test_graph_all_exhibits_on_disk(landuse_graph):
    missing = [e for e in landuse_graph.exhibits if not e.exists_on_disk]
    assert missing == [], (
        f"{len(missing)} exhibits referenced in .tex but missing from disk:\n"
        + "\n".join(f"  {e.tex_path}" for e in missing[:10])
    )


def test_graph_no_inline_statistic_gaps(landuse_graph):
    """Output .tex tables must be excluded — no false inline_statistic hits."""
    stat_gaps = [g for g in landuse_graph.gaps if g.kind == GapKind.inline_statistic]
    assert stat_gaps == [], (
        f"{len(stat_gaps)} inline_statistic gaps (likely false positives from output tables):\n"
        + "\n".join(f"  {g.location}: {g.snippet!r}" for g in stat_gaps[:5])
    )


def test_graph_all_gaps_no_source_script(landuse_graph):
    """paper_production has no code scripts — all gaps should be exhibit_no_source_script."""
    wrong = [g for g in landuse_graph.gaps if g.kind == GapKind.exhibit_missing_from_disk]
    assert wrong == [], (
        f"{len(wrong)} exhibits missing from disk — macro resolution broken:\n"
        + "\n".join(f"  {g.exhibit}" for g in wrong[:10])
    )


# ---------------------------------------------------------------------------
# Capture — Julia (Manifest.toml present and locally synced)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def julia_env():
    return capture_env(_root() / "code" / "LandUse.jl")


def test_julia_capture_language(julia_env):
    assert julia_env.language == "Julia"


def test_julia_capture_confidence(julia_env):
    assert julia_env.confidence >= 0.9


def test_julia_capture_pin_method(julia_env):
    assert julia_env.pin_method == PinMethod.manifest_toml


def test_julia_capture_package_count(julia_env):
    """Manifest.toml has 382 packages (full dependency tree)."""
    assert len(julia_env.packages) >= 50


def test_julia_capture_key_packages(julia_env):
    names = {p.name for p in julia_env.packages}
    for pkg in ["Optim", "DataFrames", "CSV", "Plots"]:
        assert pkg in names, f"Expected package {pkg!r} not found in Julia env"


def test_julia_packages_have_versions(julia_env):
    versioned = [p for p in julia_env.packages if p.version is not None]
    assert len(versioned) >= 50, "Expected most packages to have version pins"


# ---------------------------------------------------------------------------
# Capture — R (renv.lock — requires Dropbox selective sync of code/LandUseR/)
# ---------------------------------------------------------------------------

_RENV_LOCK = _PKG_ROOT / "code" / "LandUseR" / "renv.lock" if _PKG_ROOT else None


def _renv_readable() -> bool:
    """Return True only if renv.lock exists AND is readable (not Dropbox cloud-only)."""
    if not _RENV_LOCK or not _RENV_LOCK.exists():
        return False
    try:
        import signal

        def _timeout(signum, frame):
            raise TimeoutError

        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(3)
        try:
            _RENV_LOCK.read_bytes()[:128]
            return True
        except (OSError, TimeoutError):
            return False
        finally:
            signal.alarm(0)
    except Exception:
        return False


_skip_r = pytest.mark.skipif(
    not _renv_readable(),
    reason="code/LandUseR/renv.lock absent or Dropbox cloud-only (sync required)",
)


@_skip_r
def test_r_capture_language():
    spec = capture_env(_root() / "code" / "LandUseR")
    assert spec.language == "R"


@_skip_r
def test_r_capture_confidence():
    spec = capture_env(_root() / "code" / "LandUseR")
    assert spec.confidence >= 0.9


@_skip_r
def test_r_capture_pin_method():
    spec = capture_env(_root() / "code" / "LandUseR")
    assert spec.pin_method == PinMethod.renv_lock


@_skip_r
def test_r_capture_version_442():
    """run_all.sh pins R 4.4.2; renv.lock must record the same."""
    spec = capture_env(_root() / "code" / "LandUseR")
    assert spec.language_version == "4.4.2", (
        f"Expected R 4.4.2 (pinned in run_all.sh), got {spec.language_version!r}"
    )


# ---------------------------------------------------------------------------
# Orchestrator — static pipeline (DETECT → RESOLVE, no native execution)
#
# Copies only code/ + paper_production/ to a tmp dir.  Each file is copied
# with a SIGALRM watchdog so Dropbox cloud-only files are silently skipped
# rather than hanging the test suite.
# ---------------------------------------------------------------------------


def _safe_copy_file(src: str, dst: str) -> None:
    """shutil.copy2 wrapper that skips files that block > 5 s (cloud-only)."""
    def _handler(signum, frame):
        raise TimeoutError
    signal.signal(signal.SIGALRM, _handler)
    signal.alarm(5)
    try:
        shutil.copy2(src, dst)
    except (TimeoutError, OSError):
        pass
    finally:
        signal.alarm(0)


@pytest.fixture(scope="module")
def landuse_local_copy(tmp_path_factory):
    """Shallow local copy: code/ + paper_production/ only, data/ excluded."""
    root = _root()
    tmp = tmp_path_factory.mktemp("landuse_copy")
    for subdir in ("code", "paper_production"):
        shutil.copytree(
            root / subdir,
            tmp / subdir,
            copy_function=_safe_copy_file,
        )
    return tmp


def test_orchestrator_detects_master_script(landuse_local_copy):
    """_detect_master_script must find code/run_all.sh."""
    from deadreckoning.orchestrator import _detect_master_script
    assert _detect_master_script(landuse_local_copy) == "code/run_all.sh"


def test_orchestrator_static_pipeline(landuse_local_copy):
    """Static pipeline completes without error through RESOLVE."""
    result = run_pipeline(
        landuse_local_copy,
        master_script="code/run_all.sh",
        skip_run=True,
        skip_docker=True,
    )
    assert result.error is None, f"Pipeline error: {result.error}"
    assert result.graph is not None
    assert result.env_spec is not None
    assert result.scan is not None
    assert result.resolve is not None


def test_orchestrator_graph_finds_exhibits(landuse_local_copy):
    result = run_pipeline(
        landuse_local_copy,
        master_script="code/run_all.sh",
        skip_run=True,
        skip_docker=True,
    )
    assert len(result.graph.exhibits) >= 10


def test_orchestrator_env_detected(landuse_local_copy):
    result = run_pipeline(
        landuse_local_copy,
        master_script="code/run_all.sh",
        skip_run=True,
        skip_docker=True,
    )
    assert result.env_spec.language in ("R", "Julia", "Stata"), (
        f"Unexpected language: {result.env_spec.language!r}"
    )


def test_orchestrator_scan_finds_packages(landuse_local_copy):
    """Multi-language package — scan should find external paths or packages."""
    result = run_pipeline(
        landuse_local_copy,
        master_script="code/run_all.sh",
        skip_run=True,
        skip_docker=True,
    )
    total = (
        len(result.scan.used_packages)
        + len(result.scan.external_paths)
        + len(result.scan.download_calls)
    )
    assert total >= 1, "scan found nothing across packages/paths/downloads"
