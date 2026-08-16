"""#188 — vacuity evidence policy: generation-scoped calibration + advisory kinds.

External behaviour only: statuses derive from instrument triple + receipt;
raw weak_directive never becomes operational; mixed generations refused;
renderers cannot emit bare kind-precision or claim recall measured.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_harness.extractor.models import ExtractorInstrument
from skill_harness.extractor.vacuity_policy import (
    AdjudicationRecord,
    AmbiguousCalibrationReceiptError,
    BareKindPrecisionRenderError,
    MixedExtractorGenerationsError,
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
