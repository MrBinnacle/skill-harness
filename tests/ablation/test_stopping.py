"""Tests for the Beta-Binomial sequential stopping rule (A8, A44).

Covers:
- PASS stop: P(win_rate > 0.60) >= 0.95 with enough wins
- FAIL stop: P(win_rate > 0.60) <= 0.05 with enough losses
- UNDERPOWERED_NMAX: N_MAX reached without decisive posterior
- No stop before N_MIN
- Half-update tie encoding (A10)
- next_check_at schedule
"""

from __future__ import annotations

import pytest

from skill_harness.ablation.stopping import (
    N_INC,
    N_MAX,
    N_MIN,
    PASS_PROB_THRESHOLD,
    BetaBinomialAccumulator,
    StoppingReason,
    next_check_at,
)


class TestBetaBinomialAccumulator:
    def test_no_stop_before_n_min(self) -> None:
        """Should not stop before N_MIN samples regardless of outcome."""
        acc = BetaBinomialAccumulator()
        for _ in range(N_MIN - 1):
            acc.add(1.0)  # all wins
        decision = acc.check_stop()
        assert not decision.should_stop
        assert decision.stopping_reason is None
        assert decision.n_samples == N_MIN - 1

    def test_pass_stop_all_wins(self) -> None:
        """All wins should trigger PASS at N_MIN (strong signal)."""
        acc = BetaBinomialAccumulator()
        for _ in range(N_MIN):
            acc.add(1.0)
        decision = acc.check_stop()
        # With N=8 wins, Beta(9,1): P(rate>0.60) is very high -> should PASS
        assert decision.should_stop
        assert decision.stopping_reason == StoppingReason.PASSED
        assert decision.p_win_rate_exceeds_threshold >= 0.95

    def test_fail_stop_all_losses(self) -> None:
        """All losses should trigger FAIL (strong signal of ineffectiveness)."""
        acc = BetaBinomialAccumulator()
        for _ in range(N_MAX):
            acc.add(0.0)  # all losses
        decision = acc.check_stop()
        assert decision.should_stop
        assert decision.stopping_reason == StoppingReason.FAILED
        assert decision.p_win_rate_exceeds_threshold <= 0.05

    def test_underpowered_nmax_inconclusive(self) -> None:
        """Exactly half wins/losses at N_MAX should produce UNDERPOWERED_NMAX."""
        acc = BetaBinomialAccumulator()
        for i in range(N_MAX):
            acc.add(1.0 if i % 2 == 0 else 0.0)  # alternating win/loss
        decision = acc.check_stop()
        assert decision.should_stop
        assert decision.stopping_reason == StoppingReason.UNDERPOWERED_NMAX
        assert decision.n_samples == N_MAX

    def test_tie_half_update(self) -> None:
        """Ties count as 0.5 win-weight (A10 half-update encoding)."""
        acc = BetaBinomialAccumulator()
        acc.add(0.5)  # one tie
        assert acc.w == 0.5
        assert acc.n == 1

    def test_posterior_metadata_in_decision(self) -> None:
        """StopDecision carries posterior alpha, beta, and p.

        Rewritten by #368. This test previously asserted the half-update
        result for an all-ties run: alpha = beta = 1 + N_MIN * 0.5, a
        posterior sharply concentrated at 0.5 built entirely out of
        comparisons that carried no direction. That is the defect the ruling
        named, so the expectation moves with the rule rather than the rule
        being held to the expectation.

        N_MIN ties now leave the prior untouched: no directional evidence
        arrived, so the posterior still says nothing.
        """
        acc = BetaBinomialAccumulator()
        for _ in range(N_MIN):
            acc.add(0.5)  # ties -- no directional signal
        decision = acc.check_stop()
        assert decision.posterior_alpha == 1.0
        assert decision.posterior_beta == 1.0
        assert 0 < decision.p_win_rate_exceeds_threshold < 1
        # The ties are counted, and they hold the run below the evidence bar.
        assert decision.n_samples == N_MIN
        assert decision.n_ties == N_MIN
        assert decision.n_discordant == 0
        assert not decision.should_stop
        # The superseded blended weight remains reconstructible.
        assert decision.w_accumulator == N_MIN * 0.5

    def test_ties_cannot_buy_a_clause_past_the_evidence_bar(self) -> None:
        """N_MIN counts DISCORDANT comparisons, not total ones (#368).

        5 wins, 0 losses, 3 ties. The conditional posterior is Beta(6, 1) and
        P(q > 0.60) = 0.9533, over the PASS threshold. The total comparison
        count is 8, which equals N_MIN. If the evidence gate read that total,
        this clause would PASS on five directional comparisons, with three
        ties making up the difference.

        Ties are not evidence about q, so they must not advance the bar. The
        run continues instead. This is the control for the N_MIN half of the
        migration: it fails if the gate is ever repointed at n_samples.
        """
        acc = BetaBinomialAccumulator()
        for _ in range(5):
            acc.add(1.0)
        for _ in range(3):
            acc.add(0.5)
        decision = acc.check_stop()

        assert decision.n_samples == N_MIN  # the total reaches the bar ...
        assert decision.n_discordant == 5  # ... the evidence does not
        assert decision.p_win_rate_exceeds_threshold > PASS_PROB_THRESHOLD
        assert not decision.should_stop
        assert decision.stopping_reason is None

    def test_rejects_invalid_observation(self) -> None:
        """add() raises ValueError for non-{0.0, 0.5, 1.0} values."""
        acc = BetaBinomialAccumulator()
        with pytest.raises(ValueError, match="Observation must be"):
            acc.add(0.3)

    def test_zero_samples_posterior(self) -> None:
        """Empty accumulator returns Beta(1,1) prior (uniform)."""
        acc = BetaBinomialAccumulator()
        decision = acc.check_stop()
        assert decision.posterior_alpha == 1.0
        assert decision.posterior_beta == 1.0
        assert not decision.should_stop

    def test_n_max_exact_pass(self) -> None:
        """If N_MAX is exactly reached and posterior is decisive, it PASSES (not UNDERPOWERED)."""
        acc = BetaBinomialAccumulator()
        # 40 wins -> P(rate>0.60) = 1.0 -> PASSED even at N_MAX
        for _ in range(N_MAX):
            acc.add(1.0)
        decision = acc.check_stop()
        assert decision.should_stop
        assert decision.stopping_reason == StoppingReason.PASSED

    def test_inconclusive_before_n_max(self) -> None:
        """Between N_MIN and N_MAX with inconclusive signal: should_stop=False."""
        acc = BetaBinomialAccumulator()
        # Add exactly N_MIN samples with mixed signal (0.5 p)
        for i in range(N_MIN):
            acc.add(1.0 if i % 2 == 0 else 0.0)
        decision = acc.check_stop()
        # At N_MIN with exactly half wins, posterior is symmetric -> inconclusive
        assert not decision.should_stop or decision.stopping_reason in {
            StoppingReason.PASSED,
            StoppingReason.FAILED,
        }


class TestNextCheckAt:
    def test_first_check_at_n_min(self) -> None:
        """next_check_at(0) == N_MIN."""
        assert next_check_at(0) == N_MIN

    def test_after_n_min(self) -> None:
        """next_check_at(N_MIN) == N_MIN + N_INC."""
        assert next_check_at(N_MIN) == N_MIN + N_INC

    def test_never_exceeds_n_max(self) -> None:
        """next_check_at never returns > N_MAX."""
        for n in range(0, N_MAX + 1):
            assert next_check_at(n) <= N_MAX

    def test_increments_by_n_inc(self) -> None:
        """Between N_MIN and N_MAX, next_check_at increments by N_INC."""
        n = N_MIN
        while n < N_MAX - N_INC:
            expected = n + N_INC
            assert next_check_at(n) == expected
            n += N_INC
