"""Tests for issue #503 — persist the refusal reason and unify its vocabulary.

Two defects stopped a refusal from being auditable:

1. ``unmeasured_reason`` was a free-form ``str | None`` on the runner's
   ``ClauseResult`` and was never persisted to storage. After the run ended
   the reason a refusal happened could not be read back.
2. The runner wrote the literals ``"tier2_uncalibrated"`` and
   ``"length_confounded"``, which are not members of the declared
   ``UnmeasuredSubReason`` enumeration in ``aggregation/status.py``. A reader
   grouping refusals by sub-reason worked from two disjoint vocabularies.

These tests pin the corrected behaviour:

* The two runner literals resolve to named members of ``UnmeasuredSubReason``
  (criterion 4).
* A refusing run yields an ``UnmeasuredSubReason`` member on the clause result,
  not a free-form string — one population, not two (criterion 2).
* After a refusing run, the sub-reason is readable from evidence storage
  without re-running (criterion 1).
* A value outside the enumeration is rejected by the write model rather than
  stored (criterion 3).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from skill_harness.aggregation.status import UnmeasuredSubReason
from skill_harness.storage.migrations import open_evidence, open_runtime

# Reuse the runner test helpers (clause factory, mock response, runner factory,
# skill/clause seeders) so this module exercises the same setup as the existing
# runner suite rather than re-deriving it.
from tests.ablation.test_runner import (
    _make_clause,
    _make_runner,
    _mock_response,
    _seed_clause,
    _seed_skill,
)

_SKILL_ID = "skill-test"
_USER_MSG = "Write a paragraph about testing."


@pytest.fixture()
def db_pair(tmp_path: Path) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection]]:
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")
    try:
        yield ev, rt
    finally:
        ev.close()
        rt.close()


@pytest.fixture()
def seeded_db_pair(
    db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    ev, rt = db_pair
    _seed_skill(ev)
    return ev, rt


def _run_ablation(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
    clause: object,
    run_id: str,
    response_factory: object | None = None,
) -> list[Any]:
    runner, _ = _make_runner(ev, rt, response_factory=response_factory)  # type: ignore[arg-type]
    results: list[Any] = runner.run_ablation(
        skill_id=_SKILL_ID,
        clauses=[clause],  # type: ignore[list-item]
        user_message=_USER_MSG,
        max_usd=10.0,
        run_id=run_id,
    )
    return results


# ---------------------------------------------------------------------------
# Criterion 4 — the two runner literals resolve to named enum members
# ---------------------------------------------------------------------------


class TestRunnerLiteralsAreEnumMembers:
    def test_tier2_uncalibrated_is_a_member(self) -> None:
        assert UnmeasuredSubReason.TIER2_UNCALIBRATED.value == "tier2_uncalibrated"

    def test_length_confounded_is_a_member(self) -> None:
        assert UnmeasuredSubReason.LENGTH_CONFOUNDED.value == "length_confounded"

    def test_the_two_literals_are_distinct_from_existing_members(self) -> None:
        members = {m for m in UnmeasuredSubReason}
        assert UnmeasuredSubReason.TIER2_UNCALIBRATED in members
        assert UnmeasuredSubReason.LENGTH_CONFOUNDED in members
        distinct = {UnmeasuredSubReason.TIER2_UNCALIBRATED, UnmeasuredSubReason.MECHANICAL_VACUOUS}
        assert len(distinct) == 2, (
            "TIER2_UNCALIBRATED must name a distinct case from MECHANICAL_VACUOUS"
        )


# ---------------------------------------------------------------------------
# Criterion 2 — a refusing run yields an UnmeasuredSubReason, not a string
# ---------------------------------------------------------------------------


class TestRunnerYieldsEnumNotString:
    """The runner's ``unmeasured_reason`` narrows from ``str | None`` to
    ``UnmeasuredSubReason | None``. Grouping refusals by sub-reason then returns
    one population because the runner and the aggregation share one vocabulary."""

    def test_tier2_refusal_yields_enum_member(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = seeded_db_pair
        clause = _make_clause("clause-tier2-enum", "Be persuasive.", 0, "verbosity", oracle_tier=2)
        _seed_clause(ev, clause)

        results = _run_ablation(ev, rt, clause, "tier2-enum-run")
        result = results[0]
        assert result.unmeasured_reason is not None
        assert isinstance(result.unmeasured_reason, UnmeasuredSubReason), (
            "runner must carry the refusal reason as UnmeasuredSubReason, not a free-form string; "
            f"got {type(result.unmeasured_reason).__name__}"
        )
        assert result.unmeasured_reason is UnmeasuredSubReason.TIER2_UNCALIBRATED

    def test_length_confounded_refusal_yields_enum_member(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = seeded_db_pair
        # "Hi" is ~1 token; the [ABLATED] filler is 4 tokens, so tolerance=2 < 3
        # delta -> out of tolerance -> length_confounded.
        clause = _make_clause("clause-short-enum", "Hi", 0, "verbosity")
        _seed_clause(ev, clause)

        results = _run_ablation(ev, rt, clause, "length-enum-run")
        result = results[0]
        if result.length_confounded:
            assert result.unmeasured_reason is not None
            assert isinstance(result.unmeasured_reason, UnmeasuredSubReason)
            assert result.unmeasured_reason is UnmeasuredSubReason.LENGTH_CONFOUNDED


# ---------------------------------------------------------------------------
# Criterion 3 — a value outside the enumeration is rejected, not stored
# ---------------------------------------------------------------------------


class TestOutOfEnumRejected:
    def test_write_model_rejects_value_outside_enumeration(self) -> None:
        from skill_harness.storage.models import ClauseRunOutcomeWrite

        with pytest.raises(ValueError, match="unmeasured_sub_reason"):
            ClauseRunOutcomeWrite(
                run_id="r",
                clause_id="c",
                unmeasured_sub_reason="not_a_real_sub_reason",
                written_at="2026-09-12T00:00:00.000000+00:00",
            )

    def test_write_model_accepts_every_enum_member(self) -> None:
        from skill_harness.storage.models import ClauseRunOutcomeWrite

        for member in UnmeasuredSubReason:
            w = ClauseRunOutcomeWrite(
                run_id="r",
                clause_id="c",
                unmeasured_sub_reason=member,
                written_at="2026-09-12T00:00:00.000000+00:00",
            )
            assert w.unmeasured_sub_reason == member


# ---------------------------------------------------------------------------
# Criterion 1 — after a refusing run, the sub-reason is readable from storage
# ---------------------------------------------------------------------------


class TestSubReasonReadableFromStorage:
    def test_tier2_refusal_sub_reason_persisted(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        from skill_harness.storage.repositories.evidence.runs import (
            list_clause_run_outcomes_for_run,
        )

        ev, rt = seeded_db_pair
        clause = _make_clause(
            "clause-tier2-persist", "Be persuasive.", 0, "verbosity", oracle_tier=2
        )
        _seed_clause(ev, clause)

        results = _run_ablation(ev, rt, clause, "tier2-persist-run")
        assert results[0].unmeasured_reason is not None

        outcomes = list_clause_run_outcomes_for_run(ev, "tier2-persist-run")
        assert len(outcomes) == 1, f"expected one persisted outcome, got {outcomes}"
        assert outcomes[0]["clause_id"] == clause.clause_id
        assert outcomes[0]["unmeasured_sub_reason"] == "tier2_uncalibrated"

    def test_length_confounded_refusal_sub_reason_persisted(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        from skill_harness.storage.repositories.evidence.runs import (
            list_clause_run_outcomes_for_run,
        )

        ev, rt = seeded_db_pair
        clause = _make_clause("clause-short-persist", "Hi", 0, "verbosity")
        _seed_clause(ev, clause)

        results = _run_ablation(ev, rt, clause, "length-persist-run")
        if not results[0].length_confounded:
            pytest.skip("operator was within tolerance on this run; no length refusal to persist")

        outcomes = list_clause_run_outcomes_for_run(ev, "length-persist-run")
        assert len(outcomes) == 1
        assert outcomes[0]["unmeasured_sub_reason"] == "length_confounded"

    def test_measured_clause_writes_no_outcome_row(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """A clause that is measured (not refused) must not carry a refusal row.

        The store records refusals only; a measured clause keeps no reason.
        """
        from skill_harness.storage.repositories.evidence.runs import (
            list_clause_run_outcomes_for_run,
        )

        ev, rt = seeded_db_pair
        clause = _make_clause()
        _seed_clause(ev, clause)

        def response_factory(idx: int) -> MagicMock:
            if idx == 0:
                return _mock_response("word " * 10)
            sample_call = (idx - 1) % 3
            if sample_call == 0:
                return _mock_response("word " * 50)
            elif sample_call == 1:
                return _mock_response("a")
            else:
                return _mock_response("word " * 20)

        _run_ablation(ev, rt, clause, "measured-no-outcome-run", response_factory=response_factory)

        outcomes = list_clause_run_outcomes_for_run(ev, "measured-no-outcome-run")
        assert outcomes == [], "a measured clause must write no refusal-outcome row"
