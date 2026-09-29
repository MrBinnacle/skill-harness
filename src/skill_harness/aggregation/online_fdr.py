"""Online FDR control through the normalised LORDdep procedure (#644).

FDR is controlled at q = 0.05 under arbitrary dependence (Javanmard &
Montanari 2018, Theorem 3.7, Example 3.8), with the xi sequence normalised
to sum to at most 1.  The module owns the ledger state and the receipt facts
that let a reader reconstruct a KEEP discovery.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from skill_harness.aggregation.verdict import KeepCutVerdict

DEFAULT_Q: float = 0.05
DEFAULT_W0: float = 0.025
DEFAULT_B0: float = 0.025
_N_GRID: int = 10**6
_P_VALUE_BISECT_ITERS: int = 48


def _compute_K() -> float:
    """Compute K from the pinned finite sum and a bound on its remaining tail."""
    partial_sum = math.fsum(1.0 / (j * math.log(max(j, 2)) ** 3) for j in range(1, _N_GRID + 1))
    tail_bound = 1.0 / (2.0 * math.log(_N_GRID) ** 2)
    return 1.0 / (partial_sum + tail_bound)


K: float = _compute_K()


def xi(j: int) -> float:
    """Return the jth element of the normalised LORDdep spending sequence."""
    if j < 1:
        raise ValueError(f"j must be >= 1, got {j!r}")
    return K / (j * math.log(max(j, 2)) ** 3)


def anytime_valid_p_value(observations: Sequence[float], margin: float = 0.20) -> float:
    """Invert the one-sided betting confidence sequence for H0: d <= margin.

    The returned value is the smallest alpha for which the lower confidence
    bound exceeds ``margin``.  It is valid at every data-dependent stop because
    it inverts the same anytime-valid sequence used for the bound.
    """
    if not 0.0 <= margin <= 1.0 or math.isnan(margin):
        raise ValueError(f"margin must be in [0, 1], got {margin!r}")

    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

    upper = 1.0 - 1e-12
    if one_sided_betting_bound(observations, alpha=upper, side="lower") <= margin:
        return 1.0

    lower = 1e-12
    for _ in range(_P_VALUE_BISECT_ITERS):
        alpha = (lower + upper) / 2.0
        bound = one_sided_betting_bound(observations, alpha=alpha, side="lower")
        if bound > margin:
            upper = alpha
        else:
            lower = alpha
    return upper


@dataclass(frozen=True)
class CardPValues:
    """The two contrast p-values and their card-level intersection p-value."""

    anytime_valid_p: float
    p_fn: float
    p_fp: float

    def __post_init__(self) -> None:
        """Refuse malformed card p-values before they can reach the ledger."""
        values = (self.anytime_valid_p, self.p_fn, self.p_fp)
        if any(not 0.0 <= value <= 1.0 or math.isnan(value) for value in values):
            raise ValueError("card p-values must be finite values in [0, 1]")
        if not math.isclose(
            self.anytime_valid_p,
            max(self.p_fn, self.p_fp),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("anytime_valid_p must equal max(p_fn, p_fp)")


def card_anytime_valid_p_values(
    fn_observations: Sequence[float],
    fp_observations: Sequence[float],
    margin: float = 0.20,
) -> CardPValues:
    """Compute the card p-value as max(p_FN, p_FP)."""
    p_fn = anytime_valid_p_value(fn_observations, margin)
    p_fp = anytime_valid_p_value(fp_observations, margin)
    return CardPValues(anytime_valid_p=max(p_fn, p_fp), p_fn=p_fn, p_fp=p_fp)


@dataclass(frozen=True)
class Multiplicity:
    """SERS multiplicity facts persisted with an admitted KEEP receipt."""

    ledger_hypothesis_id: str
    hypothesis_index: int
    discovery_type: str
    procedure: str
    target_fdr: float
    test_level: float
    anytime_valid_p: float
    p_fn: float
    p_fp: float
    initial_wealth: float
    payout: float
    wealth_before: float
    wealth_after: float
    shared_control_family_id: str
    batch_order: int

    def as_dict(self) -> dict[str, str | int | float]:
        """Return the JSON-compatible SERS representation."""
        return {
            "ledger_hypothesis_id": self.ledger_hypothesis_id,
            "hypothesis_index": self.hypothesis_index,
            "discovery_type": self.discovery_type,
            "procedure": self.procedure,
            "target_fdr": self.target_fdr,
            "test_level": self.test_level,
            "anytime_valid_p": self.anytime_valid_p,
            "p_fn": self.p_fn,
            "p_fp": self.p_fp,
            "initial_wealth": self.initial_wealth,
            "payout": self.payout,
            "wealth_before": self.wealth_before,
            "wealth_after": self.wealth_after,
            "shared_control_family_id": self.shared_control_family_id,
            "batch_order": self.batch_order,
        }


@dataclass
class NormalisedLORDdep:
    """Pinned LORDdep state for a pre-registered sequence of card hypotheses."""

    _hypothesis_index: int = field(default=0, init=False, repr=False)
    _order_cursor: int = field(default=0, init=False, repr=False)
    _discovery_index: int = field(default=0, init=False, repr=False)
    _wealth: float = field(default=DEFAULT_W0, init=False, repr=False)
    _discovery_wealth: float = field(default=DEFAULT_W0, init=False, repr=False)
    _discovery_count: int = field(default=0, init=False, repr=False)
    _order: list[str] = field(default_factory=list, init=False, repr=False)

    @property
    def hypothesis_index(self) -> int:
        """LORDdep's global test index t: the number of KEEPs that were tested."""
        return self._hypothesis_index

    @property
    def discovery_index(self) -> int:
        """Global index of the most recent discovery, or zero before one exists."""
        return self._discovery_index

    @property
    def wealth(self) -> float:
        """Current wealth after the most recently processed hypothesis."""
        return self._wealth

    @property
    def discovery_count(self) -> int:
        """Number of rejected hypotheses in the ledger."""
        return self._discovery_count

    @property
    def order(self) -> tuple[str, ...]:
        """The pre-registered hypothesis IDs in their immutable ledger order."""
        return tuple(self._order)

    def set_order(self, order: Sequence[str]) -> None:
        """Register the hypothesis order before any result is available."""
        if self._hypothesis_index > 0 or self._order_cursor > 0:
            raise ValueError("Cannot set order after tests have been run")
        if not order:
            raise ValueError("order must contain at least one hypothesis")
        if any(not hypothesis_id for hypothesis_id in order):
            raise ValueError("order must contain non-empty hypothesis IDs")
        if len(set(order)) != len(order):
            raise ValueError("order must not repeat a hypothesis ID")
        self._order = list(order)

    def test_level(self) -> float:
        """Return the alpha level for the next global hypothesis position."""
        if self._hypothesis_index >= len(self._order):
            raise ValueError("No more hypotheses in the order")
        global_index = self._hypothesis_index + 1
        wealth_at_last_discovery = (
            DEFAULT_W0 if self._discovery_index == 0 else self._discovery_wealth
        )
        return xi(global_index) * wealth_at_last_discovery

    def step(self, p_value: float) -> bool:
        """Process the next registered hypothesis and return whether it is rejected."""
        if not 0.0 <= p_value <= 1.0 or math.isnan(p_value):
            raise ValueError(f"p_value must be in [0, 1], got {p_value!r}")
        alpha = self.test_level()
        global_index = self._hypothesis_index + 1
        rejected = p_value <= alpha
        self._wealth = self._wealth - alpha + (DEFAULT_B0 if rejected else 0.0)
        self._hypothesis_index = global_index
        if rejected:
            self._discovery_index = global_index
            self._discovery_wealth = self._wealth
            self._discovery_count += 1
        return rejected

    def record_verdict(
        self,
        verdict: KeepCutVerdict,
        *,
        ledger_hypothesis_id: str,
        card_p_values: CardPValues,
        b_world_condition: bool,
        shared_control_family_id: str,
        batch_order: int,
    ) -> Multiplicity | None:
        """Admit a registered KEEP or pass a CUT over its registered slot.

        Every verdict must arrive in the registered order.  A KEEP that meets
        the B-world condition is tested at the next global index t; a rejected
        one receives its multiplicity record.  A CUT or a failed B-world
        condition moves past its registered slot and leaves t and the wealth
        unchanged, so it neither spends nor advances the ledger.
        """
        if self._order_cursor >= len(self._order):
            raise ValueError("No more hypotheses in the order")
        if self._order[self._order_cursor] != ledger_hypothesis_id:
            raise ValueError("ledger_hypothesis_id does not match the registered order")
        if verdict is not KeepCutVerdict.KEEP or not b_world_condition:
            self._order_cursor += 1
            return None
        if not shared_control_family_id:
            raise ValueError("shared_control_family_id must be non-empty")
        if batch_order < 1:
            raise ValueError("batch_order must be >= 1")

        wealth_before = self._wealth
        test_level = self.test_level()
        rejected = self.step(card_p_values.anytime_valid_p)
        self._order_cursor += 1
        if not rejected:
            return None
        return Multiplicity(
            ledger_hypothesis_id=ledger_hypothesis_id,
            hypothesis_index=self._hypothesis_index,
            discovery_type=KeepCutVerdict.KEEP.value,
            procedure="LORDdep",
            target_fdr=DEFAULT_Q,
            test_level=test_level,
            anytime_valid_p=card_p_values.anytime_valid_p,
            p_fn=card_p_values.p_fn,
            p_fp=card_p_values.p_fp,
            initial_wealth=DEFAULT_W0,
            payout=DEFAULT_B0,
            wealth_before=wealth_before,
            wealth_after=self._wealth,
            shared_control_family_id=shared_control_family_id,
            batch_order=batch_order,
        )
