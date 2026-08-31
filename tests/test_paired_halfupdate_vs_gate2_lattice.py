"""The half-update scalar and the Gate-2 lattice are not the same measurement.

Falsification-plan item 3. Paired ingest maps each Full-versus-Null epoch to an observation
in `{1.0, 0.5, 0.0}`. The aggregation engine pools those scalars into
`ClauseObservations(w, n)` and fits a Beta. Gate 2 instead requires the discordant pair
`(x_f, x_n)`, Full-only wins and Null-only wins, and forbids scalar half-update state for its
estimand.

Both are fed by the same 2x2 outcome table, so a reader can reasonably assume they carry the
same information. They do not, and this module pins exactly where the difference bites.

The collapse
------------
A 2x2 table is `(x_f, x_n, both_pass, both_fail)`. The half-update encoding sends a Full-only
win to 1.0, a Null-only win to 0.0, and BOTH tie cells to 0.5. So it retains only

    w = x_f + ties/2,   n = the total pair count

where `ties = both_pass + both_fail`. The two tie cells mean opposite outcomes, everything
worked and nothing worked, and are already indistinguishable at that point.

The map is many-to-one across the discordant cells as well. Replacing two ties with one
Full-only win and one Null-only win leaves `w` unchanged:

    (x_f + 1) + (ties - 2)/2 == x_f + ties/2

So `(x_f, x_n, ties)` and `(x_f + 1, x_n + 1, ties - 2)` are the *same* half-update state and
*different* Gate-2 tables. Everything downstream of the pooling step, including the
posterior, `p_win_gt_threshold`, the PASS rule in `docs/INVARIANTS.md` section 1, and
`paired_verdict`, sees one state where Gate 2 sees a distinct table per discordant split.

What was measured
-----------------
Enumerating every table at a fixed pair count and grouping by half-update state:

| n_pairs | half-update states | states holding tables Gate 2 decides differently |
| ---     | ---                | ---                                             |
| 8       | 17                 | 0                                               |
| 12      | 25                 | 2                                               |
| 20      | 41                 | 9                                               |
| 40      | 81                 | 19                                              |

The zero at `n_pairs = 8` matters as much as the rest. The divergence is not visible at the
smallest design, so an argument conducted at small n would conclude the two agree. It has to
be measured across the grid, which is why this module sweeps rather than spot-checks.

A worked case, pinned below: at `n_pairs = 12` the single half-update state `w = 9.5, n = 12`
contains `(x_f=7, x_n=0, ties=5)`, which Gate 2 calls BENEFIT, and `(x_f=9, x_n=2, ties=1)`,
which Gate 2 calls UNRESOLVED. Identical scalar state, opposite discordant verdicts.

What this module asserts, and what it does not
----------------------------------------------
It asserts that the divergence is real, structural, and non-empty above the smallest design.
It does NOT assert that either estimand is wrong. They answer different questions, and
`docs/PRD.md` section 14.3 still marks the tie encoding provisional. The failure guarded
against is the two silently converging or silently drifting further apart without the change
being noticed, and a reader concluding from a passing half-update that Gate 2 would agree.

`paired_verdict`'s own docstring records that Path B has never fired to date, so nothing here
claims to describe observed production behaviour.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Final

import pytest

from skill_harness.aggregation.fit import ClauseObservations, fit_skill
from skill_harness.oc import Gate2Design, MMESpec
from skill_harness.oc.gate2 import Gate2Decision, gate2_decide
from skill_harness.subject.ingest import _observation

# The locked PASS rule: a clause passes when P(win_rate > 0.60) >= 0.95
# (docs/INVARIANTS.md section 1).
PASS_PROB_THRESHOLD: Final[float] = 0.95

GAMMA: Final[float] = 0.90
DELTA_MIN: Final[float] = 0.20
Q_MIN: Final[float] = 0.70

# Measured divergence counts, per the table in the module docstring. Pinned so that a change
# to either estimand moves a number here and has to be explained in a diff.
EXPECTED_SPLIT_STATE_COUNTS: Final[dict[int, int]] = {8: 0, 12: 2, 20: 9, 40: 19}


def _design(n_pairs: int) -> Gate2Design:
    return Gate2Design(n_pairs=n_pairs, gamma=GAMMA, mme=MMESpec(delta_min=DELTA_MIN, q_min=Q_MIN))


def _observations(x_f: int, x_n: int, ties: int) -> list[float]:
    """Return the per-epoch observations production would write for this table.

    The encoding is taken from `subject.ingest._observation` rather than restated here. A
    detector that reimplemented the map would keep passing after production changed it, which
    is the failure this whole module is about.
    """
    return (
        [_observation(1.0, 0.0)] * x_f
        + [_observation(0.0, 1.0)] * x_n
        + [_observation(1.0, 1.0)] * ties
    )


def _half_update_state(x_f: int, ties: int, n_pairs: int) -> tuple[float, int]:
    """Return the (w, n) the aggregation engine would pool this table into.

    `w` is the sum of the observations and `n` their count, matching
    `aggregation/engine.py`, which builds `ClauseObservations(w=sum(...), n=len(...))`.
    """
    x_n = n_pairs - x_f - ties
    observations = _observations(x_f, x_n, ties)
    return (sum(observations), len(observations))


def _half_update_pass_probability(x_f: int, ties: int, n_pairs: int) -> float:
    """Return P(win_rate > 0.60) for the pooled half-update state of one table."""
    w, n = _half_update_state(x_f, ties, n_pairs)
    result = fit_skill([ClauseObservations(clause_id="clause", w=w, n=n)])
    return result.posteriors[0].p_win_gt_threshold


def _tables(n_pairs: int) -> list[tuple[int, int, int]]:
    """Return every (x_f, x_n, ties) table with the given total pair count."""
    return [
        (x_f, x_n, n_pairs - x_f - x_n)
        for x_f in range(n_pairs + 1)
        for x_n in range(n_pairs + 1 - x_f)
    ]


def _states_with_split_decisions(
    n_pairs: int,
) -> dict[tuple[float, int], set[Gate2Decision]]:
    """Return half-update states whose tables Gate 2 does not decide identically."""
    design = _design(n_pairs)
    by_state: defaultdict[tuple[float, int], set[Gate2Decision]] = defaultdict(set)
    for x_f, x_n, ties in _tables(n_pairs):
        by_state[_half_update_state(x_f, ties, n_pairs)].add(gate2_decide(design, x_f, x_n))
    return {state: decisions for state, decisions in by_state.items() if len(decisions) > 1}


def test_the_enumeration_is_not_empty() -> None:
    """Anti-vacuity: every assertion below quantifies over these tables."""
    for n_pairs in EXPECTED_SPLIT_STATE_COUNTS:
        tables = _tables(n_pairs)
        expected = (n_pairs + 1) * (n_pairs + 2) // 2
        assert len(tables) == expected, (
            f"enumerating tables at n_pairs={n_pairs} produced {len(tables)}, expected "
            f"{expected}; the sweep is not covering the simplex"
        )


def test_swapping_two_ties_for_a_win_and_a_loss_is_invisible_to_the_half_update() -> None:
    """The collapse itself, asserted as arithmetic rather than as a claim.

    This is the mechanism behind every divergence below. If it ever stops holding, the
    encoding changed and the rest of this module needs rereading.
    """
    n_pairs = 20
    for x_f, _, ties in _tables(n_pairs):
        if ties < 2:
            continue
        original = _half_update_state(x_f, ties, n_pairs)
        shifted = _half_update_state(x_f + 1, ties - 2, n_pairs)
        assert original == shifted, (
            f"expected (x_f={x_f}, ties={ties}) and (x_f={x_f + 1}, ties={ties - 2}) to pool "
            f"to the same half-update state; got {original} and {shifted}"
        )


@pytest.mark.parametrize("n_pairs", sorted(EXPECTED_SPLIT_STATE_COUNTS))
def test_the_number_of_ambiguous_half_update_states_is_the_measured_one(
    n_pairs: int,
) -> None:
    """Pin how many half-update states hold tables Gate 2 decides differently.

    The count at n_pairs=8 is zero, and that row is deliberately kept. It records that the
    divergence is invisible at the smallest design, so a future argument that the two
    estimands agree cannot be settled by testing there.
    """
    measured = len(_states_with_split_decisions(n_pairs))
    expected = EXPECTED_SPLIT_STATE_COUNTS[n_pairs]
    assert measured == expected, (
        f"at n_pairs={n_pairs}, {measured} half-update states hold tables that Gate 2 "
        f"decides differently; {expected} were measured when this was written. Either "
        "estimand changed, or the tie encoding changed. Both need explaining before this "
        "number is updated."
    )


def test_one_half_update_state_holds_both_a_benefit_and_an_unresolved_table() -> None:
    """The worked case: identical scalar state, opposite Gate-2 verdicts.

    This is the whole of item 3 in one assertion. The half-update pools these two tables into
    the same `(w, n)`, so they produce the same posterior, the same `p_win_gt_threshold` and
    the same PASS decision, while Gate 2 separates them.
    """
    n_pairs = 12
    design = _design(n_pairs)

    benefit_table = (7, 0, 5)
    unresolved_table = (9, 2, 1)

    assert _half_update_state(benefit_table[0], benefit_table[2], n_pairs) == _half_update_state(
        unresolved_table[0], unresolved_table[2], n_pairs
    ), "the two pinned tables no longer pool to the same half-update state"

    assert _half_update_pass_probability(
        benefit_table[0], benefit_table[2], n_pairs
    ) == _half_update_pass_probability(unresolved_table[0], unresolved_table[2], n_pairs), (
        "the two pinned tables no longer produce the same posterior probability, so the "
        "half-update can now tell them apart"
    )

    assert gate2_decide(design, benefit_table[0], benefit_table[1]) is Gate2Decision.BENEFIT
    assert (
        gate2_decide(design, unresolved_table[0], unresolved_table[1]) is Gate2Decision.UNRESOLVED
    )


def test_a_table_can_clear_gate2_without_clearing_the_half_update_pass_rule() -> None:
    """Gate 2 reads BENEFIT on tables the locked PASS rule does not pass.

    Measured at n_pairs=8: `(x_f=6, x_n=0, ties=2)` and `(x_f=7, x_n=1, ties=0)` both reach
    P(win_rate > 0.60) = 0.9295, below the locked 0.95, while Gate 2 calls both BENEFIT.

    The direction matters. Item 3 anticipated the opposite hazard, a tie-heavy table
    approaching PASSED without discordant benefit. At these designs the half-update is the
    more conservative of the two, and no table passes the half-update rule while Gate 2
    withholds BENEFIT. That is worth pinning, because it is the reverse of what was expected.
    """
    n_pairs = 8
    design = _design(n_pairs)

    passes_half_but_not_gate2 = [
        (x_f, x_n, ties)
        for x_f, x_n, ties in _tables(n_pairs)
        if _half_update_pass_probability(x_f, ties, n_pairs) >= PASS_PROB_THRESHOLD
        and gate2_decide(design, x_f, x_n) is not Gate2Decision.BENEFIT
    ]
    assert not passes_half_but_not_gate2, (
        "a table clears the locked half-update PASS rule while Gate 2 withholds BENEFIT: "
        f"{passes_half_but_not_gate2}. That is the hazard item 3 registered, and it was not "
        "reachable at n_pairs=8 when this was written."
    )

    gate2_benefit_but_not_half_pass = [
        (x_f, x_n, ties)
        for x_f, x_n, ties in _tables(n_pairs)
        if gate2_decide(design, x_f, x_n) is Gate2Decision.BENEFIT
        and _half_update_pass_probability(x_f, ties, n_pairs) < PASS_PROB_THRESHOLD
    ]
    assert gate2_benefit_but_not_half_pass == [(6, 0, 2), (7, 1, 0)], (
        "the set of tables Gate 2 calls BENEFIT while the half-update withholds PASS has "
        f"changed; measured {gate2_benefit_but_not_half_pass}, expected "
        "[(6, 0, 2), (7, 1, 0)]"
    )
