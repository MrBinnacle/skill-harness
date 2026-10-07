"""Mutation-killing tests for audit/ (#166)."""

from __future__ import annotations

import sqlite3

from skill_harness.audit import (
    audit_all_verdicts,
    get_verdict_by_id,
    list_verdicts_for_clause,
    select_verdicts_by_admissibility,
)
from skill_harness.storage.models import OracleVerdictWrite
from skill_harness.storage.repositories.evidence import clauses as clauses_repo
from skill_harness.storage.repositories.evidence import metric_versions as mv_repo
from skill_harness.storage.repositories.evidence import oracle_verdicts as verdicts_repo
from skill_harness.storage.repositories.evidence import runs as runs_repo
from skill_harness.storage.repositories.evidence import samples as samples_repo
from skill_harness.storage.repositories.evidence import skills as skills_repo
from tests.test_repo_roundtrip import (
    _make_clause,
    _make_metric_version,
    _make_run,
    _make_sample,
    _make_skill,
)

_TS = "2026-06-04T12:00:00.000Z"


def _setup(conn: sqlite3.Connection) -> None:
    skills_repo.insert_skill(conn, _make_skill())
    clauses_repo.insert_clause(conn, _make_clause())
    mv_repo.insert_metric_version(conn, _make_metric_version())
    runs_repo.insert_run(conn, _make_run())
    samples_repo.insert_sample(conn, _make_sample("s1", sample_index=0))
    samples_repo.insert_sample(conn, _make_sample("s2", sample_index=1))


def _verdict(
    verdict_id: str,
    *,
    clause_id: str = "clause-1",
    admissibility_state: str = "admissible",
    written_at: str = _TS,
) -> OracleVerdictWrite:
    return OracleVerdictWrite(
        verdict_id=verdict_id,
        run_id="run-1",
        clause_id=clause_id,
        axis="citation_support",
        comparison="full_vs_ablated",
        sample_a_id="s1",
        sample_b_id="s2",
        observation=1.0,
        oracle_tier=1,
        metric_id="hedge_index",
        metric_version="1.0.0",
        judge_id=None,
        calibration_event_id=None,
        position_swap_agreement=None,
        admissibility_state=admissibility_state,
        inadmissibility_reason=None,
        written_at=written_at,
    )


class TestAuditMutationContracts:
    def test_audit_all_verdicts_run_filter_order_and_fields(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        _setup(evidence_db)
        verdicts_repo.insert_oracle_verdict(
            evidence_db, _verdict("v2", written_at="2026-06-05T00:00:00.000Z")
        )
        verdicts_repo.insert_oracle_verdict(
            evidence_db, _verdict("v1", written_at="2026-06-04T00:00:00.000Z")
        )
        rows = audit_all_verdicts(evidence_db, "run-1")
        assert [r["verdict_id"] for r in rows] == ["v1", "v2"]
        assert rows[0]["observation"] == 1.0
        assert rows[0]["admissibility_state"] == "admissible"
        assert rows[0]["clause_id"] == "clause-1"
        assert audit_all_verdicts(evidence_db, "no-such-run") == []

    def test_get_verdict_by_id_hit_and_miss(self, evidence_db: sqlite3.Connection) -> None:
        _setup(evidence_db)
        assert get_verdict_by_id(evidence_db, "missing") is None
        verdicts_repo.insert_oracle_verdict(evidence_db, _verdict("vx"))
        row = get_verdict_by_id(evidence_db, "vx")
        assert row is not None
        assert row["verdict_id"] == "vx"
        assert row["run_id"] == "run-1"
        assert row["observation"] == 1.0

    def test_list_for_clause_and_select_admissibility(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        _setup(evidence_db)
        clauses_repo.insert_clause(
            evidence_db, _make_clause(clause_id="clause-2").model_copy(update={"clause_index": 1})
        )
        verdicts_repo.insert_oracle_verdict(evidence_db, _verdict("a1"))
        verdicts_repo.insert_oracle_verdict(
            evidence_db, _verdict("i1", admissibility_state="inadmissible")
        )
        verdicts_repo.insert_oracle_verdict(evidence_db, _verdict("a2", clause_id="clause-2"))
        clause_rows = list_verdicts_for_clause(evidence_db, "clause-1")
        assert {r["verdict_id"] for r in clause_rows} == {"a1", "i1"}
        adm = select_verdicts_by_admissibility(evidence_db, "admissible")
        assert {r["verdict_id"] for r in adm} == {"a1", "a2"}
        assert all(r["admissibility_state"] == "admissible" for r in adm)
        assert select_verdicts_by_admissibility(evidence_db, "nope") == []
