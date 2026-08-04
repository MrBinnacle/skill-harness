"""Article fingerprint — model pin required on every newly-minted verdict (#75).

An ``ArticleFingerprint`` pins the model a verdict was measured on so no cell
floats free of its measuring model. Primary form is ``model_snapshot``; when no
snapshot exists the fallback is a captured ``response_fingerprint`` plus a
``requalify_on_drift`` flag.

``drift_fingerprint`` is the stable token compared against the current fleet
model (precondition for the board's day-one stale badge). Historical /
pre-registry rows may lack a pin entirely (#41 no-retrofit) — those yield no
stale badge from this mechanism.
"""

from __future__ import annotations

import hashlib
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, model_validator


class VerdictPinColumns(NamedTuple):
    """Column values for ``oracle_verdicts`` model-pin fields (migration 0600)."""

    model_snapshot: str | None
    response_fingerprint: str | None
    requalify_on_drift: int
    drift_fingerprint: str


class ArticleFingerprint(BaseModel):
    """Mandatory model pin carried by every newly-minted verdict."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    model_snapshot: str | None = None
    response_fingerprint: str | None = None
    requalify_on_drift: bool = False

    @model_validator(mode="after")
    def _require_pin(self) -> ArticleFingerprint:
        if self.model_snapshot is not None and self.model_snapshot != "":
            return self
        if (
            self.response_fingerprint is not None
            and self.response_fingerprint != ""
            and self.requalify_on_drift
        ):
            return self
        raise ValueError(
            "ArticleFingerprint requires model_snapshot, or "
            "response_fingerprint with requalify_on_drift=True"
        )

    @property
    def drift_fingerprint(self) -> str:
        """Stable token for fleet-model drift detection."""
        if self.model_snapshot is not None and self.model_snapshot != "":
            payload = f"model_snapshot:{self.model_snapshot}"
        else:
            payload = f"response_fingerprint:{self.response_fingerprint}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_verdict_columns(self) -> VerdictPinColumns:
        """Column values for ``oracle_verdicts`` (migration 0600)."""
        return VerdictPinColumns(
            model_snapshot=self.model_snapshot,
            response_fingerprint=self.response_fingerprint,
            requalify_on_drift=1 if self.requalify_on_drift else 0,
            drift_fingerprint=self.drift_fingerprint,
        )


def fleet_drift_fingerprint(fleet_model: str) -> str:
    """Drift token for the current fleet model (stale-badge comparison target)."""
    return ArticleFingerprint(model_snapshot=fleet_model).drift_fingerprint


def is_stale_vs_fleet(stored_drift_fingerprint: str | None, current_fleet_model: str) -> bool:
    """True when a pinned verdict's model differs from the current fleet model.

    Historical rows with no drift fingerprint return False — they predate the
    pin and are not retrofitted with a stale badge from this mechanism.
    """
    if stored_drift_fingerprint is None:
        return False
    return stored_drift_fingerprint != fleet_drift_fingerprint(current_fleet_model)
