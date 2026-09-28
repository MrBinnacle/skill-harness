"""Online FDR control via normalised LORDdep procedure (#644).

Implements the LORDdep procedure with a normalised xi sequence whose sum is
at most 1, keeping the rule inside Theorem 3.7 of Javanmard & Montanari
(Annals of Statistics 2018; arXiv 1603.09000). The xi shape
``1 / (j * log^3(max(j, 2)))`` comes from the onlineFDR R package, but the
normalisation constant K and the absence of an alpha/b0 scaling factor make
this procedure differ from both the deprecated ``LORDdep()`` and the current
``LORD(version="dep")`` in that package.

Public constants
----------------
DEFAULT_Q
    Target FDR level (0.05).
DEFAULT_W0
    Initial wealth / b0 (0.025).
``NormalisedLORDdep`` is the procedure object.

Procedure
---------
- q = 0.05, w0 = b0 = 0.025, psi_j = b0.
- xi_j = K / (j * log(max(j, 2))^3), K = 1 / (S + T) where S is the sum
  over j = 1..10^6 and T is an upper bound on the tail.
- alpha_t = xi_t * W(tau_t). t is the GLOBAL hypothesis index (1-based),
  never t - tau. tau_t is the index of the most recent discovery before t,
  or 0 before any discovery. W(0) = w0.
- W(t) = W(t-1) - alpha_t + b0 * R_t. Never cap alpha_t.
- The hypothesis counter and the discovery counter are separate fields.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

DEFAULT_Q: float = 0.05
DEFAULT_W0: float = 0.025
DEFAULT_B0: float = 0.025

_N_GRID: int = 10**6

# ---------------------------------------------------------------------------
# Normalised xi sequence
# ---------------------------------------------------------------------------


def _compute_K() -> float:
    """Compute the normalisation constant K = 1/(S + T).

    S is the sum over j=1..10^6 of 1/(j*log^3(max(j,2))).
    T = 1/(2*log^2(10^6)) is an upper bound on the tail.
    K * (S + T) = 1 by construction.
    """
    S = 0.0
    for j in range(1, _N_GRID + 1):
        S += 1.0 / (j * math.log(max(j, 2)) ** 3)
    T = 1.0 / (2 * math.log(_N_GRID) ** 2)
    return 1.0 / (S + T)


K: float = _compute_K()


def xi(j: int) -> float:
    """Normalised LORDdep xi sequence element.

    xi_j = K / (j * log(max(j, 2))^3).
    sum over all j of xi_j <= 1.
    """
    if j < 1:
        raise ValueError(f"j must be >= 1, got {j!r}")
    return K / (j * math.log(max(j, 2)) ** 3)


# ---------------------------------------------------------------------------
# Procedure state
# ---------------------------------------------------------------------------


@dataclass(frozen=False)
class NormalisedLORDdep:
    """Normalised LORDdep online FDR procedure.

    Parameters are frozen at q = 0.05, w0 = b0 = 0.025.

    State fields (mutable, persisted in evidence store):
        _hypothesis_index: global hypothesis counter (1-based)
        _discovery_index: index of most recent discovery (0 = none)
        _wealth: current wealth W(t)
        _discovery_count: number of rejections
        _order: list of hypothesis indices in test order
    """

    q: float = DEFAULT_Q
    w0: float = DEFAULT_W0
    b0: float = DEFAULT_B0

    _hypothesis_index: int = field(default=0, init=False, repr=False)
    _discovery_index: int = field(default=0, init=False, repr=False)
    _wealth: float = field(default=0.0, init=False, repr=False)
    _discovery_count: int = field(default=0, init=False, repr=False)
    _order: list[int] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._wealth = self.w0

    @property
    def hypothesis_index(self) -> int:
        """Current hypothesis index (0 before first test)."""
        return self._hypothesis_index

    @property
    def discovery_index(self) -> int:
        """Index of most recent discovery (0 = none)."""
        return self._discovery_index

    @property
    def wealth(self) -> float:
        """Current wealth W(t)."""
        return self._wealth

    @property
    def discovery_count(self) -> int:
        """Number of rejections so far."""
        return self._discovery_count

    @property
    def order(self) -> tuple[int, ...]:
        """Hypothesis order (fixed before results are read)."""
        return tuple(self._order)

    def test_level(self, p_value: float) -> float:
        """Compute the test level for the next hypothesis.

        Parameters
        ----------
        p_value: float
            The p-value for the current hypothesis.

        Returns
        -------
        float
            The test level alpha_t = xi_t * W(tau_t).
        """
        if self._hypothesis_index >= len(self._order):
            raise ValueError("No more hypotheses in the order")
        t = self._order[self._hypothesis_index]
        tau_t = self._discovery_index
        W_tau = self.w0 if tau_t == 0 else self._wealth
        alpha_t = xi(t) * W_tau
        return alpha_t

    def step(self, p_value: float) -> bool:
        """Process one hypothesis test.

        Parameters
        ----------
        p_value: float
            The p-value for the current hypothesis.

        Returns
        -------
        bool
            True if the hypothesis is rejected (discovery).
        """
        if self._hypothesis_index >= len(self._order):
            raise ValueError("No more hypotheses in the order")
        t = self._order[self._hypothesis_index]
        tau_t = self._discovery_index
        W_tau = self.w0 if tau_t == 0 else self._wealth
        alpha_t = xi(t) * W_tau
        reject = p_value <= alpha_t
        R_t = 1 if reject else 0
        self._wealth = self._wealth - alpha_t + self.b0 * R_t
        self._hypothesis_index += 1
        if reject:
            self._discovery_index = t
            self._discovery_count += 1
        return reject

    def set_order(self, order: list[int]) -> None:
        """Set the hypothesis order. Must be called before any tests.

        Parameters
        ----------
        order: list[int]
            List of hypothesis indices (1-based).
        """
        if self._hypothesis_index > 0:
            raise ValueError("Cannot set order after tests have been run")
        self._order = list(order)


# ---------------------------------------------------------------------------
# Anytime-valid p-value
# ---------------------------------------------------------------------------


def anytime_valid_p_value(
    observations: list[float],
    margin: float,
    alpha_grid: list[float] | None = None,
) -> float:
    """Invert the betting confidence sequence to get the anytime-valid p-value.

    The p-value for H0: d <= margin is the smallest alpha at which the
    one-sided (1 - alpha) lower bound excludes margin.

    Parameters
    ----------
    observations: list[float]
        Sequence of bounded observations in [0, 1].
    margin: float
        The margin to test against (e.g., 0.20).
    alpha_grid: list[float] | None
        Grid of alpha values to search over.

    Returns
    -------
    float
        The anytime-valid p-value.
    """
    if alpha_grid is None:
        alpha_grid = [0.001 * i for i in range(1, 1000)]

    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

    for alpha in sorted(alpha_grid):
        bound = one_sided_betting_bound(observations, alpha=alpha, side="lower")
        if bound > margin:
            return alpha

    return 1.0
