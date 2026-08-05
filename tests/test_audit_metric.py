"""Tests for the `audit-metric` act (A-double-prime audited-metric lane).

Design provenance: the S88 audited-metric design council record (private
research notes; operator-ratified A-double-prime, conditions K1-K8). The act
pre-registers an audited=1 metric_versions row BEFORE a store's first ingest
(pre-register-before-ingest — Branch A), so ingest's existence guard
short-circuits and freeze/currency can label frozen cases 'current'.

Semantics (K3): audited=1 attests "a deliberate operator act registered this
metric implementation, hash-pinned against the shipped module at execution
time" — an operator-attested, hash-pinned registration, NOT independent
construct-validity review. The act REQUIRES a non-empty operator-typed
--attest string, echoed in both dry-run and execute output.

Red tests (council record tests 1-6 plus TEST-ARCH additions A-D), proven RED
before implementation:
  1. audit-metric --execute on a fresh store writes the audited=1 row; the
     current_metric_versions VIEW is non-empty afterwards.
  2. Refusal on an existing audited=0 row (the r3 store shape) — the message
     names the fresh-store re-ingest recovery path.
  3. Refusal on a metric_id not registered in PAIRED_FREEZE_BINARY_METRIC_IDS.
  4. Dry-run writes nothing (read-only open, I4 least-privilege like freeze).
  5. End-to-end: pre-register → ingest (guard skips, pre-registered row
     untouched) → freeze → currency_state='current' → Rule 6 KEEP path
     unblocked (fixture-level; bolts the guard-skip front onto the
     TestR3ShapedKeepEndToEnd tail proven in test_freeze_verdict_paired.py).
  6. Hash-drift refusal: existing audited=1 row whose hash does not match the
     live module → refuse loudly.
  A. Hash-alignment (K1 guard, highest priority): the act-registered hash
     byte-equals the hash write_paired_evidence would write — both pin
     skill_harness/subject/ingest.py via the SAME imported function.
  B. Idempotence: re-run after success → "already audited", exit 0, no
     second row (hash-MATCH arm).
  C. Dry-run on an unbootstrapped (absent) DB → exit 1, nothing created.
  D. K2 ingest fail-closed re-check: when ingest's guard finds an existing
     (metric_id, version) row whose hash does not match the live module,
     ingest REFUSES with a message naming the remedy.

Socket discipline mirrors tests/oracles/tier1/conftest.py: an autouse
module-local fixture wraps every test with pytest-socket's socket_disabled.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from skill_harness.aggregation.status import (
    ClauseStatus,
    ClauseStatusInput,
    derive_clause_status,
)
from skill_harness.aggregation.verdict import KeepCutVerdict, paired_verdict
from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence, open_evidence_readonly
from skill_harness.storage.repositories.evidence.frozen_cases import freeze_verdict
from skill_harness.storage.repositories.evidence.metric_versions import (
    plan_audited_metric_registration,
    register_audited_metric,
)
from skill_harness.subject import ingest as ingest_module
from skill_harness.subject.ingest import (
    ORACLE_METRIC_VERSION,
    MetricImplementationDriftError,
    ParsedEvalLog,
    ParsedSample,
    write_paired_evidence,
)

_BINARY_METRIC = "subject:file_contains"
_TS = "2026-07-27T10:00:00.000Z"
_WRONG_HASH = "e" * 64
_ATTEST = "reviewed file_contains scorer mapping against PRD section 12.1 evidence"

PIN_FP = "a" * 64
PIN_JSON = json.dumps({"model": "openrouter/anthropic/claude-haiku-4.5"}, sort_keys=True)


@pytest.fixture(autouse=True)
def _no_network(socket_disabled: None) -> None:
    """Offline discipline — mirrors tests/oracles/tier1/conftest.py."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke(*args: str) -> Any:
    runner = CliRunner()
    return runner.invoke(cli, list(args), env={"COLUMNS": "200"})


def _live_hash() -> str:
    """The tamper-evidence pin the act must register (K1: ingest.py's bytes)."""
    return hashlib.sha256(Path(ingest_module.__file__).read_bytes()).hexdigest()


def _seed_metric_row(
    conn: sqlite3.Connection,
    *,
    audited: int,
    implementation_hash: str,
    metric_id: str = _BINARY_METRIC,
) -> None:
    conn.execute(
        "INSERT INTO metric_versions (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at) VALUES (?, ?, ?, 1, ?, 1, ?)",
        (metric_id, ORACLE_METRIC_VERSION, implementation_hash, audited, _TS),
    )
    conn.commit()


def _metric_rows(db: Path) -> list[tuple[Any, ...]]:
    conn = open_evidence_readonly(db)
    try:
        return conn.execute(
            "SELECT metric_id, version, implementation_hash, tier, audited,"
            " mechanical_validity_test_passed, registered_at FROM metric_versions"
        ).fetchall()
    finally:
        conn.close()


def make_sample(
    condition: str,
    epoch: int,
    score: float,
    *,
    scorer_name: str = "file_contains",
) -> ParsedSample:
    return ParsedSample(
        condition=condition,  # type: ignore[arg-type]
        skill_name="some-skill",
        epoch=epoch,
        scorer_name=scorer_name,
        score_value=score,
        invoked_skill=condition == "full",
        output_text=f"output-{condition}-{epoch}",
        subject_model="openrouter/anthropic/claude-haiku-4.5",
        harness_pin_json=PIN_JSON,
        harness_pin_fingerprint=PIN_FP,
        input_tokens=100,
        cache_read_input_tokens=50,
        cache_creation_input_tokens=25,
        output_tokens=10,
        usd=None,
    )


def make_log(condition: str, samples: tuple[ParsedSample, ...]) -> ParsedEvalLog:
    return ParsedEvalLog(
        task_name=f"some-skill-{condition}",
        task_id=f"task-{condition}",
        created="2026-07-27T10:00:00+00:00",
        status="success",
        samples=samples,
    )


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    d = tmp_path / "some-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: some-skill\n---\nbody\n", encoding="utf-8")
    return d


@pytest.fixture
def evidence_path(tmp_path: Path) -> Path:
    return tmp_path / "evidence.db"


# ---------------------------------------------------------------------------
# Red test 1 — fresh-store registration via CLI --execute
# ---------------------------------------------------------------------------


class TestFreshStoreRegistration:
    def test_execute_writes_audited_row(self, evidence_path: Path) -> None:
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
            "--execute",
        )
        assert result.exit_code == 0, result.output
        rows = _metric_rows(evidence_path)
        assert len(rows) == 1
        metric_id, version, impl_hash, tier, audited, mvtp, registered_at = rows[0]
        assert metric_id == _BINARY_METRIC
        assert version == ORACLE_METRIC_VERSION
        assert impl_hash == _live_hash()
        assert (tier, audited, mvtp) == (1, 1, 1)
        # K6: ms resolution matching ingest's _utcnow_iso (e.g. ...T10:00:00.123Z)
        assert registered_at.endswith("Z")
        assert len(registered_at.rsplit(".", 1)[-1]) == 4  # 'mmmZ'

    def test_execute_makes_currency_view_nonempty(self, evidence_path: Path) -> None:
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
            "--execute",
        )
        assert result.exit_code == 0, result.output
        conn = open_evidence_readonly(evidence_path)
        try:
            row = conn.execute(
                "SELECT version, implementation_hash FROM current_metric_versions"
                " WHERE metric_id = ?",
                (_BINARY_METRIC,),
            ).fetchone()
        finally:
            conn.close()
        assert row == (ORACLE_METRIC_VERSION, _live_hash())

    def test_execute_echoes_attestation(self, evidence_path: Path) -> None:
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
            "--execute",
        )
        assert result.exit_code == 0, result.output
        assert _ATTEST in result.output


# ---------------------------------------------------------------------------
# Red test 2 — refusal on existing audited=0 row (the r3 store shape)
# ---------------------------------------------------------------------------


class TestExistingUnauditedRowRefused:
    def test_refuses_and_names_fresh_store_recovery(self, evidence_path: Path) -> None:
        conn = open_evidence(evidence_path)
        try:
            _seed_metric_row(conn, audited=0, implementation_hash=_live_hash())
        finally:
            conn.close()
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
            "--execute",
        )
        assert result.exit_code == 1, result.output
        assert "fresh store" in result.output
        # nothing written, no in-place flip (append-only holds)
        rows = _metric_rows(evidence_path)
        assert len(rows) == 1
        assert rows[0][4] == 0  # audited still 0


# ---------------------------------------------------------------------------
# Red test 3 — refusal on non-registered metric_id
# ---------------------------------------------------------------------------


class TestUnregisteredMetricRefused:
    def test_refuses_unknown_metric_id(self, evidence_path: Path) -> None:
        result = _invoke(
            "audit-metric",
            "subject:not_a_registered_metric",
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
            "--execute",
        )
        assert result.exit_code == 1, result.output
        assert "subject:file_contains" in result.output  # names the allowed set
        assert not evidence_path.exists()  # refused before any store creation

    def test_repo_fn_refuses_unknown_metric_id(self, evidence_db: sqlite3.Connection) -> None:
        with pytest.raises(ValueError, match="not registered"):
            register_audited_metric(evidence_db, "subject:not_a_registered_metric")


# ---------------------------------------------------------------------------
# Red test 4 — dry-run writes nothing (I4 least-privilege)
# ---------------------------------------------------------------------------


class TestDryRunWritesNothing:
    def test_dry_run_leaves_store_empty(self, evidence_path: Path) -> None:
        conn = open_evidence(evidence_path)
        conn.close()
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
        )
        assert result.exit_code == 0, result.output
        assert "DRY-RUN" in result.output
        assert _live_hash() in result.output  # full would-be row incl. hash
        assert _ATTEST in result.output  # K3: echoed in dry-run too
        assert _metric_rows(evidence_path) == []


# ---------------------------------------------------------------------------
# Red test 5 — end-to-end: pre-register → ingest guard-skip → freeze →
#              currency 'current' → Rule 6 KEEP path unblocked
# ---------------------------------------------------------------------------


class TestPreRegisterThenIngestKeepEndToEnd:
    def _paired_r3_shape(self) -> tuple[ParsedEvalLog, ParsedEvalLog]:
        full = make_log("full", tuple(make_sample("full", epoch, 1.0) for epoch in range(8)))
        null = make_log("null", tuple(make_sample("null", epoch, 0.0) for epoch in range(8)))
        return full, null

    def test_guard_skips_and_keep_reachable(
        self, evidence_db: sqlite3.Connection, skill_dir: Path
    ) -> None:
        registered = register_audited_metric(evidence_db, _BINARY_METRIC)
        pre_row = evidence_db.execute(
            "SELECT metric_id, version, implementation_hash, tier, audited,"
            " mechanical_validity_test_passed, registered_at FROM metric_versions"
        ).fetchall()
        assert len(pre_row) == 1
        assert registered["audited"] == 1

        full, null = self._paired_r3_shape()
        result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=evidence_db)
        assert result.admissibility_state == "admissible"
        assert len(result.verdict_ids) == 8

        # guard skipped: the pre-registered row is byte-untouched and still unique
        post_row = evidence_db.execute(
            "SELECT metric_id, version, implementation_hash, tier, audited,"
            " mechanical_validity_test_passed, registered_at FROM metric_versions"
        ).fetchall()
        assert post_row == pre_row

        freeze_verdict(evidence_db, result.verdict_ids[0], oracle_source="mechanical")
        current = evidence_db.execute(
            "SELECT COUNT(*) FROM frozen_cases_with_currency"
            " WHERE clause_id = ? AND axis = 'outcome' AND currency_state = 'current'",
            (result.clause_id,),
        ).fetchone()[0]
        assert current >= 1

        # Rule 6 tail (r3 measured posterior: Full 8/8 vs Null 0/8, p_win 0.9899)
        status, sub = derive_clause_status(
            ClauseStatusInput(
                axis="verbosity",
                admissible_verdict_count=8,
                total_verdict_count=8,
                confounded_verdict_count=0,
                n_verdicts=8,
                p_win_gt_threshold=0.9899,
                current_frozen_case_count=int(current),
                any_stale_frozen_case=False,
            )
        )
        assert status is ClauseStatus.PASSED
        assert sub is None
        assert paired_verdict(status).verdict is KeepCutVerdict.KEEP


# ---------------------------------------------------------------------------
# Red test 6 — hash-drift refusal on existing audited row
# ---------------------------------------------------------------------------


class TestAuditedHashDriftRefused:
    def test_cli_refuses_drifted_audited_row(self, evidence_path: Path) -> None:
        conn = open_evidence(evidence_path)
        try:
            _seed_metric_row(conn, audited=1, implementation_hash=_WRONG_HASH)
        finally:
            conn.close()
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
            "--execute",
        )
        assert result.exit_code == 1, result.output
        assert "drift" in result.output.lower()

    def test_repo_fn_refuses_drifted_audited_row(self, evidence_db: sqlite3.Connection) -> None:
        _seed_metric_row(evidence_db, audited=1, implementation_hash=_WRONG_HASH)
        with pytest.raises(ValueError, match="drift"):
            register_audited_metric(evidence_db, _BINARY_METRIC)


# ---------------------------------------------------------------------------
# Red test A — hash-alignment (K1 guard, highest priority)
# ---------------------------------------------------------------------------


class TestHashAlignment:
    def test_act_hash_byte_equals_ingest_pin(self, evidence_db: sqlite3.Connection) -> None:
        """The act must pin ingest.py itself — a lift of the hash function to
        another module would repoint Path(__file__) and break this test."""
        row = register_audited_metric(evidence_db, _BINARY_METRIC)
        assert row["implementation_hash"] == _live_hash()

    def test_act_hash_equals_what_ingest_would_write(self, tmp_path: Path, skill_dir: Path) -> None:
        """Byte-equality with write_paired_evidence's own registration."""
        act_conn = open_evidence(tmp_path / "act.db")
        try:
            act_hash = register_audited_metric(act_conn, _BINARY_METRIC)["implementation_hash"]
        finally:
            act_conn.close()

        ingest_conn = open_evidence(tmp_path / "ingest.db")
        try:
            write_paired_evidence(
                full=make_log("full", (make_sample("full", 0, 1.0),)),
                null=make_log("null", (make_sample("null", 0, 0.0),)),
                skill_dir=skill_dir,
                conn=ingest_conn,
            )
            ingest_hash = ingest_conn.execute(
                "SELECT implementation_hash FROM metric_versions WHERE metric_id = ?",
                (_BINARY_METRIC,),
            ).fetchone()[0]
        finally:
            ingest_conn.close()
        assert act_hash == ingest_hash


# ---------------------------------------------------------------------------
# Red test B — idempotence (hash-MATCH arm → exit 0, no second row)
# ---------------------------------------------------------------------------


class TestIdempotentRerun:
    def test_second_execute_exits_zero_already_audited(self, evidence_path: Path) -> None:
        first = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
            "--execute",
        )
        assert first.exit_code == 0, first.output
        second = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
            "--execute",
        )
        assert second.exit_code == 0, second.output
        assert "already audited" in second.output
        assert len(_metric_rows(evidence_path)) == 1

    def test_repo_fn_already_audited_is_not_an_error(self, evidence_db: sqlite3.Connection) -> None:
        register_audited_metric(evidence_db, _BINARY_METRIC)
        plan = plan_audited_metric_registration(evidence_db, _BINARY_METRIC)
        assert plan.action == "already_audited"


# ---------------------------------------------------------------------------
# Red test C — dry-run on unbootstrapped DB → exit 1, nothing created
# ---------------------------------------------------------------------------


class TestDryRunUnbootstrappedDb:
    def test_exit_1_and_no_file_created(self, evidence_path: Path) -> None:
        assert not evidence_path.exists()
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            _ATTEST,
            "--evidence-db",
            str(evidence_path),
        )
        assert result.exit_code == 1, result.output
        assert "Cannot open evidence DB" in result.output
        assert not evidence_path.exists()


# ---------------------------------------------------------------------------
# K3 — attestation string is required and non-empty (dry-run AND execute)
# ---------------------------------------------------------------------------


class TestAttestationRequired:
    @pytest.mark.parametrize("extra", [(), ("--execute",)])
    def test_missing_attest_refused(self, evidence_path: Path, extra: tuple[str, ...]) -> None:
        conn = open_evidence(evidence_path)
        conn.close()
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--evidence-db",
            str(evidence_path),
            *extra,
        )
        assert result.exit_code == 1, result.output
        assert "--attest" in result.output
        assert _metric_rows(evidence_path) == []

    @pytest.mark.parametrize("extra", [(), ("--execute",)])
    def test_blank_attest_refused(self, evidence_path: Path, extra: tuple[str, ...]) -> None:
        conn = open_evidence(evidence_path)
        conn.close()
        result = _invoke(
            "audit-metric",
            _BINARY_METRIC,
            "--attest",
            "   ",
            "--evidence-db",
            str(evidence_path),
            *extra,
        )
        assert result.exit_code == 1, result.output
        assert "--attest" in result.output
        assert _metric_rows(evidence_path) == []


# ---------------------------------------------------------------------------
# Red test D — K2: ingest's fail-closed hash re-check on the guard-hit path
# ---------------------------------------------------------------------------


class TestIngestHashRecheck:
    def test_ingest_refuses_when_existing_row_hash_drifted(
        self, evidence_db: sqlite3.Connection, skill_dir: Path
    ) -> None:
        """Module drifted AFTER the row was registered → later ingest must
        refuse fail-closed instead of silently minting verdicts under a hash
        that no longer matches the scoring code (ATTACK-1, condition K2)."""
        _seed_metric_row(evidence_db, audited=1, implementation_hash=_WRONG_HASH)
        with pytest.raises(MetricImplementationDriftError, match="ORACLE_METRIC_VERSION"):
            write_paired_evidence(
                full=make_log("full", (make_sample("full", 0, 1.0),)),
                null=make_log("null", (make_sample("null", 0, 0.0),)),
                skill_dir=skill_dir,
                conn=evidence_db,
            )
        # fail-closed: the aborted ingest wrote nothing
        assert evidence_db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert evidence_db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0

    def test_ingest_refusal_applies_to_unaudited_rows_too(
        self, evidence_db: sqlite3.Connection, skill_dir: Path
    ) -> None:
        """K2 closes the hole for every future store, not only audited ones."""
        _seed_metric_row(evidence_db, audited=0, implementation_hash=_WRONG_HASH)
        with pytest.raises(MetricImplementationDriftError):
            write_paired_evidence(
                full=make_log("full", (make_sample("full", 0, 1.0),)),
                null=make_log("null", (make_sample("null", 0, 0.0),)),
                skill_dir=skill_dir,
                conn=evidence_db,
            )
