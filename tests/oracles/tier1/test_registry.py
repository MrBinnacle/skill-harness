"""Tests for Tier-1 metric registry (A14, A33).

RED tests for:
- Tier1Metric Pydantic strict model
- register_metric() auto-downgrade when mechanical_validity_test_passed=False
- registry returns registered metrics by name
- duplicate registration raises ValueError
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from skill_harness.oracles.tier1.registry import (
    OracleTier,
    Tier1Metric,
    get_metric,
    list_metrics,
    register_metric,
)

# ---------------------------------------------------------------------------
# Tier1Metric model construction
# ---------------------------------------------------------------------------


def test_tier1_metric_construction_valid() -> None:
    """Tier1Metric accepts valid inputs."""
    m = Tier1Metric(
        name="test_metric",
        version="1.0",
        implementation_hash="abc123",
        mechanical_validity_test_passed=True,
        tier=OracleTier.TIER1,
    )
    assert m.name == "test_metric"
    assert m.tier == OracleTier.TIER1


def test_tier1_metric_rejects_extra_fields() -> None:
    """Tier1Metric extra='forbid' rejects unknown keys."""
    with pytest.raises(ValidationError):
        Tier1Metric(  # type: ignore[call-arg]
            name="x",
            version="1.0",
            implementation_hash="abc",
            mechanical_validity_test_passed=True,
            tier=OracleTier.TIER1,
            unknown_field="oops",
        )


def test_tier1_metric_is_frozen() -> None:
    """Tier1Metric is immutable (frozen=True)."""
    m = Tier1Metric(
        name="x",
        version="1.0",
        implementation_hash="abc",
        mechanical_validity_test_passed=True,
        tier=OracleTier.TIER1,
    )
    with pytest.raises(Exception):  # ValidationError or AttributeError depending on pydantic
        m.name = "y"  # type: ignore[misc]


def test_tier1_metric_rejects_nul_in_name() -> None:
    """Tier1Metric name field rejects NUL bytes."""
    with pytest.raises(ValidationError):
        Tier1Metric(
            name="bad\x00name",
            version="1.0",
            implementation_hash="abc",
            mechanical_validity_test_passed=True,
            tier=OracleTier.TIER1,
        )


# ---------------------------------------------------------------------------
# register_metric — auto-downgrade
# ---------------------------------------------------------------------------


def test_register_metric_keeps_tier1_when_validity_passes() -> None:
    """register_metric keeps tier=TIER1 when mechanical_validity_test_passed=True."""
    m = register_metric(
        name="__test_valid__",
        version="1.0",
        implementation_hash="abc",
        mechanical_validity_test_passed=True,
    )
    assert m.tier == OracleTier.TIER1


def test_register_metric_downgrades_to_tier2_when_validity_fails() -> None:
    """register_metric auto-downgrades to TIER2 when mechanical_validity_test_passed=False."""
    m = register_metric(
        name="__test_invalid__",
        version="1.0",
        implementation_hash="abc",
        mechanical_validity_test_passed=False,
    )
    assert m.tier == OracleTier.TIER2


def test_register_metric_duplicate_raises() -> None:
    """register_metric raises ValueError when the name is already registered."""
    register_metric(
        name="__test_dup__",
        version="1.0",
        implementation_hash="abc",
        mechanical_validity_test_passed=True,
    )
    with pytest.raises(ValueError, match="already registered"):
        register_metric(
            name="__test_dup__",
            version="1.0",
            implementation_hash="abc",
            mechanical_validity_test_passed=True,
        )


def test_get_metric_returns_registered() -> None:
    """get_metric returns the Tier1Metric that was registered."""
    register_metric(
        name="__test_get__",
        version="1.0",
        implementation_hash="abc",
        mechanical_validity_test_passed=True,
    )
    m = get_metric("__test_get__")
    assert m is not None
    assert m.name == "__test_get__"


def test_get_metric_returns_none_for_unknown() -> None:
    """get_metric returns None for an unregistered name."""
    result = get_metric("__does_not_exist__")
    assert result is None


def test_list_metrics_includes_registered() -> None:
    """list_metrics returns all registered metrics."""
    register_metric(
        name="__test_list__",
        version="1.0",
        implementation_hash="abc",
        mechanical_validity_test_passed=True,
    )
    names = [m.name for m in list_metrics()]
    assert "__test_list__" in names
