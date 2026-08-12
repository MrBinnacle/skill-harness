"""Vacuity evidence policy: generation-scoped calibration + advisory kinds (#188).

Statuses are always derived from the instrument triple + checked-in receipts.
Never extractor-authored. Raw ``vacuity_kind`` predictions are advisory until
independently adjudicated; a raw ``weak_directive`` never becomes decision-ready.

Flag-driven exclusion stays (flag-precision calibrated for the matching
generation only). Exclusion labeling is honest: flag-based, pending review,
generation-scoped precision receipt.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from skill_harness.extractor.models import ExtractorInstrument

FlagEvidenceStatus = Literal["CALIBRATED_FROZEN_CAPTURE", "UNMEASURED_GENERATION_MISMATCH"]
KindEvidenceStatus = Literal["ADVISORY", "ADJUDICATED"]
AdjudicatedVacuityKind = Literal[
    "weak_directive",
    "not_a_directive",
    "testable_directive",
    "undecided",
]
PredictedVacuityKind = Literal["weak_directive", "not_a_directive"]

_SHA_LEN: Final[int] = 64

_DEFAULT_RECEIPT_NAME: Final[str] = "vacuity-flag-calibration-2026-08-08.json"
# Repo-checkout path (editable install / worktree). Package-local mirror ships
# beside this module so installed wheels resolve without the docs/ tree.
_REPO_RECEIPT_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "docs" / "calibration" / _DEFAULT_RECEIPT_NAME
)
_PACKAGE_RECEIPT_PATH: Final[Path] = (
    Path(__file__).resolve().parent / "calibration" / _DEFAULT_RECEIPT_NAME
)

_ADJ_RECORDS_NAME: Final[str] = "vacuity-adjudication-2026-08-09.jsonl"
_REPO_ADJ_RECORDS_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "docs" / "calibration" / _ADJ_RECORDS_NAME
)
_PACKAGE_ADJ_RECORDS_PATH: Final[Path] = (
    Path(__file__).resolve().parent / "calibration" / _ADJ_RECORDS_NAME
)

_ADJUDICATED_KINDS: Final[frozenset[str]] = frozenset(
    {"weak_directive", "not_a_directive", "testable_directive", "undecided"}
)
_PREDICTED_KINDS: Final[frozenset[str]] = frozenset({"weak_directive", "not_a_directive"})


class MixedExtractorGenerationsError(ValueError):
    """Raised when callers attempt to pool rows across instrument generations."""


class BareKindPrecisionRenderError(ValueError):
    """Raised when a renderer would emit aggregate kind-precision without class split."""


@dataclass(frozen=True, slots=True)
class VacuityFlagCalibrationReceipt:
    """One frozen-capture calibration receipt bound to a complete instrument triple."""

    receipt_id: str
    capture_date: str
    extractor_model: str
    system_prompt_sha256: str
    tool_schema_sha256: str
    flagged_population_size: int
    adjudicated_rows: int
    seats: int
    flag_precision_weighted_undecided_wrong: float
    flag_precision_weighted_undecided_correct: float
    wilson_95_fpc_low: float
    wilson_95_fpc_high: float
    kind_precision_aggregate: float
    kind_precision_not_a_directive_correct: int
    kind_precision_not_a_directive_n: int
    kind_precision_weak_directive_correct: int
    kind_precision_weak_directive_n: int
    recall: Literal["UNMEASURED"]

    def instrument(self) -> ExtractorInstrument:
        return ExtractorInstrument(
            model_id=self.extractor_model,
            system_prompt_sha256=self.system_prompt_sha256,
            tool_schema_sha256=self.tool_schema_sha256,
        )

    def matches_instrument(self, instrument: ExtractorInstrument) -> bool:
        return self.instrument().same_generation_as(instrument)


@dataclass(frozen=True, slots=True)
class AdjudicationRecord:
    """One independently adjudicated clause verdict (never model-authored)."""

    source_sha256: str
    clause_context_sha256: str
    adjudicated_vacuity_kind: AdjudicatedVacuityKind
    adjudication_receipt: str


@dataclass(frozen=True, slots=True)
class VacuityPolicyView:
    """Derived evidence statuses for one clause. Pure function of inputs + receipts."""

    flag_evidence_status: FlagEvidenceStatus
    kind_evidence_status: KindEvidenceStatus
    predicted_vacuity_kind: PredictedVacuityKind | None
    adjudicated_vacuity_kind: AdjudicatedVacuityKind | None
    adjudication_receipt: str | None
    calibration_receipt: VacuityFlagCalibrationReceipt | None
    clause_context_sha256: str

    @property
    def decision_ready_kind(self) -> AdjudicatedVacuityKind | None:
        """Operational kind: adjudicated only. Raw predictions never qualify."""
        if self.kind_evidence_status != "ADJUDICATED":
            return None
        return self.adjudicated_vacuity_kind


def default_receipt_path() -> Path:
    """Path to the committed receipt of record."""
    if _PACKAGE_RECEIPT_PATH.is_file():
        return _PACKAGE_RECEIPT_PATH
    return _REPO_RECEIPT_PATH


def load_calibration_receipt(path: Path | str | None = None) -> VacuityFlagCalibrationReceipt:
    """Load one receipt JSON; numbers must match the ticket verbatim."""
    target = Path(path) if path is not None else default_receipt_path()
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{target}: expected a JSON object")
    return _receipt_from_mapping(raw)


def load_default_receipts() -> tuple[VacuityFlagCalibrationReceipt, ...]:
    """All checked-in receipts the policy layer knows about."""
    return (load_calibration_receipt(),)


def default_adjudication_records_path() -> Path:
    """Path to the committed per-row adjudication records of record."""
    if _PACKAGE_ADJ_RECORDS_PATH.is_file():
        return _PACKAGE_ADJ_RECORDS_PATH
    return _REPO_ADJ_RECORDS_PATH


def load_adjudication_records(
    path: Path | str | None = None,
) -> dict[tuple[str, str], AdjudicationRecord]:
    """Load checked-in adjudication records keyed on (source_sha256, clause_context_sha256).

    Fail-closed on malformed rows, unknown kinds, and duplicate join keys: an
    adjudication file that cannot be trusted whole upgrades nothing. A missing
    file returns an empty mapping (no records, everything stays ADVISORY).
    """
    target = Path(path) if path is not None else default_adjudication_records_path()
    if not target.is_file():
        return {}
    records: dict[tuple[str, str], AdjudicationRecord] = {}
    for lineno, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"{target}:{lineno}: expected a JSON object")
        source = raw.get("source_sha256")
        ctx = raw.get("clause_context_sha256")
        kind = raw.get("adjudicated_vacuity_kind")
        receipt = raw.get("adjudication_receipt")
        if not isinstance(source, str) or len(source) != _SHA_LEN:
            raise ValueError(f"{target}:{lineno}: source_sha256 invalid")
        if not isinstance(ctx, str) or len(ctx) != _SHA_LEN:
            raise ValueError(f"{target}:{lineno}: clause_context_sha256 invalid")
        if not isinstance(kind, str) or kind not in _ADJUDICATED_KINDS:
            raise ValueError(f"{target}:{lineno}: adjudicated_vacuity_kind invalid: {kind!r}")
        if not isinstance(receipt, str) or not receipt:
            raise ValueError(f"{target}:{lineno}: adjudication_receipt required")
        key = (source, ctx)
        if key in records:
            raise ValueError(f"{target}:{lineno}: duplicate adjudication join key")
        records[key] = AdjudicationRecord(
            source_sha256=source,
            clause_context_sha256=ctx,
            adjudicated_vacuity_kind=kind,  # type: ignore[arg-type]
            adjudication_receipt=receipt,
        )
    return records


def match_calibration_receipt(
    instrument: ExtractorInstrument | None,
    receipts: Sequence[VacuityFlagCalibrationReceipt] | None = None,
) -> VacuityFlagCalibrationReceipt | None:
    """Return the receipt whose complete triple matches, else None (fail closed)."""
    if instrument is None:
        return None
    pool = load_default_receipts() if receipts is None else receipts
    hits = [r for r in pool if r.matches_instrument(instrument)]
    if len(hits) != 1:
        return None
    return hits[0]


def clause_context_sha256(
    clause_text: str,
    *,
    context: str = "",
) -> str:
    """Stable clause identity hash. Never includes clause_index."""
    payload = clause_text + "\n" + context
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def adjudication_identity_key(
    source_sha256: str,
    clause_text: str,
    *,
    context: str = "",
) -> tuple[str, str]:
    """Join key for adjudication: (source_sha256, clause_context_sha256).

    Structurally excludes clause_index — index is unstable across extraction repeats.
    """
    if len(source_sha256) != _SHA_LEN:
        raise ValueError("source_sha256 must be a 64-char hex digest")
    return source_sha256, clause_context_sha256(clause_text, context=context)


def require_single_generation(
    instruments: Iterable[ExtractorInstrument | None],
) -> ExtractorInstrument | None:
    """Refuse mixed generations; return the sole instrument or None if all unknown.

    Raises ``MixedExtractorGenerationsError`` when two or more distinct complete
    triples appear, or when known triples are mixed with missing triples.
    """
    seen: list[ExtractorInstrument] = []
    unknown = 0
    for inst in instruments:
        if inst is None:
            unknown += 1
            continue
        if any(inst.same_generation_as(s) for s in seen):
            continue
        seen.append(inst)
    if len(seen) > 1:
        raise MixedExtractorGenerationsError(
            "mixed_extractor_generations: refusing to pool vacuity calibration "
            "across instrument triples"
        )
    if seen and unknown:
        raise MixedExtractorGenerationsError(
            "mixed_extractor_generations: known instrument mixed with generation-unknown rows"
        )
    if not seen:
        return None
    return seen[0]


def derive_vacuity_policy(
    *,
    instrument: ExtractorInstrument | None,
    vacuity_flag: str,
    predicted_vacuity_kind: str | None,
    source_sha256: str,
    clause_text: str,
    context: str = "",
    adjudication: AdjudicationRecord | None = None,
    receipts: Sequence[VacuityFlagCalibrationReceipt] | None = None,
) -> VacuityPolicyView:
    """Pure derivation of evidence statuses. Same inputs → same statuses."""
    ctx_sha = clause_context_sha256(clause_text, context=context)
    receipt = match_calibration_receipt(instrument, receipts)
    flag_status: FlagEvidenceStatus = (
        "CALIBRATED_FROZEN_CAPTURE" if receipt is not None else "UNMEASURED_GENERATION_MISMATCH"
    )

    pred: PredictedVacuityKind | None = None
    if isinstance(predicted_vacuity_kind, str) and predicted_vacuity_kind in _PREDICTED_KINDS:
        pred = predicted_vacuity_kind  # type: ignore[assignment]

    adj_kind: AdjudicatedVacuityKind | None = None
    adj_receipt: str | None = None
    kind_status: KindEvidenceStatus = "ADVISORY"

    if (
        adjudication is not None
        and adjudication.source_sha256 == source_sha256
        and adjudication.clause_context_sha256 == ctx_sha
        and adjudication.adjudicated_vacuity_kind in _ADJUDICATED_KINDS
    ):
        kind_status = "ADJUDICATED"
        adj_kind = adjudication.adjudicated_vacuity_kind
        adj_receipt = adjudication.adjudication_receipt
    # Mismatched adjudication identity → stay ADVISORY, no transfer.

    # Flag none: kind prediction should be absent; still no operational kind.
    _ = vacuity_flag  # flag drives exclusion elsewhere; statuses remain derived here.

    return VacuityPolicyView(
        flag_evidence_status=flag_status,
        kind_evidence_status=kind_status,
        predicted_vacuity_kind=pred,
        adjudicated_vacuity_kind=adj_kind if kind_status == "ADJUDICATED" else None,
        adjudication_receipt=adj_receipt if kind_status == "ADJUDICATED" else None,
        calibration_receipt=receipt,
        clause_context_sha256=ctx_sha,
    )


def decision_ready_vacuity_kind(view: VacuityPolicyView) -> AdjudicatedVacuityKind | None:
    """Sole operational kind path. Raw weak_directive / not_a_directive never pass."""
    return view.decision_ready_kind


def exclusion_label_for_flag(
    *,
    flag_evidence_status: FlagEvidenceStatus,
    calibration_receipt: VacuityFlagCalibrationReceipt | None,
) -> str:
    """Honest exclusion surface: flag-based + pending review + receipt scope."""
    base = (
        "flag-based exclusion pending review: semantic_vacuous_pending_review "
        "is an unreviewed model judgement about model instructions, not an "
        "adjudicated finding"
    )
    if flag_evidence_status == "CALIBRATED_FROZEN_CAPTURE" and calibration_receipt is not None:
        fp = calibration_receipt.flag_precision_weighted_undecided_wrong
        lo = calibration_receipt.wilson_95_fpc_low
        hi = calibration_receipt.wilson_95_fpc_high
        rid = calibration_receipt.receipt_id
        return (
            f"{base}; generation-scoped flag-precision {fp} "
            f"Wilson95+FPC [{lo}, {hi}] "
            f"(receipt {rid}; CALIBRATED_FROZEN_CAPTURE for matching instrument triple only)"
        )
    return (
        f"{base}; flag-precision UNMEASURED_GENERATION_MISMATCH "
        f"(no calibration claim for this instrument triple)"
    )


def format_kind_precision_for_render(receipt: VacuityFlagCalibrationReceipt) -> str:
    """Render kind-precision only with the class split. Bare aggregate is refused."""
    agg = receipt.kind_precision_aggregate
    nad_c = receipt.kind_precision_not_a_directive_correct
    nad_n = receipt.kind_precision_not_a_directive_n
    wd_c = receipt.kind_precision_weak_directive_correct
    wd_n = receipt.kind_precision_weak_directive_n
    text = (
        f"kind-precision {agg} "
        f"(not_a_directive {nad_c}/{nad_n}; "
        f"weak_directive {wd_c}/{wd_n}; advisory until adjudicated)"
    )
    assert_kind_precision_render_safe(text, receipt)
    return text


def assert_kind_precision_render_safe(
    rendered: str,
    receipt: VacuityFlagCalibrationReceipt | None = None,
) -> None:
    """Guard: aggregate kind score must never appear without both class splits.

    Poison direction: emitting the bare aggregate (e.g. 'kind-precision 0.835')
    without the receipt-backed class split must raise.
    """
    if receipt is None:
        raise BareKindPrecisionRenderError(
            "refusing to validate kind-precision rendering without a calibration receipt"
        )
    agg = _fmt_num(receipt.kind_precision_aggregate)
    if agg not in rendered and "kind-precision" not in rendered.lower():
        return
    # If aggregate appears, both class splits must sit beside it.
    nad = (
        f"{receipt.kind_precision_not_a_directive_correct}/"
        f"{receipt.kind_precision_not_a_directive_n}"
    )
    wd = (
        f"{receipt.kind_precision_weak_directive_correct}/{receipt.kind_precision_weak_directive_n}"
    )
    if agg in rendered and (nad not in rendered or wd not in rendered):
        raise BareKindPrecisionRenderError(
            f"refusing to render aggregate kind-precision without class split ({nad} and {wd})"
        )


def assert_recall_not_claimed_measured(rendered: str) -> None:
    """Guard: no surface may describe vacuity-flag recall as measured."""
    lowered = rendered.lower()
    if "recall" not in lowered:
        return
    forbidden = (
        "recall: measured",
        "recall measured",
        "recall is measured",
        "measured recall",
        "recall:measured",
    )
    for phrase in forbidden:
        if phrase in lowered:
            raise ValueError(f"refusing to claim vacuity recall is measured: found {phrase!r}")


def _fmt_num(value: float) -> str:
    # Prefer compact ticket form (0.835 not 0.835000).
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text


def _receipt_from_mapping(raw: Mapping[str, Any]) -> VacuityFlagCalibrationReceipt:
    triple = raw.get("instrument_triple")
    if not isinstance(triple, Mapping):
        raise ValueError("receipt missing instrument_triple")
    model = triple.get("extractor_model")
    prompt = triple.get("system_prompt_sha256")
    schema = triple.get("tool_schema_sha256")
    if not isinstance(model, str) or not model:
        raise ValueError("receipt instrument_triple.extractor_model invalid")
    if not isinstance(prompt, str) or len(prompt) != _SHA_LEN:
        raise ValueError("receipt instrument_triple.system_prompt_sha256 invalid")
    if not isinstance(schema, str) or len(schema) != _SHA_LEN:
        raise ValueError("receipt instrument_triple.tool_schema_sha256 invalid")

    fp = raw.get("flag_precision")
    kp = raw.get("kind_precision")
    sample = raw.get("sample")
    if not isinstance(fp, Mapping) or not isinstance(kp, Mapping):
        raise ValueError("receipt missing flag_precision or kind_precision")
    if not isinstance(sample, Mapping):
        raise ValueError("receipt missing sample")

    recall = raw.get("recall")
    if recall != "UNMEASURED":
        raise ValueError("receipt recall must be UNMEASURED")

    receipt_id = raw.get("receipt_id")
    capture_date = raw.get("capture_date")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise ValueError("receipt_id required")
    if not isinstance(capture_date, str) or not capture_date:
        raise ValueError("capture_date required")

    return VacuityFlagCalibrationReceipt(
        receipt_id=receipt_id,
        capture_date=capture_date,
        extractor_model=model,
        system_prompt_sha256=prompt,
        tool_schema_sha256=schema,
        flagged_population_size=int(sample["flagged_population_size"]),
        adjudicated_rows=int(sample["adjudicated_rows"]),
        seats=int(sample["seats"]),
        flag_precision_weighted_undecided_wrong=float(fp["weighted_undecided_wrong"]),
        flag_precision_weighted_undecided_correct=float(fp["weighted_undecided_correct"]),
        wilson_95_fpc_low=float(fp["wilson_95_fpc_low"]),
        wilson_95_fpc_high=float(fp["wilson_95_fpc_high"]),
        kind_precision_aggregate=float(kp["aggregate"]),
        kind_precision_not_a_directive_correct=int(kp["not_a_directive_correct"]),
        kind_precision_not_a_directive_n=int(kp["not_a_directive_n"]),
        kind_precision_weak_directive_correct=int(kp["weak_directive_correct"]),
        kind_precision_weak_directive_n=int(kp["weak_directive_n"]),
        recall="UNMEASURED",
    )
