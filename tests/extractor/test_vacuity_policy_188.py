"""#188 — vacuity evidence policy: generation-scoped calibration + advisory kinds.

External behaviour only: statuses derive from instrument triple + receipt;
raw weak_directive never becomes operational; mixed generations refused;
renderers cannot emit bare kind-precision or claim recall measured.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from skill_harness.extractor.models import ExtractorInstrument
from skill_harness.extractor.vacuity_policy import (
    AdjudicationRecord,
    AmbiguousCalibrationReceiptError,
    BareKindPrecisionRenderError,
    KindPrecisionClaim,
    KindPrecisionClaimError,
    MixedExtractorGenerationsError,
    VacuityFlagCalibrationReceipt,
    adjudication_identity_key,
    assert_kind_precision_render_safe,
    assert_recall_not_claimed_measured,
    clause_context_sha256,
    decision_ready_vacuity_kind,
    default_receipt_path,
    derive_vacuity_policy,
    exclusion_label_for_flag,
    format_kind_precision_for_render,
    load_calibration_receipt,
    load_citable_receipts,
    load_default_receipts,
    match_calibration_receipt,
    require_single_generation,
)

_REPO = Path(__file__).resolve().parent.parent.parent
_DOCS_RECEIPT = _REPO / "docs" / "calibration" / "vacuity-flag-calibration-2026-08-08.json"
_ADJ_RECEIPT = _REPO / "docs" / "calibration" / "vacuity-adjudication-receipt-2026-08-09.json"

_CAL_MODEL = "claude-opus-5"
_CAL_PROMPT = "525ac4445febc96403e139af752d7a17790c2cd3bf54f56b8dcf3c1773eb7054"
_CAL_SCHEMA = "39c50daa5e2438b45d86b877d2215be3246d7f27bc4e0c29e6062e158a9e0cd3"
_SOURCE = "a" * 64
_CLAUSE = "Prefer elegance in layout."


def _calibrated_instrument() -> ExtractorInstrument:
    return ExtractorInstrument(
        model_id=_CAL_MODEL,
        system_prompt_sha256=_CAL_PROMPT,
        tool_schema_sha256=_CAL_SCHEMA,
    )


def _other_instrument(**overrides: str) -> ExtractorInstrument:
    data = {
        "model_id": _CAL_MODEL,
        "system_prompt_sha256": _CAL_PROMPT,
        "tool_schema_sha256": _CAL_SCHEMA,
    }
    data.update(overrides)
    return ExtractorInstrument(
        model_id=data["model_id"],
        system_prompt_sha256=data["system_prompt_sha256"],
        tool_schema_sha256=data["tool_schema_sha256"],
    )


# ---------------------------------------------------------------------------
# Receipt round-trip reproduces ticket figures
# ---------------------------------------------------------------------------


def test_committed_receipt_round_trips_ticket_figures() -> None:
    assert _DOCS_RECEIPT.is_file()
    receipt = load_calibration_receipt(_DOCS_RECEIPT)
    assert receipt.extractor_model == "claude-opus-5"
    assert receipt.system_prompt_sha256 == _CAL_PROMPT
    assert receipt.tool_schema_sha256 == _CAL_SCHEMA
    assert receipt.flag_precision_weighted_undecided_wrong == 0.972
    assert receipt.flag_precision_weighted_undecided_correct == 0.975
    assert receipt.wilson_95_fpc_low == 0.923
    assert receipt.wilson_95_fpc_high == 0.986
    assert receipt.kind_precision_aggregate == 0.835
    assert receipt.kind_precision_not_a_directive_correct == 77
    assert receipt.kind_precision_not_a_directive_n == 78
    assert receipt.kind_precision_weak_directive_correct == 4
    assert receipt.kind_precision_weak_directive_n == 20
    assert receipt.recall == "UNMEASURED"
    # Default loader sees the same figures.
    default = load_default_receipts()
    assert len(default) == 1
    assert default[0].flag_precision_weighted_undecided_wrong == 0.972
    assert default_receipt_path().is_file()


def test_adjudication_receipt_loads_measured_recall_with_intervals_and_n() -> None:
    receipt = load_calibration_receipt(_ADJ_RECEIPT)
    assert receipt.recall != "UNMEASURED"
    assert receipt.recall.point_undecided_clean == 0.7524
    assert receipt.recall.point_undecided_vacuous == 0.7331
    assert receipt.recall.stratified_fpc_95 == (0.66, 0.874)
    assert receipt.recall.skill_cluster_bootstrap_95 == (0.622, 0.913)
    assert receipt.recall.sample_n == 120
    assert receipt.recall.skill_n == 47


def test_receipt_round_trip_preserves_optional_supersedes_note() -> None:
    gen_1 = load_calibration_receipt(_DOCS_RECEIPT)
    gen_2 = load_calibration_receipt(_ADJ_RECEIPT)

    assert gen_1.supersedes_note is None
    assert (
        gen_2.supersedes_note
        == json.loads(_ADJ_RECEIPT.read_text(encoding="utf-8"))["supersedes_note"]
    )


def test_non_string_supersedes_note_is_refused_not_coerced(tmp_path: Path) -> None:
    """A note is prose or absent; a number there would render as a citation."""
    raw = json.loads(_ADJ_RECEIPT.read_text(encoding="utf-8"))
    raw["supersedes_note"] = 189
    path = tmp_path / "numeric-note.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="supersedes_note"):
        load_calibration_receipt(path)


def test_citable_registry_loads_both_generations_without_expanding_operational_pool() -> None:
    citable = load_citable_receipts()
    assert [receipt.receipt_id for receipt in citable] == [
        "vacuity-flag-calibration-2026-08-08",
        "vacuity-flag-adjudication-2026-08-09",
    ]
    assert citable[0].supersedes_note is None
    assert citable[1].supersedes_note is not None

    operational = load_default_receipts()
    assert [receipt.receipt_id for receipt in operational] == [
        "vacuity-flag-calibration-2026-08-08"
    ]


def test_receipt_missing_recall_is_refused_not_defaulted(tmp_path: Path) -> None:
    raw = json.loads(_DOCS_RECEIPT.read_text(encoding="utf-8"))
    del raw["recall"]
    path = tmp_path / "missing-recall.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="recall"):
        load_calibration_receipt(path)


def test_recall_interval_is_never_published_as_the_flag_precision_interval() -> None:
    """A recall band is not a precision band, however similar the field names.

    ``arm_A`` of the 2026-08-09 receipt is a population census: it publishes no
    sampling interval at all. Filling the flag-precision Wilson95+FPC fields from
    ``arm_B``'s ``stratified_fpc_95`` puts [0.66, 0.874] on the exclusion label
    beside a 0.9574 precision point that the band does not even contain -- an
    interval the receipt never claimed, attached to the wrong quantity.
    """
    receipt = load_calibration_receipt(_ADJ_RECEIPT)
    assert receipt.wilson_95_fpc_low is None
    assert receipt.wilson_95_fpc_high is None

    label = exclusion_label_for_flag(
        flag_evidence_status="CALIBRATED_FROZEN_CAPTURE",
        calibration_receipt=receipt,
    )
    assert "flag-based" in label.lower()
    assert "pending review" in label.lower()
    assert receipt.receipt_id in label
    assert "0.9574" in label
    assert "no flag-precision interval in receipt" in label
    assert "Wilson" not in label
    for recall_figure in ("0.66", "0.874", "0.622", "0.913", "0.7524", "0.7331"):
        assert recall_figure not in label, f"recall figure {recall_figure} leaked into precision"


def test_sampled_receipt_must_still_carry_its_own_interval(tmp_path: Path) -> None:
    """Optional-for-a-census must not become optional-for-everyone."""
    raw = json.loads(_DOCS_RECEIPT.read_text(encoding="utf-8"))
    del raw["flag_precision"]["wilson_95_fpc_low"]
    del raw["flag_precision"]["wilson_95_fpc_high"]
    path = tmp_path / "no-interval.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="wilson_95_fpc"):
        load_calibration_receipt(path)

    half = json.loads(_ADJ_RECEIPT.read_text(encoding="utf-8"))
    half["arm_A_census"]["wilson_95_fpc_low"] = 0.94
    half_path = tmp_path / "half-interval.json"
    half_path.write_text(json.dumps(half), encoding="utf-8")
    with pytest.raises(ValueError, match="both"):
        load_calibration_receipt(half_path)


def test_ambiguous_prose_denominator_is_refused_not_first_wins(tmp_path: Path) -> None:
    """The sample n is read out of prose, so ambiguity must fail closed.

    ``design`` carrying two ``n=`` figures took the first one, publishing the
    positives count (11) as the sample size (120) with no error anywhere.
    """
    raw = json.loads(_ADJ_RECEIPT.read_text(encoding="utf-8"))
    raw["arm_B_recall"]["design"] = "positives n=11 inside the n=120 stratified draw, seed 189"
    path = tmp_path / "ambiguous-n.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="unambiguous"):
        load_calibration_receipt(path)


# ---------------------------------------------------------------------------
# Instrument triple mismatch → UNMEASURED_GENERATION_MISMATCH
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_id": "claude-sonnet-4"},
        {"system_prompt_sha256": "1" * 64},
        {"tool_schema_sha256": "2" * 64},
    ],
)
def test_each_triple_field_mismatch_is_unmeasured(overrides: dict[str, str]) -> None:
    view = derive_vacuity_policy(
        instrument=_other_instrument(**overrides),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="weak_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
    )
    assert view.flag_evidence_status == "UNMEASURED_GENERATION_MISMATCH"
    assert view.calibration_receipt is None


def test_absent_receipt_pool_is_unmeasured() -> None:
    view = derive_vacuity_policy(
        instrument=_calibrated_instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="not_a_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
        receipts=(),
    )
    assert view.flag_evidence_status == "UNMEASURED_GENERATION_MISMATCH"


def test_none_instrument_is_unmeasured() -> None:
    view = derive_vacuity_policy(
        instrument=None,
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="weak_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
    )
    assert view.flag_evidence_status == "UNMEASURED_GENERATION_MISMATCH"
    assert match_calibration_receipt(None) is None


def test_matching_triple_is_calibrated_frozen_capture() -> None:
    view = derive_vacuity_policy(
        instrument=_calibrated_instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="not_a_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
    )
    assert view.flag_evidence_status == "CALIBRATED_FROZEN_CAPTURE"
    assert view.calibration_receipt is not None
    assert view.calibration_receipt.flag_precision_weighted_undecided_wrong == 0.972


def test_injected_duplicate_triple_raises_typed_ambiguity() -> None:
    receipts = (
        load_calibration_receipt(_DOCS_RECEIPT),
        load_calibration_receipt(_ADJ_RECEIPT),
    )
    with pytest.raises(AmbiguousCalibrationReceiptError, match="2 calibration receipts"):
        match_calibration_receipt(_calibrated_instrument(), receipts)


def test_default_pool_duplicate_triple_raises_typed_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import skill_harness.extractor.vacuity_policy as policy

    receipts = (
        load_calibration_receipt(_DOCS_RECEIPT),
        load_calibration_receipt(_ADJ_RECEIPT),
    )
    monkeypatch.setattr(policy, "load_default_receipts", lambda: receipts)
    with pytest.raises(AmbiguousCalibrationReceiptError, match="2 calibration receipts"):
        match_calibration_receipt(_calibrated_instrument())


def test_zero_matching_receipts_remains_none() -> None:
    assert match_calibration_receipt(_other_instrument(model_id="foreign"), ()) is None


# ---------------------------------------------------------------------------
# Kind is advisory until adjudicated; weak_directive never operational
# ---------------------------------------------------------------------------


def test_raw_weak_directive_cannot_become_operational_kind() -> None:
    view = derive_vacuity_policy(
        instrument=_calibrated_instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="weak_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
    )
    assert view.kind_evidence_status == "ADVISORY"
    assert view.predicted_vacuity_kind == "weak_directive"
    assert view.adjudicated_vacuity_kind is None
    assert decision_ready_vacuity_kind(view) is None
    assert view.decision_ready_kind is None


def test_raw_not_a_directive_remains_advisory_until_adjudicated() -> None:
    view = derive_vacuity_policy(
        instrument=_calibrated_instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="not_a_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
    )
    assert view.kind_evidence_status == "ADVISORY"
    assert view.predicted_vacuity_kind == "not_a_directive"
    assert view.adjudicated_vacuity_kind is None
    assert decision_ready_vacuity_kind(view) is None


def test_adjudicated_kind_is_decision_ready() -> None:
    ctx = clause_context_sha256(_CLAUSE)
    adj = AdjudicationRecord(
        source_sha256=_SOURCE,
        clause_context_sha256=ctx,
        adjudicated_vacuity_kind="not_a_directive",
        adjudication_receipt="panel-2026-08-08#row-1",
    )
    view = derive_vacuity_policy(
        instrument=_calibrated_instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="weak_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
        adjudication=adj,
    )
    assert view.kind_evidence_status == "ADJUDICATED"
    assert view.adjudicated_vacuity_kind == "not_a_directive"
    assert view.adjudication_receipt == "panel-2026-08-08#row-1"
    # Prediction stays visible but does not drive decision_ready.
    assert view.predicted_vacuity_kind == "weak_directive"
    assert decision_ready_vacuity_kind(view) == "not_a_directive"


# ---------------------------------------------------------------------------
# Mixed generations refused
# ---------------------------------------------------------------------------


def test_mixed_extractor_generations_refused_not_pooled() -> None:
    a = _calibrated_instrument()
    b = _other_instrument(model_id="other-model")
    with pytest.raises(MixedExtractorGenerationsError, match="mixed_extractor_generations"):
        require_single_generation([a, b])
    with pytest.raises(MixedExtractorGenerationsError):
        require_single_generation([a, None])
    single = require_single_generation([a, a])
    assert single is not None
    assert single.same_generation_as(a)
    assert require_single_generation([None, None]) is None


# ---------------------------------------------------------------------------
# Adjudication identity: source_sha + clause context hash; never clause_index
# ---------------------------------------------------------------------------


def test_adjudication_identity_joins_across_clause_index_repeats() -> None:
    key_a = adjudication_identity_key(_SOURCE, _CLAUSE)
    key_b = adjudication_identity_key(_SOURCE, _CLAUSE)
    assert key_a == key_b
    assert key_a[0] == _SOURCE
    assert len(key_a[1]) == 64

    ctx = clause_context_sha256(_CLAUSE)
    adj = AdjudicationRecord(
        source_sha256=_SOURCE,
        clause_context_sha256=ctx,
        adjudicated_vacuity_kind="weak_directive",
        adjudication_receipt="r1",
    )
    # Two "extraction repeats" with different clause_index values join the same adj.
    v0 = derive_vacuity_policy(
        instrument=_calibrated_instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="weak_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
        adjudication=adj,
    )
    v1 = derive_vacuity_policy(
        instrument=_calibrated_instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="weak_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
        adjudication=adj,
    )
    assert v0.clause_context_sha256 == v1.clause_context_sha256 == ctx
    assert v0.adjudicated_vacuity_kind == v1.adjudicated_vacuity_kind == "weak_directive"

    # clause_index is not part of the identity API surface.
    import inspect

    sig = inspect.signature(adjudication_identity_key)
    assert "clause_index" not in sig.parameters
    sig2 = inspect.signature(derive_vacuity_policy)
    assert "clause_index" not in sig2.parameters


def test_clause_index_keyed_join_is_structurally_impossible() -> None:
    """No public API accepts clause_index as an adjudication join key."""
    import skill_harness.extractor.vacuity_policy as vp

    public = [n for n in dir(vp) if not n.startswith("_")]
    for name in public:
        obj = getattr(vp, name)
        if not callable(obj):
            continue
        try:
            params = inspect_params(obj)
        except (TypeError, ValueError):
            continue
        assert "clause_index" not in params, f"{name} exposes clause_index"


def inspect_params(obj: object) -> set[str]:
    import inspect

    return set(inspect.signature(obj).parameters)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_policy_derivation_is_pure_and_deterministic() -> None:
    kwargs = dict(
        instrument=_calibrated_instrument(),
        vacuity_flag="semantic_vacuous_pending_review",
        predicted_vacuity_kind="not_a_directive",
        source_sha256=_SOURCE,
        clause_text=_CLAUSE,
    )
    a = derive_vacuity_policy(**kwargs)  # type: ignore[arg-type]
    b = derive_vacuity_policy(**kwargs)  # type: ignore[arg-type]
    assert a == b
    assert a.flag_evidence_status == b.flag_evidence_status
    assert a.kind_evidence_status == b.kind_evidence_status
    assert a.clause_context_sha256 == b.clause_context_sha256


@pytest.mark.parametrize(
    ("receipt_index", "changes"),
    [
        (0, {"kind_precision_aggregate": 0.99}),
        (1, {"kind_precision_aggregate": 0.9667001}),
        (0, {"receipt_id": "invented-receipt"}),
        (0, {"extractor_model": "invented-model"}),
        (0, {"system_prompt_sha256": "1" * 64}),
        (0, {"tool_schema_sha256": "2" * 64}),
        (0, {"kind_precision_not_a_directive_correct": 76}),
        (0, {"kind_precision_not_a_directive_n": 79}),
        (0, {"kind_precision_weak_directive_correct": 5}),
        (0, {"kind_precision_weak_directive_n": 21}),
    ],
)
def test_kind_precision_claim_refuses_invented_and_near_miss_figures(
    receipt_index: int, changes: dict[str, Any]
) -> None:
    receipt = replace(load_citable_receipts()[receipt_index], **changes)
    with pytest.raises(KindPrecisionClaimError, match="citable receipt"):
        KindPrecisionClaim.from_receipt(receipt)


def test_kind_precision_claim_validation_fails_against_a_poisoned_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The claim must consult the registry, not trust a receipt-shaped source."""
    import skill_harness.extractor.vacuity_policy as policy

    receipt = load_citable_receipts()[0]
    poisoned = replace(receipt, kind_precision_aggregate=0.99)
    monkeypatch.setattr(policy, "load_citable_receipts", lambda: (poisoned,))

    with pytest.raises(KindPrecisionClaimError, match="citable receipt"):
        KindPrecisionClaim.from_receipt(receipt)


def test_kind_precision_claim_refuses_a_receipt_forged_outside_the_kind_figures() -> None:
    """Nine matching kind figures do not license the rest of the receipt.

    ``KindPrecisionClaim.supersedes_note`` republishes the source receipt's
    provenance line, and the line of record for the 2026-08-09 receipt says it
    EXTENDS the 2026-08-08 receipt rather than replacing it. A receipt whose
    kind block matches the registry while its note, capture date or recall block
    does not is a different receipt making a different provenance claim, so
    ``from_receipt`` refuses it instead of taking the caller's copy.
    """
    gen_2 = load_citable_receipts()[1]
    forged_note = replace(
        gen_2,
        supersedes_note="Replaces receipt vacuity-flag-calibration-2026-08-08 in full.",
    )
    with pytest.raises(KindPrecisionClaimError, match="source receipt"):
        KindPrecisionClaim.from_receipt(forged_note)

    with pytest.raises(KindPrecisionClaimError, match="source receipt"):
        KindPrecisionClaim.from_receipt(replace(gen_2, capture_date="2026-12-31"))

    with pytest.raises(KindPrecisionClaimError, match="source receipt"):
        KindPrecisionClaim.from_receipt(replace(gen_2, recall="UNMEASURED"))


def test_kind_precision_claim_from_receipt_retains_its_source() -> None:
    receipt = load_citable_receipts()[1]
    claim = KindPrecisionClaim.from_receipt(receipt)
    assert claim.source_receipt is receipt


def test_kind_precision_claim_direct_construction_accepts_coherence_without_custody() -> None:
    """Copied registered values are coherent even without the original object."""
    receipt = load_citable_receipts()[0]
    claim = KindPrecisionClaim(
        receipt_id=receipt.receipt_id,
        extractor_model=receipt.extractor_model,
        system_prompt_sha256=receipt.system_prompt_sha256,
        tool_schema_sha256=receipt.tool_schema_sha256,
        aggregate=receipt.kind_precision_aggregate,
        not_a_directive_correct=receipt.kind_precision_not_a_directive_correct,
        not_a_directive_n=receipt.kind_precision_not_a_directive_n,
        weak_directive_correct=receipt.kind_precision_weak_directive_correct,
        weak_directive_n=receipt.kind_precision_weak_directive_n,
    )
    assert claim.source_receipt == receipt


def test_kind_precision_claim_has_one_canonical_serialization() -> None:
    receipt = load_citable_receipts()[1]
    claim = KindPrecisionClaim.from_receipt(receipt)
    assert claim.serialize() == (
        "kind-precision 0.9667 (not_a_directive 255/255; "
        "weak_directive 6/15; advisory until adjudicated)"
    )


def test_existing_kind_precision_render_is_a_thin_claim_serializer_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = load_citable_receipts()[0]
    monkeypatch.setattr(KindPrecisionClaim, "serialize", lambda self: "canonical sentinel")
    assert format_kind_precision_for_render(receipt) == "canonical sentinel"


def test_kind_precision_render_refuses_a_receipt_no_citable_receipt_backs(
    tmp_path: Path,
) -> None:
    """The renderer is the surface that refuses uncitable figures, not just the claim.

    ``corpus_census`` publishes through ``format_kind_precision_for_render``, so
    the refusal has to hold there. A receipt loaded from any other path carries
    figures the citable registry cannot confirm -- including the next capture
    generation, until it is registered -- and an unconfirmable figure is refused
    rather than rendered.
    """
    raw = json.loads(_DOCS_RECEIPT.read_text(encoding="utf-8"))
    raw["receipt_id"] = "vacuity-flag-calibration-2026-09-01"
    raw["capture_date"] = "2026-09-01"
    raw["kind_precision"]["aggregate"] = 0.91
    raw["kind_precision"]["not_a_directive_correct"] = 90
    raw["kind_precision"]["not_a_directive_n"] = 95
    path = tmp_path / "unregistered-capture.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(KindPrecisionClaimError, match="citable receipt"):
        format_kind_precision_for_render(load_calibration_receipt(path))


def test_kind_precision_render_still_refuses_a_bare_aggregate_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The render guard runs on the string the claim hands back, not on trust.

    ``format_kind_precision_for_render`` promises in its own docstring that a
    bare aggregate is refused. Citability and class-split completeness are two
    different properties: a claim can be perfectly citable and still serialise
    to a bare 'kind-precision 0.835'. The renderer checks the string it is about
    to publish, so the promise does not depend on one serialiser staying correct.
    """
    receipt = load_citable_receipts()[0]
    monkeypatch.setattr(KindPrecisionClaim, "serialize", lambda self: "kind-precision 0.835")
    with pytest.raises(BareKindPrecisionRenderError, match="class split"):
        format_kind_precision_for_render(receipt)


def test_kind_precision_claim_exposes_supersession_only_as_metadata() -> None:
    receipt = load_citable_receipts()[1]
    claim = KindPrecisionClaim.from_receipt(receipt)
    assert claim.supersedes_note == receipt.supersedes_note
    assert claim.supersedes_note is not None
    assert claim.supersedes_note not in claim.serialize()
    assert "supersed" not in claim.serialize().lower()


def test_kind_precision_claim_refuses_backstop_named_residual_pairing() -> None:
    gen_1, gen_2 = load_citable_receipts()
    with pytest.raises(KindPrecisionClaimError, match="citable receipt"):
        KindPrecisionClaim(
            receipt_id=gen_2.receipt_id,
            extractor_model=gen_2.extractor_model,
            system_prompt_sha256=gen_2.system_prompt_sha256,
            tool_schema_sha256=gen_2.tool_schema_sha256,
            aggregate=gen_2.kind_precision_aggregate,
            not_a_directive_correct=gen_1.kind_precision_not_a_directive_correct,
            not_a_directive_n=gen_1.kind_precision_not_a_directive_n,
            weak_directive_correct=gen_1.kind_precision_weak_directive_correct,
            weak_directive_n=gen_1.kind_precision_weak_directive_n,
        )


def test_gen_1_citation_renders_the_denominator_its_own_receipt_carries() -> None:
    """Generation one still renders, and it renders the split its receipt records.

    Two checked-in receipts disagree about this denominator. The 2026-08-08
    receipt records ``not_a_directive_n = 78`` and its own note repeats the
    77/78 split. The 2026-08-09 receipt's ``arm_C_kind`` note says "the published
    77/78 was an off-by-one denominator, reconciled 2026-08-09" and puts the
    split of record at 77/77 -- which is what README.md carries and what the
    public-copy ban in ``tests/test_structural_bans.py`` requires beside the
    0.835 aggregate. So this render passes ``assert_kind_precision_render_safe``,
    which checks it against the same receipt that carries the off-by-one, and the
    identical string would be flagged as a stale split on any public surface.

    This test pins today's behaviour. It does not ratify 77/78: which figure the
    renderer should carry is a decision about a published number, and it belongs
    to the maintainer who can amend the receipt of record.
    """
    gen_1 = load_citable_receipts()[0]
    rendered = format_kind_precision_for_render(gen_1)
    assert rendered == (
        "kind-precision 0.835 (not_a_directive 77/78; "
        "weak_directive 4/20; advisory until adjudicated)"
    )
    assert_kind_precision_render_safe(rendered, gen_1)


# ---------------------------------------------------------------------------
# Renderer guards: bare kind score RED; recall-not-measured
# ---------------------------------------------------------------------------


def test_bare_kind_precision_render_poison_goes_red() -> None:
    receipt = load_calibration_receipt(_DOCS_RECEIPT)
    bare = f"kind-precision {receipt.kind_precision_aggregate}"
    with pytest.raises(BareKindPrecisionRenderError):
        assert_kind_precision_render_safe(bare, receipt)
    # Safe form includes both class splits.
    safe = format_kind_precision_for_render(receipt)
    assert "0.835" in safe
    assert "77/78" in safe
    assert "4/20" in safe
    assert_kind_precision_render_safe(safe, receipt)


def test_kind_precision_render_requires_receipt_and_renders_when_supplied() -> None:
    with pytest.raises(BareKindPrecisionRenderError, match="receipt"):
        assert_kind_precision_render_safe("kind-precision 0.835")

    receipt = load_calibration_receipt(_DOCS_RECEIPT)
    rendered = format_kind_precision_for_render(receipt)
    assert_kind_precision_render_safe(rendered, receipt)


def test_no_receipt_refuses_the_space_separated_claim_too() -> None:
    """The separator must not decide whether an unverifiable claim is refused.

    'kind precision' is the form the public-copy ban already recognises
    (``kind[ -]precision``); a guard that only saw the hyphen left the
    no-receipt branch — the one where nothing can be checked — the most
    permissive of the three.
    """
    for claim in (
        "kind precision 0.835",
        "vacuity kind precision was 0.835 for this run",
        "Kind Precision: advisory",
    ):
        with pytest.raises(BareKindPrecisionRenderError, match="receipt"):
            assert_kind_precision_render_safe(claim)


def test_no_receipt_render_of_the_receipt_block_key_is_not_a_claim() -> None:
    """``"kind_precision": null`` is the absence of a claim, not a claim.

    The census receipt serialises that key on every path; treating the
    underscored key as a claim would refuse the legitimate
    UNMEASURED_GENERATION_MISMATCH receipt.
    """
    assert_kind_precision_render_safe('{"kind_precision": null, "recall": "UNMEASURED"}')


def test_no_receipt_passes_a_render_that_claims_no_kind_precision() -> None:
    """UNMEASURED_GENERATION_MISMATCH is legitimate, not a violation.

    A render carrying no kind-precision claim has nothing to validate, so the
    absent receipt is not itself an error. Only an unverifiable CLAIM is refused.
    """
    assert_kind_precision_render_safe(
        "flag-precision UNMEASURED_GENERATION_MISMATCH "
        "(no calibration claim for this instrument triple)"
    )


# ---------------------------------------------------------------------------
# #237: document-level co-occurrence backstop over the citable registry
# ---------------------------------------------------------------------------


def _split_pair(receipt: VacuityFlagCalibrationReceipt) -> tuple[str, str]:
    return (
        f"{receipt.kind_precision_not_a_directive_correct}/"
        f"{receipt.kind_precision_not_a_directive_n}",
        f"{receipt.kind_precision_weak_directive_correct}/"
        f"{receipt.kind_precision_weak_directive_n}",
    )


@pytest.mark.parametrize("cited_index", [0, 1])
def test_backstop_refuses_every_registry_members_bare_aggregate(cited_index: int) -> None:
    """Paired disclosure is a registry-wide rule, not a default-receipt rule.

    RED before this guard looped the registry: the caller holds one generation's
    receipt and the document cites the other's aggregate, so the old
    ``agg in rendered`` comparison never fired and the bare figure published
    clean (the #218 reproduction, both directions). The refusal names the
    receipt whose splits are missing, so a pass/fail here cannot be read as
    incidental substring luck.
    """
    registry = load_citable_receipts()
    cited, held = registry[cited_index], registry[1 - cited_index]
    document = f"The detector's kind-precision is {cited.kind_precision_aggregate}."

    with pytest.raises(BareKindPrecisionRenderError, match=cited.receipt_id):
        assert_kind_precision_render_safe(document, held)


@pytest.mark.parametrize("cited_index", [0, 1])
def test_backstop_refuses_a_registered_aggregate_carrying_one_split_only(
    cited_index: int,
) -> None:
    """Both splits, not either: the aggregate means nothing without the pair.

    Same call shape as the row above -- the caller holds the other generation's
    receipt -- so this is the registry loop being asked whether half a class
    split satisfies paired disclosure at document scope. It does not.
    """
    registry = load_citable_receipts()
    cited, held = registry[cited_index], registry[1 - cited_index]
    nad, wd = _split_pair(cited)

    for lone_split in (nad, wd):
        document = (
            f"kind-precision {cited.kind_precision_aggregate}, with {lone_split} adjudicated."
        )
        with pytest.raises(BareKindPrecisionRenderError, match=cited.receipt_id):
            assert_kind_precision_render_safe(document, held)


def test_backstop_refuses_a_figure_only_aggregate_with_no_receipt() -> None:
    """A bare aggregate does not need the words 'kind precision' to be a claim.

    Without a receipt the guard used to inspect the wording only, so an
    aggregate spelled as a plain figure was the one bare form that survived the
    strictest branch. The registry supplies the figure, so it no longer does.
    """
    gen_2 = load_citable_receipts()[1]

    with pytest.raises(BareKindPrecisionRenderError, match=gen_2.receipt_id):
        assert_kind_precision_render_safe(f"The detector scored {gen_2.kind_precision_aggregate}.")


def test_backstop_passes_a_document_carrying_both_complete_generation_pairs() -> None:
    """The legitimate direction: two coherent citations in one document.

    Each half is built by the canonical serializer, so the document states each
    aggregate beside the splits its own receipt records.
    """
    gen_1, gen_2 = load_citable_receipts()
    document = (
        f"Generation 1 (superseded): {format_kind_precision_for_render(gen_1)}\n\n"
        f"Generation 2 (current): {format_kind_precision_for_render(gen_2)}\n"
    )

    assert_kind_precision_render_safe(document, gen_1)
    assert_kind_precision_render_safe(document, gen_2)


def test_backstop_passes_the_named_residual_mismatched_local_pairing() -> None:
    """The residual, pinned as a fact rather than left as a hidden hole.

    Co-occurrence is document-level and there is no prose claim parser (an
    allowlist of known-good figures was rejected on #218), so a Gen-2 headline
    wearing Gen-1's splits passes HERE whenever the Gen-2 splits appear anywhere
    else in the document. The same figure tuple is refused at construction by
    ``KindPrecisionClaim`` -- see
    ``test_kind_precision_claim_refuses_backstop_named_residual_pairing`` -- so
    the residual is scoped to prose that bypasses the claim object, and it
    closes as prose migrates to it.
    """
    gen_1, gen_2 = load_citable_receipts()
    gen_1_nad, gen_1_wd = _split_pair(gen_1)
    gen_2_nad, gen_2_wd = _split_pair(gen_2)
    document = (
        f"kind-precision {gen_2.kind_precision_aggregate} "
        f"(not_a_directive {gen_1_nad}; weak_directive {gen_1_wd})\n\n"
        f"Elsewhere: the {gen_2.receipt_id} receipt records not_a_directive "
        f"{gen_2_nad} and weak_directive {gen_2_wd}."
    )

    assert_kind_precision_render_safe(document, gen_1)


def test_backstop_leaves_plain_decimals_and_no_claim_documents_alone() -> None:
    """No claim-detector was introduced: ordinary decimals are ordinary prose."""
    gen_1 = load_citable_receipts()[0]

    assert_kind_precision_render_safe("The release threshold is 0.99.", gen_1)
    assert_kind_precision_render_safe("The release threshold is 0.99.")
    assert_kind_precision_render_safe("This report contains no precision claim.", gen_1)


def test_recall_claim_is_scoped_to_the_backing_receipt() -> None:
    unmeasured = load_calibration_receipt(_DOCS_RECEIPT)
    measured = load_calibration_receipt(_ADJ_RECEIPT)
    claim = (
        "vacuity recall measured 0.7331-0.7524; stratified FPC 95% [0.66, 0.874]; "
        "skill cluster bootstrap 95% [0.622, 0.913] (n=120, skills n=47)"
    )

    with pytest.raises(ValueError, match="recall"):
        assert_recall_not_claimed_measured(claim, unmeasured)
    assert_recall_not_claimed_measured(claim, measured)
    with pytest.raises(ValueError, match="interval"):
        assert_recall_not_claimed_measured("vacuity recall measured 0.7524 (n=120)", measured)
    assert_recall_not_claimed_measured("recall: UNMEASURED", unmeasured)
    with pytest.raises(ValueError, match="receipt"):
        assert_recall_not_claimed_measured(claim)

    assert unmeasured.recall == "UNMEASURED"
    raw = json.loads(_DOCS_RECEIPT.read_text(encoding="utf-8"))
    assert raw["recall"] == "UNMEASURED"


# ---------------------------------------------------------------------------
# Exclusion label honesty
# ---------------------------------------------------------------------------


def test_exclusion_label_carries_flag_based_pending_review_and_receipt() -> None:
    receipt = load_calibration_receipt(_DOCS_RECEIPT)
    label = exclusion_label_for_flag(
        flag_evidence_status="CALIBRATED_FROZEN_CAPTURE",
        calibration_receipt=receipt,
    )
    assert "flag-based" in label.lower()
    assert "pending review" in label.lower()
    assert "0.972" in label
    assert "0.923" in label
    assert "0.986" in label
    assert "CALIBRATED_FROZEN_CAPTURE" in label
    assert "unreviewed model judgement" in label.lower()

    mismatch = exclusion_label_for_flag(
        flag_evidence_status="UNMEASURED_GENERATION_MISMATCH",
        calibration_receipt=None,
    )
    assert "UNMEASURED_GENERATION_MISMATCH" in mismatch
    assert "flag-based" in mismatch.lower()


# ---------------------------------------------------------------------------
# Census / clause-evidence surfaces
# ---------------------------------------------------------------------------


def test_census_never_emits_bare_kind_precision_or_measured_recall(tmp_path: Path) -> None:
    from skill_harness.extractor.corpus_census import format_human_report, run_census

    path = tmp_path / "cal.jsonl"
    skill = {
        "slug": "cal-skill",
        "ok": True,
        "extractor_model": _CAL_MODEL,
        "system_prompt_sha256": _CAL_PROMPT,
        "tool_schema_sha256": _CAL_SCHEMA,
        "clauses": [
            {
                "clause_index": 0,
                "clause_text": "be nice",
                "axis": "compliance_proxy",
                "comparator": "increase",
                "oracle_tier": 1,
                "vacuity_flag": "semantic_vacuous_pending_review",
                "vacuity_kind": "weak_directive",
            },
            {
                "clause_index": 1,
                "clause_text": "use bullets",
                "axis": "structure_score",
                "comparator": "increase",
                "oracle_tier": 1,
                "vacuity_flag": "none",
                "falsifying_case": {
                    "input_population_spec": "lists",
                    "expected_directional_pair": "A more structured",
                    "min_reproducibility": 0.8,
                },
            },
        ],
    }
    path.write_text(json.dumps(skill) + "\n", encoding="utf-8")
    result = run_census(path)
    assert result.flag_evidence_status == "CALIBRATED_FROZEN_CAPTURE"
    assert result.kind_evidence_advisory_count == 1
    assert result.kind_evidence_adjudicated_count == 0
    assert result.vacuity_weak_directive_count == 1
    human = format_human_report(result)
    assert "0.835" in human
    assert "77/78" in human
    assert "4/20" in human
    assert "recall: UNMEASURED" in human
    assert "ADVISORY" in human
    receipt = result.to_receipt()
    assert receipt["vacuity_evidence"]["recall"] == "UNMEASURED"
    kp = receipt["vacuity_evidence"]["kind_precision"]
    assert kp is not None
    assert "77/78" in kp["not_a_directive"]
    assert "4/20" in kp["weak_directive"]
    # Poison: bare aggregate without class split must go RED.
    with pytest.raises(BareKindPrecisionRenderError):
        assert_kind_precision_render_safe(
            f"kind-precision {result._calibration_receipt.kind_precision_aggregate}",  # type: ignore[union-attr]
            result._calibration_receipt,
        )


def test_census_generation_mismatch_renders_unmeasured_and_passes_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import skill_harness.extractor.corpus_census as census

    guarded_receipts: list[object] = []
    original_guard = census.assert_recall_not_claimed_measured  # type: ignore[attr-defined]

    def observe_guard(rendered: str, receipt: object = "not supplied") -> None:
        guarded_receipts.append(receipt)
        original_guard(rendered, receipt)  # type: ignore[arg-type]

    monkeypatch.setattr(census, "assert_recall_not_claimed_measured", observe_guard)

    path = tmp_path / "mismatch.jsonl"
    skill = {
        "slug": "mismatch-skill",
        "ok": True,
        "extractor_model": "other-model",
        "system_prompt_sha256": "1" * 64,
        "tool_schema_sha256": "2" * 64,
        "clauses": [],
    }
    path.write_text(json.dumps(skill) + "\n", encoding="utf-8")

    result = census.run_census(path)
    assert result.flag_evidence_status == "UNMEASURED_GENERATION_MISMATCH"
    assert result.to_receipt()["vacuity_evidence"]["recall"] == "UNMEASURED"
    report = census.format_human_report(result)
    assert "UNMEASURED_GENERATION_MISMATCH" in report
    assert "recall: UNMEASURED" in report
    assert guarded_receipts == [None, None]


def test_clause_evidence_exposes_policy_fields_separately(tmp_path: Path) -> None:
    from skill_harness.extractor.clause_evidence import (
        append_extraction_result,
        load_clause_evidence,
    )
    from skill_harness.extractor.models import ExtractedClause, ExtractionResult

    sha = "d" * 64
    result = ExtractionResult(
        skill_id=sha,
        name="x",
        source_path="/tmp/x",
        source_sha256=sha,
        clauses=[
            ExtractedClause(
                clause_index=0,
                clause_text="Prefer elegance.",
                axis="elegance",
                comparator="increase",
                oracle_tier=2,
                vacuity_flag="semantic_vacuous_pending_review",
                vacuity_kind="weak_directive",
                vacuity_reason="not measurable",
            )
        ],
        raw_frontmatter={},
        extractor_model=_CAL_MODEL,
        system_prompt_sha256=_CAL_PROMPT,
        tool_schema_sha256=_CAL_SCHEMA,
    )
    out = tmp_path / "e.jsonl"
    append_extraction_result(out, result)
    outcome = load_clause_evidence(out, sha)
    assert outcome.kind == "measured"
    assert outcome.measured is not None
    row = outcome.measured.rows[0]
    assert row.vacuity_kind == "weak_directive"
    assert row.kind_evidence_status == "ADVISORY"
    assert row.adjudicated_vacuity_kind is None
    assert row.flag_evidence_status == "CALIBRATED_FROZEN_CAPTURE"
    assert outcome.measured.summary.flag_evidence_status == "CALIBRATED_FROZEN_CAPTURE"
    assert "0.972" in outcome.measured.summary.exclusion_label
    # No operational path from the row's raw kind.
    from skill_harness.extractor.vacuity_policy import (
        decision_ready_vacuity_kind,
        derive_vacuity_policy,
    )

    view = derive_vacuity_policy(
        instrument=outcome.measured.instrument,
        vacuity_flag=row.vacuity_flag,
        predicted_vacuity_kind=row.vacuity_kind,
        source_sha256=sha,
        clause_text="Prefer elegance.",
    )
    assert decision_ready_vacuity_kind(view) is None


def test_clause_evidence_default_pool_calibrates_gen1_and_rejects_foreign(
    tmp_path: Path,
) -> None:
    from skill_harness.extractor.clause_evidence import (
        append_extraction_result,
        load_clause_evidence,
    )
    from skill_harness.extractor.models import ExtractionResult

    out = tmp_path / "evidence.jsonl"
    for sha, model in (("e" * 64, _CAL_MODEL), ("f" * 64, "foreign-model")):
        append_extraction_result(
            out,
            ExtractionResult(
                skill_id=sha,
                name=model,
                source_path=f"/tmp/{model}",
                source_sha256=sha,
                clauses=[],
                raw_frontmatter={},
                extractor_model=model,
                system_prompt_sha256=_CAL_PROMPT,
                tool_schema_sha256=_CAL_SCHEMA,
            ),
        )

    calibrated = load_clause_evidence(out, "e" * 64)
    assert calibrated.measured is not None
    assert calibrated.measured.summary.flag_evidence_status == "CALIBRATED_FROZEN_CAPTURE"
    assert calibrated.measured.calibration_receipt is not None
    assert calibrated.measured.calibration_receipt.receipt_id == (
        "vacuity-flag-calibration-2026-08-08"
    )

    foreign = load_clause_evidence(out, "f" * 64)
    assert foreign.measured is not None
    assert foreign.measured.summary.flag_evidence_status == "UNMEASURED_GENERATION_MISMATCH"
    assert foreign.measured.calibration_receipt is None
