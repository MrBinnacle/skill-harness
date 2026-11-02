"""`run ablation --resume` runs the plan frozen in runs.config_json (#886).

Every test drives the real command, the real runner and real SQLite stores. Only
the SDK client under the subject adapter is faked, and a run is interrupted by
making that client raise, so a resume always continues a run the runner started.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner, Result

from skill_harness.ablation.runner import AblationRunner, RunConfig
from skill_harness.ablation.subject import SubjectClient
from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence, open_runtime
from skill_harness.storage.models import (
    ClauseWrite,
    RunProgressWrite,
    RunWrite,
    SampleWrite,
    SkillWrite,
)
from skill_harness.storage.repositories.evidence.clauses import insert_clause
from skill_harness.storage.repositories.evidence.runs import insert_run
from skill_harness.storage.repositories.evidence.samples import insert_sample
from skill_harness.storage.repositories.evidence.skills import insert_skill
from skill_harness.storage.repositories.runtime.run_progress import insert_run_progress
from skill_harness.storage.transaction import writer_transaction

_TS = "2026-11-01T00:00:00.000000+00:00"
_SKILL_A = "skill-a"
_SKILL_B = "skill-b"
_CLAUSE_A1 = "clause-a1"
_CLAUSE_A2 = "clause-a2"
_CLAUSE_B1 = "clause-b1"
_RAT_ID = "RAT-0009"
_FROZEN_MODEL = "gpt-5.5"
_CLI_DEFAULT_MODEL = "claude-sonnet-4-6"

_RECORD = """---
rat: {rat}
status: RATIFIED
skill_id: {skill_id}
task_family: fixture
estimand: treatment-policy
gate: gate2
n: 20
worst_case_cost_usd: 5.00
hard_cap_usd: 5.00
cost_provenance: project_pair_usd
sme_status: deliberated
ratified_date: "2026-09-05"
gamma: 0.90
delta_min: 0.20
q_min: 0.70
---

# {rat} - resume fixture
"""


class _Store:
    """A scratch evidence and runtime store with two skills seeded."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.evidence = root / "evidence.db"
        self.runtime = root / "runtime.db"
        self.factory_models: list[str] = []
        self.calls_until_crash: int | None = None
        ev = open_evidence(self.evidence)
        try:
            with writer_transaction(ev):
                for skill_id in (_SKILL_A, _SKILL_B):
                    insert_skill(
                        ev,
                        SkillWrite(
                            skill_id=skill_id,
                            name=skill_id,
                            source_path=f"/{skill_id}.md",
                            source_sha256="a" * 64,
                            imported_at=_TS,
                        ),
                    )
                for clause_id, skill_id, index in (
                    (_CLAUSE_A1, _SKILL_A, 0),
                    (_CLAUSE_A2, _SKILL_A, 1),
                    (_CLAUSE_B1, _SKILL_B, 0),
                ):
                    insert_clause(
                        ev,
                        ClauseWrite(
                            clause_id=clause_id,
                            skill_id=skill_id,
                            clause_index=index,
                            rendering_index=index,
                            clause_text=f"Always begin clause {clause_id} with 'Certainly!'.",
                            axis="verbosity",
                            comparator="increase",
                            oracle_tier=1,
                            vacuity_flag="none",
                            falsifying_case_schema_sha256=None,
                            created_at=_TS,
                        ),
                    )
        finally:
            ev.close()
        open_runtime(self.runtime).close()

    def record(self, skill_id: str = _SKILL_A) -> Path:
        path = self.root / f"{_RAT_ID}-{skill_id}.md"
        path.write_text(_RECORD.format(rat=_RAT_ID, skill_id=skill_id), encoding="utf-8")
        return path

    def make_client(self, model: str) -> SubjectClient:
        self.factory_models.append(model)
        sdk = MagicMock()

        def create(**_: Any) -> MagicMock:
            if self.calls_until_crash is not None:
                if self.calls_until_crash == 0:
                    raise RuntimeError("injected crash")
                self.calls_until_crash -= 1
            response = MagicMock()
            response.content = [MagicMock(text="word " * 12)]
            response.model = model
            response.stop_reason = "end_turn"
            response.usage = MagicMock(
                input_tokens=100,
                output_tokens=20,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            return response

        sdk.messages.create.side_effect = create
        return SubjectClient(client=sdk, model=model)

    def invoke(
        self,
        skill_id: str,
        *extra: str,
        record: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> Result:
        merged_env = {
            "COLUMNS": "400",
            "ANTHROPIC_API_KEY": "sk-test",
            "OPENAI_API_KEY": "sk-test",
            "OPENROUTER_API_KEY": "",
            **(env or {}),
        }
        with patch("skill_harness.ablation.subject.make_subject_client", self.make_client):
            return CliRunner().invoke(
                cli,
                [
                    "run",
                    "ablation",
                    skill_id,
                    "--evidence-db",
                    str(self.evidence),
                    "--runtime-db",
                    str(self.runtime),
                    "--execute",
                    "--ratification",
                    str(record if record is not None else self.record(skill_id)),
                    "--task-family",
                    "fixture",
                    "--estimand",
                    "treatment-policy",
                    "--max-usd",
                    "5.00",
                    *extra,
                ],
                env=merged_env,
            )

    def start_and_crash(self, *extra: str, record: Path | None = None) -> str:
        """Start a run of skill A under gpt-5.5 and crash it after one comparison."""
        self.calls_until_crash = 4  # warmup, then Full, Ablated and Null of one comparison
        result = self.invoke(
            _SKILL_A, "--subject-model", _FROZEN_MODEL, *extra, record=record or self.record()
        )
        self.calls_until_crash = None
        assert isinstance(result.exception, RuntimeError), result.output
        run_id = self.scalar("SELECT run_id FROM runs")
        assert isinstance(run_id, str)
        assert self.sampled_models(run_id) == {_FROZEN_MODEL}
        return run_id

    def scalar(self, sql: str, *params: Any) -> Any:
        ev = open_evidence(self.evidence)
        try:
            row = ev.execute(sql, params).fetchone()
            return row[0] if row is not None else None
        finally:
            ev.close()

    def sampled_models(self, run_id: str) -> set[str]:
        return self._column("SELECT DISTINCT subject_model FROM samples WHERE run_id = ?", run_id)

    def sampled_clauses(self, run_id: str) -> set[str]:
        return self._column("SELECT DISTINCT clause_id FROM samples WHERE run_id = ?", run_id)

    def sample_count(self, run_id: str) -> int:
        count = self.scalar("SELECT COUNT(*) FROM samples WHERE run_id = ?", run_id)
        assert isinstance(count, int)
        return count

    def completed_at(self, run_id: str) -> str | None:
        value = self.scalar("SELECT completed_at FROM runs WHERE run_id = ?", run_id)
        assert value is None or isinstance(value, str)
        return value

    def config(self, run_id: str) -> RunConfig:
        return RunConfig.from_json(
            self.scalar("SELECT config_json FROM runs WHERE run_id = ?", run_id)
        )

    def _column(self, sql: str, run_id: str) -> set[str]:
        ev = open_evidence(self.evidence)
        try:
            return {row[0] for row in ev.execute(sql, (run_id,)).fetchall()}
        finally:
            ev.close()


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[_Store]:
    yield _Store(tmp_path)


def _assert_refused_before_spend(store: _Store, result: Result, run_id: str, phrase: str) -> None:
    assert result.exit_code == 1, result.output
    assert phrase in result.output, result.output
    assert store.completed_at(run_id) is None


class TestFreshRun:
    def test_records_the_model_it_sampled(self, store: _Store) -> None:
        run_id = store.start_and_crash()
        assert store.config(run_id).subject_model == _FROZEN_MODEL


class TestResumeKeepsTheModel:
    def test_resume_without_the_flag_samples_the_frozen_model(self, store: _Store) -> None:
        run_id = store.start_and_crash()
        before = store.sample_count(run_id)

        result = store.invoke(_SKILL_A, "--resume", run_id)

        assert result.exit_code in (0, 2), result.output
        assert store.sample_count(run_id) > before
        assert store.sampled_models(run_id) == {_FROZEN_MODEL}
        assert store.factory_models[-1] == _FROZEN_MODEL

    def test_resume_ignores_a_different_flag(self, store: _Store) -> None:
        run_id = store.start_and_crash()

        result = store.invoke(_SKILL_A, "--subject-model", _CLI_DEFAULT_MODEL, "--resume", run_id)

        assert result.exit_code in (0, 2), result.output
        assert store.sampled_models(run_id) == {_FROZEN_MODEL}

    def test_cost_backfill_names_the_frozen_model(self, store: _Store) -> None:
        run_id = store.start_and_crash()

        with patch.object(AblationRunner, "_write_cost_ledger"):
            result = store.invoke(_SKILL_A, "--resume", run_id)

        assert result.exit_code in (0, 2), result.output
        rt = open_runtime(store.runtime)
        try:
            models = {
                row[0]
                for row in rt.execute(
                    "SELECT model_id FROM cost_ledger WHERE run_id = ?", (run_id,)
                ).fetchall()
            }
        finally:
            rt.close()
        assert models == {_FROZEN_MODEL}

    def test_refuses_when_resolving_would_rewrite_the_route(self, store: _Store) -> None:
        run_id = store.start_and_crash()
        before = store.sample_count(run_id)

        result = store.invoke(
            _SKILL_A,
            "--resume",
            run_id,
            env={"OPENAI_API_KEY": "", "OPENROUTER_API_KEY": "sk-test"},
        )

        _assert_refused_before_spend(store, result, run_id, "would route")
        assert store.sample_count(run_id) == before

    def test_refuses_when_stored_samples_disagree_with_the_recorded_model(
        self, store: _Store
    ) -> None:
        """A run from before this fix recorded the default and sampled the flag's model."""
        run_id = "run-wrong-record"
        ev = open_evidence(store.evidence)
        try:
            with writer_transaction(ev):
                insert_run(
                    ev,
                    RunWrite(
                        run_id=run_id,
                        skill_id=_SKILL_A,
                        run_kind="ablation",
                        config_json=RunConfig(
                            run_id=run_id,
                            skill_id=_SKILL_A,
                            clauses=[{"clause_id": _CLAUSE_A1}],
                            subject_model=_CLI_DEFAULT_MODEL,
                            user_message="m",
                        ).to_json(),
                        started_at=_TS,
                        completed_at=None,
                    ),
                )
                insert_sample(
                    ev,
                    SampleWrite(
                        sample_id="s-0",
                        run_id=run_id,
                        clause_id=_CLAUSE_A1,
                        condition="full",
                        subject_model=_FROZEN_MODEL,
                        subject_seed=None,
                        output_text="x",
                        output_sha256="a" * 64,
                        sampled_at=_TS,
                        sample_index=0,
                        input_tokens=1,
                        cache_read_input_tokens=0,
                        cache_creation_input_tokens=0,
                        output_tokens=1,
                        usd=0.001,
                    ),
                )
        finally:
            ev.close()
        rt = open_runtime(store.runtime)
        try:
            with writer_transaction(rt):
                insert_run_progress(
                    rt,
                    RunProgressWrite(
                        run_id=run_id,
                        state="running",
                        samples_planned=3,
                        samples_collected=1,
                        last_heartbeat=_TS,
                        error=None,
                    ),
                )
        finally:
            rt.close()

        result = store.invoke(_SKILL_A, "--resume", run_id)

        _assert_refused_before_spend(store, result, run_id, _FROZEN_MODEL)
        assert store.sample_count(run_id) == 1


class TestResumeKeepsTheRatification:
    def test_clause_decisions_keep_the_registered_thresholds(self, store: _Store) -> None:
        run_id = store.start_and_crash()

        result = store.invoke(_SKILL_A, "--resume", run_id)

        assert result.exit_code in (0, 2), result.output
        assert "no_ratification_reference" not in result.output
        assert _RAT_ID in result.output

    def test_refuses_when_the_frozen_record_cannot_be_read(self, store: _Store) -> None:
        frozen = store.root / f"{_RAT_ID}-frozen.md"
        frozen.write_text(_RECORD.format(rat=_RAT_ID, skill_id=_SKILL_A), encoding="utf-8")
        run_id = store.start_and_crash(record=frozen)
        before = store.sample_count(run_id)
        frozen.unlink()

        result = store.invoke(_SKILL_A, "--resume", run_id)

        _assert_refused_before_spend(store, result, run_id, str(frozen))
        assert store.sample_count(run_id) == before


class TestResumeKeepsTheClauses:
    @pytest.mark.parametrize("narrowed_to", [_CLAUSE_A1, _CLAUSE_A2])
    def test_refuses_a_clause_that_narrows_the_plan(self, store: _Store, narrowed_to: str) -> None:
        run_id = store.start_and_crash()
        before = store.sample_count(run_id)

        result = store.invoke(_SKILL_A, "--resume", run_id, "--clause", narrowed_to)

        _assert_refused_before_spend(store, result, run_id, "--clause")
        assert store.sample_count(run_id) == before

    def test_resume_without_the_flag_covers_the_whole_plan(self, store: _Store) -> None:
        run_id = store.start_and_crash()

        result = store.invoke(_SKILL_A, "--resume", run_id)

        assert result.exit_code in (0, 2), result.output
        assert store.sampled_clauses(run_id) == {_CLAUSE_A1, _CLAUSE_A2}

    def test_a_single_clause_plan_stays_a_single_clause_plan(self, store: _Store) -> None:
        run_id = store.start_and_crash("--clause", _CLAUSE_A1)

        result = store.invoke(_SKILL_A, "--resume", run_id)

        assert result.exit_code in (0, 2), result.output
        assert store.sampled_clauses(run_id) == {_CLAUSE_A1}

    def test_naming_the_only_frozen_clause_is_allowed(self, store: _Store) -> None:
        run_id = store.start_and_crash("--clause", _CLAUSE_A1)

        result = store.invoke(_SKILL_A, "--resume", run_id, "--clause", _CLAUSE_A1)

        assert result.exit_code in (0, 2), result.output
        assert store.completed_at(run_id) is not None


class TestResumeKeepsTheSkill:
    def test_refuses_a_run_of_another_skill(self, store: _Store) -> None:
        run_id = store.start_and_crash()
        before = store.sample_count(run_id)

        result = store.invoke(_SKILL_B, "--resume", run_id)

        _assert_refused_before_spend(store, result, run_id, "belongs to skill")
        assert store.sample_count(run_id) == before
        assert _CLAUSE_B1 not in store.sampled_clauses(run_id)
