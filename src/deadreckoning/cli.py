"""Command-line interface for DeadReckoning."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# ANSI helpers (no deps; fall back to plain if not a tty)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _green(t: str) -> str:   return _c(t, "32")
def _red(t: str) -> str:     return _c(t, "31")
def _yellow(t: str) -> str:  return _c(t, "33")
def _bold(t: str) -> str:    return _c(t, "1")
def _dim(t: str) -> str:     return _c(t, "2")

_OK   = _green("✓")
_FAIL = _red("✗")
_WARN = _yellow("!")


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------

def _to_jsonable(obj: Any) -> Any:
    """Recursively make an object JSON-serializable."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    # pydantic BaseModel
    try:
        return _to_jsonable(obj.model_dump())
    except AttributeError:
        pass
    # dataclass
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _to_jsonable(dataclasses.asdict(obj))
    # enum
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


# ---------------------------------------------------------------------------
# Gap table printer
# ---------------------------------------------------------------------------

_GAP_LABELS = {
    "exhibit_no_source_script":   "no source script",
    "inline_table":               "inline table",
    "inline_statistic":           "inline statistic",
    "exhibit_missing_from_disk":  "file missing",
    "script_writes_wrong_path":   "path mismatch",
}


def _print_gap_table(graph: Any) -> None:
    gaps = graph.gaps
    if not gaps:
        print(f"  {_OK} no gaps found")
        return

    col_w = max(len(str(g.exhibit or g.location or "—")) for g in gaps) + 2
    print(f"  {_bold('Gap'):<{col_w+2}}  {_bold('Kind')}")
    print(f"  {'—'*col_w}  {'—'*24}")
    for gap in gaps:
        label = str(gap.exhibit or gap.location or "—")
        kind  = _GAP_LABELS.get(gap.kind.value if hasattr(gap.kind, 'value') else gap.kind, str(gap.kind))
        print(f"  {_red(label):<{col_w+9}}  {kind}")


# ---------------------------------------------------------------------------
# sub-command: graph
# ---------------------------------------------------------------------------

def _cmd_graph(args: argparse.Namespace) -> int:
    from .confidentiality import check_restricted
    from .graph import build_graph

    project = Path(args.project).resolve()
    if not project.exists():
        print(f"{_FAIL} path not found: {project}", file=sys.stderr)
        return 1

    restricted = check_restricted(project)
    if restricted.is_restricted:
        print(f"{_FAIL} restricted data: {restricted.reason}", file=sys.stderr)
        return 1

    graph = build_graph(project)

    if args.json:
        print(json.dumps(_to_jsonable(graph), indent=2, default=str))
        return 0 if graph.is_complete else 1

    print(_bold(f"\nDependency graph — {project.name}"))
    print(f"  tex files  : {len(graph.tex_files)}")
    print(f"  exhibits   : {len(graph.exhibits)}")
    print(f"  gaps       : {len(graph.gaps)}")
    print()
    _print_gap_table(graph)
    print()
    return 0 if graph.is_complete else 1


# ---------------------------------------------------------------------------
# sub-command: check
# ---------------------------------------------------------------------------

def _cmd_check(args: argparse.Namespace) -> int:
    from .capture import capture_env
    from .confidentiality import check_restricted
    from .graph import build_graph

    project = Path(args.project).resolve()
    if not project.exists():
        print(f"{_FAIL} path not found: {project}", file=sys.stderr)
        return 1

    restricted = check_restricted(project)
    if restricted.is_restricted:
        print(f"{_FAIL} restricted data: {restricted.reason}", file=sys.stderr)
        return 1

    graph = build_graph(project)
    env   = capture_env(project)

    if args.json:
        print(json.dumps({"graph": _to_jsonable(graph), "env": _to_jsonable(env)}, indent=2, default=str))
        return 0 if graph.is_complete else 1

    print(_bold(f"\nCheck — {project.name}"))

    print(f"\n  {_bold('Environment')}")
    pin_ok = env.pin_method.value != "unknown"
    icon   = _OK if pin_ok else _WARN
    print(f"  {icon} language    : {env.language}")
    print(f"  {icon} pin method  : {env.pin_method.value}")
    if env.snapshot_date:
        print(f"  {_OK} snapshot    : {env.snapshot_date}")
    print(f"  {_dim('packages')}   : {len(env.packages)}")
    print(f"  {_dim('confidence')} : {env.confidence:.0%}")

    print(f"\n  {_bold('Dependency graph')}")
    print(f"  exhibits : {len(graph.exhibits)}")
    print(f"  gaps     : {len(graph.gaps)}")
    _print_gap_table(graph)
    print()
    return 0 if graph.is_complete else 1


# ---------------------------------------------------------------------------
# sub-command: run
# ---------------------------------------------------------------------------

def _cmd_run(args: argparse.Namespace) -> int:
    from .orchestrator import run_pipeline

    project = Path(args.project).resolve()
    if not project.exists():
        print(f"{_FAIL} path not found: {project}", file=sys.stderr)
        return 1

    if not args.json:
        print(_bold(f"\nRunning pipeline — {project.name}"))
        print(_dim("  (working copy created; original untouched)"))

    result = run_pipeline(
        project,
        master_script=args.master_script or None,
        skip_docker=args.skip_docker,
    )

    if args.json:
        print(json.dumps(_to_jsonable(result), indent=2, default=str))
        return 0 if (not result.error and result.native_ok) else 1

    print(f"\n  {'step':<22}  result")
    print(f"  {'—'*22}  {'—'*20}")

    def _row(step: str, ok: bool | None, note: str = "") -> None:
        if ok is None:
            icon = _dim("—")
        elif ok:
            icon = _OK
        else:
            icon = _FAIL
        suffix = f"  {_dim(note)}" if note else ""
        print(f"  {step:<22}  {icon}{suffix}")

    _row("DETECT",         not result.restricted.is_restricted)
    _row("GRAPH",          result.graph is not None,
         f"{len(result.graph.gaps)} gap(s)" if result.graph else "")
    _row("CAPTURE",        result.env_spec is not None,
         result.env_spec.pin_method.value if result.env_spec else "")
    _row("RUN (native)",   result.native_run.success if result.native_run else None,
         f"rc={result.native_run.returncode}" if result.native_run else "skipped")
    _row("VALIDATE (native)", result.native_validation is not None and result.native_validation.success
         if result.native_validation else None,
         "" if not result.native_validation else
         f"{len(result.native_validation.missing)} missing")

    if not args.skip_docker:
        _row("GENERATE",      result.dockerfile is not None)
        _row("BUILD (docker)", result.docker_build.success if result.docker_build else None,
             "" if not result.docker_build else ("" if result.docker_build.success else "see logs"))
        _row("VALIDATE (docker)", result.container_ok if result.container_validation else None)

    print()
    if result.error:
        print(f"  {_FAIL} {_bold('FAILED')}: {result.error}")
    else:
        print(f"  {_OK} {_bold('PASSED')}")
    print()

    ok = not result.error and result.native_ok
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# sub-command: detect-stata
# ---------------------------------------------------------------------------

def _cmd_detect_stata(args: argparse.Namespace) -> int:
    from .stata import detect_stata

    install = detect_stata()

    if args.json:
        print(json.dumps(_to_jsonable(install), indent=2, default=str))
        return 0 if install.found else 1

    if install.found:
        loc = f"(on PATH)" if install.on_path else f"(at {install.hint_path})"
        flavor = f" [{install.flavor}]" if install.flavor else ""
        ver    = f" v{install.version}"  if install.version else ""
        print(f"  {_OK} Stata{flavor}{ver}  {_green(install.binary)}  {_dim(loc)}")
    else:
        print(f"  {_FAIL} Stata not found")
        if install.advice:
            print(f"\n  {_WARN} {install.advice}")

    return 0 if install.found else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deadreckoning",
        description="Reconstruct and validate computational replication packages.",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    sub = parser.add_subparsers(dest="command", required=True)

    # graph
    p_graph = sub.add_parser("graph", help="Build dependency graph and print gap report")
    p_graph.add_argument("project", help="Path to project directory")
    p_graph.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    # check
    p_check = sub.add_parser("check", help="GRAPH + CAPTURE; no execution")
    p_check.add_argument("project", help="Path to project directory")
    p_check.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    # run
    p_run = sub.add_parser("run", help="Full pipeline: DETECT → RUN → VALIDATE [→ Docker]")
    p_run.add_argument("project", help="Path to project directory")
    p_run.add_argument("--master-script", metavar="SCRIPT",
                       help="Override auto-detected master script (e.g. code/run.R)")
    p_run.add_argument("--skip-docker", action=argparse.BooleanOptionalAction, default=True,
                       help="Skip Docker steps (default: skip; use --no-skip-docker to enable)")
    p_run.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    # detect-stata
    p_stata = sub.add_parser("detect-stata", help="Print Stata detection result and advice")
    p_stata.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    args = parser.parse_args()

    if args.no_color:
        global _USE_COLOR
        _USE_COLOR = False

    dispatch = {
        "graph":         _cmd_graph,
        "check":         _cmd_check,
        "run":           _cmd_run,
        "detect-stata":  _cmd_detect_stata,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
