"""Path C: the ablation lane's Gate-2 discordant route (#368).

Two things are under test and they are separable. First, that the registered
thresholds are consumed BY REFERENCE and that an unregistered record is
refused rather than defaulted. Second, that routing through Gate 2 restores
the effect-size floor the conditional posterior alone cannot see.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from skill_harness.ablation.path_c import (
    PathCResult,
    RegisteredGate2Thresholds,
    UnregisteredThresholdsError,
    decide_clause,
    registered_thresholds,
)
from skill_harness.ablation.stopping import BetaBinomialAccumulator, StopDecision
from skill_harness.oc.gate2 import Gate2Decision

REPO_ROOT = Path(__file__).resolve().parent.parent
RAT_0001 = REPO_ROOT / "docs" / "ratifications" / "RAT-0001-git-pull-rebase-trap.md"

_RECORD_TEMPLATE = """---
rat: {rat}
status: {status}
skill_id: path-c-fixture
task_family: fixture
estimand: treatment-policy
gate: {gate}
n: 20
worst_case_cost_usd: 1.00
hard_cap_usd: 1.00
cost_provenance: {provenance}
sme_status: deliberated
ratified_date: "2026-09-05"
{thresholds}---

# {rat} - Path C threshold fixture
"""


def _record(
    tmp_path: Path,
    *,
    rat: str = "RAT-0009",
    status: str = "RATIFIED",
    gate: str = "gate2",
    provenance: str = "project_pair_usd",
    thresholds: str = "gamma: 0.90\ndelta_min: 0.20\nq_min: 0.70\n",
) -> Path:
    path = tmp_path / f"{rat}-fixture.md"
    path.write_text(
        _RECORD_TEMPLATE.format(
            rat=rat,
            status=status,
            gate=gate,
            provenance=provenance,
            thresholds=thresholds,
        ),
        encoding="utf-8",
    )
    return path


def _run(wins: int, losses: int, ties: int) -> StopDecision:
    """Drive the production accumulator and return its stop decision."""
    acc = BetaBinomialAccumulator()
    for _ in range(wins):
        acc.add(1.0)
    for _ in range(losses):
        acc.add(0.0)
    for _ in range(ties):
        acc.add(0.5)
    return acc.check_stop()


# ---------------------------------------------------------------------------
# Thresholds are consumed by reference
# ---------------------------------------------------------------------------


class TestRegisteredThresholds:
    def test_reads_the_real_ratified_record(self) -> None:
        """RAT-0001 is RATIFIED and carries all three Gate-2 thresholds.

        Read from the record rather than restated here on purpose: a literal
        in this file would be a second copy that can drift from the
        registration, which is the failure registering thresholds prevents.
        """
        t = registered_thresholds(RAT_0001)
        assert t.ratification_id == "RAT-0001"
        assert 0.5 < t.gamma < 1.0
        assert 0.0 < t.delta_min < 1.0
        assert 0.5 < t.q_min < 1.0

    def test_design_carries_the_registered_thresholds_not_local_defaults(self) -> None:
        t = registered_thresholds(RAT_0001)
        design = t.design(n_pairs=24)
        assert design.n_pairs == 24
        assert design.gamma == t.gamma
        assert design.mme.delta_min == t.delta_min
        assert design.mme.q_min == t.q_min

    def test_unratified_record_is_refused(self) -> None:
        """A proposal is not a registration."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _record(Path(tmp), status="DRAFT")
            with pytest.raises(UnregisteredThresholdsError, match="RATIFIED"):
                registered_thresholds(path)

    def test_missing_threshold_refuses_rather_than_defaulting(self) -> None:
        """The refusal is the point: a defaulted gamma forges a registration.

        This is the negative control for the whole by-reference claim. If it
        ever passes by returning a value, the module is inventing thresholds
        and every decision it makes is unregistered while looking registered.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = _record(Path(tmp), thresholds="gamma: 0.90\nq_min: 0.70\n")
            with pytest.raises(UnregisteredThresholdsError, match="delta_min"):
                registered_thresholds(path)

    def test_non_gate2_record_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # gate1 records carry a different cost provenance; the fixture is a
            # VALID gate1 record, so the refusal below is Path C's, not the parser's.
            path = _record(Path(tmp), gate="gate1", provenance="project_trial_usd")
            with pytest.raises(UnregisteredThresholdsError, match="gate2"):
                registered_thresholds(path)


# ---------------------------------------------------------------------------
# The decision route
# ---------------------------------------------------------------------------


class TestDecideClause:
    def test_clean_win_with_no_ties_is_a_benefit(self) -> None:
        t = registered_thresholds(RAT_0001)
        result = decide_clause(_run(8, 0, 0), t)
        assert isinstance(result, PathCResult)
        assert result.decision is Gate2Decision.BENEFIT
        assert result.n_ties == 0
        assert result.net_lift_point == pytest.approx(1.0)
        assert result.ratification_id == "RAT-0001"

    def test_tie_heavy_win_is_held_below_the_effect_floor(self) -> None:
        """The case the scalar rule alone gets wrong, and the reason for Path C.

        7 wins, 1 loss, 30 ties. The conditional posterior is Beta(8, 2), a
        strong q, and the scalar rule sees nothing to object to. The net lift
        is 0.158, under the registered delta_min. Gate 2 declines to certify a
        benefit, which is the correct reading: the clause wins when it does
        anything at all, and it almost never does anything at all.
        """
        t = registered_thresholds(RAT_0001)
        decision = _run(7, 1, 30)
        result = decide_clause(decision, t)

        # The conditional posterior is genuinely strong ...
        assert decision.posterior_alpha == 8.0
        assert decision.posterior_beta == 2.0
        # ... and the net lift is genuinely small.
        assert result.net_lift_point < t.delta_min
        assert result.decision is not Gate2Decision.BENEFIT

    def test_ties_reach_the_decision_rather_than_being_discarded(self) -> None:
        """Same discordant table, different tie count, different decision.

        This is the property that distinguishes Path C from a plain drop-ties
        recompute. Dropping ties would make these two runs indistinguishable;
        Gate 2 keeps the tie count in the pooled tie cell, so the second run
        cannot certify a benefit the first can.
        """
        t = registered_thresholds(RAT_0001)
        few = decide_clause(_run(8, 0, 0), t)
        many = decide_clause(_run(8, 0, 24), t)

        assert (few.x_full_wins, few.x_ablated_wins) == (many.x_full_wins, many.x_ablated_wins)
        assert few.decision is Gate2Decision.BENEFIT
        assert many.decision is not Gate2Decision.BENEFIT
        assert many.n_ties == 24

    def test_harm_is_available_and_is_not_a_forced_call(self) -> None:
        """The rule is three-sided: a loss-heavy table can reach HARM."""
        t = registered_thresholds(RAT_0001)
        result = decide_clause(_run(0, 20, 0), t)
        assert result.decision is Gate2Decision.HARM

    def test_zero_comparisons_is_unresolved_not_a_crash(self) -> None:
        """An empty run has no table; Gate 2's defined zero-discordant branch."""
        t = registered_thresholds(RAT_0001)
        result = decide_clause(_run(0, 0, 0), t)
        assert result.decision is Gate2Decision.UNRESOLVED
        assert result.n_pairs == 1  # degenerate design, not a special case

    def test_region_masses_sum_to_one(self) -> None:
        t = registered_thresholds(RAT_0001)
        for case in ((8, 0, 0), (7, 1, 30), (2, 6, 4), (0, 0, 12)):
            result = decide_clause(_run(*case), t)
            total = (
                result.region_probs.p_benefit
                + result.region_probs.p_harm
                + result.region_probs.p_equivalent
            )
            assert total == pytest.approx(1.0), f"case {case}"

    def test_result_is_reproducible_from_its_own_fields(self) -> None:
        """The result carries the table it was decided on, so a reader can redo it."""
        t = registered_thresholds(RAT_0001)
        result = decide_clause(_run(6, 2, 10), t)
        assert result.x_full_wins == 6
        assert result.x_ablated_wins == 2
        assert result.n_ties == 10
        assert result.n_pairs == 18
        assert result.net_lift_point == pytest.approx((6 - 2) / 18)


class TestThresholdProvenance:
    def test_thresholds_are_not_hardcoded_in_the_module(self) -> None:
        """Static guard: no Gate-2 threshold literal appears in path_c.py.

        The by-reference requirement is an acceptance criterion of #368, and
        a criterion nothing tests is a criterion that decays. This reads the
        source because that is where the violation would appear.
        """
        source = (REPO_ROOT / "src" / "skill_harness" / "ablation" / "path_c.py").read_text(
            encoding="utf-8"
        )
        code_lines = [
            line
            for line in source.splitlines()
            if "gamma=" in line or "delta_min=" in line or "q_min=" in line
        ]
        for line in code_lines:
            assert "0.9" not in line and "0.2" not in line and "0.7" not in line, (
                f"a registered threshold looks hard-coded in path_c.py: {line.strip()!r}"
            )

    def test_a_different_record_produces_a_different_design(self) -> None:
        """Proves the values follow the record rather than a constant."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _record(Path(tmp), thresholds="gamma: 0.75\ndelta_min: 0.35\nq_min: 0.80\n")
            t = registered_thresholds(path)
        assert isinstance(t, RegisteredGate2Thresholds)
        assert (t.gamma, t.delta_min, t.q_min) == (0.75, 0.35, 0.80)

        real = registered_thresholds(RAT_0001)
        assert (t.gamma, t.delta_min, t.q_min) != (real.gamma, real.delta_min, real.q_min)


class TestRunnerWiring:
    """Path C must be REACHED by the production runner, not merely importable.

    A code review of this migration found the module complete, tested, and
    called by nothing, while the invariant document already claimed a
    tie-bearing clause was decided by it. These tests exist so that gap cannot
    reopen silently: they assert the wiring, not the arithmetic.
    """

    def test_run_ablation_accepts_a_ratification_reference(self) -> None:
        """The runner's entry point takes the record Path C consumes."""
        import inspect

        from skill_harness.ablation.runner import AblationRunner

        params = inspect.signature(AblationRunner.run_ablation).parameters
        assert "ratification_path" in params

    def test_run_config_records_the_ratification_id(self) -> None:
        """#368 acceptance: the id reaches the runner config, hence config_json.

        A stored run must say which registration its clause decisions were made
        under. Without this a reader cannot retrieve the thresholds that
        produced a verdict.
        """
        import json

        from skill_harness.ablation.runner import RunConfig

        config = RunConfig(
            run_id="r1",
            skill_id="s1",
            clauses=[],
            subject_model="claude-sonnet-4-6",
            user_message="m",
            ratification_id="RAT-0001",
            ratification_path="docs/ratifications/RAT-0001-git-pull-rebase-trap.md",
        )
        payload = json.loads(config.to_json())
        assert payload["ratification_id"] == "RAT-0001"
        assert payload["ratification_path"].endswith("RAT-0001-git-pull-rebase-trap.md")

        # The key is present even with no record, so an unregistered run is
        # distinguishable from a row written before the field existed.
        bare = RunConfig(
            run_id="r2",
            skill_id="s1",
            clauses=[],
            subject_model="claude-sonnet-4-6",
            user_message="m",
        )
        bare_payload = json.loads(bare.to_json())
        assert "ratification_id" in bare_payload
        assert bare_payload["ratification_id"] is None

        # And it survives a round trip.
        assert RunConfig.from_json(config.to_json()).ratification_id == "RAT-0001"

    def test_absent_ratification_is_a_typed_refusal_not_a_silence(self) -> None:
        """A clause with no registered thresholds must SAY so.

        This is the failure mode the whole module guards: a missing Path C
        decision and a Path C decision of BENEFIT must never render the same
        way. ClauseResult.path_c is None here, and the reason field is what
        stops a reader treating that as the floor having been cleared.
        """
        from skill_harness.ablation.runner import ClauseResult
        from skill_harness.ablation.stopping import StoppingReason

        result = ClauseResult(
            clause_id="c1",
            stopping_reason=StoppingReason.PASSED,
            stop_decision=_run(8, 0, 16),
            samples_collected=24,
            length_confounded=False,
            path_c=None,
            path_c_unavailable_reason="no_ratification_reference",
        )
        assert result.path_c is None
        assert result.path_c_unavailable_reason == "no_ratification_reference"

    def test_the_decision_helper_is_reached_from_a_stop_decision(self) -> None:
        """The runner's own helper turns a StopDecision into a Path C result.

        Exercises AblationRunner._decide_path_c directly rather than through a
        paid sampling loop: the wiring under test is the thresholds-to-decision
        step, and no subject call is needed to prove it runs.
        """
        from skill_harness.ablation.runner import AblationRunner

        runner = AblationRunner.__new__(AblationRunner)
        runner._path_c_thresholds = registered_thresholds(RAT_0001)
        runner._path_c_unavailable_reason = None

        decision = _run(8, 0, 16)
        result, reason = runner._decide_path_c(decision)

        assert reason is None
        assert result is not None
        assert result.ratification_id == "RAT-0001"
        # The scalar rule PASSES this clause; the registered floor does not.
        assert decision.stopping_reason is not None
        assert result.decision is not Gate2Decision.BENEFIT

    def test_unresolved_thresholds_are_reported_not_defaulted(self) -> None:
        from skill_harness.ablation.runner import AblationRunner

        runner = AblationRunner.__new__(AblationRunner)
        runner._path_c_thresholds = None
        runner._path_c_unavailable_reason = "unregistered_thresholds"

        result, reason = runner._decide_path_c(_run(8, 0, 0))
        assert result is None
        assert reason == "unregistered_thresholds"
