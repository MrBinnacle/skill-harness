"""Pre-spend identity binding compiler (#263)."""

from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from skill_harness.aggregation import binding
from skill_harness.aggregation.binding import (
    BINDING_ALGO_VERSION,
    BindingRecord,
    BindingVerificationDivergence,
    BindingVerificationMatch,
    BindingVerificationRefusal,
    BindingVerificationRefusalReason,
    DivergenceReason,
    UnverifiableAxis,
    compile_binding,
    verify_binding,
)
from skill_harness.aggregation.matched_bridge import MatchedGate2Decision, aggregate_matched_gate2
from skill_harness.oc import FrontierRow, Gate2Design, Gate2NullErrorBound, MMESpec
from skill_harness.semantics import (
    HAND_INVOKED_NULL_ARM_SEMANTIC,
    DeliveryMechanism,
    Estimand,
    RegisteredScope,
)
from skill_harness.subject import HarnessPin
from skill_harness.task_frontier import (
    Arm,
    FrozenHashes,
    Observation,
    Phase,
    StoredObservation,
    admit,
    load_manifest,
    matched_evidence,
)


def _compile_minimal() -> BindingRecord:
    manifest = load_manifest(
        {
            "task_family_id": "family",
            "task_family_version": "v1",
            "frozen_hashes": {
                "generator": "g",
                "fixture": "f",
                "oracle": "o",
                "harness": "h",
                "code": "c",
            },
            "phase_partition": {
                "calibration": [],
                "confirmation": [],
                "matched": [],
            },
            "confirmation_attempt_budget": 0,
        }
    )
    return compile_binding(
        scope=RegisteredScope(
            skill="skill",
            task_family="family",
            estimand=Estimand.HYPOTHETICAL,
            delivery_mechanism=DeliveryMechanism.MODEL_PULL,
        ),
        manifest=manifest,
        design=Gate2Design(n_pairs=6, gamma=0.9, mme=MMESpec(delta_min=0.2, q_min=0.7)),
        frontier_row=FrontierRow(
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
        ),
        budget_cap_cents=600,
        harness_pin=HarnessPin(
            inspect_ai_version="a",
            inspect_swe_version="s",
            agent_version="1",
            model="m",
            sandbox="docker",
            sandbox_image="image@sha256:" + "a" * 64,
            cwd="/workspace",
            env={"A": "first"},
            disallowed_tools=("WebSearch",),
        ),
    )


def _stored(
    observation_id: str,
    *,
    task_family_id: str = "family",
    task_family_version: str = "v1",
    phase: Phase = Phase.MATCHED,
    generator_fingerprint: str = "g",
    oracle_fingerprint: str = "o",
    admissibility_state: str = "admissible",
    inadmissibility_reason: str | None = None,
) -> StoredObservation:
    return StoredObservation(
        observation_id=observation_id,
        task_family_id=task_family_id,
        task_family_version=task_family_version,
        semantic_lineage_id="lineage",
        phase=phase,
        instance_id="instance",
        arm=Arm.FULL,
        passed=True,
        generator_fingerprint=generator_fingerprint,
        oracle_fingerprint=oracle_fingerprint,
        admissibility_state=admissibility_state,
        inadmissibility_reason=inadmissibility_reason,
        observed_at="2026-08-17T12:00:00Z",
        ingested_at="2026-08-17T12:00:01Z",
    )


def test_verify_binding_ledgers_every_evidence_divergence_without_raising() -> None:
    record = _compile_minimal()
    evidence = (
        _stored("obs-family", task_family_id="other-family"),
        _stored("obs-version", task_family_version="v2"),
        _stored("obs-oracle", oracle_fingerprint="other-oracle"),
        _stored("obs-generator", generator_fingerprint="other-generator"),
        _stored("obs-phase", phase=Phase.CONFIRMATION),
        _stored(
            "obs-inadmissible",
            admissibility_state="inadmissible",
            inadmissibility_reason="fixture-refused-at-write-time",
        ),
    )

    result = verify_binding(record, evidence)

    assert isinstance(result, BindingVerificationDivergence)
    assert result.binding_digest == record.digest
    assert result.task_family_id == record.task_family_id
    assert result.task_family_version == record.task_family_version
    assert result.observation_ids == tuple(sorted(item.observation_id for item in evidence))
    assert tuple(entry.reason for entry in result.ledger.entries[:6]) == (
        DivergenceReason.TASK_FAMILY_MISMATCH,
        DivergenceReason.GENERATOR_FINGERPRINT_DRIFT,
        DivergenceReason.INADMISSIBLE_EVIDENCE,
        DivergenceReason.ORACLE_FINGERPRINT_DRIFT,
        DivergenceReason.PHASE_VIOLATION,
        DivergenceReason.TASK_FAMILY_VERSION_MISMATCH,
    )
    assert tuple(entry.observation_ids for entry in result.ledger.entries[:6]) == (
        ("obs-family",),
        ("obs-generator",),
        ("obs-inadmissible",),
        ("obs-oracle",),
        ("obs-phase",),
        ("obs-version",),
    )
    assert result.ledger.entries[2].stored_reason == "fixture-refused-at-write-time"
    assert {
        entry.axis
        for entry in result.ledger.entries
        if entry.reason is DivergenceReason.UNVERIFIABLE_AXIS
    } == set(UnverifiableAxis)
    assert set(UnverifiableAxis) == {
        UnverifiableAxis.ESTIMAND,
        UnverifiableAxis.SKILL_ID,
        UnverifiableAxis.DESIGN_IDENTITY,
        UnverifiableAxis.DELIVERY_MECHANISM,
        UnverifiableAxis.ADMISSIBILITY_POLICY,
    }
    assert all(
        isinstance(value, tuple) for value in (result.observation_ids, result.ledger.entries)
    )


def test_verify_binding_returns_typed_whole_verification_refusals() -> None:
    record = _compile_minimal()

    malformed = verify_binding(object(), (_stored("obs"),))  # type: ignore[arg-type]
    empty = verify_binding(record, ())

    assert isinstance(malformed, BindingVerificationRefusal)
    assert malformed.refusal is BindingVerificationRefusalReason.MALFORMED_BINDING
    assert malformed.binding_digest == ""
    assert malformed.task_family_id == ""
    assert malformed.task_family_version == ""
    assert malformed.observation_ids == ()
    assert malformed.ledger.entries == ()
    assert isinstance(empty, BindingVerificationRefusal)
    assert empty.refusal is BindingVerificationRefusalReason.EMPTY_EVIDENCE
    assert empty.binding_digest == record.digest
    assert empty.task_family_id == record.task_family_id
    assert empty.task_family_version == record.task_family_version
    assert empty.observation_ids == ()
    assert empty.ledger.entries == ()


def test_verify_binding_is_deterministic_for_match_and_divergence() -> None:
    record = _compile_minimal()
    matching = (_stored("obs-z"), _stored("obs-a"))
    diverging = (
        _stored("obs-z", oracle_fingerprint="other-oracle"),
        _stored("obs-a", task_family_version="v2"),
    )

    match_forward = verify_binding(record, matching)
    match_reverse = verify_binding(record, tuple(reversed(matching)))
    divergence_forward = verify_binding(record, diverging)
    divergence_reverse = verify_binding(record, tuple(reversed(diverging)))

    assert isinstance(match_forward, BindingVerificationMatch)
    assert match_forward == match_reverse
    assert match_forward.observation_ids == ("obs-a", "obs-z")
    assert tuple(entry.axis for entry in match_forward.ledger.entries) == tuple(
        sorted(UnverifiableAxis, key=lambda axis: axis.value)
    )
    assert isinstance(divergence_forward, BindingVerificationDivergence)
    assert divergence_forward == divergence_reverse
    assert divergence_forward.observation_ids == ("obs-a", "obs-z")
    assert tuple(entry.observation_ids for entry in divergence_forward.ledger.entries[:2]) == (
        ("obs-a",),
        ("obs-z",),
    )


def test_oracle_drift_is_invisible_to_e1_but_refused_by_binding(
    evidence_db: sqlite3.Connection,
) -> None:
    manifest = load_manifest(
        {
            "task_family_id": "family",
            "task_family_version": "v1",
            "frozen_hashes": {
                "generator": "g",
                "fixture": "f",
                "oracle": "stored-oracle",
                "harness": "h",
                "code": "c",
            },
            "phase_partition": {
                "calibration": [],
                "confirmation": [],
                "matched": ["lineage"],
            },
            "confirmation_attempt_budget": 0,
        }
    )
    for arm, passed in ((Arm.FULL, True), (Arm.NULL, False)):
        admission = admit(
            evidence_db,
            manifest,
            Observation(
                observation_id=f"obs-{arm.value}",
                semantic_lineage_id="lineage",
                instance_id="instance",
                arm=arm,
                passed=passed,
                generator_fingerprint="g",
                oracle_fingerprint="stored-oracle",
                observed_at="2026-08-17T12:00:00Z",
            ),
        )
        assert admission.admissible
    binding_record = _compile_minimal()
    evidence = matched_evidence(evidence_db, manifest)

    bridge_design = Gate2Design(
        n_pairs=1,
        gamma=binding_record.gate2_design.gamma,
        mme=binding_record.gate2_design.mme,
    )
    bridge_result = aggregate_matched_gate2(evidence_db, manifest, bridge_design)
    binding_result = verify_binding(binding_record, evidence)

    assert isinstance(bridge_result, MatchedGate2Decision)
    assert bridge_result.decision is not None
    assert isinstance(binding_result, BindingVerificationDivergence)
    oracle_entries = tuple(
        entry
        for entry in binding_result.ledger.entries
        if entry.reason is DivergenceReason.ORACLE_FINGERPRINT_DRIFT
    )
    assert tuple(entry.observation_ids for entry in oracle_entries) == (
        ("obs-full",),
        ("obs-null",),
    )


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

    record = compile_binding(
        scope=scope,
        manifest=manifest,
        design=design,
        frontier_row=frontier_row,
        budget_cap_cents=1555,
        harness_pin=pin,
    )

    # RAT TEMPLATE declared fields land on the record without optional knobs.
    assert record.registered_scope == scope
    assert record.registered_scope.estimand is Estimand.TREATMENT_POLICY
    assert record.registered_scope.skill == "append-only-evidence-design"
    assert record.registered_scope.task_family == "append-only-evidence-design"
    assert record.task_family_id == manifest.task_family_id
    assert record.task_family_version == manifest.task_family_version
    assert record.frozen_hashes == manifest.frozen_hashes
    assert record.gate2_design == design
    assert record.gate2_design.n_pairs == 20
    assert record.gate2_design.gamma == 0.90
    assert record.gate2_design.mme.delta_min == 0.20
    assert record.gate2_design.mme.q_min == 0.70
    assert len(record.frontier_row_hash) == 64
    assert record.budget_cap_cents == 1555  # hard_cap cents from worst-case $15.55
    assert record.harness_pin == pin
    assert record.harness_pin_fingerprint == pin.fingerprint()
    assert len(record.digest) == 64
    assert record.canonical_bytes
    assert record.binding_algo_version == BINDING_ALGO_VERSION


def test_binding_record_is_a_frozen_value() -> None:
    """Immutability is a property of an instance, not of the class object alone.

    ``object.__new__`` plus a bare ``FrozenInstanceError`` check can stay green
    on a non-frozen dataclass that simply has no ``__dict__`` yet. Compile a
    real record, mutate it, and require the field types that carry nested
    identity to be the existing carriers (not re-derived dicts or lists).
    """
    record = _compile_minimal()

    with pytest.raises(FrozenInstanceError):
        record.digest = "replacement"  # type: ignore[misc]

    assert isinstance(record.registered_scope, RegisteredScope)
    assert isinstance(record.frozen_hashes, FrozenHashes)
    assert isinstance(record.gate2_design, Gate2Design)
    assert isinstance(record.harness_pin, HarnessPin)
    assert isinstance(record.harness_pin.disallowed_tools, tuple)
    assert not any(
        type(getattr(record, name)) is list for name in BindingRecord.__dataclass_fields__
    )


def test_binding_canonical_recipe_is_versioned_and_byte_stable() -> None:
    """House recipe on the harness pin: sorted keys, compact separators, UTF-8, sha256.

    Byte-stability is the external claim: permute construction order of the
    inputs and the canonical bytes and digest must not move. The recipe itself
    is pinned by rebuilding the expected bytes from the decoded payload with
    the same knobs the pin uses, not by trusting the module's private helper.
    """
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

    decoded = json.loads(first.canonical_bytes.decode("utf-8"))
    expected = json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert BINDING_ALGO_VERSION == "1"
    assert decoded["binding_algo_version"] == BINDING_ALGO_VERSION
    assert set(decoded) == {
        "binding_algo_version",
        "budget_cap_cents",
        "frontier_row_hash",
        "gate2_design",
        "harness_pin_fingerprint",
        "registered_scope",
        "task_family",
    }
    assert decoded["registered_scope"]["estimand"] == scope.estimand.value
    assert decoded["registered_scope"]["delivery_mechanism"] == (scope.delivery_mechanism.value)
    assert decoded["registered_scope"]["skill"] == scope.skill
    assert decoded["task_family"]["id"] == manifest.task_family_id
    assert decoded["task_family"]["version"] == manifest.task_family_version
    assert decoded["task_family"]["frozen_hashes"] == {
        "generator": "g",
        "fixture": "f",
        "oracle": "o",
        "harness": "h",
        "code": "c",
    }
    assert decoded["gate2_design"] == {
        "n_pairs": 6,
        "gamma": 0.9,
        "mme": {"delta_min": 0.2, "q_min": 0.7},
    }
    assert decoded["budget_cap_cents"] == 600
    assert decoded["harness_pin_fingerprint"] == pin.fingerprint()
    assert len(decoded["frontier_row_hash"]) == 64
    assert first.canonical_bytes == expected == second.canonical_bytes
    assert first.digest == hashlib.sha256(expected).hexdigest() == second.digest
    assert first.harness_pin_fingerprint == pin.fingerprint()
    assert first.registered_scope is scope or first.registered_scope == scope


def test_binding_module_public_functions_are_compile_and_verify_only() -> None:
    """Pin entry points this module DEFINES, not how it spells its imports.

    A bare ``vars`` + leading-underscore filter also matches imported callables
    (``asdict``, ``dataclass``). That criterion is satisfiable by renaming the
    imports to ``_asdict`` / ``_dataclass``, which changes no interface — and
    is how an earlier form of this assertion was made to pass. Scoping to
    functions whose ``__module__`` is this module cannot be satisfied that way.
    """
    defined_public_callables = {
        name
        for name, value in vars(binding).items()
        if not name.startswith("_")
        and inspect.isfunction(value)
        and value.__module__ == binding.__name__
    }

    assert defined_public_callables == {"compile_binding", "verify_binding"}
    assert list(inspect.signature(compile_binding).parameters) == [
        "scope",
        "manifest",
        "design",
        "frontier_row",
        "budget_cap_cents",
        "harness_pin",
    ]
    for parameter in inspect.signature(compile_binding).parameters.values():
        assert parameter.default is inspect.Parameter.empty
    assert list(inspect.signature(verify_binding).parameters) == ["binding", "evidence"]
    for parameter in inspect.signature(verify_binding).parameters.values():
        assert parameter.default is inspect.Parameter.empty
