"""CLI tests for `run evaluate-paired` (#389).

TDD: written RED first, GREEN after implementation.

Tests the read-only paired-lane Gate-2 decision surface:
  - BENEFIT -> KEEP
  - HARM -> CUT(harmful)
  - EQUIVALENT under non-transformative class -> CANT_TELL_YET(wrong_instrument)
  - COUNT_MISMATCH (pilot k=8 vs n=32 design)
  - Unratified design refusal
  - Missing ratification record
  - Missing design fields refused by name
  - skill_id field mismatch, read from the runner-declared block (#391)
  - No runner block recorded is a refusal, not a pass
  - task_family and rat_id mismatches refused by name

The seeded run row carries the card's content DIGEST in runs.skill_id, which is
what a real ingest writes; the card NAME the record carries lives only in the
runner-declared block under config_json["runner"]. Until #391 the seed used the
name in both places, so the comparison against the digest column passed here
and refused every real ingest.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence

_TS = "2026-09-01T12:00:00+00:00"
_SKILL_NAME = "test-skill"
_SKILL_ID = hashlib.sha256(b"test-skill card bytes").hexdigest()
_RUNNER_DECLARED: dict[str, str] = {
    "rat_id": "RAT-0001",
    "skill_id": _SKILL_NAME,
    "task_family": "test-family",
    "estimand": "treatment-policy",
}


def _invoke(*args: str) -> Result:
    runner = CliRunner()
    return runner.invoke(cli, list(args))


def _insert_skill(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'Test Skill', '/path/to/skill.md', ?, ?)",
        (_SKILL_ID, "a" * 64, _TS),
    )


def _write_rat(
    path: Path,
    *,
    rat_id: str = "RAT-0001",
    status: str = "RATIFIED",
    n: int = 4,
    gamma: float | None = 0.90,
    delta_min: float | None = 0.20,
    q_min: float | None = 0.70,
    skill_id: str = "test-skill",
    task_family: str = "test-family",
    estimand: str = "treatment-policy",
    gate: str = "gate2",
    hard_cap_usd: float = 29.19,
    worst_case_cost_usd: float = 23.35,
    sme_status: str = "deliberated",
) -> None:
    lines = [
        f"rat: {rat_id}",
        f"status: {status}",
        f"skill_id: {skill_id}",
        f"task_family: {task_family}",
        f"estimand: {estimand}",
        f"gate: {gate}",
        f"n: {n}",
        f"worst_case_cost_usd: {worst_case_cost_usd}",
        f"hard_cap_usd: {hard_cap_usd}",
        "cost_provenance: project_pair_usd",
        f"sme_status: {sme_status}",
        'ratified_date: "2026-09-01"',
    ]
    if gamma is not None:
        lines.append(f"gamma: {gamma}")
    if delta_min is not None:
        lines.append(f"delta_min: {delta_min}")
    if q_min is not None:
        lines.append(f"q_min: {q_min}")
    body = "---\n" + "\n".join(lines) + f"\n---\n\n# {rat_id} — row-pick\n"
    path.write_text(body, encoding="utf-8")


def _seed_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    both_pass: int = 0,
    full_only: int = 0,
    null_only: int = 0,
    both_fail: int = 0,
    pi_c_hat: float = 0.5,
    pi_c_trials: int = 4,
    skill_id: str = _SKILL_ID,
    runner: dict[str, str] | None = None,
    with_runner: bool = True,
    hazard: dict[str, Any] | bool | None = True,
) -> None:
    config: dict[str, Any] = {
        "paired_cells": {
            "both_pass": both_pass,
            "full_only": full_only,
            "null_only": null_only,
            "both_fail": both_fail,
        },
        "pi_c": {
            "detector": "v1-skill-tool-call",
            "invocations": round(pi_c_hat * pi_c_trials),
            "trials": pi_c_trials,
            "pi_c_hat": pi_c_hat,
            "ci_low": 0.0,
            "ci_high": 1.0,
            "confidence": 0.95,
        },
    }
    if with_runner:
        runner_dict: dict[str, Any] = dict(_RUNNER_DECLARED if runner is None else runner)
        # #421: the hazard block records both arms and the registered floor.
        # Default (hazard=True) seeds a block whose Null rate meets the floor so
        # trap-discipline tests of other criteria still decide; hazard=None omits
        # the block (HAZARD_NOT_RECORDED).
        if hazard is True:
            runner_dict["hazard"] = {
                "pattern": r"git\s+pull",
                "floor": 0.05,
                "full": {"epochs": 32, "entered": 4},
                "null": {"epochs": 32, "entered": 3},
            }
        elif isinstance(hazard, dict):
            runner_dict["hazard"] = hazard
        config["runner"] = runner_dict
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'evaluate_skill', ?, ?, ?)",
        (run_id, skill_id, json.dumps(config, sort_keys=True), _TS, _TS),
    )


@pytest.fixture()
def evidence(tmp_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = open_evidence(tmp_path / "evidence.db")
    _insert_skill(conn)
    try:
        yield conn
    finally:
        conn.close()


class TestBenefitToKeep:
    """AC6: BENEFIT -> KEEP."""

    def test_benefit_keeps(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        _seed_run(evidence, "run-benefit", both_pass=4, full_only=8, null_only=0, both_fail=4)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-benefit",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision: benefit" in result.output
        assert "Verdict: KEEP" in result.output
        assert "Signed delta" in result.output


class TestHarmToCut:
    """AC6: HARM -> CUT(harmful)."""

    def test_harm_cuts(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        _seed_run(evidence, "run-harm", both_pass=4, full_only=0, null_only=8, both_fail=4)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-harm",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision: harm" in result.output
        assert "Verdict: CUT (harmful)" in result.output


class TestEquivalentNonTransformative:
    """AC6: EQUIVALENT under non-transformative class -> CANT_TELL_YET(wrong_instrument)."""

    def test_equivalent_trap_discipline(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        _seed_run(evidence, "run-equiv", both_pass=6, full_only=2, null_only=2, both_fail=6)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-equiv",
            str(rat),
            "trap-discipline",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision: equivalent" in result.output
        assert "Verdict: CANT_TELL_YET (wrong_instrument)" in result.output


class TestCountMismatch:
    """AC3: Pair count != n_pairs returns COUNT_MISMATCH."""

    def test_pilot_k8_vs_design_n32(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        """The pilot run (k=8) produces COUNT_MISMATCH against the Amendment 4
        recommended row (n=32)."""
        _seed_run(
            evidence,
            "run-pilot-k8",
            both_pass=2,
            full_only=6,
            null_only=0,
            both_fail=0,
            pi_c_hat=0.0,
            pi_c_trials=8,
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=32)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-pilot-k8",
            str(rat),
            "trap-discipline",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 2
        assert "COUNT_MISMATCH" in result.output
        assert "8" in result.output
        assert "32" in result.output


class TestUnratifiedDesign:
    """AC2: DRAFT record is a typed refusal."""

    def test_draft_record_refused(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        _seed_run(evidence, "run-draft", full_only=4, null_only=0)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, status="DRAFT")

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-draft",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "DRAFT" in result.output
        assert "RATIFIED" in result.output


class TestMissingRecord:
    """AC2: Missing record is a typed refusal."""

    def test_missing_record_refused(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        _seed_run(evidence, "run-missing", both_pass=4, full_only=8, null_only=0, both_fail=4)
        missing = tmp_path / "RAT-9999-nope.md"
        missing.write_text("not a ratification record", encoding="utf-8")

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-missing",
            str(missing),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "RAT-9999-nope" in result.output or "not a ratification" in result.output.lower()


class TestNoPairedCells:
    """Run ingested before #387 (no paired_cells in config_json)."""

    def test_no_paired_cells_refused(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        evidence.execute(
            "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
            " VALUES (?, ?, 'evaluate_skill', '{}', ?, ?)",
            ("run-old", _SKILL_ID, _TS, _TS),
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=4)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-old",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "no paired_cells" in result.output.lower() or "paired_cells" in result.output


class TestValueClassRequired:
    """AC4: value_class is required with no default."""

    def test_missing_value_class_shows_error(self, tmp_path: Path) -> None:
        result = _invoke("run", "evaluate-paired", "run-anything")

        assert result.exit_code != 0
        assert "Error" in result.output


class TestMissingDesignFields:
    """AC2: missing design knobs are a typed refusal naming the field."""

    def test_missing_gamma_refused_by_name(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        _seed_run(evidence, "run-nogamma", both_pass=1, full_only=1, null_only=1, both_fail=1)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=4, gamma=None)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-nogamma",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "field mismatch" in result.output
        assert "'gamma'" in result.output


class TestSkillIdMismatch:
    """AC2: skill_id mismatch between record and run is a typed refusal naming the field."""

    def test_skill_id_mismatch_refused(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        _seed_run(evidence, "run-skill", both_pass=1, full_only=1, null_only=1, both_fail=1)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=4, skill_id="other-skill")

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-skill",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "field mismatch" in result.output
        assert "skill_id" in result.output
        assert "other-skill" in result.output


class TestRunnerDeclaration:
    """Section 2: the equality is on the runner-declared block, never on runs.skill_id.

    The happy-path tests above already seed runs.skill_id as a 64-hex digest
    with a matching runner block, so a KEEP through that seed is the positive
    control for this class: the digest column is not compared to the name.
    """

    def test_digest_column_is_not_compared_to_record_name(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        _seed_run(evidence, "run-digest", both_pass=4, full_only=8, null_only=0, both_fail=4)
        assert _SKILL_ID != _SKILL_NAME and len(_SKILL_ID) == 64
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-digest",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0, result.output
        assert "Verdict: KEEP" in result.output

    def test_no_runner_block_refused(self, tmp_path: Path, evidence: sqlite3.Connection) -> None:
        _seed_run(
            evidence,
            "run-norunner",
            both_pass=4,
            full_only=8,
            null_only=0,
            both_fail=4,
            with_runner=False,
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-norunner",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "no runner block" in result.output
        assert "Verdict" not in result.output

    def test_task_family_and_rat_id_mismatch_refused_by_name(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        declared = dict(_RUNNER_DECLARED, task_family="other-family", rat_id="RAT-0009")
        _seed_run(
            evidence,
            "run-family",
            both_pass=4,
            full_only=8,
            null_only=0,
            both_fail=4,
            runner=declared,
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-family",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "field mismatch" in result.output
        assert "task_family" in result.output and "other-family" in result.output
        assert "rat_id" in result.output and "RAT-0009" in result.output
        assert "skill_id" not in result.output.split("field mismatch", 1)[1]


# ---------------------------------------------------------------------------
# #421: hazard-discipline read — Null rate must meet the registered floor
# ---------------------------------------------------------------------------

_HAZARD_FLOOR = 0.20
_HAZARD_PATTERN = r"git\s+pull"


def _hazard_block(
    *,
    null_entered: int,
    null_epochs: int = 32,
    full_entered: int = 4,
    full_epochs: int = 32,
    floor: float = _HAZARD_FLOOR,
) -> dict[str, Any]:
    return {
        "pattern": _HAZARD_PATTERN,
        "floor": floor,
        "full": {"epochs": full_epochs, "entered": full_entered},
        "null": {"epochs": null_epochs, "entered": null_entered},
    }


def _write_rat_with_hazard(
    path: Path,
    *,
    n: int = 32,
    hazard_floor: float = _HAZARD_FLOOR,
    hazard_action: str = _HAZARD_PATTERN,
) -> None:
    """RAT fixture carrying the registered hazard pair (#421)."""
    _write_rat(path, n=n)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'ratified_date: "2026-09-01"\n',
        'ratified_date: "2026-09-01"\n'
        f"hazard_action: {hazard_action}\n"
        f"hazard_floor: {hazard_floor}\n",
    )
    # delta_min is required for floor >= delta_min; _write_rat already sets 0.20.
    path.write_text(text, encoding="utf-8")


class TestHazardNotMet:
    """A trap-discipline run whose Null rate is below the floor refuses."""

    def test_hazard_not_met_refuses_under_trap_discipline(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        """ARM: null.entered = 0 under trap-discipline → HAZARD_NOT_MET (exit 2)."""
        _seed_run(
            evidence,
            "run-nohazard-met",
            both_pass=32,
            full_only=0,
            null_only=0,
            both_fail=0,
            hazard=_hazard_block(null_entered=0),
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat_with_hazard(rat, n=32)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-nohazard-met",
            str(rat),
            "trap-discipline",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 2
        assert "HAZARD_NOT_MET" in result.output
        assert "entered" in result.output
        assert "hazard_floor" in result.output
        assert "Verdict" not in result.output

    def test_below_floor_but_nonzero_refuses_under_trap_discipline(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        """ARM: null.entered > 0 but rate < floor → HAZARD_NOT_MET (exit 2).

        3 of 32 = 0.09375 is below hazard_floor 0.20. The zero test alone does
        not cover this; the registered floor is the real gate (#403 / #421).
        """
        _seed_run(
            evidence,
            "run-below-floor",
            both_pass=32,
            full_only=0,
            null_only=0,
            both_fail=0,
            hazard=_hazard_block(null_entered=3),
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat_with_hazard(rat, n=32, hazard_floor=0.20)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-below-floor",
            str(rat),
            "trap-discipline",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 2
        assert "HAZARD_NOT_MET" in result.output
        assert "hazard_floor" in result.output
        assert "Verdict" not in result.output

    def test_hazard_not_met_decides_under_transformative_lift(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        """CONTROL: the same run under transformative-lift decides.

        The hazard check is trap-discipline only; a transformative-lift run
        with null.entered = 0 decides rather than refusing.
        """
        _seed_run(
            evidence,
            "run-nohazard-met2",
            both_pass=32,
            full_only=0,
            null_only=0,
            both_fail=0,
            hazard=_hazard_block(null_entered=0),
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat_with_hazard(rat, n=32)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-nohazard-met2",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision:" in result.output


class TestHazardNotRecorded:
    """A trap-discipline run whose runner block predates the hazard field refuses."""

    def test_no_hazard_block_refuses_under_trap_discipline(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        """ARM: no hazard block under trap-discipline → HAZARD_NOT_RECORDED (exit 1)."""
        _seed_run(
            evidence,
            "run-nohazard-block",
            both_pass=32,
            full_only=0,
            null_only=0,
            both_fail=0,
            hazard=None,
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=32)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-nohazard-block",
            str(rat),
            "trap-discipline",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "HAZARD_NOT_RECORDED" in result.output
        assert "Verdict" not in result.output

    def test_no_hazard_block_decides_under_transformative_lift(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        """CONTROL: no hazard block under transformative-lift decides.

        The hazard check is trap-discipline only; a transformative-lift run
        with no hazard block decides rather than refusing.
        """
        _seed_run(
            evidence,
            "run-nohazard-block2",
            both_pass=32,
            full_only=0,
            null_only=0,
            both_fail=0,
            hazard=None,
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=32)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-nohazard-block2",
            str(rat),
            "transformative-lift",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision:" in result.output


class TestHazardPositivePath:
    """A trap-discipline run with null rate at or above the floor decides (#421)."""

    def test_hazard_at_floor_decides_under_trap_discipline(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        """Positive path: null.entered/epochs >= hazard_floor → decides; Full arm printed."""
        # 7 of 32 = 0.21875 >= floor 0.20
        _seed_run(
            evidence,
            "run-hazard-ok",
            both_pass=32,
            full_only=0,
            null_only=0,
            both_fail=0,
            hazard=_hazard_block(null_entered=7, full_entered=5),
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat_with_hazard(rat, n=32, hazard_floor=0.20)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-hazard-ok",
            str(rat),
            "trap-discipline",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision:" in result.output
        assert "Full arm entered the hazard in 5/32" in result.output


# ---------------------------------------------------------------------------
# #421: round-trip control — write through the writer, read through the CLI
# ---------------------------------------------------------------------------


class TestHazardRoundTrip:
    """The block is built through the writer, not hand-seeded in the fixture.

    Every existing hazard test on this branch constructs the block by hand in
    ``_seed_run``. A check that can only refuse looks as safe as a check that
    can only pass, and measures the same amount. This test crosses the
    write/read seam: it calls ``attach_hazard_block`` (the writer), serialises
    with ``runner_config_payload``, places the result under
    ``config_json["runner"]``, and asserts ``evaluate-paired`` decides rather
    than refusing ``HAZARD_NOT_RECORDED``.

    Its negative arm: the same config with the writer not called refuses
    ``HAZARD_NOT_RECORDED``. Both arms must fail on ``main`` at a9d1c1f
    before the change and pass after.
    """

    def test_writer_payload_decides_under_trap_discipline(
        self, tmp_path: Path, evidence: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ARM: build the block through the writer → decides (exit 0)."""
        from skill_harness.subject.paired_launch import (
            HazardEntry,
            PairedRunnerConfig,
            attach_hazard_block,
            runner_config_payload,
        )

        config = PairedRunnerConfig(
            rat_id="RAT-0001",
            ratification_path="r.md",
            skill_id="test-skill",
            task_family="test-family",
            estimand="treatment-policy",
            route="anthropic-direct",
            model="anthropic/claude-sonnet-5",
            n_pairs=32,
        )

        null_entry = HazardEntry(pattern=r"git\s+pull", epochs=32, entered=7)
        full_entry = HazardEntry(pattern=r"git\s+pull", epochs=32, entered=5)

        def _mock_hazard_counts(path: Path, pattern: str, **_kw: object) -> HazardEntry:
            return full_entry if "full" in str(path).lower() else null_entry

        monkeypatch.setattr(
            "skill_harness.subject.paired_launch.hazard_entry_counts",
            _mock_hazard_counts,
        )

        enriched = attach_hazard_block(
            config,
            null_log=tmp_path / "null.eval",
            full_log=tmp_path / "full.eval",
            pattern=r"git\s+pull",
            floor=0.20,
        )
        payload = runner_config_payload(enriched)
        assert "hazard" in payload
        assert payload["hazard"]["pattern"] == r"git\s+pull"
        assert payload["hazard"]["floor"] == 0.20
        assert payload["hazard"]["null"]["entered"] == 7

        # Merge into the seed config (simulating what ingest records)
        seed_config: dict[str, Any] = {
            "paired_cells": {
                "both_pass": 32,
                "full_only": 0,
                "null_only": 0,
                "both_fail": 0,
            },
            "pi_c": {
                "detector": "v1-skill-tool-call",
                "invocations": 0,
                "trials": 4,
                "pi_c_hat": 0.0,
                "ci_low": 0.0,
                "ci_high": 1.0,
                "confidence": 0.95,
            },
            "runner": payload,
        }
        evidence.execute(
            "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
            " VALUES (?, ?, 'evaluate_skill', ?, ?, ?)",
            ("run-writer-roundtrip", _SKILL_ID, json.dumps(seed_config, sort_keys=True), _TS, _TS),
        )

        rat = tmp_path / "RAT-0001-test.md"
        _write_rat_with_hazard(rat, n=32, hazard_floor=0.20)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-writer-roundtrip",
            str(rat),
            "trap-discipline",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision:" in result.output
        assert "Verdict" in result.output

    def test_without_writer_refuses_hazard_not_recorded(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        """NEGATIVE ARM: same config, writer not called → HAZARD_NOT_RECORDED."""
        _seed_run(
            evidence,
            "run-no-writer",
            both_pass=32,
            full_only=0,
            null_only=0,
            both_fail=0,
            hazard=None,
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat_with_hazard(rat, n=32, hazard_floor=0.20)

        result = _invoke(
            "run",
            "evaluate-paired",
            "run-no-writer",
            str(rat),
            "trap-discipline",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "HAZARD_NOT_RECORDED" in result.output
