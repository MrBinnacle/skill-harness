"""Typed exceptions for the aggregation engine (Track E.2).

Three exception types, each with a structured code and optional payload:
- PreconditionError  — raised at engine entry when DB state prevents aggregation.
- MalformedRunConfig — raised when runs.config_json is structurally invalid.
- ConvergenceFailure — raised when EB-MoM produces invalid hyperparameters
                       (caller translates to fallback; not normally surfaced to user).
"""

from __future__ import annotations


class PreconditionError(Exception):
    """Aggregation entry precondition not met.

    Attributes
    ----------
    code : str
        ``"incomplete_runs"`` — one or more runs for skill_id lack completed_at.
        ``"no_completed_runs"`` — no ablation runs with completed_at exist for skill_id.
    payload : list[str] | None
        When code == "incomplete_runs": list of incomplete run_ids.
        When code == "no_completed_runs": None.

    E.3 catches these and emits exit 1 with a user-facing message.
    """

    def __init__(self, code: str, payload: list[str] | None = None) -> None:
        self.code = code
        self.payload = payload
        super().__init__(f"PreconditionError({code!r}, {payload!r})")


class MalformedRunConfig(Exception):
    """runs.config_json is structurally invalid or missing required fields.

    Attributes
    ----------
    reason : str
        Human-readable description of what is missing/invalid.
    run_id : str
        The run_id whose config_json triggered the error.
    """

    def __init__(self, reason: str, run_id: str) -> None:
        self.reason = reason
        self.run_id = run_id
        super().__init__(f"MalformedRunConfig({reason!r}, run_id={run_id!r})")


class ConvergenceFailure(Exception):
    """EB-MoM hyperprior estimation failed (alpha_hat <= 0 or beta_hat <= 0).

    Raised internally by fit.py; the engine translates it into BH-FDR fallback.
    Callers of aggregate_skill() do NOT normally see this exception.

    Attributes
    ----------
    reason : str
        ``"alpha_le_zero"`` | ``"beta_le_zero"`` | ``"var_below_threshold"``
    alpha_hat : float
        Estimated alpha (may be <= 0).
    beta_hat : float
        Estimated beta (may be <= 0).
    sample_mean : float
    sample_var : float
    """

    def __init__(
        self,
        reason: str,
        alpha_hat: float,
        beta_hat: float,
        sample_mean: float,
        sample_var: float,
    ) -> None:
        self.reason = reason
        self.alpha_hat = alpha_hat
        self.beta_hat = beta_hat
        self.sample_mean = sample_mean
        self.sample_var = sample_var
        super().__init__(
            f"ConvergenceFailure({reason!r}, "
            f"alpha_hat={alpha_hat:.4f}, beta_hat={beta_hat:.4f}, "
            f"sample_mean={sample_mean:.4f}, sample_var={sample_var:.6f})"
        )
