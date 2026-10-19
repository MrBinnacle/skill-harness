"""Tests for skill_harness/semantics.py — estimand registry + decision-semantics
vocabulary (#51, PR-1; resolution record #36).

The registry is a labeling + routing decision over the two EXISTING subject
layers, not a new runner: agentic paired (skill AVAILABLE) = treatment-policy;
ablation forced-injection = hypothetical. ICH E9(R1) vocabulary; "per-protocol"
is banned repo-wide with an EMPTY allowlist. One falsifying test per registry
rule, plus the repo-wide token-ban scan (structural-bans pattern — pytest-visible
now; the declarative drift-check CI row DC-3 lands with its own ticket and stays
the enforcement of record once live).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from skill_harness.semantics import (
    BANNED_DECISION_TERMS,
    BANNED_TERM_ALLOWLIST,
    HAND_INVOKED_NULL_ARM_SEMANTIC,
    PRE_REGISTRY_ESTIMAND_LABEL,
    DeliveryMechanism,
    Estimand,
    PiCHandling,
    RegisteredScope,
    pi_c_handling,
)

# ---------------------------------------------------------------------------
# Estimand enum — exactly two, E9(R1) names (#36 item 1)
# ---------------------------------------------------------------------------


def test_exactly_two_estimands_no_third_invented() -> None:
    """#51 AC: the two subject layers ARE the two estimands — a third member here
    would be an invented decision target with no realizing arm."""
    assert {e.value for e in Estimand} == {"treatment-policy", "hypothetical"}
    assert len(Estimand) == 2


def test_estimand_names_are_the_e9r1_vocabulary() -> None:
    assert Estimand.TREATMENT_POLICY.value == "treatment-policy"
    assert Estimand.HYPOTHETICAL.value == "hypothetical"


# ---------------------------------------------------------------------------
# Delivery mechanism — 4-class taxonomy (#36 item 2)
# ---------------------------------------------------------------------------


def test_delivery_mechanism_is_the_four_class_taxonomy() -> None:
    assert {m.value for m in DeliveryMechanism} == {
        "model-pull",
        "hand-invoked",
        "hook-nudged",
        "hook-blocked",
    }
    assert len(DeliveryMechanism) == 4


# ---------------------------------------------------------------------------
# π_c handling per mechanism (#36 item 3: detector lanes vs structural π_c ≡ 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mechanism", [DeliveryMechanism.MODEL_PULL, DeliveryMechanism.HOOK_NUDGED])
def test_pull_and_nudge_lanes_measure_pi_c(mechanism: DeliveryMechanism) -> None:
    assert pi_c_handling(mechanism) is PiCHandling.MEASURED


@pytest.mark.parametrize(
    "mechanism", [DeliveryMechanism.HAND_INVOKED, DeliveryMechanism.HOOK_BLOCKED]
)
def test_frozen_and_blocked_lanes_have_structural_pi_c(mechanism: DeliveryMechanism) -> None:
    """hand-invoked (frozen-task) and hook-blocked force invocation by
    construction — π_c ≡ 1, nothing to detect."""
    assert pi_c_handling(mechanism) is PiCHandling.STRUCTURAL_ONE


# ---------------------------------------------------------------------------
# RegisteredScope — the full scope tuple every verdict carries (#51 AC)
# ---------------------------------------------------------------------------


def _scope(**overrides: object) -> RegisteredScope:
    base: dict[str, object] = {
        "skill": "example-skill",
        "task_family": "example-family",
        "estimand": Estimand.TREATMENT_POLICY,
        "delivery_mechanism": DeliveryMechanism.MODEL_PULL,
    }
    base.update(overrides)
    return RegisteredScope(**base)  # type: ignore[arg-type]


def test_scope_tuple_carries_all_four_dimensions() -> None:
    s = _scope()
    assert (s.skill, s.task_family, s.estimand, s.delivery_mechanism) == (
        "example-skill",
        "example-family",
        Estimand.TREATMENT_POLICY,
        DeliveryMechanism.MODEL_PULL,
    )


def test_scope_derives_pi_c_handling_from_mechanism() -> None:
    assert _scope().pi_c is PiCHandling.MEASURED
    assert (
        _scope(
            delivery_mechanism=DeliveryMechanism.HOOK_BLOCKED,
        ).pi_c
        is PiCHandling.STRUCTURAL_ONE
    )


def test_scope_label_is_estimand_then_mechanism() -> None:
    """#36's ratified verdict-line shape: 'treatment-policy, hook-nudged, ...'."""
    s = _scope(delivery_mechanism=DeliveryMechanism.HOOK_NUDGED)
    assert s.label() == "treatment-policy, hook-nudged"


@pytest.mark.parametrize("blank", ["", "   "])
def test_scope_refuses_blank_skill_or_family(blank: str) -> None:
    with pytest.raises(ValueError, match="skill"):
        _scope(skill=blank)
    with pytest.raises(ValueError, match="task_family"):
        _scope(task_family=blank)


# ---------------------------------------------------------------------------
# Hand-invoked class — frozen-task default, Null-arm semantic MUST be declared
# (#36 item 5; #51 AC)
# ---------------------------------------------------------------------------


def test_hand_invoked_treatment_policy_requires_declared_null_arm_semantic() -> None:
    """A hand-invoked treatment-policy registration is the frozen-task design;
    its Null arm is NOT a neutral baseline, so the semantic must be declared."""
    with pytest.raises(ValueError, match=r"[Nn]ull-arm semantic"):
        _scope(delivery_mechanism=DeliveryMechanism.HAND_INVOKED)


@pytest.mark.parametrize("blank", ["", "   "])
def test_hand_invoked_null_arm_semantic_must_be_nonblank(blank: str) -> None:
    with pytest.raises(ValueError, match=r"[Nn]ull-arm semantic"):
        _scope(delivery_mechanism=DeliveryMechanism.HAND_INVOKED, null_arm_semantic=blank)


def test_hand_invoked_with_ratified_semantic_registers() -> None:
    s = _scope(
        delivery_mechanism=DeliveryMechanism.HAND_INVOKED,
        null_arm_semantic=HAND_INVOKED_NULL_ARM_SEMANTIC,
    )
    assert s.null_arm_semantic == "the invocation names an absent skill"
    assert s.pi_c is PiCHandling.STRUCTURAL_ONE


def test_hand_invoked_hypothetical_needs_no_null_arm_semantic() -> None:
    """The registered fallback for the class: hypothetical-only — the forced arm
    has no Null-arm counterfactual to declare."""
    s = _scope(
        estimand=Estimand.HYPOTHETICAL,
        delivery_mechanism=DeliveryMechanism.HAND_INVOKED,
    )
    assert s.null_arm_semantic is None


def test_other_mechanisms_need_no_null_arm_semantic() -> None:
    for mechanism in (
        DeliveryMechanism.MODEL_PULL,
        DeliveryMechanism.HOOK_NUDGED,
        DeliveryMechanism.HOOK_BLOCKED,
    ):
        assert _scope(delivery_mechanism=mechanism).null_arm_semantic is None


# ---------------------------------------------------------------------------
# Pre-registry label (historical observations carry honest n/a markers — #41)
# ---------------------------------------------------------------------------


def test_pre_registry_label_is_the_ratified_na_marker() -> None:
    assert PRE_REGISTRY_ESTIMAND_LABEL == "n/a (pre-registry observation)"


# ---------------------------------------------------------------------------
# Banned vocabulary — the surface the DC-3 drift row will consume (#51 AC)
# ---------------------------------------------------------------------------

_BANNED = "per-protocol"  # assembled once here; the scan below exempts this file


def test_banned_terms_contain_the_e9r1_ban_with_empty_allowlist() -> None:
    assert BANNED_DECISION_TERMS == (_BANNED,)
    assert frozenset() == BANNED_TERM_ALLOWLIST, (
        "the allowlist is EMPTY by ratified decision; it grows only by dated amendment"
    )


# Repo-wide scan (structural-bans pattern). The definition site (semantics.py)
# and this test file carry the literal token by necessity and are self-exempt —
# that is the same E1b self-exclusion the sqlite-connect ban uses, NOT an
# allowlist entry: BANNED_TERM_ALLOWLIST above stays empty.

_REPO_ROOT = Path(__file__).resolve().parent.parent
_THIS_FILE = Path(__file__).resolve()
_DEFINITION_SITE = _REPO_ROOT / "src" / "skill_harness" / "semantics.py"
# The DC-3 drift-check row (#53) and its tests carry the token in their own
# registered table / test data — same E1b structural exemption, not allowlist.
_DRIFT_CHECK_SITES = (
    _REPO_ROOT / "scripts" / "drift_check.py",
    _REPO_ROOT / "tests" / "test_drift_check.py",
)

_SCAN_ROOTS = ("src", "tests", "docs", "scripts", "examples")
_SCAN_SUFFIXES = {".py", ".md", ".txt", ".toml", ".yaml", ".yml"}


def _iter_scannable_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        base = _REPO_ROOT / root
        if not base.is_dir():
            continue
        files.extend(
            p
            for p in base.rglob("*")
            if p.is_file() and p.suffix in _SCAN_SUFFIXES and "__pycache__" not in p.parts
        )
    files.extend(p for p in _REPO_ROOT.glob("*.md"))
    files.append(_REPO_ROOT / "pyproject.toml")
    return files


def test_banned_term_absent_repo_wide() -> None:
    """#51 AC: "per-protocol" is gone from the repo — code, docs, docstrings.
    Case-insensitive token scan over every prose/code surface; failures list every
    hit (never first-fail)."""
    pattern = re.compile(re.escape(_BANNED), re.IGNORECASE)
    violations: list[str] = []
    for path in _iter_scannable_files():
        if path in {_THIS_FILE, _DEFINITION_SITE, *_DRIFT_CHECK_SITES}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                violations.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}")
    assert violations == [], (
        f"banned decision term {_BANNED!r} found (allowlist is empty): {violations}"
    )
