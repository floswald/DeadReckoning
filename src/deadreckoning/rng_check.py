"""
RNG-CHECK step: flag a stochastic call (sampling, simulation, bootstrap,
random draws, ...) with no seed call anywhere upstream of it in the run
order. Non-blocking — writes RNG-WARNINGS.md, same posture as CLEANUP.md.

Why this exists: a script that draws random numbers without seeding can
exit 0, every exhibit can land on disk, and VALIDATE is satisfied — the run
looks identical to a correct one, but the numbers it produced are not the
numbers that were published. This is exactly the failure class an
execution-first pipeline (run it, see if it crashes) walks straight past
unless something specifically looks for it. See Action Point 2 in
compare.md.

Covers all 8 languages DeadReckoning targets: Stata, R, Python, MATLAB,
Julia, Fortran, C, C++ — not just the two reproai covers (Stata, R), and
not gated on DeadReckoning being able to *execute* that language as a
master script (Fortran/C/C++ routinely show up as compiled helper code
called from an R/Python/Stata master script).

Best-effort regex, like the rest of the static layer — no AST, no
language-specific parser. A script relying on an upstream script having
already seeded (common: one `set.seed()` in the master, sourced children
inherit the RNG state) is handled by walking `graph.script_order` and
treating "any script up to and including this one has a seed call" as
satisfied — not just the current script in isolation.

The C/C++ stochastic patterns also cover Rcpp's embedding of R's own RNG
(`Rcpp::rnorm`/`R::rnorm`/`norm_rand`/`unif_rand`/...) — an Rcpp-compiled
`.cpp` draws from the SAME RNG stream as the R script that calls it, so
it is correctly "seeded" by an upstream `set.seed()` in that R driver,
via the same `graph.script_order` walk (R scripts are master scripts and
so appear in script_order; the `.cpp` they source via `sourceCpp()` is
picked up by the fallback scan below and always walked after them).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models import DependencyGraph

_RNG_WARNINGS_FILE = "RNG-WARNINGS.md"

# suffix (lowercased) -> (language label, seed-call regex, stochastic-call regex)
_RNG_PATTERNS: dict[str, tuple[str, re.Pattern[str], re.Pattern[str]]] = {
    ".r": (
        "R",
        re.compile(r"\bset\.seed\s*\("),
        re.compile(r"\b(?:sample|rnorm|runif|rbinom|rpois|rexp|rgamma|rbeta|mvrnorm|boot)\s*\("),
    ),
    ".py": (
        "Python",
        re.compile(
            r"\b(?:random\.seed|np\.random\.seed|numpy\.random\.seed"
            r"|np\.random\.default_rng|numpy\.random\.default_rng"
            r"|torch\.manual_seed|tf\.random\.set_seed)\s*\(\s*\S"
        ),
        re.compile(
            r"\b(?:random\.random|random\.choice|random\.shuffle|random\.randint"
            r"|np\.random\.rand|np\.random\.randn|np\.random\.normal|np\.random\.choice"
            r"|np\.random\.permutation|torch\.randn|torch\.rand)\s*\("
        ),
    ),
    ".do": (
        "Stata",
        re.compile(r"\bset\s+seed\b", re.IGNORECASE),
        re.compile(
            r"\b(?:runiform|rnormal|rbeta|rpoisson|rbinomial|bootstrap|bsample|permute|simulate)\b",
            re.IGNORECASE,
        ),
    ),
    ".jl": (
        "Julia",
        re.compile(r"\bRandom\.seed!\s*\("),
        re.compile(r"\b(?:rand|randn|randexp|shuffle)\s*\("),
    ),
    ".m": (
        "MATLAB",
        re.compile(r"\brng\s*\("),
        re.compile(r"\b(?:rand|randn|randi|randperm|datasample)\s*\("),
    ),
    ".f90": (
        "Fortran",
        re.compile(r"\bcall\s+random_seed\s*\("),
        re.compile(r"\bcall\s+random_number\s*\("),
    ),
    ".f95": (
        "Fortran",
        re.compile(r"\bcall\s+random_seed\s*\("),
        re.compile(r"\bcall\s+random_number\s*\("),
    ),
    ".f": (
        "Fortran",
        re.compile(r"\bcall\s+random_seed\s*\("),
        re.compile(r"\bcall\s+random_number\s*\("),
    ),
    ".for": (
        "Fortran",
        re.compile(r"\bcall\s+random_seed\s*\("),
        re.compile(r"\bcall\s+random_number\s*\("),
    ),
    ".c": (
        "C",
        re.compile(r"\bsrand\s*\("),
        re.compile(r"\brand\s*\(\s*\)"),
    ),
    ".h": (
        "C",
        re.compile(r"\bsrand\s*\("),
        re.compile(r"\brand\s*\(\s*\)"),
    ),
    ".cpp": (
        "C++",
        re.compile(
            r"\b(?:std::)?(?:mt19937(?:_64)?|default_random_engine|minstd_rand|ranlux\w*)"
            r"\s+\w+\s*\([^)]*[0-9A-Za-z_][^)]*\)"
        ),
        re.compile(
            r"\brand\s*\(\s*\)"
            r"|\b(?:uniform_real_distribution|uniform_int_distribution"
            r"|normal_distribution|bernoulli_distribution)\s*<"
            r"|\b(?:Rcpp|R)::r(?:norm|unif|binom|pois|exp|gamma|beta)\s*\("
            r"|\b(?:norm_rand|unif_rand|exp_rand)\s*\(\s*\)"
        ),
    ),
    ".cc": (
        "C++",
        re.compile(
            r"\b(?:std::)?(?:mt19937(?:_64)?|default_random_engine|minstd_rand|ranlux\w*)"
            r"\s+\w+\s*\([^)]*[0-9A-Za-z_][^)]*\)"
        ),
        re.compile(
            r"\brand\s*\(\s*\)"
            r"|\b(?:uniform_real_distribution|uniform_int_distribution"
            r"|normal_distribution|bernoulli_distribution)\s*<"
            r"|\b(?:Rcpp|R)::r(?:norm|unif|binom|pois|exp|gamma|beta)\s*\("
            r"|\b(?:norm_rand|unif_rand|exp_rand)\s*\(\s*\)"
        ),
    ),
    ".cxx": (
        "C++",
        re.compile(
            r"\b(?:std::)?(?:mt19937(?:_64)?|default_random_engine|minstd_rand|ranlux\w*)"
            r"\s+\w+\s*\([^)]*[0-9A-Za-z_][^)]*\)"
        ),
        re.compile(
            r"\brand\s*\(\s*\)"
            r"|\b(?:uniform_real_distribution|uniform_int_distribution"
            r"|normal_distribution|bernoulli_distribution)\s*<"
            r"|\b(?:Rcpp|R)::r(?:norm|unif|binom|pois|exp|gamma|beta)\s*\("
            r"|\b(?:norm_rand|unif_rand|exp_rand)\s*\(\s*\)"
        ),
    ),
    ".hpp": (
        "C++",
        re.compile(
            r"\b(?:std::)?(?:mt19937(?:_64)?|default_random_engine|minstd_rand|ranlux\w*)"
            r"\s+\w+\s*\([^)]*[0-9A-Za-z_][^)]*\)"
        ),
        re.compile(
            r"\brand\s*\(\s*\)"
            r"|\b(?:uniform_real_distribution|uniform_int_distribution"
            r"|normal_distribution|bernoulli_distribution)\s*<"
            r"|\b(?:Rcpp|R)::r(?:norm|unif|binom|pois|exp|gamma|beta)\s*\("
            r"|\b(?:norm_rand|unif_rand|exp_rand)\s*\(\s*\)"
        ),
    ),
}

# A C++ engine seeded straight from entropy is deliberately non-reproducible
# — flag it the same way as "no seed at all", not as a seed.
_CPP_RANDOM_DEVICE_RE = re.compile(r"random_device")

_SCRIPT_EXTS = tuple(_RNG_PATTERNS.keys())


class RngFinding(BaseModel):
    script: Path
    line: int
    call: str
    language: str


class RngCheckResult(BaseModel):
    findings: list[RngFinding] = Field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0


def _find_all_candidate_scripts(working_copy: Path) -> list[Path]:
    paths: set[Path] = set()
    for ext in _SCRIPT_EXTS:
        paths.update(p for p in working_copy.rglob(f"*{ext}") if p.is_file())
    return sorted(paths)


def _effective_seed_line(text: str, seed_re: re.Pattern[str], suffix: str) -> Optional[int]:
    """First line with a real seed call, or None. For C++, a `random_device`-
    seeded engine doesn't count — see module docstring."""
    for i, line in enumerate(text.splitlines(), start=1):
        if seed_re.search(line):
            if suffix in (".cpp", ".cc", ".cxx", ".hpp") and _CPP_RANDOM_DEVICE_RE.search(line):
                continue
            return i
    return None


def check_rng_seeding(working_copy: Path, graph: DependencyGraph) -> RngCheckResult:
    """
    Walk scripts in `graph.script_order` (falling back to a stable sorted
    list for anything the graph didn't connect), tracking whether a seed
    call has been seen in this script or any earlier one in that order.
    Flag every stochastic call reached before a seed call is in effect.
    """
    ordered: list[Path] = []
    seen: set[Path] = set()
    for p in graph.script_order:
        abs_p = p if p.is_absolute() else working_copy / p
        if abs_p.exists() and abs_p not in seen:
            ordered.append(abs_p)
            seen.add(abs_p)
    for p in _find_all_candidate_scripts(working_copy):
        if p not in seen:
            ordered.append(p)
            seen.add(p)

    findings: list[RngFinding] = []
    seed_seen_upstream = False

    for script in ordered:
        suffix = script.suffix.lower()
        patterns = _RNG_PATTERNS.get(suffix)
        if patterns is None:
            continue
        language, seed_re, stochastic_re = patterns
        try:
            text = script.read_text(errors="replace")
        except OSError:
            continue

        seed_line = _effective_seed_line(text, seed_re, suffix)

        for i, line in enumerate(text.splitlines(), start=1):
            m = stochastic_re.search(line)
            if not m:
                continue
            locally_seeded = seed_line is not None and seed_line <= i
            if seed_seen_upstream or locally_seeded:
                continue
            try:
                rel = script.relative_to(working_copy)
            except ValueError:
                rel = script
            findings.append(
                RngFinding(script=rel, line=i, call=m.group(0), language=language)
            )

        if seed_line is not None:
            seed_seen_upstream = True

    return RngCheckResult(findings=findings)


def write_rng_warnings_file(working_copy: Path, result: RngCheckResult) -> Path:
    lines = [
        "# DeadReckoning — RNG Seeding Warnings\n\n",
        "A stochastic call (sampling, simulation, bootstrap, random draws, ...) "
        "was found with no seed call in this script or any script run before it. "
        "The run can succeed and every exhibit can land on disk with this "
        "unchanged — the numbers may still differ from a prior run.\n\n",
        "This is advisory only; the pipeline is not blocked by it.\n\n",
    ]
    for f in result.findings:
        lines.append(f"- `{f.script}:{f.line}` ({f.language}) — `{f.call}`\n")
    path = working_copy / _RNG_WARNINGS_FILE
    path.write_text("".join(lines))
    return path


def run_rng_check_step(working_copy: Path, graph: DependencyGraph) -> RngCheckResult:
    """Full RNG-CHECK step: detect, and if anything was found, write
    RNG-WARNINGS.md. Always non-blocking."""
    result = check_rng_seeding(working_copy, graph)
    if result.has_findings:
        write_rng_warnings_file(working_copy, result)
    return result
