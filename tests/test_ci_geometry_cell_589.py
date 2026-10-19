"""#589: the browser measurement runs on one cell, and somebody counts the skips.

``tests/sitegen/test_rendered_geometry.py`` measures a real build in Chromium. Font
fallback differs per platform, so the reading is only reproducible where the font stack
is identical, and exactly one CI cell is designated to take it. Everywhere else those
tests skip.

That arrangement has a quiet failure mode, and it is the same one #589 is about. If the
designation is misspelled, moved, or lost in a merge, every cell skips, the suite stays
green, and the measurement silently stops happening. A skip nobody counts is a dead
control. These tests are the count.

They read the real ``.github/workflows/ci.yml`` and the real ``pyproject.toml`` rather
than a copy, and each fails when the configuration it reads changes:

* exactly one cell of the Test matrix receives ``SKILL_HARNESS_GEOMETRY_CELL``, and that
  cell exists in the declared matrix rather than naming a runner that is not there;
* ``addopts`` carries ``--dist loadgroup`` and the Test cell runs under ``-n``, which is
  what sends the grouped tests to one worker instead of rebuilding the site and
  relaunching Chromium on each of them;
* the designated cell, and only it, installs the ``[geometry]`` extra and its browser.
  Without that pair the fixtures would not skip, would find no browser, and would redden
  the cell for a reason that has nothing to do with the site.

The workflow is read with regular expressions and not a YAML parser, following
``tests/test_ci_test_cell_attribution_509.py``. PyYAML is not in this repository's dev
extra or its CI constraints, and a static test is not the place to add a dependency.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.sitegen.conftest import GEOMETRY_CELL_ENV

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# A job block runs from its two-space key to the next two-space key (the #509 idiom).
_TEST_JOB_BLOCK = re.compile(r"\n  test:\n(?P<body>.*?)(?=\n  [A-Za-z_-]+:\n)", re.DOTALL)
# Steps in that block are six-space list items.
_STEP_BOUNDARY = re.compile(r"\n      - ")
_DESIGNATION = re.compile(rf"^[ \t]*{GEOMETRY_CELL_ENV}:[ \t]*(?P<value>.+?)[ \t]*$", re.MULTILINE)
_OS_LITERAL = re.compile(r"matrix\.os\s*==\s*'([^']*)'")
_PYTHON_LITERAL = re.compile(r"matrix\.python-version\s*==\s*'([^']*)'")
_PYTEST_PARALLELISM = re.compile(r"^\s*run:\s*pytest\b[^\n]*?\s-n\s+\S+", re.MULTILINE)
_DIST_LOADGROUP = re.compile(r"--dist[= ]loadgroup")

_GEOMETRY_EXTRA_INSTALL = '".[dev,geometry]"'
_BROWSER_INSTALL = "playwright install chromium"


def _ci_yml() -> str:
    return CI_YML.read_text(encoding="utf-8")


def _test_job_body() -> str:
    block = _TEST_JOB_BLOCK.search(_ci_yml())
    assert block is not None, "could not find the `test:` job in ci.yml"
    return block.group("body")


def _test_job_steps() -> list[str]:
    return _STEP_BOUNDARY.split(_test_job_body())[1:]


def _designation_value() -> str:
    """The single expression that decides which cell takes the reading.

    One assignment is the contract. Two cells running the browser would produce two
    readings of one stylesheet on two font stacks, which is the disagreement the
    designation exists to prevent, and zero would retire the measurement without saying
    so.
    """
    found = _DESIGNATION.findall(_ci_yml())
    assert len(found) == 1, (
        f"expected exactly one {GEOMETRY_CELL_ENV} assignment in ci.yml, found {len(found)}: "
        f"{found}"
    )
    return str(found[0])


def _matrix_values(key: str) -> list[str]:
    """The Test job's declared values for one matrix axis, in declaration order."""
    axis = re.search(rf"^\s*{re.escape(key)}:\s*\[(?P<items>[^\]]*)\]\s*$", _test_job_body(), re.M)
    assert axis is not None, f"the Test job declares no `{key}` matrix axis"
    return [item.strip().strip("\"'") for item in axis.group("items").split(",")]


def _designated_cells() -> list[tuple[str, str]]:
    """Every (os, python-version) cell of the Test matrix the designation switches on.

    An axis the expression does not constrain is unconstrained, so widening the
    designation from one cell to a whole row counts as the two cells it really is
    rather than passing on the strength of naming one runner.
    """
    value = _designation_value()
    operating_systems = _matrix_values("os")
    pythons = _matrix_values("python-version")
    wanted_os = set(_OS_LITERAL.findall(value)) or set(operating_systems)
    wanted_python = set(_PYTHON_LITERAL.findall(value)) or set(pythons)
    return [
        (system, python)
        for system in operating_systems
        for python in pythons
        if system in wanted_os and python in wanted_python
    ]


def _addopts() -> list[str]:
    with PYPROJECT.open("rb") as fh:
        options = tomllib.load(fh)["tool"]["pytest"]["ini_options"]
    assert "addopts" in options, "pyproject.toml [tool.pytest.ini_options] sets no addopts"
    return [str(opt) for opt in options["addopts"]]


def _steps_containing(fragment: str) -> list[str]:
    return [step for step in _test_job_steps() if fragment in step]


def test_exactly_one_matrix_cell_takes_the_browser_reading() -> None:
    """One cell is designated, and it is a cell the matrix actually produces.

    Naming a runner or an interpreter the matrix does not declare designates nothing.
    The workflow would still be valid YAML, every cell would skip, and the suite would
    stay green with the measurement gone, so the membership check is the half that
    catches a typo.
    """
    designated = _designated_cells()

    assert len(designated) == 1, (
        f"{GEOMETRY_CELL_ENV} designates {len(designated)} cells of the Test matrix, not one: "
        f"{designated}. Zero retires the browser measurement silently; more than one takes the "
        f"same reading on two font stacks."
    )


def test_the_designation_switches_the_gate_on() -> None:
    """The designated cell gets a truthy value.

    ``tests/sitegen/conftest.py`` skips on falsiness, so a designation that resolves to
    an empty string on every cell is a designation in name only.
    """
    value = _designation_value()

    assert "'1'" in value, (
        f"the {GEOMETRY_CELL_ENV} expression sets no '1' on the designated cell, and the "
        f"fixture gate reads the variable's truthiness: {value}"
    )


def test_the_grouped_tests_reach_one_worker() -> None:
    """``--dist loadgroup`` is configured, and the Test cell runs with workers to group.

    The geometry fixtures build a site and launch Chromium once per session. Under the
    default ``load`` distribution each worker that receives one of those tests repeats
    all of it. Without ``-n`` on the cell's pytest line the setting is inert, so both
    halves are read: the option that groups, and the parallelism that makes grouping
    mean anything.
    """
    joined = " ".join(_addopts())
    assert _DIST_LOADGROUP.search(joined), (
        f"addopts carries no --dist loadgroup (#589), so the geometry tests scatter across "
        f"workers and each one rebuilds the site: {joined}"
    )
    assert _PYTEST_PARALLELISM.search(_test_job_body()), (
        "the Test cell runs pytest without -n, which leaves --dist loadgroup inert"
    )


def test_only_the_designated_cell_installs_the_browser() -> None:
    """The extra and the browser are installed exactly where the reading is taken.

    Two failure directions, and the gate on each step is what separates them. Installing
    nowhere leaves the designated cell with a gate that refuses to skip and a fixture
    that finds no browser, which reddens the cell for a reason unrelated to the site.
    Installing everywhere puts a Chromium download on three cells that never use it and
    breaks the property that ``pip install -e ".[dev]"`` is browser-free.
    """
    for fragment in (_GEOMETRY_EXTRA_INSTALL, _BROWSER_INSTALL):
        steps = _steps_containing(fragment)
        assert len(steps) == 1, (
            f"expected exactly one Test-job step running {fragment}, found {len(steps)}"
        )
        assert f"if: env.{GEOMETRY_CELL_ENV} ==" in steps[0], (
            f"the step running {fragment} is not gated on {GEOMETRY_CELL_ENV}, so every cell "
            f"pays for it:\n{steps[0]}"
        )


def test_the_geometry_extra_is_declared_and_dev_stays_browser_free() -> None:
    """``[geometry]`` carries playwright, and ``[dev]`` carries none of it.

    The extra is the whole gate on the browser reaching a contributor's environment. If
    playwright were ever folded into ``[dev]``, every cell and every `pip install -e
    ".[dev]"` would pull it, the designation above would still read as one cell, and
    nothing else in the suite would notice.
    """
    with PYPROJECT.open("rb") as fh:
        extras = tomllib.load(fh)["project"]["optional-dependencies"]

    assert "geometry" in extras, "pyproject.toml declares no [geometry] extra (#589)"
    geometry = " ".join(extras["geometry"])
    assert "playwright" in geometry, f"the [geometry] extra names no playwright: {geometry}"

    dev = " ".join(extras["dev"])
    assert "playwright" not in dev, (
        f'the dev extra names playwright, so `pip install -e ".[dev]"` is no longer '
        f"browser-free: {dev}"
    )
