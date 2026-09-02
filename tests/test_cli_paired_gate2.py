"""CLI tests for `run evaluate-paired` (#389).

TDD: written RED first, GREEN after implementation.

Tests the read-only paired-lane Gate-2 decision surface:
  - BENEFIT -> KEEP
  - HARM -> CUT(harmful)
  - EQUIVALENT under non-transformative class -> CANT_TELL_YET(wrong_instrument)
  - COUNT_MISMATCH (pilot k=8 vs n=32 design)
  - Unratified design refusal
  - Missing ratification record
  - DRAFT ratification record
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence

_TS = "2026-09-01T12:00:00+00:00"
_SKILL_ID = "test-skill"


def _invoke(*args: str) -> object:
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
    gamma: float = 0.90,
    delta_min: float = 0.20,
    q_min: float = 0.70,
    skill_id: str = "test-skill",
    task_family: str = "test-family",
    estimand: str = "treatment-policy",
    gate: str = "gate2",
    hard_cap_usd: float = 29.19,
    worst_case_cost_usd: float = 23.35,
    sme_status: str = "deliberated",
) -> None:
    path.write_text(
        f"""---
rat: {rat_id}
status: {status}
skill_id: {skill_id}
task_family: {task_family}
estimand: {estimand}
gate: {gate}
n: {n}
worst_case_cost_usd: {worst_case_cost_usd}
hard_cap_usd: {hard_cap_usd}
cost_provenance: project_pair_usd
sme_status: {sme_status}
ratified_date: "2026-09-01"
gamma: {gamma}
delta_min: {delta_min}
q_min: {q_min}
---

# {rat_id} — row-pick
""",
        encoding="utf-8",
    )


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
) -> None:
    config = {
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
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, 'test-skill', 'evaluate_skill', ?, ?, ?)",
        (run_id, json.dumps(config, sort_keys=True), _TS, _TS),
    )


@pytest.fixture()
def evidence(tmp_path: Path) -> sqlite3.Connection:
    conn = open_evidence(tmp_path / "evidence.db")
    _insert_skill(conn)
    try:
        yield conn
    finally:
        conn.close()


class TestBenefitToKeep:
    """AC6: BENEFIT -> KEEP."""

    def test_benefit_keeps(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        _seed_run(evidence, "run-benefit", both_pass=4, full_only=8, null_only=0, both_fail=4)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run", "evaluate-paired", "run-benefit", str(rat), "transformative-lift",
            "--evidence-db", str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision: benefit" in result.output
        assert "Verdict: KEEP" in result.output
        assert "Signed delta" in result.output


class TestHarmToCut:
    """AC6: HARM -> CUT(harmful)."""

    def test_harm_cuts(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        _seed_run(evidence, "run-harm", both_pass=4, full_only=0, null_only=8, both_fail=4)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run", "evaluate-paired", "run-harm", str(rat), "transformative-lift",
            "--evidence-db", str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision: harm" in result.output
        assert "CUT" in result.output
        assert "harmful" in result.output


class TestEquivalentNonTransformative:
    """AC6: EQUIVALENT under non-transformative class -> CANT_TELL_YET(wrong_instrument)."""

    def test_equivalent_trap_discipline(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        _seed_run(evidence, "run-equiv", both_pass=6, full_only=2, null_only=2, both_fail=6)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=16)

        result = _invoke(
            "run", "evaluate-paired", "run-equiv", str(rat), "trap-discipline",
            "--evidence-db", str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 0
        assert "Decision: equivalent" in result.output
        assert "CANT_TELL_YET" in result.output
        output_lower = result.output.lower()
        assert "wrong_instrument" in output_lower or "wrong instrument" in output_lower


class TestCountMismatch:
    """AC3: Pair count != n_pairs returns COUNT_MISMATCH."""

    def test_pilot_k8_vs_design_n32(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
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
            "run", "evaluate-paired", "run-pilot-k8", str(rat), "trap-discipline",
            "--evidence-db", str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 2
        assert "COUNT_MISMATCH" in result.output
        assert "8" in result.output
        assert "32" in result.output


class TestUnratifiedDesign:
    """AC2: DRAFT record is a typed refusal."""

    def test_draft_record_refused(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        _seed_run(evidence, "run-draft", full_only=4, null_only=0)
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, status="DRAFT")

        result = _invoke(
            "run", "evaluate-paired", "run-draft", str(rat), "transformative-lift",
            "--evidence-db", str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "DRAFT" in result.output
        assert "RATIFIED" in result.output


class TestMissingRecord:
    """AC2: Missing record is a typed refusal."""

    def test_missing_record_refused(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        _seed_run(evidence, "run-missing", both_pass=4, full_only=8, null_only=0, both_fail=4)
        missing = tmp_path / "RAT-9999-nope.md"
        missing.write_text("not a ratification record", encoding="utf-8")

        result = _invoke(
            "run", "evaluate-paired", "run-missing", str(missing), "transformative-lift",
            "--evidence-db", str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "RAT-9999-nope" in result.output or "not a ratification" in result.output.lower()


class TestNoPairedCells:
    """Run ingested before #387 (no paired_cells in config_json)."""

    def test_no_paired_cells_refused(
        self, tmp_path: Path, evidence: sqlite3.Connection
    ) -> None:
        evidence.execute(
            "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
            " VALUES (?, 'test-skill', 'evaluate_skill', '{}', ?, ?)",
            ("run-old", _TS, _TS),
        )
        rat = tmp_path / "RAT-0001-test.md"
        _write_rat(rat, n=4)

        result = _invoke(
            "run", "evaluate-paired", "run-old", str(rat), "transformative-lift",
            "--evidence-db", str(tmp_path / "evidence.db"),
        )

        assert result.exit_code == 1
        assert "no paired_cells" in result.output.lower() or "paired_cells" in result.output


class TestValueClassRequired:
    """AC4: value_class is required with no default."""

    def test_missing_value_class_shows_error(self, tmp_path: Path) -> None:
        result = _invoke("run", "evaluate-paired", "run-anything")

        assert result.exit_code != 0
        assert "Error" in result.output
