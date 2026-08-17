"""Pre-spend identity binding compiler (#263)."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from skill_harness.aggregation import binding
from skill_harness.aggregation.binding import (
    BINDING_ALGO_VERSION,
    BindingRecord,
    compile_binding,
)
from skill_harness.oc import FrontierRow, Gate2Design, Gate2NullErrorBound, MMESpec
from skill_harness.semantics import (
    HAND_INVOKED_NULL_ARM_SEMANTIC,
    DeliveryMechanism,
    Estimand,
    RegisteredScope,
)
from skill_harness.subject import HarnessPin
from skill_harness.task_frontier import load_manifest


def test_realistic_rat_declared_identity_compiles_from_component_objects() -> None:
    manifest = load_manifest(
        {
            "task_family_id": "append-only-evidence-design",
            "task_family_version": "1",
            "frozen_hashes": {
                "generator": "gen-sha-e2",
                "fixture": "fix-sha-e2",
                "oracle": "ora-sha-e2",
                "harness": "har-sha-e2",
                "code": "cod-sha-e2",
            },
            "phase_partition": {
                "calibration": [],
                "confirmation": [],
                "matched": ["lineage-1"],
            },
            "confirmation_attempt_budget": 0,
        }
    )
    scope = RegisteredScope(
        skill="append-only-evidence-design",
        task_family="append-only-evidence-design",
        estimand=Estimand.TREATMENT_POLICY,
        delivery_mechanism=DeliveryMechanism.HAND_INVOKED,
        null_arm_semantic=HAND_INVOKED_NULL_ARM_SEMANTIC,
    )
    design = Gate2Design(
        n_pairs=20,
        gamma=0.90,
        mme=MMESpec(delta_min=0.20, q_min=0.70),
    )
    frontier_row = FrontierRow(
        n_pairs=20,
        in_band=True,
        alpha_null=Gate2NullErrorBound(
            grid_max=0.031,
            certified_upper_bound=0.04,
        ),
        power_h1_min=0.82,
        power_h1_argmin=(0.5, 0.7),
        expected_n_null_max=18.25,
        expected_n_h1_max=16.75,
        worst_case_cost_usd=15.55,
        meets_candidate_alpha=True,
        meets_power_floor=True,
        feasible=True,
        ratifiable=True,
    )
    pin = HarnessPin(
        inspect_ai_version="0.3.245",
        inspect_swe_version="0.2.65",
        agent_version="1.0.98",
        model="anthropic/claude-sonnet-5",
        sandbox="docker",
        sandbox_image="aisiuk/inspect-tool-support@sha256:" + "a" * 64,
        cwd="/workspace",
        env={"LANG": "C.UTF-8"},
        disallowed_tools=("WebSearch",),
    )

    binding = compile_binding(
        scope=scope,
        manifest=manifest,
        design=design,
        frontier_row=frontier_row,
        budget_cap_cents=1555,
        harness_pin=pin,
    )

    assert binding.registered_scope == scope
    assert binding.task_family_id == manifest.task_family_id
    assert binding.task_family_version == manifest.task_family_version
    assert binding.frozen_hashes == manifest.frozen_hashes
    assert binding.gate2_design == design
    assert binding.frontier_row_hash
    assert binding.budget_cap_cents == 1555
    assert binding.harness_pin == pin
    assert binding.harness_pin_fingerprint == pin.fingerprint()
    assert len(binding.digest) == 64
    assert binding.canonical_bytes


def test_binding_record_is_a_frozen_value() -> None:
    fields = BindingRecord.__dataclass_fields__

    assert fields
    assert fields["registered_scope"].type == "RegisteredScope"
    assert fields["frozen_hashes"].type == "FrozenHashes"
    assert fields["gate2_design"].type == "Gate2Design"
    assert fields["harness_pin"].type == "HarnessPin"

    record = object.__new__(BindingRecord)
    with pytest.raises(FrozenInstanceError):
        record.__setattr__("digest", "replacement")


def test_binding_canonical_recipe_is_versioned_and_byte_stable() -> None:
    manifest_fields = {
        "task_family_id": "family",
        "task_family_version": "v1",
        "frozen_hashes": {
            "generator": "g",
            "fixture": "f",
            "oracle": "o",
            "harness": "h",
            "code": "c",
        },
        "phase_partition": {"calibration": [], "confirmation": [], "matched": []},
        "confirmation_attempt_budget": 0,
    }
    manifest = load_manifest(manifest_fields)
    permuted_manifest = load_manifest(dict(reversed(manifest_fields.items())))
    scope = RegisteredScope(
        skill="skill",
        task_family="family",
        estimand=Estimand.HYPOTHETICAL,
        delivery_mechanism=DeliveryMechanism.MODEL_PULL,
    )
    design = Gate2Design(n_pairs=6, gamma=0.9, mme=MMESpec(delta_min=0.2, q_min=0.7))
    row = FrontierRow(
        n_pairs=6,
        in_band=False,
        alpha_null=Gate2NullErrorBound(grid_max=0.03, certified_upper_bound=0.04),
        power_h1_min=0.8,
        power_h1_argmin=(0.5, 0.7),
        expected_n_null_max=5.0,
        expected_n_h1_max=4.0,
        worst_case_cost_usd=6.0,
        meets_candidate_alpha=True,
        meets_power_floor=True,
        feasible=True,
        ratifiable=True,
    )
    pin_fields: dict[str, Any] = {
        "inspect_ai_version": "a",
        "inspect_swe_version": "s",
        "agent_version": "1",
        "model": "m",
        "sandbox": "docker",
        "sandbox_image": "image@sha256:" + "a" * 64,
        "cwd": "/workspace",
        "env": {"Z": "last", "A": "first"},
        "disallowed_tools": ("WebSearch",),
    }
    pin = HarnessPin(**pin_fields)
    permuted_pin = HarnessPin(**dict(reversed(pin_fields.items())))

    first = compile_binding(
        scope=scope,
        manifest=manifest,
        design=design,
        frontier_row=row,
        budget_cap_cents=600,
        harness_pin=pin,
    )
    second = compile_binding(
        scope=scope,
        manifest=permuted_manifest,
        design=design,
        frontier_row=row,
        budget_cap_cents=600,
        harness_pin=permuted_pin,
    )

    decoded = json.loads(first.canonical_bytes)
    expected = json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert BINDING_ALGO_VERSION == "1"
    assert decoded["binding_algo_version"] == BINDING_ALGO_VERSION
    assert first.canonical_bytes == expected == second.canonical_bytes
    assert first.digest == hashlib.sha256(expected).hexdigest() == second.digest


def test_binding_module_public_functions_are_compile_only() -> None:
    public_functions = {
        name
        for name, value in vars(binding).items()
        if not name.startswith("_") and inspect.isfunction(value)
    }

    assert public_functions == {"compile_binding"}
