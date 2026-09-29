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
    assert proc.wealth == DEFAULT_W0

    assert (
        proc.record_verdict(
            KeepCutVerdict.KEEP,
            ledger_hypothesis_id="card-2",
            card_p_values=p_values,
            b_world_condition=False,
            shared_control_family_id="control-a",
            batch_order=1,
        )
        is None
    )
    assert proc.hypothesis_index == proc.discovery_count == 0
    assert proc.wealth == DEFAULT_W0


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


def _record(
    proc: NormalisedLORDdep,
    verdict: KeepCutVerdict,
    hypothesis_id: str,
    p_value: float,
    *,
    b_world_condition: bool = True,
) -> Any:
    return proc.record_verdict(
        verdict,
        ledger_hypothesis_id=hypothesis_id,
        card_p_values=_card_p_values(p_value),
        b_world_condition=b_world_condition,
        shared_control_family_id="control-a",
        batch_order=1,
    )


def test_a_cut_passes_over_its_registered_slot_without_spending() -> None:
    proc = NormalisedLORDdep()
    proc.set_order(["c1", "c2"])

    assert _record(proc, KeepCutVerdict.CUT, "c1", 0.001) is None
    assert proc.wealth == DEFAULT_W0
    assert proc.hypothesis_index == 0

    multiplicity = _record(proc, KeepCutVerdict.KEEP, "c2", 0.001)

    assert multiplicity is not None
    assert multiplicity.ledger_hypothesis_id == "c2"
    assert multiplicity.hypothesis_index == 1
    assert multiplicity.wealth_before == DEFAULT_W0
    # xi(1) * w0, the level c2 would get if c1 had never been registered.
    assert multiplicity.test_level == pytest.approx(0.0148105042, abs=1e-9)


def test_a_non_keep_out_of_registered_order_is_refused() -> None:
    proc = NormalisedLORDdep()
    proc.set_order(["c1", "c2"])
    with pytest.raises(ValueError, match="registered order"):
        _record(proc, KeepCutVerdict.CUT, "c2", 0.5)
    with pytest.raises(ValueError, match="registered order"):
        _record(proc, KeepCutVerdict.KEEP, "c2", 0.001, b_world_condition=False)


def test_a_mixed_batch_replays_with_identical_indices_levels_and_wealth() -> None:
    order = ["k1", "cut", "bfail", "k-miss", "k2"]
    outcomes: list[tuple[KeepCutVerdict, float, bool]] = [
        (KeepCutVerdict.KEEP, 0.001, True),
        (KeepCutVerdict.CUT, 0.001, True),
        (KeepCutVerdict.KEEP, 0.001, False),
        (KeepCutVerdict.KEEP, 0.5, True),
        (KeepCutVerdict.KEEP, 0.0001, True),
    ]

    def replay() -> tuple[list[float], list[Any], float, int, int]:
        proc = NormalisedLORDdep()
        proc.set_order(order)
        levels: list[float] = []
        records: list[Any] = []
        for hypothesis_id, (verdict, p_value, b_world) in zip(order, outcomes, strict=True):
            levels.append(proc.test_level())
            records.append(
                _record(proc, verdict, hypothesis_id, p_value, b_world_condition=b_world)
            )
        return levels, records, proc.wealth, proc.hypothesis_index, proc.discovery_count

    first = replay()
    assert first == replay()

    levels, records, _, hypothesis_index, discovery_count = first
    assert [record.hypothesis_index for record in records if record is not None] == [1, 3]
    assert hypothesis_index == 3
    assert discovery_count == 2
    # The CUT and the failed B-world check leave the level for the next KEEP at xi(2) * W(1).
    assert levels[1] == levels[2] == levels[3]


def _lower_bound(observations: list[float], alpha: float) -> float:
    return one_sided_betting_bound(observations, alpha=alpha, side="lower")


def _binomial_upper_tail_p(successes: int, trials: int, rate: float) -> float:
    """Fixed-sample exact p-value for H0: rate <= margin, read at a single look."""
    return math.fsum(
        math.comb(trials, k) * rate**k * (1.0 - rate) ** (trials - k)
        for k in range(successes, trials + 1)
    )


def test_a_stream_whose_bound_sits_at_the_margin_at_level_a_returns_a() -> None:
    level_a = 0.05
    length = 60
    below, above = 0.20, 1.0
    for _ in range(80):
        value = (below + above) / 2.0
        if _lower_bound([value] * length, level_a) > 0.20:
            above = value
        else:
            below = value
    constructed = [above] * length
    assert _lower_bound(constructed, level_a) == pytest.approx(0.20, abs=1e-12)

    assert anytime_valid_p_value(constructed) == pytest.approx(level_a, abs=1e-6)


def test_the_p_value_is_valid_at_every_early_look_and_differs_from_a_fixed_sample_p() -> None:
    looks = (20, 40, 60)
    level_a = 0.10
    rng = random.Random(644)

    stream = [1.0 if rng.random() < 0.40 else 0.0 for _ in range(looks[-1])]
    decisions: list[bool] = []
    for look in looks:
        prefix = stream[:look]
        anytime_p = anytime_valid_p_value(prefix)
        decisions.append(anytime_p <= level_a)
        assert decisions[-1] is (_lower_bound(prefix, level_a) > 0.20)
        fixed_p = _binomial_upper_tail_p(int(sum(prefix)), look, 0.20)
        assert fixed_p < anytime_p / 2.0
    # The stream crosses level a between looks, so the check above sees both decisions.
    assert set(decisions) == {True, False}

    streams = 200
    anytime_rejections = 0
    fixed_rejections = 0
    for _ in range(streams):
        null_stream = [1.0 if rng.random() < 0.20 else 0.0 for _ in range(looks[-1])]
        prefixes = [null_stream[:look] for look in looks]
        if any(_lower_bound(prefix, level_a) > 0.20 for prefix in prefixes):
            anytime_rejections += 1
        if any(
            _binomial_upper_tail_p(int(sum(prefix)), len(prefix), 0.20) <= level_a
            for prefix in prefixes
        ):
            fixed_rejections += 1
    # Peeking at three looks under the boundary null: the anytime-valid test keeps its
    # level, and the fixed-sample test read at a data-dependent stop does not.
    assert anytime_rejections / streams <= level_a
    assert fixed_rejections / streams > level_a
