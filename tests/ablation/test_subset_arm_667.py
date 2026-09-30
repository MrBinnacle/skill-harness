"""Tests for the seeded random-subset arm (#667).

Part of the collection-effect screen (#663); blocked on #664's delivered
listing. Per-ticket rule: write the test first, watch it fail for the right
reason, then make it pass. A test that passed before the change pins nothing.

Mock discipline: all API calls mocked at the SDK boundary
(anthropic.Anthropic.messages.create) per A32 precedent. No live calls.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from skill_harness.ablation.arms import ArmSpec
from skill_harness.ablation.runner import RunConfig
from skill_harness.ablation.subject import SubjectClient
from skill_harness.ablation.subset_arm import (
    SUBSET_ARM_NAME,
    SubsetArmDrawRecord,
    draw_subset_arm,
    trace_subset_draw,
)
from skill_harness.sers import build_subject_identity
from skill_harness.storage.migrations import open_evidence, open_runtime

# Seeds pinned for AC1: same seed, same subset; these two differ.
_SEED_A = 1729
_SEED_B = 2718

_TS = "2026-06-06T00:00:00.000000+00:00"
_SHA = "a" * 64
_SKILL_ID = "skill-subset-test"
_USER_MSG = "Write a paragraph about testing."

# The exact subset seed 1729 draws from the 14-card package. Pinned so a
# change to the sampling stream fails this assertion instead of silently
# redefining what "the same subset" means.
_EXPECTED_SEED_A = (
    "card-00",
    "card-02",
    "card-06",
    "card-07",
    "card-08",
    "card-10",
    "card-12",
)


def _package(size: int = 14) -> dict[str, str]:
    """A subject package of ``size`` cards in fixed order (name -> description)."""
    return {
        f"card-{i:02d}": f"Description of card {i:02d}: distinct body {i:02d}." for i in range(size)
    }


# ---------------------------------------------------------------------------
# AC1: the same package and seed give the same subset on every call; a
# different seed gives a different subset for a package of 14.
# ---------------------------------------------------------------------------


class TestSameSeedSameSubset:
    def test_same_package_and_seed_give_the_same_subset_on_every_call(self) -> None:
        """AC1: two draws of the same package at the same seed are identical,
        names and assembly bodies alike."""
        package = _package(14)
        first = draw_subset_arm(package, seed=_SEED_A)
        second = draw_subset_arm(package, seed=_SEED_A)

        assert first.seed == second.seed == _SEED_A
        assert first.card_names == second.card_names
        assert first.arm.body_texts == second.arm.body_texts
        assert first.arm.name == second.arm.name == SUBSET_ARM_NAME

    def test_every_drawn_name_is_a_package_card_and_bodies_match(self) -> None:
        """AC1: the subset is drawn from the package; each chosen name carries
        its own description into the assembly body."""
        package = _package(14)
        draw = draw_subset_arm(package, seed=_SEED_A)

        assert set(draw.card_names) <= set(package)
        assert draw.arm.body_texts == tuple(package[name] for name in draw.card_names)

    def test_a_different_seed_gives_a_different_subset_for_a_package_of_14(self) -> None:
        """AC1: seed 1729 and seed 2718 draw different halves of the 14-card package."""
        package = _package(14)
        draw_a = draw_subset_arm(package, seed=_SEED_A)
        draw_b = draw_subset_arm(package, seed=_SEED_B)

        assert draw_a.card_names != draw_b.card_names

    def test_the_pinned_seed_draws_the_pinned_subset(self) -> None:
        """AC1: seed 1729 on the 14-card package draws exactly these names —
        the regression pin for the sampling stream itself."""
        package = _package(14)
        draw = draw_subset_arm(package, seed=_SEED_A)
        assert draw.card_names == _EXPECTED_SEED_A

    def test_the_seed_a_caller_passes_is_the_seed_recorded(self) -> None:
        """AC1: a passed seed is used verbatim; the draw reports it."""
        package = _package(14)
        draw = draw_subset_arm(package, seed=_SEED_A)
        assert draw.seed == _SEED_A


# ---------------------------------------------------------------------------
# AC2: the subset size is half the package, rounded down, and never zero for
# a package of two or more.
# ---------------------------------------------------------------------------


class TestSubsetSizeIsHalfRoundedDown:
    @pytest.mark.parametrize(
        ("package_size", "expected_subset"),
        [
            (2, 1),
            (3, 1),
            (4, 2),
            (5, 2),
            (7, 3),
            (14, 7),
        ],
    )
    def test_subset_size_is_the_package_size_divided_by_two_rounded_down(
        self,
        package_size: int,
        expected_subset: int,
    ) -> None:
        """AC2: len(subset) == floor(len(package) / 2) at any seed, so an odd
        package loses its last card rather than keeping it."""
        package = _package(package_size)
        for seed in (_SEED_A, _SEED_B):
            draw = draw_subset_arm(package, seed=seed)
            assert len(draw.card_names) == expected_subset
            assert len(draw.arm.body_texts) == expected_subset

    @pytest.mark.parametrize("package_size", [2, 3, 5, 7, 14, 15])
    def test_subset_is_never_zero_for_a_package_of_two_or_more(
        self,
        package_size: int,
    ) -> None:
        """AC2: every package of two or more yields at least one card."""
        draw = draw_subset_arm(_package(package_size), seed=_SEED_A)
        assert len(draw.card_names) >= 1

    def test_a_caller_who_passes_no_seed_gets_a_fresh_drawn_seed(self) -> None:
        """AC2 (seed policy): seed=None draws new entropy, so two seedless
        runs of one package carry different seeds and may differ subsets."""
        package = _package(14)
        first = draw_subset_arm(package)
        second = draw_subset_arm(package)
        assert first.seed != second.seed
        assert isinstance(first.seed, int)
        assert isinstance(second.seed, int)


# ---------------------------------------------------------------------------
# Helpers for the run-record tests: a mocked-subject runner over a seeded
# evidence/runtime DB pair, mirroring tests/ablation/test_arms.py's A32
# discipline.
# ---------------------------------------------------------------------------


def _mock_response() -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text="This is a test response.")]
    mock_resp.model = "claude-sonnet-4-6"
    mock_resp.stop_reason = "end_turn"
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 20
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    mock_resp.usage = usage
    return mock_resp


def _seed_skill(evidence_conn: sqlite3.Connection) -> None:
    from skill_harness.storage.models import SkillWrite
    from skill_harness.storage.repositories.evidence.skills import insert_skill
    from skill_harness.storage.transaction import writer_transaction

    with writer_transaction(evidence_conn):
        insert_skill(
            evidence_conn,
            SkillWrite(
                skill_id=_SKILL_ID,
                name="Test Skill",
                source_path="/test/skill.md",
                source_sha256=_SHA,
                imported_at=_TS,
            ),
        )


def _make_runner(
    evidence_conn: sqlite3.Connection,
    runtime_conn: sqlite3.Connection,
) -> tuple[Any, MagicMock]:
    from skill_harness.ablation.runner import AblationRunner

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_response()
    subject = SubjectClient(client=mock_client, model="claude-sonnet-4-6")
    runner = AblationRunner(
        evidence_conn=evidence_conn,
        runtime_conn=runtime_conn,
        subject_client=subject,
        scorers={"verbosity": lambda t: float(len(t.split()))},
        max_retries=0,
        retry_delay_s=0.0,
    )
    return runner, mock_client


@pytest.fixture()
def seeded_db_pair(
    tmp_path: Path,
) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection]]:
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")
    _seed_skill(ev)
    try:
        yield ev, rt
    finally:
        ev.close()
        rt.close()


def _run_one_subset_arm(
    runner: Any,
    package: dict[str, str],
    *,
    seed: int,
) -> tuple[Any, Any]:
    draw = draw_subset_arm(package, seed=seed)
    return draw, runner.run_arms(
        skill_id=_SKILL_ID,
        arms=(draw.arm,),
        user_message=_USER_MSG,
        samples_per_arm=1,
        max_usd=10.0,
        receipt_arms=draw.arm.name,
        subset_draws=(draw,),
    )


# ---------------------------------------------------------------------------
# AC3: the seed and the subset names appear in the run record, and a receipt
# can be traced back to them.
# ---------------------------------------------------------------------------


class TestRunRecordCarriesTheDraw:
    def test_run_config_json_freezes_the_seed_and_the_subset_names(
        self,
        seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
    ) -> None:
        """AC3: runs.config_json holds the draw — arm name, seed, and every
        chosen card name — written when the run starts."""
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        draw, results = _run_one_subset_arm(runner, _package(14), seed=_SEED_A)
        assert results[0].arm_name == SUBSET_ARM_NAME

        cur = ev.execute("SELECT config_json FROM runs WHERE skill_id = ?", (_SKILL_ID,))
        config_json = cur.fetchone()[0]
        stored = json.loads(config_json)
        assert stored["subset_draws"] == [
            {
                "arm_name": SUBSET_ARM_NAME,
                "seed": _SEED_A,
                "card_names": list(_EXPECTED_SEED_A),
            }
        ]

        restored = RunConfig.from_json(config_json)
        assert restored.subset_draws == (draw.record,)

    def test_a_default_run_freezes_an_empty_draw_list(
        self,
        seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
    ) -> None:
        """AC3: a run that draws no subset still writes the key, so an absent
        draw reads as 'none declared', not as an old row predating the field."""
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        runner.run_arms(
            skill_id=_SKILL_ID,
            arms=(ArmSpec(name="plain", body_texts=("Plain body.",)),),
            user_message=_USER_MSG,
            samples_per_arm=1,
            max_usd=10.0,
        )
        cur = ev.execute("SELECT config_json FROM runs WHERE skill_id = ?", (_SKILL_ID,))
        config_json = cur.fetchone()[0]
        stored = json.loads(config_json)
        assert stored["subset_draws"] == []
        assert RunConfig.from_json(config_json).subset_draws == ()

    def test_a_receipt_traces_back_to_the_seed_and_the_subset_names(
        self,
        seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
    ) -> None:
        """AC3: the receipt's arm vocabulary names the arm; the run record
        maps that name back to the seed and the chosen card names."""
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        draw, _ = _run_one_subset_arm(runner, _package(14), seed=_SEED_A)

        cur = ev.execute("SELECT config_json FROM runs WHERE skill_id = ?", (_SKILL_ID,))
        config_json = cur.fetchone()[0]
        config = RunConfig.from_json(config_json)

        identity = build_subject_identity(
            skill_md=b"# subject skill",
            arms=config.receipt_arm_names(),
        )
        assert identity["arms"] == SUBSET_ARM_NAME

        traced = trace_subset_draw(config_json, arm_name=str(identity["arms"]))
        assert traced.seed == _SEED_A
        assert traced.card_names == _EXPECTED_SEED_A
        assert traced.arm_name == draw.arm.name

    def test_a_draw_naming_an_undeclared_arm_is_refused_before_any_run_row(
        self,
        seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
    ) -> None:
        """AC3: the record cannot describe an arm this run never declared —
        refused before the run row, so nothing is spent on the lie."""
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        rogue = SubsetArmDrawRecord(
            arm_name="other_arm",
            seed=_SEED_A,
            card_names=_EXPECTED_SEED_A,
        )
        with pytest.raises(ValueError, match="does not declare"):
            runner.run_arms(
                skill_id=_SKILL_ID,
                arms=(ArmSpec(name="plain", body_texts=("Plain body.",)),),
                user_message=_USER_MSG,
                samples_per_arm=1,
                max_usd=10.0,
                subset_draws=(rogue,),
            )
        assert ev.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
