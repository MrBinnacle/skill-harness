"""External acceptance coverage for the normalised LORDdep ledger (#644)."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import pytest

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound
from skill_harness.aggregation.online_fdr import (
    _N_GRID,
    DEFAULT_W0,
    CardPValues,
    K,
    NormalisedLORDdep,
    anytime_valid_p_value,
    card_anytime_valid_p_values,
    xi,
)
from skill_harness.aggregation.verdict import KeepCutVerdict
from skill_harness.sitegen import SiteBuildError, load_schema, validate_receipts


def _order(size: int) -> list[str]:
    return [f"card-{number}" for number in range(1, size + 1)]


def _card_p_values(value: float) -> CardPValues:
    return CardPValues(anytime_valid_p=value, p_fn=value, p_fp=value)


def test_cold_start_levels_are_pinned() -> None:
    with pytest.raises(TypeError):
        NormalisedLORDdep(w0=0.1)  # type: ignore[call-arg]

    proc = NormalisedLORDdep()
    proc.set_order(_order(5))
    expected = [0.0148105042, 0.0074052521, 0.0012399141, 0.0004628283, 0.0002366211]

    for expected_alpha in expected:
        assert proc.test_level() == pytest.approx(expected_alpha, abs=1e-9)
        assert proc.step(0.5) is False


def test_normalisation_and_paper_condition_are_computed_from_the_definition() -> None:
    partial_sum = math.fsum(1.0 / (j * math.log(max(j, 2)) ** 3) for j in range(1, _N_GRID + 1))
    tail_bound = 1.0 / (2.0 * math.log(_N_GRID) ** 2)
    assert K * (partial_sum + tail_bound) == pytest.approx(1.0, abs=1e-12)

    condition = math.fsum(xi(j) * (1.0 + math.log(j)) for j in range(1, _N_GRID + 1))
    condition += K * (tail_bound + 1.0 / math.log(_N_GRID))
    assert condition <= 0.05 / 0.025
    assert condition == pytest.approx(1.4162, abs=0.001)


def test_global_index_uses_the_wealth_at_the_last_discovery() -> None:
    proc = NormalisedLORDdep()
    proc.set_order(_order(4))
    proc.step(0.5)
    assert proc.step(0.001) is True
    wealth_at_discovery = proc.wealth
    assert wealth_at_discovery == pytest.approx(0.0277842437, abs=1e-9)

    assert proc.test_level() == pytest.approx(0.0013780031, abs=1e-9)
    proc.step(0.5)
    # This catches the old implementation, which used W(3) instead of W(2).
    assert proc.test_level() == pytest.approx(xi(4) * wealth_at_discovery, abs=1e-15)


def test_wealth_stays_non_negative_and_levels_do_not_exceed_it() -> None:
    proc = NormalisedLORDdep()
    proc.set_order(_order(500))
    for _ in range(500):
        assert proc.test_level() <= proc.wealth + 1e-15
        proc.step(0.5)
        assert proc.wealth >= 0.0

    random_proc = NormalisedLORDdep()
    random_proc.set_order(_order(10_000))
    rng = random.Random(42)
    for _ in range(10_000):
        assert random_proc.test_level() <= random_proc.wealth + 1e-15
        random_proc.step(rng.random())
        assert random_proc.wealth >= 0.0


def test_unnormalised_poison_sequence_exhausts_the_wealth() -> None:
    old_constant = 0.139307
    wealth = DEFAULT_W0
    for index in range(1, 501):
        alpha = old_constant / (index * math.log(max(index, 2)) ** 3) * DEFAULT_W0 * 2.0
        wealth -= alpha
        if wealth < 0.0:
            break
    assert wealth < 0.0


def test_anytime_valid_p_value_inverts_the_same_bound_to_micro_precision() -> None:
    observations = [0.25] * 80
    p_value = anytime_valid_p_value(observations)
    assert one_sided_betting_bound(observations, alpha=p_value, side="lower") > 0.20
    just_below = max(1e-12, p_value - 1e-6)
    assert one_sided_betting_bound(observations, alpha=just_below, side="lower") <= 0.20


def test_card_p_value_is_the_maximum_of_both_contrasts() -> None:
    p_values = card_anytime_valid_p_values([0.9] * 80, [0.8] * 80)
    assert p_values.anytime_valid_p == max(p_values.p_fn, p_values.p_fp)


def test_cut_and_failed_b_world_do_not_advance_the_ledger() -> None:
    proc = NormalisedLORDdep()
    proc.set_order(_order(2))
    p_values = _card_p_values(0.001)

    assert (
        proc.record_verdict(
            KeepCutVerdict.CUT,
            ledger_hypothesis_id="card-1",
            card_p_values=p_values,
            b_world_condition=True,
            shared_control_family_id="control-a",
            batch_order=1,
        )
        is None
    )
    assert proc.hypothesis_index == proc.discovery_count == 0

    assert (
        proc.record_verdict(
            KeepCutVerdict.KEEP,
            ledger_hypothesis_id="card-1",
            card_p_values=p_values,
            b_world_condition=False,
            shared_control_family_id="control-a",
            batch_order=1,
        )
        is None
    )
    assert proc.hypothesis_index == proc.discovery_count == 0


def test_registered_keep_receives_a_reconstructable_multiplicity_record() -> None:
    proc = NormalisedLORDdep()
    proc.set_order(["card-a"])
    multiplicity = proc.record_verdict(
        KeepCutVerdict.KEEP,
        ledger_hypothesis_id="card-a",
        card_p_values=_card_p_values(0.001),
        b_world_condition=True,
        shared_control_family_id="control-a",
        batch_order=1,
    )

    assert multiplicity is not None
    assert multiplicity.hypothesis_index == 1
    assert multiplicity.anytime_valid_p <= multiplicity.test_level
    assert multiplicity.wealth_after == pytest.approx(
        multiplicity.wealth_before - multiplicity.test_level + multiplicity.payout
    )


def test_order_is_fixed_before_results_and_identifies_each_hypothesis_once() -> None:
    proc = NormalisedLORDdep()
    with pytest.raises(ValueError, match="repeat"):
        proc.set_order(["card-a", "card-a"])

    proc.set_order(["card-a", "card-b"])
    proc.step(0.5)
    with pytest.raises(ValueError, match="Cannot set order"):
        proc.set_order(["card-b", "card-a"])


def test_registered_order_replays_with_identical_indices_and_levels() -> None:
    order = ["card-a", "card-b", "card-c"]
    p_values = [0.5, 0.001, 0.5]
    first = NormalisedLORDdep()
    second = NormalisedLORDdep()
    first.set_order(order)
    second.set_order(order)

    first_levels: list[float] = []
    second_levels: list[float] = []
    for p_value in p_values:
        first_levels.append(first.test_level())
        second_levels.append(second.test_level())
        assert first.step(p_value) is second.step(p_value)

    assert first_levels == second_levels
    assert first.hypothesis_index == second.hypothesis_index
    assert first.discovery_index == second.discovery_index
    assert first.discovery_count == second.discovery_count
    assert first.wealth == second.wealth


def _receipt(multiplicity: dict[str, str | int | float]) -> dict[str, Any]:
    return {
        "sers_version": "1.7.0",
        "skill_name": "ledger-fixture",
        "verdict": "KEEP",
        "cut_sub_reason": None,
        "unmeasured_sub_reason": None,
        "value_class": "transformative-lift",
        "evidence_admissibility": {"status": "not_applicable"},
        "cost": {
            "standing_tokens": {"refusal": "not_applicable"},
            "fired_tokens": {"refusal": "not_applicable"},
            "aux_tokens": {"refusal": "not_applicable"},
        },
        "instrument_identity": {
            "extractor_model": {"refusal": "not_applicable"},
            "prompt_fingerprint": "a",
            "schema_fingerprint": "b",
        },
        "source": {"prose_path": "README.md"},
        "summary": "Receipt fixture for the online FDR ledger.",
        "subject_identity": {
            "skill_id": "aa" * 32,
            "harness_version": "0.3.0",
            "metric_version": "0.4.1",
            "implementation_hash": "bb" * 32,
            "arms": ["null", "full"],
            "subject_model": "model-2026-09",
        },
        "delivery": {
            "channel": "not_instrumented",
            "exposure": {"refusal": "not_instrumented"},
            "pi_c": {"refusal": "not_instrumented"},
        },
        "verdict_scope": {
            "model_id": "model-2026-09",
            "task_family": "ledger-test",
            "estimand": "treatment-policy",
            "delivery_mechanism": "hook-nudged",
            "control_world_result": "pass",
        },
        "multiplicity": multiplicity,
    }


def test_sers_refuses_an_invalid_keep_multiplicity_record(tmp_path: Path) -> None:
    proc = NormalisedLORDdep()
    proc.set_order(["card-a"])
    multiplicity = proc.record_verdict(
        KeepCutVerdict.KEEP,
        ledger_hypothesis_id="card-a",
        card_p_values=_card_p_values(0.001),
        b_world_condition=True,
        shared_control_family_id="control-a",
        batch_order=1,
    )
    assert multiplicity is not None
    receipt = _receipt(multiplicity.as_dict())
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    (receipts_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    schema = load_schema(Path("docs/sers/sers.schema.json"))
    assert validate_receipts(schema, receipts_dir) == [receipt]

    receipt["multiplicity"]["anytime_valid_p"] = 0.02
    (receipts_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(SiteBuildError, match="anytime_valid_p"):
        validate_receipts(schema, receipts_dir)
