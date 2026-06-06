"""Tier-1 metric registry (A14, A33).

Design decisions:
- Tier1Metric is a frozen Pydantic strict model (A24 discipline).
- register_metric() auto-downgrades to OracleTier.TIER2 when
  mechanical_validity_test_passed=False.  This enforces the invariant
  that a metric cannot self-declare Tier-1 without passing its offline
  validity gate.
- The registry is a module-level dict (functional style, A24).  No class
  with shared mutable state.
- Duplicate registration raises ValueError (intentional: metrics are
  versioned artifacts; silent overwrite would corrupt implementation_hash
  provenance).

Per CLAUDE.md metric-provenance invariant: every registered metric carries
name, version, and implementation_hash so frozen cases can be re-audited
when a metric changes.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

# ---------------------------------------------------------------------------
# Forbidden control-character pattern (reuses CLAUDE.md A24 discipline)
# ---------------------------------------------------------------------------

_FORBIDDEN_CTRL: Final = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _check_text(value: str, field_name: str = "value") -> str:
    """Reject NUL bytes and forbidden C0 control characters."""
    if _FORBIDDEN_CTRL.search(value):
        raise ValueError(
            f"{field_name}: contains forbidden control characters "
            "(NUL or C0 0x00-0x1F excluding \\t, \\n, \\r)"
        )
    return value


# ---------------------------------------------------------------------------
# OracleTier enum
# ---------------------------------------------------------------------------


class OracleTier(StrEnum):
    """Oracle tier per CLAUDE.md oracle-tiering invariant."""

    TIER1 = "tier1"  # Mechanical, deterministic, offline
    TIER2 = "tier2"  # Human-calibrated LLM judge
    TIER3 = "tier3"  # Real-world consequence (terminal authority)


# ---------------------------------------------------------------------------
# Tier1Metric model (A24 Pydantic strict)
# ---------------------------------------------------------------------------


class Tier1Metric(BaseModel):
    """Immutable descriptor for a registered Tier-1 oracle metric.

    Fields
    ------
    name : str
        Unique identifier; used as registry key.
    version : str
        Semantic version string.  Bump when implementation changes.
    implementation_hash : str
        SHA-256 hex of the metric's frozen data (e.g. wordlist file) or
        of implementation constants.  Stored in frozen regression cases so
        re-audit is possible after a metric version bump.
    mechanical_validity_test_passed : bool
        Set True only when (a) all bit-equality tests pass AND (b) no
        socket attempts were detected by pytest-socket.  If False,
        register_metric() auto-downgrades tier to TIER2.
    tier : OracleTier
        Resolved at registration time.  Do NOT set directly — use
        register_metric() which applies the auto-downgrade logic.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    name: str
    version: str
    implementation_hash: str
    mechanical_validity_test_passed: bool
    tier: OracleTier

    @field_validator("name", "version", "implementation_hash", mode="after")
    @classmethod
    def _no_forbidden_ctrl(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)


# ---------------------------------------------------------------------------
# Module-level registry (functional style, A24)
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Tier1Metric] = {}


def register_metric(
    *,
    name: str,
    version: str,
    implementation_hash: str,
    mechanical_validity_test_passed: bool,
) -> Tier1Metric:
    """Register a metric and return the resolved Tier1Metric descriptor.

    Auto-downgrade rule (A33): if ``mechanical_validity_test_passed`` is
    False, the returned metric has ``tier=OracleTier.TIER2`` regardless of
    the caller's intent.  The metric is still registered (so callers can
    inspect it), but aggregation will treat it as Tier-2.

    Raises
    ------
    ValueError
        If a metric with ``name`` is already registered.
    """
    if name in _REGISTRY:
        raise ValueError(
            f"Metric {name!r} is already registered. Use a new name or bump the version."
        )

    resolved_tier = OracleTier.TIER1 if mechanical_validity_test_passed else OracleTier.TIER2

    metric = Tier1Metric(
        name=name,
        version=version,
        implementation_hash=implementation_hash,
        mechanical_validity_test_passed=mechanical_validity_test_passed,
        tier=resolved_tier,
    )
    _REGISTRY[name] = metric
    return metric


def get_metric(name: str) -> Tier1Metric | None:
    """Return the Tier1Metric registered under ``name``, or None."""
    return _REGISTRY.get(name)


def list_metrics() -> list[Tier1Metric]:
    """Return all registered metrics in registration order."""
    return list(_REGISTRY.values())
