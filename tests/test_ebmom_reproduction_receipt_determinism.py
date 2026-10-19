"""The canonical v2 reproduction receipt carries no clock-derived field (#452).

The invariant::

    same tree + same inputs + same configuration  ->  identical canonical receipt bytes

``scripts/ebmom_form_b_reproduction.py`` already stated that invariant, as a
comment on its v1 path, twelve lines above the v2 line that broke it. A comment
is what let the regression through, so the rule is stated here as an executable
control instead.

How the control is built
------------------------
Both runs score the same regime with the same root seed and the same replicate
count, so every measured quantity is identical by construction. The only thing
that differs between them is the clock: run 1 is driven by a fake clock that
advances one second per reading, run 2 by one that advances seven. Any field
derived from wall time therefore takes a different value in the two runs, and
byte identity of the canonical payload is exactly the claim that no such field
reached the receipt.

A real clock cannot do this job. Two R=2 runs take about 3.4 seconds each and
``round(elapsed, 1)`` collides often enough that the control would pass by
coincidence rather than by construction, which is the state this test exists to
rule out.

Why the negative control is separate
------------------------------------
``test_a_reintroduced_timing_field_breaks_byte_identity`` puts a timing field
back into the assembled receipt and requires the *same* comparison to report a
difference. Without it, a green run cannot be told apart from an assertion that
can never go red -- and this defect was filed precisely because an
unenforced rule looks identical to an enforced one until something violates it.

The scale is a smoke, not a measurement. ``SMOKE_NOT_CONFIRMATORY`` at R=2 on
one regime exercises the receipt's construction, which is what the invariant is
about. Nothing here may be cited as a result about the estimator.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

ROOT_SEED = "SMOKE_NOT_CONFIRMATORY"
REGIME = "small_n_bite"
REPLICATES = 2


def _load_script(name: str) -> ModuleType:
    """Import a module from scripts/ by path.

    scripts/ carries no ``__init__.py`` and is not a package, and
    ``ebmom_form_b_reproduction`` imports ``ebmom_acceptance_matrix`` by bare
    name, so the dependency is registered in ``sys.modules`` under that bare
    name before the dependent module is executed.
    """
    path = _REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_load_script("ebmom_acceptance_matrix")
# Typed as Any deliberately: the module is loaded from a path at runtime, so a
# checker has no stub for its attributes, and the clock swap below assigns to
# one of them.
_REPRO: Any = _load_script("ebmom_form_b_reproduction")


class _FakeClock:
    """A clock whose readings advance by a fixed step, and nothing else.

    Stands in for the ``time`` module inside the script under test. It records
    its first and last reading so the negative control can re-introduce the
    exact duration the run would have reported.
    """

    def __init__(self, step: float) -> None:
        self._step = step
        self._now = 0.0
        self.first: float | None = None
        self.last = 0.0

    def time(self) -> float:
        self._now += self._step
        if self.first is None:
            self.first = self._now
        self.last = self._now
        return self._now

    def elapsed(self) -> float:
        """The duration this run's readings describe, rounded as the receipt did."""
        assert self.first is not None, "the clock was never read"
        return round(self.last - self.first, 1)


def _expected_stub(tmp_path: Path) -> Path:
    """A prototype dump that declares the run's root and R and compares no cells.

    ``run_v2_reproduction`` refuses a dump whose root seed or replicate count
    disagrees with the run. An empty ``estimators`` therefore exercises the whole
    receipt assembly while leaving the numbers to the estimator's own tests.

    Since the fail-closed fix, an absent column is RECORDED as a difference
    rather than skipped, so a receipt built from this stub reports one difference
    per column and ``port_identity_holds`` is False. That is the intended
    reading: this stub compared nothing, and the receipt now says so. The
    invariant this file is about is byte identity across two clocks, which holds
    either way because both runs see the same stub.
    """
    path = tmp_path / "proto-pb-all-R2-SMOKE_NO.json"
    path.write_text(
        json.dumps(
            {
                "root_seed": ROOT_SEED,
                "replicates": REPLICATES,
                "regimes": {REGIME: {"estimators": {}}},
            }
        ),
        encoding="utf-8",
    )
    return path


#: One generated report paired with the clock the run saw.
_Run = tuple[dict[str, object], _FakeClock]


def _run(step: float, expected_path: Path) -> _Run:
    """Generate one report, with the script's clock replaced by a fake one."""
    clock = _FakeClock(step)
    real_time = _REPRO.time
    _REPRO.time = clock
    try:
        report = _REPRO.run_v2_reproduction(
            expected_path=expected_path,
            root_seed=ROOT_SEED,
            replicates=REPLICATES,
            regimes=[REGIME],
            freeze_range=None,
        )
    finally:
        _REPRO.time = real_time
    return report, clock


def _canonical_bytes(report: dict[str, object]) -> str:
    """The exact payload the script writes to the committed receipt.

    Mirrors ``_main_v2``: split the flip detail into its sidecar, then dump with
    ``indent=2, sort_keys=True``. Taking the payload from anywhere else would
    test a serialisation the receipt does not use.
    """
    # [0] is the report; [1] is the flip sidecar, which is written to its own
    # file and is not part of the canonical receipt this invariant is about.
    stripped = _REPRO.split_flip_details(copy.deepcopy(report))[0]
    return json.dumps(stripped, indent=2, sort_keys=True)


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[_Run, _Run]:
    """Two runs of the generator differing only in their clock.

    Module-scoped: the runs cost about 3.4 seconds each and both the invariant
    and its negative control read the same pair, so running them once keeps the
    control cheap enough to stay in the default suite rather than behind a
    marker CI could deselect.
    """
    expected_path = _expected_stub(tmp_path_factory.mktemp("expected"))
    return _run(1.0, expected_path), _run(7.0, expected_path)


def test_the_two_runs_really_did_see_different_clocks(
    two_runs: tuple[_Run, _Run],
) -> None:
    """Guard: the fixture must actually vary the one variable it claims to vary.

    If both runs saw the same durations, byte identity below would hold for a
    reason that has nothing to do with the receipt's contents, and the control
    would be vacuous.
    """
    (_, first_clock), (_, second_clock) = two_runs
    assert first_clock.elapsed() != second_clock.elapsed(), (
        "the two runs reported the same duration, so this fixture cannot "
        "distinguish a receipt that excludes wall time from one that includes it"
    )


def test_canonical_receipt_bytes_are_identical_across_runs(
    two_runs: tuple[_Run, _Run],
) -> None:
    """The load-bearing control: the receipt does not move when only the clock does."""
    (first_report, _), (second_report, _) = two_runs
    first = _canonical_bytes(first_report)
    second = _canonical_bytes(second_report)
    assert first == second, (
        "the canonical receipt differs between two runs of the same tree, same "
        "inputs and same configuration. The only thing that differed was the "
        "clock, so a clock-derived field has reached the canonical payload."
    )


def _with_timing_field(report: dict[str, object], clock: _FakeClock) -> dict[str, object]:
    """Put a wall-clock duration back into every regime entry, as :635 did."""
    poisoned = copy.deepcopy(report)
    regimes = cast("dict[str, dict[str, Any]]", poisoned["regimes"])
    for entry in regimes.values():
        entry["seconds"] = clock.elapsed()
    return poisoned


def test_a_reintroduced_timing_field_breaks_byte_identity(
    two_runs: tuple[_Run, _Run],
) -> None:
    """Negative control: the comparison above must be able to go red.

    Re-introduces the field this ticket removed, through the same comparison the
    real assertion uses. A run where this passes means the invariant is being
    asserted against a payload that could never have carried the defect.
    """
    (first_report, first_clock), (second_report, second_clock) = two_runs
    first = _canonical_bytes(_with_timing_field(first_report, first_clock))
    second = _canonical_bytes(_with_timing_field(second_report, second_clock))
    assert first != second, (
        "re-introducing a wall-clock duration did NOT change the canonical "
        "payload, so the byte comparison cannot detect the defect it exists to "
        "detect"
    )


def test_the_regime_entry_carries_no_duration_key(
    two_runs: tuple[_Run, _Run],
) -> None:
    """Name the field, so a failure says what to remove rather than only that bytes moved.

    Subordinate to the byte comparison, which catches a duration under any name.
    """
    (first_report, _), _ = two_runs
    regimes = cast("dict[str, dict[str, Any]]", first_report["regimes"])
    for name, entry in regimes.items():
        assert "seconds" not in entry, (
            f"regime {name!r} carries a 'seconds' field in the canonical receipt; "
            "wall time belongs on stdout, per the v1 path's own comment"
        )


def _agreeing_pair() -> tuple[dict[str, object], dict[str, Any]]:
    """A report and a dump that agree in every cell, built from the module's own
    column, path, row and field constants rather than a hand-copied shape.

    The report keys each cell by the field name the estimator uses; the dump keys
    the same value by the field name the prototype dump uses. ``DUMP_FIELDS`` is
    the mapping between them, so reading it here keeps this fixture correct if
    either vocabulary changes.
    """
    values = {"false": 1, "decisions": 2, "G": 3, "g": 4}
    report_estimators: dict[str, dict[str, Any]] = {}
    dump_estimators: dict[str, dict[str, Any]] = {}
    for column in _REPRO.V2_COLUMNS:
        report_rows: dict[str, Any] = {}
        dump_rows: dict[str, Any] = {}
        for path in (*_REPRO.V2_PATHS, "pooled"):
            for row in _REPRO.V2_ROWS:
                label = "false_pass" if row == "5c" else "false_fail"
                name = f"row{row}_{label}_{path}"
                report_rows[name] = dict(values)
                dump_rows[name] = {
                    dump_field: values[cell_field]
                    for dump_field, cell_field in _REPRO.DUMP_FIELDS.items()
                }
        report_estimators[column] = report_rows
        dump_estimators[column] = dump_rows
    excess = {column: [0, 0] for column in _REPRO.V2_COLUMNS}
    report: dict[str, object] = {
        "estimators": report_estimators,
        "excess_over_main_vs_oracle": excess,
        "admitted": REPLICATES,
    }
    expected: dict[str, Any] = {
        "estimators": dump_estimators,
        "excess_over_main_vs_oracle": {k: list(v) for k, v in excess.items()},
        "admitted": REPLICATES,
    }
    return report, expected


def test_the_agreeing_pair_really_agrees() -> None:
    """Guard for the two controls below.

    If this fixture already reported a difference, a difference in either control
    would prove nothing about the case that control is named for.
    """
    report, expected = _agreeing_pair()
    _, differences = _REPRO.cells_against_dump(report, expected)
    assert differences == [], (
        "the fixture disagrees with its own dump, so neither control below can "
        f"attribute a difference to the thing it drops: {differences}"
    )


def test_a_dump_omitting_a_column_is_a_difference_not_agreement() -> None:
    """v2 section 9 part (a) is FROZEN and one differing cell is a port defect.

    A column the dump did not carry was skipped silently, so a dump carrying no
    columns at all produced zero differences and the caller set
    ``port_identity_holds`` True having compared nothing. The absent-ROW path has
    always reported a difference; only the column path failed open, and the one
    fixture that reaches this function carries an empty ``estimators`` map.
    """
    report, expected = _agreeing_pair()
    dropped = _REPRO.V2_COLUMNS[0]
    del expected["estimators"][dropped]

    _, differences = _REPRO.cells_against_dump(report, expected)

    assert any(line.startswith(f"{dropped}:") for line in differences), (
        f"a dump omitting column {dropped!r} reported no difference naming it, "
        "so port_identity_holds would be True over a column nobody compared: "
        f"{differences}"
    )


def test_a_dump_omitting_an_excess_is_a_difference_not_agreement() -> None:
    """The vs-oracle excess path failed open the same way as the column path."""
    report, expected = _agreeing_pair()
    dropped = _REPRO.V2_COLUMNS[-1]
    del expected["excess_over_main_vs_oracle"][dropped]

    _, differences = _REPRO.cells_against_dump(report, expected)

    assert any(line.startswith(f"{dropped}.excess_over_main_vs_oracle") for line in differences), (
        f"a dump omitting the excess for {dropped!r} reported no difference "
        f"naming it: {differences}"
    )
