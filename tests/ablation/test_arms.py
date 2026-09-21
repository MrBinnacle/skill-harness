"""Tests for declared-arm runs (#554 AC1).

A run config declares named arms, each resolving to a distinct system-prompt
assembly, and the runner samples every declared arm. The per-clause
full/ablated_k/null loop is untouched; declared-arm runs are a separate unit of
comparison (composition studies), so they get their own entry point and their
own append-only evidence table (arm_samples, migration 1200).

Mock discipline: all API calls mocked at the SDK boundary
(anthropic.Anthropic.messages.create) per A32 precedent. No live calls.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from skill_harness.ablation.arms import (
    ArmAssembly,
    ArmSpec,
    ArmSpecError,
    resolve_arm_assemblies,
)
from skill_harness.ablation.render import ConditionRenderer
from skill_harness.ablation.runner import RunConfig
from skill_harness.ablation.stopping import N_MIN
from skill_harness.ablation.subject import SubjectClient
from skill_harness.storage.migrations import open_evidence, open_runtime

_TS = "2026-06-06T00:00:00.000000+00:00"
_SHA = "a" * 64
_SKILL_ID = "skill-arms-test"
_USER_MSG = "Write a paragraph about testing."


def _mock_response(
    text: str = "This is a test response.",
    input_tokens: int = 100,
    output_tokens: int = 20,
) -> MagicMock:
    """Create a mock Anthropic SDK response."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=text)]
    mock_resp.model = "claude-sonnet-4-6"
    mock_resp.stop_reason = "end_turn"
    mock_usage = MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens
    mock_usage.cache_read_input_tokens = 0
    mock_usage.cache_creation_input_tokens = 0
    mock_resp.usage = mock_usage
    return mock_resp


def _seed_skill(evidence_conn: sqlite3.Connection) -> None:
    """Insert a skill row required by the FK constraint on runs."""
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
    response_factory: Callable[[int], MagicMock] | None = None,
) -> tuple[Any, MagicMock]:
    """Create an AblationRunner with a mocked SDK client.

    :returns: (runner, mock_client)
    """
    from skill_harness.ablation.runner import AblationRunner

    mock_client = MagicMock()
    call_count = [0]

    if response_factory is None:

        def _default_factory(idx: int) -> MagicMock:
            return _mock_response()

        response_factory = _default_factory

    def _create_side_effect(**kwargs: Any) -> MagicMock:
        resp = response_factory(call_count[0])
        call_count[0] += 1
        return resp

    mock_client.messages.create.side_effect = _create_side_effect

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


# ---------------------------------------------------------------------------
# RunConfig carries declared arms
# ---------------------------------------------------------------------------


class TestRunConfigArms:
    def test_arms_roundtrip_through_config_json(self) -> None:
        """A run config declares named arms; JSON roundtrip preserves them (#554 AC1)."""
        arms = (
            ArmSpec(name="parent_only", body_texts=("Parent card body text.",)),
            ArmSpec(
                name="both",
                body_texts=("Parent card body text.", "Specialist body text."),
            ),
        )
        config = RunConfig(
            run_id="r-1",
            skill_id=_SKILL_ID,
            clauses=[],
            subject_model="claude-sonnet-4-6",
            user_message=_USER_MSG,
            arms=arms,
        )
        restored = RunConfig.from_json(config.to_json())
        assert restored.arms == arms

    def test_default_run_declares_no_arms(self) -> None:
        """The per-clause run's config carries no arm field value (empty tuple)."""
        config = RunConfig(
            run_id="r-2",
            skill_id=_SKILL_ID,
            clauses=[],
            subject_model="claude-sonnet-4-6",
            user_message=_USER_MSG,
        )
        assert config.arms == ()
        restored = RunConfig.from_json(config.to_json())
        assert restored.arms == ()


# ---------------------------------------------------------------------------
# Arm resolution
# ---------------------------------------------------------------------------


class TestResolveArmAssemblies:
    def test_each_declared_arm_resolves_to_a_distinct_assembly(self) -> None:
        """One assembly per declared arm, all distinct, in declared order (#554 AC1)."""
        renderer = ConditionRenderer()
        arms = (
            ArmSpec(name="null_arm", body_texts=()),
            ArmSpec(name="parent", body_texts=("Parent body.",)),
            ArmSpec(name="both", body_texts=("Parent body.", "Specialist body.")),
        )
        assemblies = resolve_arm_assemblies(arms, renderer)
        assert list(assemblies) == ["null_arm", "parent", "both"]
        texts = [a.system_text for a in assemblies.values()]
        assert len(set(texts)) == 3
        assert "Parent body." in assemblies["parent"].system_text
        assert "Parent body." in assemblies["both"].system_text
        assert "Specialist body." in assemblies["both"].system_text
        assert "Parent body." not in assemblies["null_arm"].system_text

    def test_two_arms_resolving_to_the_same_assembly_are_refused(self) -> None:
        """A declared-arm run needs distinct assemblies; duplicates are refused."""
        renderer = ConditionRenderer()
        arms = (
            ArmSpec(name="first", body_texts=("Same body.",)),
            ArmSpec(name="second", body_texts=("Same body.",)),
        )
        with pytest.raises(ArmSpecError, match="same system-prompt assembly"):
            resolve_arm_assemblies(arms, renderer)

    def test_duplicate_arm_names_are_refused(self) -> None:
        renderer = ConditionRenderer()
        arms = (
            ArmSpec(name="dup", body_texts=("One body.",)),
            ArmSpec(name="dup", body_texts=("Other body.",)),
        )
        with pytest.raises(ArmSpecError, match="duplicate arm name"):
            resolve_arm_assemblies(arms, renderer)

    def test_empty_arm_set_is_refused(self) -> None:
        with pytest.raises(ArmSpecError, match="at least one arm"):
            resolve_arm_assemblies((), ConditionRenderer())

    @pytest.mark.parametrize("name", ("Bad Name", "arm\n"))
    def test_ill_formed_arm_name_is_refused(self, name: str) -> None:
        renderer = ConditionRenderer()
        with pytest.raises(ArmSpecError, match="not a valid declared-arm name"):
            resolve_arm_assemblies((ArmSpec(name=name, body_texts=("Body.",)),), renderer)

    def test_blank_body_text_is_refused(self) -> None:
        renderer = ConditionRenderer()
        with pytest.raises(ArmSpecError, match="blank"):
            resolve_arm_assemblies((ArmSpec(name="arm", body_texts=("   ",)),), renderer)


# ---------------------------------------------------------------------------
# AC2: an arm can include a skill body that is not the subject's own, by path
# ---------------------------------------------------------------------------


_SIBLING_SKILL_MD = """---
name: sibling-specialist
description: A recruited third-party specialist card.
---

You are the citation-checking specialist. Verify every claim against the
source list before you answer.
"""


def _write_sibling_skill(tmp_path: Path) -> Path:
    sibling = tmp_path / "sibling-specialist"
    sibling.mkdir()
    skill_md = sibling / "SKILL.md"
    skill_md.write_text(_SIBLING_SKILL_MD, encoding="utf-8")
    return skill_md


class TestArmIncludesForeignBodyByPath:
    def test_path_body_is_read_verbatim_without_frontmatter(self, tmp_path: Path) -> None:
        """The sibling's BODY joins the assembly; frontmatter is metadata only."""
        skill_md = _write_sibling_skill(tmp_path)
        renderer = ConditionRenderer()
        assemblies = resolve_arm_assemblies(
            (ArmSpec(name="with_sibling", skill_body_paths=(str(skill_md),)),),
            renderer,
        )
        text = assemblies["with_sibling"].system_text
        assert "Verify every claim against the" in text
        assert "sibling-specialist" not in text
        assert "recruited third-party specialist card" not in text

    def test_foreign_body_reaches_the_wire_in_a_declared_arm_run(
        self,
        seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """A run with a path-bodied arm sends the sibling's body to the subject."""
        ev, rt = seeded_db_pair
        skill_md = _write_sibling_skill(tmp_path)
        runner, mock_client = _make_runner(ev, rt)
        arms = (
            ArmSpec(
                name="both",
                body_texts=("Parent card body.",),
                skill_body_paths=(str(skill_md),),
            ),
        )
        results = runner.run_arms(
            skill_id=_SKILL_ID,
            arms=arms,
            user_message=_USER_MSG,
            samples_per_arm=1,
            max_usd=10.0,
        )
        assert len(results) == 1
        sample_calls = mock_client.messages.create.call_args_list[1:]
        sent_blocks = sample_calls[0].kwargs["system"]
        sent_text = "".join(block["text"] for block in sent_blocks)
        assert "Parent card body." in sent_text
        assert "Verify every claim against the" in sent_text
        assert "sibling-specialist" not in sent_text

    def test_skill_body_paths_roundtrip_through_config_json(self) -> None:
        arms = (ArmSpec(name="both", skill_body_paths=("/skills/sibling/SKILL.md",)),)
        config = RunConfig(
            run_id="r-3",
            skill_id=_SKILL_ID,
            clauses=[],
            subject_model="claude-sonnet-4-6",
            user_message=_USER_MSG,
            arms=arms,
        )
        restored = RunConfig.from_json(config.to_json())
        assert restored.arms == arms

    def test_unreadable_body_path_is_refused_before_spend(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection], tmp_path: Path
    ) -> None:
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        missing = tmp_path / "no-such-skill" / "SKILL.md"
        with pytest.raises(ArmSpecError, match=r"cannot be read as a SKILL\.md"):
            runner.run_arms(
                skill_id=_SKILL_ID,
                arms=(ArmSpec(name="broken", skill_body_paths=(str(missing),)),),
                user_message=_USER_MSG,
                samples_per_arm=1,
                max_usd=10.0,
            )
        cur = ev.execute("SELECT COUNT(*) FROM runs")
        assert cur.fetchone()[0] == 0

    def test_frontmatter_only_body_path_is_refused(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection], tmp_path: Path
    ) -> None:
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        hollow = tmp_path / "hollow"
        hollow.mkdir()
        (hollow / "SKILL.md").write_text("---\nname: hollow\n---\n   \n", encoding="utf-8")
        with pytest.raises(ArmSpecError, match=r"cannot be read as a SKILL\.md"):
            runner.run_arms(
                skill_id=_SKILL_ID,
                arms=(ArmSpec(name="hollow", skill_body_paths=(str(hollow / "SKILL.md"),)),),
                user_message=_USER_MSG,
                samples_per_arm=1,
                max_usd=10.0,
            )
        cur = ev.execute("SELECT COUNT(*) FROM runs")
        assert cur.fetchone()[0] == 0


# ---------------------------------------------------------------------------
# AC4: a 2x2 factorial is one data declaration, no runner edit
# ---------------------------------------------------------------------------


class TestCrossFactorial:
    def _design(self, tmp_path: Path) -> tuple[Any, Path, Path, Path]:
        """The motivating study's design: parent x specialist, placebo-matched absent."""
        parent_md = tmp_path / "parent"
        parent_md.mkdir()
        (parent_md / "SKILL.md").write_text(
            "---\nname: parent-card\n---\n\nAlways flag AI-slop patterns and\n"
            "produce a structured report.\n",
            encoding="utf-8",
        )
        specialist_md = tmp_path / "specialist"
        specialist_md.mkdir()
        (specialist_md / "SKILL.md").write_text(
            "---\nname: citation-specialist\n---\n\nVerify every claim against\nthe source list.\n",
            encoding="utf-8",
        )
        placebo_md = tmp_path / "placebo"
        placebo_md.mkdir()
        (placebo_md / "SKILL.md").write_text(
            "---\nname: matched-placebo\n---\n\nMaintain your usual working\n"
            "style for this task.\n",
            encoding="utf-8",
        )
        from skill_harness.ablation.arms import ArmFactor, ArmLevel, cross_factorial

        factors = (
            ArmFactor(
                "parent",
                levels=(
                    ArmLevel("present", skill_body_paths=(str(parent_md / "SKILL.md"),)),
                    ArmLevel("absent", skill_body_paths=(str(placebo_md / "SKILL.md"),)),
                ),
            ),
            ArmFactor(
                "specialist",
                levels=(
                    ArmLevel("present", skill_body_paths=(str(specialist_md / "SKILL.md"),)),
                    ArmLevel("absent", skill_body_paths=(str(placebo_md / "SKILL.md"),)),
                ),
            ),
        )
        return cross_factorial(factors), parent_md, specialist_md, placebo_md

    def test_two_crossed_factors_expand_to_the_four_cells(self, tmp_path: Path) -> None:
        """The cartesian product is the declared arm set, names read off the design."""
        arms, _parent_md, _specialist_md, _placebo_md = self._design(tmp_path)
        assert [a.name for a in arms] == [
            "parent_present__specialist_present",
            "parent_present__specialist_absent",
            "parent_absent__specialist_present",
            "parent_absent__specialist_absent",
        ]
        parent_body = "Always flag AI-slop patterns"
        specialist_body = "Verify every claim"
        placebo_body = "Maintain your usual working"

        resolved = {
            arm.name: "".join(
                block["text"]
                for block in resolve_arm_assemblies(arms, ConditionRenderer())[
                    arm.name
                ].system_blocks
            )
            for arm in arms
        }
        assert parent_body in resolved["parent_present__specialist_present"]
        assert specialist_body in resolved["parent_present__specialist_present"]
        assert specialist_body in resolved["parent_absent__specialist_present"]
        assert parent_body not in resolved["parent_absent__specialist_present"]
        assert placebo_body in resolved["parent_present__specialist_absent"]
        assert specialist_body not in resolved["parent_present__specialist_absent"]
        both_absent = resolved["parent_absent__specialist_absent"]
        assert placebo_body in both_absent
        assert parent_body not in both_absent
        assert specialist_body not in both_absent

    def test_factorial_runs_without_hand_editing_the_runner(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection], tmp_path: Path
    ) -> None:
        """The 2x2 declared by data is sampled by the stock runner, all four arms."""
        ev, rt = seeded_db_pair
        arms, _parent, _specialist, _placebo = self._design(tmp_path)
        runner, _ = _make_runner(ev, rt)
        results = runner.run_arms(
            skill_id=_SKILL_ID,
            arms=list(arms),
            user_message=_USER_MSG,
            samples_per_arm=1,
            max_usd=10.0,
        )
        assert [r.arm_name for r in results] == [a.name for a in arms]
        cur = ev.execute("SELECT arm, COUNT(*) FROM arm_samples GROUP BY arm")
        counts = dict(cur.fetchall())
        assert counts == {a.name: 1 for a in arms}

    def test_factorial_expansion_refuses_a_composed_ill_formed_name(self) -> None:
        """A factor/label pair that composes an invalid arm name fails the expansion."""
        from skill_harness.ablation.arms import ArmFactor, ArmLevel, cross_factorial

        with pytest.raises(ArmSpecError, match="not a valid declared-arm name"):
            cross_factorial((ArmFactor("Bad Factor", levels=(ArmLevel("one"), ArmLevel("two"))),))


# ---------------------------------------------------------------------------
# AC5: the runner refuses a config whose declared arms and receipt arms disagree
# ---------------------------------------------------------------------------


class TestReceiptArmsAgreement:
    def test_run_arms_refuses_a_disagreeing_receipt_arm_set(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """Declared arms {parent_only, both} vs receipt arms {null, full} is refused."""
        from skill_harness.ablation.runner import ReceiptArmsMismatchError

        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        arms = (
            ArmSpec(name="parent_only", body_texts=("Parent card body.",)),
            ArmSpec(name="both", body_texts=("Parent card body.", "Sibling body.")),
        )
        with pytest.raises(ReceiptArmsMismatchError, match="receipt arms"):
            runner.run_arms(
                skill_id=_SKILL_ID,
                arms=arms,
                user_message=_USER_MSG,
                samples_per_arm=1,
                max_usd=10.0,
                receipt_arms=["null", "full"],
            )
        cur = ev.execute("SELECT COUNT(*) FROM runs")
        assert cur.fetchone()[0] == 0
        cur = ev.execute("SELECT COUNT(*) FROM arm_samples")
        assert cur.fetchone()[0] == 0

    def test_run_arms_accepts_a_matching_receipt_arm_set(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        arms = (ArmSpec(name="parent_only", body_texts=("Parent card body.",)),)
        results = runner.run_arms(
            skill_id=_SKILL_ID,
            arms=arms,
            user_message=_USER_MSG,
            samples_per_arm=1,
            max_usd=10.0,
            receipt_arms=["parent_only"],
        )
        assert [r.arm_name for r in results] == ["parent_only"]

    def test_string_form_of_a_single_receipt_arm_is_normalized(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        results = runner.run_arms(
            skill_id=_SKILL_ID,
            arms=(ArmSpec(name="parent_only", body_texts=("Body.",)),),
            user_message=_USER_MSG,
            samples_per_arm=1,
            max_usd=10.0,
            receipt_arms="parent_only",
        )
        assert len(results) == 1

    def test_assert_receipt_arms_match_direct(self, tmp_path: Path) -> None:
        """The pure check: declared arms vs receipt arms, set equality both ways."""
        from skill_harness.ablation.runner import (
            ReceiptArmsMismatchError,
            RunConfig,
            assert_receipt_arms_match,
        )

        config = RunConfig(
            run_id="r-arms",
            skill_id="s",
            clauses=[],
            subject_model="m",
            user_message="u",
            arms=(ArmSpec(name="parent_only"), ArmSpec(name="both")),
        )
        # Disagreement in either direction is refused.
        with pytest.raises(ReceiptArmsMismatchError):
            assert_receipt_arms_match(config, ["null", "full"])
        with pytest.raises(ReceiptArmsMismatchError):
            assert_receipt_arms_match(config, ["parent_only"])
        # A duplicate receipt arm list is refused, not silently deduplicated.
        with pytest.raises(ReceiptArmsMismatchError, match="duplicate"):
            assert_receipt_arms_match(config, ["parent_only", "parent_only"])
        # An empty receipt arm list is refused.
        with pytest.raises(ReceiptArmsMismatchError, match="no arms"):
            assert_receipt_arms_match(config, [])
        # Agreement (order-insensitive) passes.
        assert_receipt_arms_match(config, ["both", "parent_only"])

    def test_default_run_receipt_vocabulary_is_null_full(self) -> None:
        """A per-clause run with no declared arms keeps the two-arm vocabulary."""
        from skill_harness.ablation.runner import (
            ReceiptArmsMismatchError,
            RunConfig,
            assert_receipt_arms_match,
        )

        config = RunConfig(
            run_id="r-default",
            skill_id="s",
            clauses=[
                {
                    "clause_id": "c",
                    "clause_text": "t",
                    "clause_index": 0,
                    "axis": "verbosity",
                    "oracle_tier": 1,
                }
            ],
            subject_model="m",
            user_message="u",
        )
        assert config.receipt_arm_names() == ("full", "null")
        assert_receipt_arms_match(config, ["null", "full"])
        with pytest.raises(ReceiptArmsMismatchError):
            assert_receipt_arms_match(config, ["null"])


# ---------------------------------------------------------------------------
# AC6: an arm declared but never sampled fails the run
# ---------------------------------------------------------------------------


class TestDeclaredArmCompleteness:
    def test_declared_but_never_sampled_arm_fails_the_run(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """A zero-sample plan completes nothing: the run fails loudly (#554 AC6)."""
        from skill_harness.ablation.runner import ArmNeverSampledError

        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        arms = (
            ArmSpec(name="parent_only", body_texts=("Parent card body.",)),
            ArmSpec(name="both", body_texts=("Parent card body.", "Sibling body.")),
        )
        with pytest.raises(ArmNeverSampledError, match="never sampled") as excinfo:
            runner.run_arms(
                skill_id=_SKILL_ID,
                arms=arms,
                user_message=_USER_MSG,
                samples_per_arm=0,
                max_usd=10.0,
            )
        assert "parent_only" in str(excinfo.value)
        assert "both" in str(excinfo.value)

        # The run is failed, not completed: no completed_at stamp, no
        # 'completed' state, and the failure names the refusal.
        cur = ev.execute("SELECT completed_at FROM runs")
        assert cur.fetchone()[0] is None
        cur = rt.execute("SELECT state, error FROM run_progress")
        state, error = cur.fetchone()
        assert state == "failed"
        assert error is not None and "declared_arm_never_sampled" in error

    def test_every_declared_arm_sampled_passes_the_gate(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """The completeness gate reads evidence; a fully sampled arm set passes."""
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        results = runner.run_arms(
            skill_id=_SKILL_ID,
            arms=(ArmSpec(name="parent_only", body_texts=("Parent card body.",)),),
            user_message=_USER_MSG,
            samples_per_arm=2,
            max_usd=10.0,
        )
        assert results[0].samples_collected == 2
        cur = rt.execute("SELECT state FROM run_progress")
        assert cur.fetchone()[0] == "completed"


# ---------------------------------------------------------------------------
# run_arms: the declared-arm sampling loop
# ---------------------------------------------------------------------------


class TestRunArms:
    def test_run_samples_every_declared_arm(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """Every declared arm is sampled; evidence rows and results agree (#554 AC1)."""
        ev, rt = seeded_db_pair
        runner, mock_client = _make_runner(ev, rt)
        arms = (
            ArmSpec(name="parent_only", body_texts=("Parent card body.",)),
            ArmSpec(name="both", body_texts=("Parent card body.", "Specialist body.")),
        )
        samples_per_arm = 2

        results = runner.run_arms(
            skill_id=_SKILL_ID,
            arms=arms,
            user_message=_USER_MSG,
            samples_per_arm=samples_per_arm,
            max_usd=10.0,
        )

        assert [(r.arm_name, r.samples_collected) for r in results] == [
            ("parent_only", 2),
            ("both", 2),
        ]

        # Evidence: one arm_samples row per (arm, sample_index), no clause rows.
        cur = ev.execute("SELECT arm, COUNT(*) FROM arm_samples GROUP BY arm ORDER BY arm")
        counts = dict(cur.fetchall())
        assert counts == {"both": 2, "parent_only": 2}
        cur = ev.execute("SELECT COUNT(*) FROM samples")
        assert cur.fetchone()[0] == 0

        # Wire: warmup + one call per sample, and the two arms saw different blocks.
        calls = mock_client.messages.create.call_args_list
        assert len(calls) == 1 + 2 * samples_per_arm  # warmup + samples
        sample_systems = [call.kwargs["system"] for call in calls[1:]]
        first_arm_blocks = sample_systems[:samples_per_arm]
        second_arm_blocks = sample_systems[samples_per_arm:]
        assert all(b == first_arm_blocks[0] for b in first_arm_blocks)
        assert first_arm_blocks[0] != second_arm_blocks[0]
        assert any("Parent card body." in block["text"] for block in first_arm_blocks[0])
        assert any("Specialist body." in block["text"] for block in second_arm_blocks[0])

    def test_run_config_json_carries_the_declared_arms(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """runs.config_json names the declared arms of the run (#554 AC1)."""
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        arms = (
            ArmSpec(name="parent_only", body_texts=("Parent card body.",)),
            ArmSpec(name="both", body_texts=("Parent card body.", "Specialist body.")),
        )
        results = runner.run_arms(
            skill_id=_SKILL_ID,
            arms=arms,
            user_message=_USER_MSG,
            samples_per_arm=1,
            max_usd=10.0,
        )
        assert len(results) == 2

        cur = ev.execute("SELECT config_json FROM runs WHERE skill_id = ?", (_SKILL_ID,))
        config_json = cur.fetchone()[0]
        stored = json.loads(config_json)
        assert [a["name"] for a in stored["arms"]] == ["parent_only", "both"]
        assert stored["arms"][1]["body_texts"] == [
            "Parent card body.",
            "Specialist body.",
        ]

        restored = RunConfig.from_json(config_json)
        assert restored.arms == arms
        assert restored.family_size == 2

    def test_run_progress_and_budget_track_the_arm_run(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        arms = (ArmSpec(name="parent_only", body_texts=("Parent card body.",)),)
        runner.run_arms(
            skill_id=_SKILL_ID,
            arms=arms,
            user_message=_USER_MSG,
            samples_per_arm=3,
            max_usd=10.0,
        )
        cur = rt.execute("SELECT state, samples_planned, samples_collected FROM run_progress")
        state, planned, collected = cur.fetchone()
        assert state == "completed"
        assert planned == 3
        assert collected == 3

    def test_default_samples_per_arm_is_n_min(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        results = runner.run_arms(
            skill_id=_SKILL_ID,
            arms=(ArmSpec(name="parent_only", body_texts=("Parent body.",)),),
            user_message=_USER_MSG,
            max_usd=10.0,
        )
        assert results[0].samples_collected == N_MIN

    def test_refusals_write_no_run_row(
        self, seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        """A refused arm declaration spends nothing and writes no run row."""
        ev, rt = seeded_db_pair
        runner, _ = _make_runner(ev, rt)
        with pytest.raises(ArmSpecError):
            runner.run_arms(
                skill_id=_SKILL_ID,
                arms=(  # two names, one assembly
                    ArmSpec(name="first", body_texts=("Same body.",)),
                    ArmSpec(name="second", body_texts=("Same body.",)),
                ),
                user_message=_USER_MSG,
                samples_per_arm=1,
                max_usd=10.0,
            )
        with pytest.raises(ArmSpecError):
            runner.run_arms(
                skill_id=_SKILL_ID,
                arms=(),
                user_message=_USER_MSG,
                samples_per_arm=1,
                max_usd=10.0,
            )
        cur = ev.execute("SELECT COUNT(*) FROM runs")
        assert cur.fetchone()[0] == 0
        cur = ev.execute("SELECT COUNT(*) FROM arm_samples")
        assert cur.fetchone()[0] == 0

    def test_arm_samples_table_is_append_only(self, evidence_db: sqlite3.Connection) -> None:
        """arm_samples carries the standard append-only triggers."""
        evidence_db.execute(
            "INSERT INTO skills (skill_id, name, source_path, source_sha256) VALUES (?,?,?,?)",
            ("sk_x", "x", "/tmp/x.md", _SHA),
        )
        evidence_db.execute(
            "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at) "
            "VALUES (?,?,?,?,?)",
            ("r-x", "sk_x", "ablation", "{}", _TS),
        )
        evidence_db.execute(
            "INSERT INTO arm_samples "
            "(sample_id, run_id, arm, sample_index, subject_model, output_text, "
            "output_sha256, sampled_at) VALUES (?,?,?,?,?,?,?,?)",
            ("s-x", "r-x", "both", 0, "claude-sonnet-4-6", "out", _SHA, _TS),
        )
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: arm_samples"):
            evidence_db.execute(
                "UPDATE arm_samples SET output_text = 'nope' WHERE sample_id = 's-x'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: arm_samples"):
            evidence_db.execute("DELETE FROM arm_samples WHERE sample_id = 's-x'")

    def test_arm_samples_unique_per_arm_index(self, evidence_db: sqlite3.Connection) -> None:
        """UNIQUE(run_id, arm, sample_index) is the crash-resume idempotency key."""
        evidence_db.execute(
            "INSERT INTO skills (skill_id, name, source_path, source_sha256) VALUES (?,?,?,?)",
            ("sk_x", "x", "/tmp/x.md", _SHA),
        )
        evidence_db.execute(
            "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at) "
            "VALUES (?,?,?,?,?)",
            ("r-y", "sk_x", "ablation", "{}", _TS),
        )
        evidence_db.execute(
            "INSERT INTO arm_samples "
            "(sample_id, run_id, arm, sample_index, subject_model, output_text, "
            "output_sha256, sampled_at) VALUES (?,?,?,?,?,?,?,?)",
            ("s-y1", "r-y", "both", 0, "claude-sonnet-4-6", "out", _SHA, _TS),
        )
        with pytest.raises(sqlite3.IntegrityError):
            evidence_db.execute(
                "INSERT INTO arm_samples "
                "(sample_id, run_id, arm, sample_index, subject_model, output_text, "
                "output_sha256, sampled_at) VALUES (?,?,?,?,?,?,?,?)",
                ("s-y2", "r-y", "both", 0, "claude-sonnet-4-6", "out", _SHA, _TS),
            )


# ---------------------------------------------------------------------------
# Reconciliation: arm-sample costs are evidence-authoritative (A41)
# ---------------------------------------------------------------------------


def test_reconciler_counts_arm_sample_costs(
    seeded_db_pair: tuple[sqlite3.Connection, sqlite3.Connection],
) -> None:
    """Evidence cost sum includes arm_samples.usd, so an arm run reconciles clean."""
    from skill_harness.ablation.reconciler import reconcile_run_cost

    ev, rt = seeded_db_pair
    ev.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at) VALUES (?,?,?,?,?)",
        ("r-cost", _SKILL_ID, "ablation", "{}", _TS),
    )
    ev.execute(
        "INSERT INTO arm_samples "
        "(sample_id, run_id, arm, sample_index, subject_model, output_text, "
        "output_sha256, sampled_at, usd) VALUES (?,?,?,?,?,?,?,?,?)",
        ("s-c1", "r-cost", "both", 0, "claude-sonnet-4-6", "out", _SHA, _TS, 0.01),
    )
    from skill_harness.storage.models import CostLedgerWrite
    from skill_harness.storage.repositories.runtime.cost_ledger import (
        insert_cost_ledger_entry,
    )
    from skill_harness.storage.transaction import writer_transaction

    with writer_transaction(rt):
        insert_cost_ledger_entry(
            rt,
            CostLedgerWrite(
                ts=_TS,
                run_id="r-cost",
                skill_id=None,
                model_id="claude-sonnet-4-6",
                call_kind="subject",
                input_tok=10,
                cache_write_tok=0,
                cache_read_tok=0,
                output_tok=5,
                usd=0.01,
            ),
        )
    # In sync: no back-fill needed.
    assert (
        reconcile_run_cost(
            evidence_conn=ev, runtime_conn=rt, run_id="r-cost", model_id="claude-sonnet-4-6"
        )
        is False
    )


def test_arm_sample_write_model_refuses_ill_formed_arm() -> None:
    """The write model is the floor: arm must match the declared-arm name pattern."""
    from pydantic import ValidationError

    from skill_harness.storage.models import ArmSampleWrite

    with pytest.raises(ValidationError, match="declared-arm name"):
        ArmSampleWrite(
            sample_id="s",
            run_id="r",
            arm="Both Arms",
            sample_index=0,
            subject_model="m",
            subject_seed=None,
            output_text="out",
            output_sha256=_SHA,
            sampled_at=_TS,
        )


def test_arm_assembly_block_layout_carries_cache_markers() -> None:
    """The assembly layout mirrors the renderer discipline: base marker + last body."""
    renderer = ConditionRenderer()
    assembly = resolve_arm_assemblies(
        (ArmSpec(name="both", body_texts=("One.", "Two.")),), renderer
    )["both"]
    blocks = assembly.system_blocks
    assert blocks[0]["text"] == renderer._base_system
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[1]["text"] == "One."
    assert "cache_control" not in blocks[1]
    assert blocks[2]["text"] == "Two."
    assert blocks[2]["cache_control"] == {"type": "ephemeral"}


def test_arm_assembly_type_holds_the_wire_shape() -> None:
    renderer = ConditionRenderer()
    assemblies = resolve_arm_assemblies((ArmSpec(name="parent", body_texts=("Body.",)),), renderer)
    assembly = assemblies["parent"]
    assert isinstance(assembly, ArmAssembly)
    assert assembly.system_text == "".join(b["text"] for b in assembly.system_blocks)
