"""Fixtures for the rendered-geometry harness (#589).

Three session fixtures, one gate and one parametrization. The build and the browser run
once per session and every geometry assertion reads the same table.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from skill_harness.sitegen.geometry import (
    REPORT_FILE_NAME,
    GeometryReport,
    measure_site,
    width_ladder,
)
from skill_harness.sitegen.render import read_stylesheet
from tests.sitegen._sites import SABOTAGE_WIDTHS, build_fixture_site, expected_page_names

#: The one environment variable that decides whether the browser runs. One mechanism and
#: nothing else, because a gate with two mechanisms is a gate somebody half-disables.
GEOMETRY_CELL_ENV = "SKILL_HARNESS_GEOMETRY_CELL"

_HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Send every test in this package to one xdist worker.

    ``xdist_group`` is a COST optimisation and never a correctness one. Each worker that
    reached the fixtures below would build its own site under its own ``tmp_path_factory``
    root, bind its own ephemeral port and launch its own browser, so nothing here is
    shared and nothing needs a lock. Grouping means one build, one Chromium and one
    measurement pass instead of up to four. Reverting it makes the suite slower and
    leaves it correct.

    The hook is declared in a directory conftest, so pytest hands it the whole session's
    items and the filter below is what keeps the marker off the other three thousand.
    """
    for item in items:
        if _HERE in item.path.parents:
            item.add_marker(pytest.mark.xdist_group("sitegen_geometry"))


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize ``page_name`` at collection time, from the receipts, not the build.

    Per PAGE and not per (page, width). One defect must produce one red line: a 7x24 grid
    reports one broken page forty times and buries the other four. The width information
    is not lost, it moves into the band and the bisected onset inside ``explain()``.

    ``build_site`` refuses an existing output directory, so the site cannot exist at
    collection time and the page list cannot come from it. ``expected_page_names`` derives
    it instead, and ``test_the_measured_page_set_is_the_built_page_set`` checks that
    derivation against a real build rather than trusting it.
    """
    if "page_name" in metafunc.fixturenames:
        metafunc.parametrize("page_name", expected_page_names())


@pytest.fixture(scope="session")
def designated_geometry_cell() -> None:
    """Skip unless this is the one cell designated to run the browser.

    Font fallback differs per platform and the measurement is only reproducible where the
    font stack is identical, so exactly one CI cell sets the variable and everywhere else
    these tests skip.

    This is the ONLY sanctioned skip in the geometry layer. On the designated cell a
    missing browser is a failure: ``BrowserNotInstalledError`` propagates out of the
    fixtures below rather than being turned into a second, quieter skip.

    A skip nobody counts is a dead control, so the count is a test of its own:
    ``tests/test_ci_geometry_cell_589.py`` reads the workflow and fails unless exactly one
    matrix cell sets this variable.
    """
    if not os.environ.get(GEOMETRY_CELL_ENV):
        pytest.skip(
            f"this is not the designated geometry cell: {GEOMETRY_CELL_ENV} is not set in "
            "this environment, so the browser measurement does not run here"
        )


@pytest.fixture(scope="session")
def geometry_report(
    tmp_path_factory: pytest.TempPathFactory, designated_geometry_cell: None
) -> GeometryReport:
    """Build the real site once, measure it once, hand the table to every test.

    The ladder is derived from the stylesheet's own breakpoints rather than written down,
    so the rungs a failure message prints are a measured thing.

    The JSON table is written beside the site because ``PageReading.explain()`` names that
    file only when it is actually there, and a CI cell can upload it.
    """
    site = build_fixture_site(tmp_path_factory.mktemp("geometry") / "site")
    report = measure_site(site, widths=width_ladder(read_stylesheet()))
    (site / REPORT_FILE_NAME).write_text(report.to_json(), encoding="utf-8", newline="\n")
    return report


@pytest.fixture(scope="session")
def sabotaged_report(
    tmp_path_factory: pytest.TempPathFactory, designated_geometry_cell: None
) -> GeometryReport:
    """The positive control's site: a second build whose ``style.css`` carries the
    cascade override.

    Three widths rather than the full ladder. It only has to prove the detector fires, so
    it does not pay for the whole matrix. Every page is measured rather than one chosen
    one, because naming a page here would pin a filename derived from a receipt, and the
    three-width pass over all of them was measured at under five seconds.
    """
    site = build_fixture_site(tmp_path_factory.mktemp("geometry-sabotaged") / "site", sabotage=True)
    return measure_site(site, widths=SABOTAGE_WIDTHS)
