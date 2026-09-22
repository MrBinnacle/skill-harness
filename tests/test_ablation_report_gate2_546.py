"""The rendered ablation report displays the Gate-2 decision (#546).

Before this ticket the report printed the scalar ``StoppingReason`` alone. A
clause that clears the scalar rule and fails the registered effect-size floor
therefore printed as PASSED, which is a manufactured verdict on the surface a
reader sees. ``docs/INVARIANTS.md`` section 8 named the gap in its own words:
"NOT wired: the report surface."

The decision already existed on ``ClauseResult.path_c`` (#368 Path C). These
tests pin the display of it:

- A clause that passes the scalar rule and fails the floor renders the Gate-2
  verdict and never the word PASSED.
- A clause that passes both renders PASSED, unchanged from before #546.
- A clause decided with no registered thresholds renders PASSED marked as
  scalar-only, with the typed refusal reason beside it. The absence of a floor
  decision is never displayed as a clause clearing the floor.
- Every row carries a Gate-2 cell, including FAILED and UNMEASURED rows.
"""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from skill_harness.ablation.path_c import PathCResult
from skill_harness.ablation.runner import ClauseResult
from skill_harness.ablation.stopping import StopDecision, StoppingReason
from skill_harness.aggregation.status import UnmeasuredSubReason
from skill_harness.cli.main import cli
from skill_harness.oc.gate2 import Gate2Decision, Gate2RegionProbs
from tests.ratification_fixture import ratified_exec_args

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _invoke(*args: str, env: dict[str, str] | None = None) -> Any:
    runner = CliRunner()
    merged_env: dict[str, str] = {"COLUMNS": "260"}
    if env is not None:
        merged_env.update(env)
    has_evidence_db = "--evidence-db" in args
    has_runtime_db = "--runtime-db" in args
    if has_evidence_db and has_runtime_db:
        return runner.invoke(cli, list(args), env=merged_env)
    # `run ablation` defaults to ./evidence.db and ./runtime.db. A private cwd
    # keeps parallel workers from sharing one SQLite file ("database is locked").
    # Explicit --evidence-db/--runtime-db flags provide defence in depth (#600).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd, contextlib.chdir(cwd):
        db_args = []
        if not has_evidence_db:
            db_args.extend(["--evidence-db", str(Path(cwd) / "evidence.db")])
        if not has_runtime_db:
            db_args.extend(["--runtime-db", str(Path(cwd) / "runtime.db")])
        return runner.invoke(cli, [*list(args[:2]), *db_args, *list(args[2:])], env=merged_env)


def _render(results: list[ClauseResult]) -> Any:
    """Run the report surface over prepared clause results."""
    with patch("skill_harness.cli.main._execute_ablation_run", return_value=results):
        return _invoke(
            "run",
            "ablation",
            "skill-test",
            *ratified_exec_args("skill-test"),
            env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
        )


def _tie_heavy_decision() -> StopDecision:
    """A clause that PASSES the scalar rule on a table the floor rejects.

    Seven wins and one loss out of thirty-eight comparisons: an excellent
    conditional win rate q, and a net lift of (7 - 1) / 38 = 0.158, below the
    registered delta_min of 0.20. This is the inversion ``path_c.py`` was built
    for, written as a fixture so the surface has a subject.
    """
    return StopDecision(
        should_stop=True,
        stopping_reason=StoppingReason.PASSED,
        posterior_alpha=8.0,
        posterior_beta=2.0,
        p_win_rate_exceeds_threshold=0.96,
        n_samples=38,
        w_accumulator=7.0,
        n_discordant=8,
        x_full_wins=7,
        x_ablated_wins=1,
        n_ties=30,
    )


def _decisive_decision() -> StopDecision:
    """A clause that passes the scalar rule and clears the floor."""
    return StopDecision(
        should_stop=True,
        stopping_reason=StoppingReason.PASSED,
        posterior_alpha=10.0,
        posterior_beta=2.0,
        p_win_rate_exceeds_threshold=0.97,
        n_samples=11,
        w_accumulator=9.0,
        n_discordant=11,
        x_full_wins=9,
        x_ablated_wins=2,
        n_ties=0,
    )


def _path_c(
    decision: Gate2Decision,
    stop_decision: StopDecision,
    *,
    ratification_id: str = "RAT-0001",
) -> PathCResult:
    n_pairs = max(stop_decision.n_samples, 1)
    return PathCResult(
        decision=decision,
        region_probs=Gate2RegionProbs(p_benefit=0.30, p_harm=0.01, p_equivalent=0.69),
        ratification_id=ratification_id,
        x_full_wins=stop_decision.x_full_wins,
        x_ablated_wins=stop_decision.x_ablated_wins,
        n_ties=stop_decision.n_ties,
        n_pairs=n_pairs,
        net_lift_point=(stop_decision.x_full_wins - stop_decision.x_ablated_wins) / n_pairs,
    )


# ---------------------------------------------------------------------------
# AC 1: the floor-rejected clause never prints PASSED
# ---------------------------------------------------------------------------


class TestScalarPassFailingTheFloor:
    def test_equivalent_clause_does_not_render_passed(self) -> None:
        """The inversion case: scalar PASSED, Gate-2 EQUIVALENT."""
        stop_decision = _tie_heavy_decision()
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-tie-heavy",
                    stopping_reason=StoppingReason.PASSED,
                    stop_decision=stop_decision,
                    samples_collected=38,
                    length_confounded=False,
                    verdict_id="verdict-tie-heavy",
                    path_c=_path_c(Gate2Decision.EQUIVALENT, stop_decision),
                )
            ]
        )

        assert "PASSED" not in result.output, (
            f"A clause below the registered floor must not print PASSED.\nOutput:\n{result.output}"
        )
        assert "EQUIVALENT" in result.output, (
            f"The Gate-2 verdict must be displayed.\nOutput:\n{result.output}"
        )

    def test_harm_clause_does_not_render_passed(self) -> None:
        """A Gate-2 HARM decision displaces the scalar pass as well."""
        stop_decision = _tie_heavy_decision()
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-harm",
                    stopping_reason=StoppingReason.PASSED,
                    stop_decision=stop_decision,
                    samples_collected=38,
                    length_confounded=False,
                    verdict_id="verdict-harm",
                    path_c=_path_c(Gate2Decision.HARM, stop_decision),
                )
            ]
        )

        assert "PASSED" not in result.output, (
            f"A Gate-2 HARM clause must not print PASSED.\nOutput:\n{result.output}"
        )
        assert "HARM" in result.output, f"Output:\n{result.output}"

    def test_unresolved_clause_does_not_render_passed(self) -> None:
        """Gate-2 UNRESOLVED is not a pass, and is not displayed as one."""
        stop_decision = _tie_heavy_decision()
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-unresolved",
                    stopping_reason=StoppingReason.PASSED,
                    stop_decision=stop_decision,
                    samples_collected=38,
                    length_confounded=False,
                    verdict_id="verdict-unresolved",
                    path_c=_path_c(Gate2Decision.UNRESOLVED, stop_decision),
                )
            ]
        )

        assert "PASSED" not in result.output, (
            f"A Gate-2 UNRESOLVED clause must not print PASSED.\nOutput:\n{result.output}"
        )
        assert "UNRESOLVED" in result.output, f"Output:\n{result.output}"


# ---------------------------------------------------------------------------
# AC 2: the clause that passes both renders unchanged
# ---------------------------------------------------------------------------


class TestClauseThatPassesBoth:
    def test_benefit_clause_still_renders_passed(self) -> None:
        stop_decision = _decisive_decision()
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-benefit",
                    stopping_reason=StoppingReason.PASSED,
                    stop_decision=stop_decision,
                    samples_collected=11,
                    length_confounded=False,
                    verdict_id="verdict-benefit",
                    path_c=_path_c(Gate2Decision.BENEFIT, stop_decision),
                )
            ]
        )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        assert "PASSED" in result.output, (
            f"A clause clearing both rules still renders PASSED.\nOutput:\n{result.output}"
        )
        assert "BENEFIT" in result.output, (
            f"The Gate-2 decision is displayed beside it.\nOutput:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# AC 3: the unapplied floor is a typed refusal on the surface
# ---------------------------------------------------------------------------


class TestFloorNotApplied:
    def test_absent_path_c_marks_the_pass_as_scalar_only(self) -> None:
        """No registered thresholds means no floor decision, and the report says so."""
        stop_decision = _decisive_decision()
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-no-record",
                    stopping_reason=StoppingReason.PASSED,
                    stop_decision=stop_decision,
                    samples_collected=11,
                    length_confounded=False,
                    verdict_id="verdict-no-record",
                    path_c=None,
                    path_c_unavailable_reason="no_ratification_reference",
                )
            ]
        )

        assert "no_ratification_reference" in result.output, (
            "The typed refusal reason must be displayed, not silently omitted.\n"
            f"Output:\n{result.output}"
        )
        assert "scalar only" in result.output, (
            "An unfloored pass must be marked as scalar-only so a reader cannot "
            f"read it as a clause clearing the floor.\nOutput:\n{result.output}"
        )

    def test_absent_path_c_prints_the_floor_caveat(self) -> None:
        stop_decision = _decisive_decision()
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-no-record",
                    stopping_reason=StoppingReason.PASSED,
                    stop_decision=stop_decision,
                    samples_collected=11,
                    length_confounded=False,
                    verdict_id="verdict-no-record",
                    path_c=None,
                    path_c_unavailable_reason="no_ratification_reference",
                )
            ]
        )

        assert "registered net lift" in result.output, (
            "The report must state that it makes no registered net-lift claim for "
            f"those rows.\nOutput:\n{result.output}"
        )

    def test_missing_reason_is_a_defect_not_a_fourth_refusal(self) -> None:
        """A result with no decision and no reason names the gap as a gap.

        The refusal vocabulary has exactly three members. A result carrying
        neither a decision nor a reason is a defect in the result object, and
        the cell says so rather than printing a fourth member of a closed
        vocabulary.
        """
        stop_decision = _decisive_decision()
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-defective",
                    stopping_reason=StoppingReason.PASSED,
                    stop_decision=stop_decision,
                    samples_collected=11,
                    length_confounded=False,
                    verdict_id="verdict-defective",
                    path_c=None,
                    path_c_unavailable_reason=None,
                )
            ]
        )

        assert "no reason recorded" in result.output, (
            f"A missing reason is displayed as a defect.\nOutput:\n{result.output}"
        )
        assert "unknown" not in result.output, (
            "A missing reason must not be given a plausible-looking vocabulary word.\n"
            f"Output:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# AC 1 (scope): every row carries a Gate-2 cell
# ---------------------------------------------------------------------------


class TestEveryRowCarriesTheCell:
    def test_failed_row_carries_the_gate2_cell(self) -> None:
        stop_decision = StopDecision(
            should_stop=True,
            stopping_reason=StoppingReason.FAILED,
            posterior_alpha=2.0,
            posterior_beta=10.0,
            p_win_rate_exceeds_threshold=0.02,
            n_samples=11,
            w_accumulator=2.0,
            n_discordant=11,
            x_full_wins=2,
            x_ablated_wins=9,
            n_ties=0,
        )
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-failed",
                    stopping_reason=StoppingReason.FAILED,
                    stop_decision=stop_decision,
                    samples_collected=11,
                    length_confounded=False,
                    verdict_id="verdict-failed",
                    path_c=_path_c(Gate2Decision.HARM, stop_decision),
                )
            ]
        )

        assert "FAILED" in result.output, f"Output:\n{result.output}"
        assert "HARM" in result.output, (
            f"A FAILED row still displays its Gate-2 decision.\nOutput:\n{result.output}"
        )

    def test_unmeasured_row_carries_the_refusal_reason(self) -> None:
        stop_decision = StopDecision(
            should_stop=True,
            stopping_reason=StoppingReason.UNDERPOWERED_NMAX,
            posterior_alpha=1.0,
            posterior_beta=1.0,
            p_win_rate_exceeds_threshold=0.0,
            n_samples=0,
            w_accumulator=0.0,
            n_discordant=0,
            x_full_wins=0,
            x_ablated_wins=0,
            n_ties=0,
        )
        result = _render(
            [
                ClauseResult(
                    clause_id="clause-unmeasured",
                    stopping_reason=StoppingReason.UNDERPOWERED_NMAX,
                    stop_decision=stop_decision,
                    samples_collected=0,
                    length_confounded=False,
                    unmeasured_reason=UnmeasuredSubReason.TIER2_UNCALIBRATED,
                    verdict_id=None,
                    path_c=None,
                    path_c_unavailable_reason="no_sampling",
                )
            ]
        )

        assert result.exit_code == 2, f"UNMEASURED must exit 2:\n{result.output}"
        assert "no_sampling" in result.output, (
            f"An UNMEASURED row displays why no floor decision exists.\nOutput:\n{result.output}"
        )
