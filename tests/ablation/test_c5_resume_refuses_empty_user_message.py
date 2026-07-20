"""C5 regression test (S49 hostile review).

_execute_ablation_run's resume path unconditionally overwrote the CLI-provided
user_message with _load_user_message_from_run(), which returns '' both when
resume_run_id doesn't exist in evidence.runs AND when the row exists but
config_json is corrupt or lacks the key (JSONDecodeError swallowed inside the
helper). The old code proceeded to call runner.resume_ablation() with an empty
prompt instead of refusing -- silently mixing an empty-prompt tail onto samples
collected under the real prompt.

These tests exercise _execute_ablation_run directly (not through the full CLI)
so the fix is verified at the exact call site named in the review, with
AblationRunner and make_subject_client mocked out (no network, no real
sampling loop).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest

from skill_harness.cli.main import _execute_ablation_run
from skill_harness.storage.migrations import open_evidence, open_runtime
from skill_harness.storage.models import ClauseWrite, RunWrite, SkillWrite
from skill_harness.storage.repositories.evidence.clauses import insert_clause
from skill_harness.storage.repositories.evidence.runs import insert_run
from skill_harness.storage.repositories.evidence.skills import insert_skill
from skill_harness.storage.transaction import writer_transaction

_TS = "2026-06-06T00:00:00.000000+00:00"
_SHA = "b" * 64
_SKILL_ID = "skill-c5-test"
_CLAUSE_ID = "clause-c5-001"


def _seed_skill_and_clause(evidence_path: Path) -> None:
    ev = open_evidence(evidence_path)
    try:
        with writer_transaction(ev):
            insert_skill(
                ev,
                SkillWrite(
                    skill_id=_SKILL_ID,
                    name="C5 skill",
                    source_path="/x.md",
                    source_sha256=_SHA,
                    imported_at=_TS,
                ),
            )
            insert_clause(
                ev,
                ClauseWrite(
                    clause_id=_CLAUSE_ID,
                    skill_id=_SKILL_ID,
                    clause_index=0,
                    rendering_index=0,
                    clause_text="Be concise.",
                    axis="verbosity",
                    comparator="increase",
                    oracle_tier=1,
                    vacuity_flag="none",
                    falsifying_case_schema_sha256="abc123",
                    created_at=_TS,
                ),
            )
    finally:
        ev.close()


def _seed_run(evidence_path: Path, run_id: str, config_json: str) -> None:
    ev = open_evidence(evidence_path)
    try:
        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json=config_json,
                    started_at=_TS,
                    completed_at=None,
                ),
            )
    finally:
        ev.close()


def _expected_message(run_id: str) -> str:
    return (
        f"Cannot resume run {run_id!r}: no user_message found in "
        "runs.config_json for this run_id (the run does not exist in "
        "evidence.db, or its config_json is corrupt/missing the key). "
        "Refusing to proceed with an empty prompt -- verify --resume "
        "RUN_ID against evidence.runs and re-run."
    )


@patch("skill_harness.ablation.subject.make_subject_client")
@patch("skill_harness.ablation.runner.AblationRunner")
def test_resume_nonexistent_run_id_refuses_empty_user_message(
    mock_runner_cls: MagicMock, mock_make_subject: MagicMock, tmp_path: Path
) -> None:
    """resume_run_id absent from evidence.runs -> _load_user_message_from_run
    returns '' -> must refuse, never call runner.resume_ablation()."""
    evidence_db = tmp_path / "evidence.db"
    runtime_db = tmp_path / "runtime.db"
    _seed_skill_and_clause(evidence_db)
    open_runtime(runtime_db).close()

    run_id = "run-does-not-exist"
    mock_runner_instance = mock_runner_cls.return_value

    with pytest.raises(click.ClickException) as exc_info:
        _execute_ablation_run(
            skill_id=_SKILL_ID,
            clause_id=None,
            subject_model="claude-sonnet-4-6",
            user_message="original CLI-provided prompt",
            max_usd=5.0,
            resume_run_id=run_id,
            evidence_db=evidence_db,
            runtime_db=runtime_db,
        )

    assert exc_info.value.message == _expected_message(run_id)
    mock_runner_instance.resume_ablation.assert_not_called()
    mock_runner_instance.run_ablation.assert_not_called()


@patch("skill_harness.ablation.subject.make_subject_client")
@patch("skill_harness.ablation.runner.AblationRunner")
def test_resume_corrupt_config_json_refuses_empty_user_message(
    mock_runner_cls: MagicMock, mock_make_subject: MagicMock, tmp_path: Path
) -> None:
    """resume_run_id exists in evidence.runs but config_json is invalid JSON ->
    _load_user_message_from_run swallows JSONDecodeError and returns '' -> must
    refuse (the 'crash-window' case: runtime.db may look resumable while
    evidence.db's config is corrupt)."""
    evidence_db = tmp_path / "evidence.db"
    runtime_db = tmp_path / "runtime.db"
    _seed_skill_and_clause(evidence_db)
    open_runtime(runtime_db).close()

    run_id = "run-corrupt-config-001"
    _seed_run(evidence_db, run_id, config_json="{not valid json")

    mock_runner_instance = mock_runner_cls.return_value

    with pytest.raises(click.ClickException) as exc_info:
        _execute_ablation_run(
            skill_id=_SKILL_ID,
            clause_id=None,
            subject_model="claude-sonnet-4-6",
            user_message="original CLI-provided prompt",
            max_usd=5.0,
            resume_run_id=run_id,
            evidence_db=evidence_db,
            runtime_db=runtime_db,
        )

    assert exc_info.value.message == _expected_message(run_id)
    mock_runner_instance.resume_ablation.assert_not_called()
    mock_runner_instance.run_ablation.assert_not_called()


@patch("skill_harness.ablation.subject.make_subject_client")
@patch("skill_harness.ablation.runner.AblationRunner")
def test_resume_missing_user_message_key_refuses(
    mock_runner_cls: MagicMock, mock_make_subject: MagicMock, tmp_path: Path
) -> None:
    """config_json parses fine but has no 'user_message' key -> '' -> refuse."""
    evidence_db = tmp_path / "evidence.db"
    runtime_db = tmp_path / "runtime.db"
    _seed_skill_and_clause(evidence_db)
    open_runtime(runtime_db).close()

    run_id = "run-no-user-message-key"
    _seed_run(evidence_db, run_id, config_json=json.dumps({"other": "stuff"}))

    mock_runner_instance = mock_runner_cls.return_value

    with pytest.raises(click.ClickException) as exc_info:
        _execute_ablation_run(
            skill_id=_SKILL_ID,
            clause_id=None,
            subject_model="claude-sonnet-4-6",
            user_message="original CLI-provided prompt",
            max_usd=5.0,
            resume_run_id=run_id,
            evidence_db=evidence_db,
            runtime_db=runtime_db,
        )

    assert exc_info.value.message == _expected_message(run_id)
    mock_runner_instance.resume_ablation.assert_not_called()


@patch("skill_harness.ablation.subject.make_subject_client")
@patch("skill_harness.ablation.runner.AblationRunner")
def test_resume_valid_config_proceeds_to_resume_ablation(
    mock_runner_cls: MagicMock, mock_make_subject: MagicMock, tmp_path: Path
) -> None:
    """Control case: a valid config_json with a real user_message must still
    reach runner.resume_ablation() -- the fix must not over-refuse."""
    evidence_db = tmp_path / "evidence.db"
    runtime_db = tmp_path / "runtime.db"
    _seed_skill_and_clause(evidence_db)
    open_runtime(runtime_db).close()

    run_id = "run-valid-config-001"
    expected_msg = "Write a detailed essay about climate change."
    _seed_run(evidence_db, run_id, config_json=json.dumps({"user_message": expected_msg}))

    mock_runner_instance = mock_runner_cls.return_value
    mock_runner_instance.resume_ablation.return_value = []

    _execute_ablation_run(
        skill_id=_SKILL_ID,
        clause_id=None,
        subject_model="claude-sonnet-4-6",
        user_message="original CLI-provided prompt (must be overridden)",
        max_usd=5.0,
        resume_run_id=run_id,
        evidence_db=evidence_db,
        runtime_db=runtime_db,
    )

    mock_runner_instance.resume_ablation.assert_called_once()
    assert mock_runner_instance.resume_ablation.call_args.kwargs["user_message"] == expected_msg
