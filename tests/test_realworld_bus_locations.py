"""Real-world test: BusLocations R package (Marra & Oswald).

Tests issue #12: smart R base image + system dep selection.
Key: sf + mapview + osrm → rocker/geospatial, not rocker/r-ver.
Also validates DESCRIPTION-based capture (no renv.lock present).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deadreckoning.capture import _parse_description_imports, capture_env
from deadreckoning.docker import (
    _select_r_base_image,
    _system_deps_for_packages,
    generate_dockerfile,
)
from deadreckoning.graph import build_graph
from deadreckoning.models import PinMethod

FIXTURE = Path(__file__).parent / "fixtures" / "real-world" / "bus_locations"


# ---------------------------------------------------------------------------
# Fixture sanity
# ---------------------------------------------------------------------------


def test_fixture_files_exist():
    assert (FIXTURE / "DESCRIPTION").exists()
    assert (FIXTURE / "code" / "analysis.R").exists()
    assert (FIXTURE / "paper.tex").exists()


# ---------------------------------------------------------------------------
# DESCRIPTION parsing
# ---------------------------------------------------------------------------


def test_parse_description_finds_sf():
    text = (FIXTURE / "DESCRIPTION").read_text()
    pkgs = _parse_description_imports(text)
    assert "sf" in pkgs


def test_parse_description_finds_mlogit():
    text = (FIXTURE / "DESCRIPTION").read_text()
    pkgs = _parse_description_imports(text)
    assert "mlogit" in pkgs


def test_parse_description_excludes_base_r():
    text = (FIXTURE / "DESCRIPTION").read_text()
    pkgs = _parse_description_imports(text)
    assert "R" not in pkgs
    assert "base" not in pkgs
    assert "stats" not in pkgs


def test_parse_description_no_duplicates():
    text = (FIXTURE / "DESCRIPTION").read_text()
    pkgs = _parse_description_imports(text)
    assert len(pkgs) == len(set(pkgs))


# ---------------------------------------------------------------------------
# capture_env — DESCRIPTION path
# ---------------------------------------------------------------------------


def test_capture_env_reads_description(tmp_path):
    (tmp_path / "DESCRIPTION").write_text(
        "Package: test\nImports:\n    sf,\n    ggplot2\n"
    )
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.R").write_text("library(sf)\n")
    spec = capture_env(tmp_path)
    assert spec.language == "R"
    assert any(p.name == "sf" for p in spec.packages)
    assert any(p.name == "ggplot2" for p in spec.packages)


def test_capture_env_description_confidence_above_inferred():
    spec = capture_env(FIXTURE)
    assert spec.confidence >= 0.5


def test_capture_env_description_pin_method():
    spec = capture_env(FIXTURE)
    assert spec.pin_method == PinMethod.inferred_from_date


def test_capture_env_description_has_packages():
    spec = capture_env(FIXTURE)
    assert len(spec.packages) >= 10


def test_capture_env_description_sf_in_packages():
    spec = capture_env(FIXTURE)
    names = {p.name for p in spec.packages}
    assert "sf" in names


# ---------------------------------------------------------------------------
# Base image selection
# ---------------------------------------------------------------------------


def test_select_geospatial_for_sf():
    assert "geospatial" in _select_r_base_image(["sf", "ggplot2"], "4.4.0")


def test_select_geospatial_for_terra():
    assert "geospatial" in _select_r_base_image(["terra"], "4.3.0")


def test_select_geospatial_for_mapview():
    assert "geospatial" in _select_r_base_image(["mapview", "dplyr"], "4.4.0")


def test_select_geospatial_priority_over_tidyverse():
    pkgs = ["sf", "ggplot2", "dplyr", "tidyr", "readr", "purrr"]
    assert "geospatial" in _select_r_base_image(pkgs, "4.4.0")


def test_select_stan_image():
    assert "stan" in _select_r_base_image(["rstan", "ggplot2"], "4.4.0")


def test_select_tidyverse_image():
    pkgs = ["ggplot2", "dplyr", "tidyr", "readr"]
    image = _select_r_base_image(pkgs, "4.4.0")
    assert "tidyverse" in image


def test_select_r_ver_default():
    assert _select_r_base_image(["haven", "fixest"], "4.4.0") == "rocker/r-ver:4.4.0"


def test_select_tidyverse_threshold_not_met():
    pkgs = ["ggplot2", "dplyr"]  # only 2, threshold is 3
    assert "tidyverse" not in _select_r_base_image(pkgs, "4.4.0")


def test_select_version_in_image():
    image = _select_r_base_image(["sf"], "4.3.2")
    assert "4.3.2" in image


# ---------------------------------------------------------------------------
# System dep mapping
# ---------------------------------------------------------------------------


def test_system_deps_xml2():
    deps = _system_deps_for_packages(["xml2"], "rocker/r-ver:4.4.0")
    assert "libxml2-dev" in deps


def test_system_deps_httr2():
    deps = _system_deps_for_packages(["httr2"], "rocker/r-ver:4.4.0")
    assert "libcurl4-openssl-dev" in deps
    assert "libssl-dev" in deps


def test_system_deps_sf_plain_image():
    deps = _system_deps_for_packages(["sf"], "rocker/r-ver:4.4.0")
    assert "libgdal-dev" in deps
    assert "libudunits2-dev" in deps


def test_system_deps_sf_geospatial_image_skipped():
    """rocker/geospatial already bundles GDAL etc — don't re-install."""
    deps = _system_deps_for_packages(["sf"], "rocker/geospatial:4.4.0")
    assert "libgdal-dev" not in deps


def test_system_deps_no_known_deps():
    assert _system_deps_for_packages(["haven", "fixest"], "rocker/r-ver:4.4.0") == []


def test_system_deps_sorted():
    deps = _system_deps_for_packages(["xml2", "httr2", "RPostgres"], "rocker/r-ver:4.4.0")
    assert deps == sorted(deps)


# ---------------------------------------------------------------------------
# Dockerfile generation — bus_locations fixture end-to-end
# ---------------------------------------------------------------------------


def test_dockerfile_bus_locations_uses_geospatial():
    spec = capture_env(FIXTURE)
    df = generate_dockerfile(spec)
    assert "rocker/geospatial" in df


def test_dockerfile_bus_locations_no_copy():
    spec = capture_env(FIXTURE)
    df = generate_dockerfile(spec)
    assert "COPY" not in df


def test_dockerfile_bus_locations_has_sf_in_install():
    spec = capture_env(FIXTURE)
    df = generate_dockerfile(spec)
    assert '"sf"' in df


def test_dockerfile_bus_locations_no_spatial_apt_block():
    """rocker/geospatial already has libgdal etc — no redundant apt-get block."""
    spec = capture_env(FIXTURE)
    df = generate_dockerfile(spec)
    assert "libgdal-dev" not in df


def test_dockerfile_xml2_project_has_apt_block(tmp_path):
    """Plain rocker/r-ver project with xml2 must get libxml2-dev."""
    (tmp_path / "DESCRIPTION").write_text(
        "Package: test\nImports:\n    xml2,\n    httr2\n"
    )
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.R").write_text("library(xml2)\n")
    spec = capture_env(tmp_path)
    df = generate_dockerfile(spec)
    assert "apt-get" in df
    assert "libxml2-dev" in df


def test_dockerfile_tidyverse_project(tmp_path):
    (tmp_path / "DESCRIPTION").write_text(
        "Package: test\nImports:\n    ggplot2,\n    dplyr,\n    tidyr,\n    readr\n"
    )
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.R").write_text("library(ggplot2)\n")
    spec = capture_env(tmp_path)
    df = generate_dockerfile(spec)
    assert "rocker/tidyverse" in df


# ---------------------------------------------------------------------------
# Graph — bus_locations fixture
# ---------------------------------------------------------------------------


def test_graph_bus_locations_detects_exhibits():
    g = build_graph(FIXTURE)
    assert len(g.exhibits) >= 2


def test_graph_bus_locations_detects_figure():
    g = build_graph(FIXTURE)
    paths = [str(e.tex_path) for e in g.exhibits]
    assert any("garage-map.pdf" in p for p in paths)


def test_graph_bus_locations_detects_table():
    g = build_graph(FIXTURE)
    paths = [str(e.tex_path) for e in g.exhibits]
    assert any("logit-results.tex" in p for p in paths)


def test_graph_bus_locations_no_gaps():
    """here()-wrapped ggsave/stargazer are now resolved — no exhibit should be a gap."""
    g = build_graph(FIXTURE)
    assert g.gaps == []


def test_graph_bus_locations_both_exhibits_sourced():
    """Both outputs must be linked to analysis.R via here() resolution."""
    g = build_graph(FIXTURE)
    assert len(g.sourced_exhibits) == 2


def test_graph_bus_locations_figure_sourced_from_analysis():
    g = build_graph(FIXTURE)
    fig = next(e for e in g.exhibits if "garage-map.pdf" in str(e.tex_path))
    assert fig.source is not None
    assert "analysis.R" in str(fig.source.script)


def test_graph_bus_locations_table_sourced_from_analysis():
    g = build_graph(FIXTURE)
    tbl = next(e for e in g.exhibits if "logit-results.tex" in str(e.tex_path))
    assert tbl.source is not None
    assert "analysis.R" in str(tbl.source.script)


def test_graph_bus_locations_figure_write_call_is_ggsave():
    g = build_graph(FIXTURE)
    fig = next(e for e in g.exhibits if "garage-map.pdf" in str(e.tex_path))
    assert "ggsave" in fig.source.write_call.lower()


def test_graph_bus_locations_table_write_call_is_stargazer():
    g = build_graph(FIXTURE)
    tbl = next(e for e in g.exhibits if "logit-results.tex" in str(e.tex_path))
    assert "stargazer" in tbl.source.write_call.lower()


# ---------------------------------------------------------------------------
# Scan — bus_locations fixture (here() paths, package detection)
# ---------------------------------------------------------------------------


def test_scan_bus_locations_finds_r_packages():
    from deadreckoning.scan import scan_scripts
    scan = scan_scripts(FIXTURE)
    pkg_names = set(scan.used_packages)
    assert "sf" in pkg_names
    assert "ggplot2" in pkg_names
    assert "mlogit" in pkg_names


def test_scan_bus_locations_no_dangerous_secrets():
    from deadreckoning.scan import scan_scripts
    scan = scan_scripts(FIXTURE)
    assert not scan.has_secrets


# ---------------------------------------------------------------------------
# _resolve_path_calls unit tests
# ---------------------------------------------------------------------------


def test_resolve_here_single_arg():
    from deadreckoning.graph import _resolve_path_calls
    out = _resolve_path_calls('ggsave(here("figures/fig.pdf"))')
    assert '"figures/fig.pdf"' in out


def test_resolve_here_two_args():
    from deadreckoning.graph import _resolve_path_calls
    out = _resolve_path_calls('ggsave(here("figures", "fig.pdf"))')
    assert '"figures/fig.pdf"' in out


def test_resolve_here_three_args():
    from deadreckoning.graph import _resolve_path_calls
    out = _resolve_path_calls('here("output", "tables", "t1.tex")')
    assert '"output/tables/t1.tex"' in out


def test_resolve_file_path():
    from deadreckoning.graph import _resolve_path_calls
    out = _resolve_path_calls('pdf(file.path("figures", "fig.pdf"))')
    assert '"figures/fig.pdf"' in out


def test_resolve_leaves_plain_string_unchanged():
    from deadreckoning.graph import _resolve_path_calls
    text = 'ggsave("figures/fig.pdf")'
    assert _resolve_path_calls(text) == text


def test_resolve_no_crash_on_empty():
    from deadreckoning.graph import _resolve_path_calls
    assert _resolve_path_calls("") == ""
