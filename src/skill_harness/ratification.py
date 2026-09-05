"""Ratification records (RAT) + the mechanical preflight gate on --execute.

Why this exists (#47, operator-picked MECHANICAL binding; landed by #57):
un-ratified spend must be mechanically impossible. Every row-pick is an
append-only record under ``docs/ratifications/RAT-NNNN-<skill-slug>.md``, and
the runner refuses ``run ablation --execute`` unless the invocation references
a record that (a) exists with status RATIFIED, (b) states a ``hard_cap_usd``
exactly equal to the budget passed into the ``run_budget`` insert, and
(c) scope-matches the invocation (skill id + task family + estimand name).
Dry-run stays ungated.

This module is the CLI-layer preflight component (``preflight.py`` lineage,
per #47's placement ruling) — deliberately NOT inside ``skill_harness.oc``,
which stays pure math with no knowledge of records or spend.

Two parsers exist on purpose: this module's schema parser feeds the spend-time
gate, and ``scripts/drift_check.py`` (DC-12) carries its own independent
minimal reader for the CI-time ledger check. They are a differential pair —
a parse bug in one is observable against the other — so neither imports the
other's logic.

The OBS front-matter schema (#41 ratified field list) also lives here: the
ticket's front-matter parse fixtures double as the RAT/OBS schema contract
tests, and DC-13's activation (owed to the first PR touching
``docs/observations/``) will consume this schema.
"""

from __future__ import annotations

import enum
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from skill_harness.oracles.calibration.cost_projection import EVALUATION_HARD_CAP_USD
from skill_harness.semantics import Estimand

# ---------------------------------------------------------------------------
# Constants (registered wording — #45 via #47: the self-certified branch must
# carry this verbatim disclosure line; DC-12 checks it ledger-wide in CI)
# ---------------------------------------------------------------------------

DISCLOSURE_LINE = "internally derived, not externally deliberated"

RAT_ID_PATTERN = re.compile(r"^RAT-\d{4}$")

_RAT_STATUSES = frozenset({"DRAFT", "RATIFIED"})
_GATES = frozenset({"gate1", "gate2"})
_SME_STATUSES = frozenset({"deliberated", "self-certified"})

# The record's cost block must be produced by the live cost_projection
# function matching its gate (#56 review carry-in: never hand arithmetic,
# never a snapshot constant — DC-9 bans those by token).
_REQUIRED_COST_PROVENANCE = {"gate1": "project_trial_usd", "gate2": "project_pair_usd"}


class RatificationError(ValueError):
    """A record failed to parse or violated the ratified schema."""


# ---------------------------------------------------------------------------
# Generic front-matter parsing (no external YAML dependency, house idiom)
# ---------------------------------------------------------------------------

Scalar = str | int | float
FrontmatterValue = Scalar | dict[str, Scalar]


def _coerce_scalar(raw: str) -> Scalar:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def parse_frontmatter(text: str) -> dict[str, FrontmatterValue]:
    """Parse a leading ``---`` front-matter block into a dict.

    Deliberately minimal and deterministic: flat ``key: value`` scalars plus
    ONE level of nesting (a bare ``key:`` line opening a block of two-space
    indented ``sub: value`` lines) — exactly the shapes the ratified RAT and
    OBS field lists use. No lists, anchors, or multi-line scalars; a record
    needing those is a schema conversation, not a parser feature.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise RatificationError("no front-matter block: file must start with '---'")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        raise RatificationError("unterminated front-matter block (no closing '---')") from None

    result: dict[str, FrontmatterValue] = {}
    open_block: dict[str, Scalar] | None = None
    for lineno, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        indented = line.startswith("  ")
        stripped = line.strip()
        if ":" not in stripped:
            raise RatificationError(f"malformed front-matter line {lineno}: {stripped!r}")
        key, _, raw = stripped.partition(":")
        key = key.strip()
        if indented:
            if open_block is None:
                raise RatificationError(
                    f"malformed front-matter line {lineno}: indented value with no open block"
                )
            open_block[key] = _coerce_scalar(raw)
            continue
        if raw.strip() == "":
            open_block = {}
            result[key] = open_block
        else:
            open_block = None
            result[key] = _coerce_scalar(raw)
    return result


def _read_frontmatter(path: Path) -> tuple[dict[str, FrontmatterValue], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RatificationError(f"cannot read {path}: {exc}") from exc
    return parse_frontmatter(text), text


def _require(
    fields: dict[str, FrontmatterValue], name: str, kind: str, path: Path
) -> FrontmatterValue:
    if name not in fields:
        raise RatificationError(f"{path.name}: required {kind} field {name!r} is missing")
    return fields[name]


def _require_str(fields: dict[str, FrontmatterValue], name: str, kind: str, path: Path) -> str:
    value = _require(fields, name, kind, path)
    if not isinstance(value, str) or not value.strip():
        raise RatificationError(f"{path.name}: field {name!r} must be a non-empty string")
    return value


def _require_number(fields: dict[str, FrontmatterValue], name: str, kind: str, path: Path) -> float:
    value = _require(fields, name, kind, path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RatificationError(f"{path.name}: field {name!r} must be numeric")
    return float(value)


# ---------------------------------------------------------------------------
# RAT record schema (front-matter mirror of the load-bearing #47 fields)
# ---------------------------------------------------------------------------


class RatRecord(BaseModel):
    """The machine-parseable mirror of one ratification record.

    Only the load-bearing fields are mirrored (#47: the full eleven-field
    checklist lives as prose in the record body; the front-matter carries
    exactly what the gate and DC-12 consume mechanically).  Gate-2 records
    may additionally carry the dual-MME and gamma fields that the paired-lane
    Gate-2 read uses to reconstruct the registered design. Those knobs have
    no defaults here: a missing value stays None, and the reader refuses by
    name rather than authoring the Amendment-4 recommended row at parse time.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    rat_id: str
    status: str
    skill_id: str
    task_family: str
    estimand: str
    gate: str
    n: int
    worst_case_cost_usd: float
    hard_cap_usd: float
    cost_provenance: str
    sme_status: str
    ratified_date: str
    gamma: float | None = None
    delta_min: float | None = None
    q_min: float | None = None
    #: #421: the hazard action pattern the trap-discipline read matches against
    #: every bash tool-call command in an epoch. Registered on the record the way
    #: the oracle knobs are, so a later run cannot quietly change what "entered"
    #: means. Optional alone only when both hazard fields are absent (a record
    #: that predates them); when either is present both are required together.
    hazard_action: str | None = None
    #: #421: the minimum Null-arm hazard-entry rate a trap-discipline read will
    #: accept. Half-open (0, 1]. Must be >= delta_min when delta_min is set: a
    #: floor below the minimum detectable effect cannot certify BENEFIT. Paired
    #: with hazard_action — one without the other is refused at parse.
    hazard_floor: float | None = None
    #: #421: the subject model the pilot ran, so a sized run on a different
    #: subject cannot launch silently. Optional at parse time (existing records
    #: without it still parse); required at every preflight_sized_run call
    #: (refuses by name when missing — not gated on evidence_db).
    pilot_subject_model: str | None = None
    #: #421: a dated block waiving a pilot_subject_model / priced-subject
    #: mismatch. Present iff pilot_subject_model differs from the priced subject
    #: and the transfer is authorised. Names the reason and the measurement.
    subject_change_waiver: dict[str, str] | None = None
    #: #424: the scoring-oracle kind the record authorises. ``pass_fail`` is the
    #: legacy conjunction oracle (Full pass AND Null fail); ``invariant`` is the
    #: split oracle (invariant_oracle I + completion_oracle C). Required for
    #: trap-discipline; absent on pass_fail records.
    outcome_type: str | None = None
    #: #424: the completion-rate margin the decision rule compares against.
    #: ``delta_min`` when absent — the minimum detectable effect the record
    #: already registered, so the completion margin inherits the same bar.
    completion_margin: float | None = None


def _cents(usd: float) -> int:
    return round(usd * 100)


def parse_rat_record(path: Path) -> RatRecord:
    """Parse + schema-validate one RAT record.

    Validity here covers internal consistency at spend time (cap within the
    #40 ceiling, cap >= the record's own worst-case cost, cent-quantized cap,
    gate-matched cost provenance, registered estimand, disclosure line when
    self-certified). DC-12 re-checks the ledger-wide subset in CI with an
    independent parser — defense in depth, not duplication.

    :raises RatificationError: on any parse or schema violation.
    """
    fields, text = _read_frontmatter(path)

    rat_id = _require_str(fields, "rat", "RAT", path)
    if not RAT_ID_PATTERN.match(rat_id):
        raise RatificationError(f"{path.name}: rat id {rat_id!r} does not match RAT-NNNN")

    status = _require_str(fields, "status", "RAT", path)
    if status not in _RAT_STATUSES:
        raise RatificationError(f"{path.name}: status {status!r} not in {sorted(_RAT_STATUSES)}")

    estimand = _require_str(fields, "estimand", "RAT", path)
    registered = {e.value for e in Estimand}
    if estimand not in registered:
        raise RatificationError(
            f"{path.name}: estimand {estimand!r} not a registered value "
            f"{sorted(registered)} (a forward-looking ratification may not use 'n/a')"
        )

    gate = _require_str(fields, "gate", "RAT", path)
    if gate not in _GATES:
        raise RatificationError(f"{path.name}: gate {gate!r} not in {sorted(_GATES)}")

    n_value = _require_number(fields, "n", "RAT", path)
    if n_value != int(n_value) or int(n_value) < 1:
        raise RatificationError(f"{path.name}: n must be a positive integer; got {n_value}")

    worst_case = _require_number(fields, "worst_case_cost_usd", "RAT", path)
    hard_cap = _require_number(fields, "hard_cap_usd", "RAT", path)
    if hard_cap > EVALUATION_HARD_CAP_USD:
        raise RatificationError(
            f"{path.name}: hard_cap_usd {hard_cap} exceeds the registered "
            f"${EVALUATION_HARD_CAP_USD:.2f} per-evaluation ceiling (#40)"
        )
    if abs(hard_cap * 100 - round(hard_cap * 100)) > 1e-6:
        raise RatificationError(
            f"{path.name}: hard_cap_usd {hard_cap} is not cent-quantized "
            "(#47: the cap is the worst-case cost rounded up to the cent)"
        )
    if hard_cap < worst_case - 1e-9:
        raise RatificationError(
            f"{path.name}: hard_cap_usd {hard_cap} is below the record's own "
            f"worst-case cost {worst_case}"
        )

    cost_provenance = _require_str(fields, "cost_provenance", "RAT", path)
    required_provenance = _REQUIRED_COST_PROVENANCE[gate]
    if cost_provenance != required_provenance:
        raise RatificationError(
            f"{path.name}: cost_provenance {cost_provenance!r} must be "
            f"{required_provenance!r} for a {gate} record (live-price projection only)"
        )

    sme_status = _require_str(fields, "sme_status", "RAT", path)
    if sme_status not in _SME_STATUSES:
        raise RatificationError(
            f"{path.name}: sme_status {sme_status!r} not in {sorted(_SME_STATUSES)}"
        )
    if sme_status == "self-certified" and DISCLOSURE_LINE not in text:
        raise RatificationError(
            f"{path.name}: self-certified record must carry the verbatim "
            f"disclosure line {DISCLOSURE_LINE!r} (#45 via #47)"
        )

    gamma_value: float | None = None
    gamma_raw = fields.get("gamma")
    if gamma_raw is not None:
        if isinstance(gamma_raw, bool) or not isinstance(gamma_raw, (int, float)):
            raise RatificationError(f"{path.name}: field 'gamma' must be numeric")
        gamma_value = float(gamma_raw)
        if not 0.5 < gamma_value < 1.0:
            raise RatificationError(f"{path.name}: gamma must lie in (0.5, 1); got {gamma_value}")
    delta_min_value: float | None = None
    delta_min_raw = fields.get("delta_min")
    if delta_min_raw is not None:
        if isinstance(delta_min_raw, bool) or not isinstance(delta_min_raw, (int, float)):
            raise RatificationError(f"{path.name}: field 'delta_min' must be numeric")
        delta_min_value = float(delta_min_raw)
        if not 0.0 < delta_min_value < 1.0:
            raise RatificationError(
                f"{path.name}: delta_min must lie in (0, 1); got {delta_min_value}"
            )
    q_min_value: float | None = None
    q_min_raw = fields.get("q_min")
    if q_min_raw is not None:
        if isinstance(q_min_raw, bool) or not isinstance(q_min_raw, (int, float)):
            raise RatificationError(f"{path.name}: field 'q_min' must be numeric")
        q_min_value = float(q_min_raw)
        if not 0.5 < q_min_value < 1.0:
            raise RatificationError(f"{path.name}: q_min must lie in (0.5, 1); got {q_min_value}")

    # #421: hazard_action + hazard_floor — required together when either is
    # present. hazard_action is a regex matched against bash tool-call commands;
    # hazard_floor is the minimum Null-arm entry rate a trap-discipline read
    # accepts. A record without both predates the fields.
    hazard_action_value: str | None = None
    hazard_action_raw = fields.get("hazard_action")
    if hazard_action_raw is not None:
        if not isinstance(hazard_action_raw, str) or not hazard_action_raw.strip():
            raise RatificationError(
                f"{path.name}: field 'hazard_action' must be a non-empty string"
            )
        try:
            re.compile(hazard_action_raw)
        except re.error as exc:
            raise RatificationError(
                f"{path.name}: field 'hazard_action' is not a valid regular expression: {exc}"
            ) from exc
        hazard_action_value = hazard_action_raw

    hazard_floor_value: float | None = None
    hazard_floor_raw = fields.get("hazard_floor")
    if hazard_floor_raw is not None:
        if isinstance(hazard_floor_raw, bool) or not isinstance(hazard_floor_raw, (int, float)):
            raise RatificationError(f"{path.name}: field 'hazard_floor' must be numeric")
        hazard_floor_value = float(hazard_floor_raw)
        if not 0.0 < hazard_floor_value <= 1.0:
            raise RatificationError(
                f"{path.name}: hazard_floor must lie in (0, 1]; got {hazard_floor_value}"
            )

    if (hazard_action_value is None) ^ (hazard_floor_value is None):
        present = "hazard_action" if hazard_action_value is not None else "hazard_floor"
        missing = "hazard_floor" if hazard_action_value is not None else "hazard_action"
        raise RatificationError(
            f"{path.name}: field {present!r} is set but {missing!r} is missing; "
            f"hazard_action and hazard_floor are required together (#421)"
        )
    if (
        hazard_floor_value is not None
        and delta_min_value is not None
        and hazard_floor_value < delta_min_value
    ):
        raise RatificationError(
            f"{path.name}: hazard_floor {hazard_floor_value} is below delta_min "
            f"{delta_min_value}; a floor below the minimum detectable effect "
            f"cannot certify BENEFIT (#421)"
        )

    # #421: pilot_subject_model — the subject the pilot ran, so a sized run on
    # a different subject cannot launch silently. Optional at parse time;
    # preflight_sized_run refuses by name when it is missing.
    pilot_subject_model_value: str | None = None
    pilot_subject_model_raw = fields.get("pilot_subject_model")
    if pilot_subject_model_raw is not None:
        if not isinstance(pilot_subject_model_raw, str) or not pilot_subject_model_raw.strip():
            raise RatificationError(
                f"{path.name}: field 'pilot_subject_model' must be a non-empty string"
            )
        pilot_subject_model_value = pilot_subject_model_raw

    # #421: subject_change_waiver — a dated block authorising a
    # pilot_subject_model / priced-subject mismatch. A nested front-matter block.
    subject_change_waiver_value: dict[str, str] | None = None
    subject_change_waiver_raw = fields.get("subject_change_waiver")
    if subject_change_waiver_raw is not None:
        if not isinstance(subject_change_waiver_raw, dict):
            raise RatificationError(
                f"{path.name}: field 'subject_change_waiver' must be a nested block"
            )
        subject_change_waiver_value = {str(k): str(v) for k, v in subject_change_waiver_raw.items()}

    # #424: outcome_type — the scoring-oracle kind the record authorises.
    # ``pass_fail`` is the legacy conjunction oracle; ``invariant`` is the
    # split oracle (invariant_oracle I + completion_oracle C). Optional alone;
    # required at evaluate-paired time for trap-discipline (refused by name
    # when absent).
    _OUTCOME_TYPES = frozenset({"pass_fail", "invariant"})
    outcome_type_value: str | None = None
    outcome_type_raw = fields.get("outcome_type")
    if outcome_type_raw is not None:
        if not isinstance(outcome_type_raw, str) or not outcome_type_raw.strip():
            raise RatificationError(f"{path.name}: field 'outcome_type' must be a non-empty string")
        if outcome_type_raw not in _OUTCOME_TYPES:
            raise RatificationError(
                f"{path.name}: outcome_type {outcome_type_raw!r} not in {sorted(_OUTCOME_TYPES)}"
            )
        outcome_type_value = outcome_type_raw

    # #424: completion_margin — the completion-rate margin the decision rule
    # compares against. Absent means delta_min (the minimum detectable effect
    # the record already registered). Half-open [0, 1).
    completion_margin_value: float | None = None
    completion_margin_raw = fields.get("completion_margin")
    if completion_margin_raw is not None:
        if isinstance(completion_margin_raw, bool) or not isinstance(
            completion_margin_raw, (int, float)
        ):
            raise RatificationError(f"{path.name}: field 'completion_margin' must be numeric")
        completion_margin_value = float(completion_margin_raw)
        if not 0.0 <= completion_margin_value < 1.0:
            raise RatificationError(
                f"{path.name}: completion_margin must lie in [0, 1); got {completion_margin_value}"
            )

    return RatRecord(
        rat_id=rat_id,
        status=status,
        skill_id=_require_str(fields, "skill_id", "RAT", path),
        task_family=_require_str(fields, "task_family", "RAT", path),
        estimand=estimand,
        gate=gate,
        n=int(n_value),
        worst_case_cost_usd=worst_case,
        hard_cap_usd=hard_cap,
        cost_provenance=cost_provenance,
        sme_status=sme_status,
        ratified_date=_require_str(fields, "ratified_date", "RAT", path),
        gamma=gamma_value,
        delta_min=delta_min_value,
        q_min=q_min_value,
        hazard_action=hazard_action_value,
        hazard_floor=hazard_floor_value,
        pilot_subject_model=pilot_subject_model_value,
        subject_change_waiver=subject_change_waiver_value,
        outcome_type=outcome_type_value,
        completion_margin=completion_margin_value,
    )


# ---------------------------------------------------------------------------
# OBS front-matter schema (#41 ratified field list)
# ---------------------------------------------------------------------------


class ObsCounts(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    epochs: int
    passes: int


class ObsFrontmatter(BaseModel):
    """The #41 ratified OBS field list (extras tolerated — records grow by
    dated amendment; only the ratified minimum is schema-checked)."""

    model_config = ConfigDict(frozen=True, strict=True)

    task_family: str
    arm: str
    counts: ObsCounts
    model: str
    date: str
    evidence: str
    pi_c: str
    estimand: str
    classification: str
    disposition_of_record: str


def parse_obs_frontmatter(path: Path) -> ObsFrontmatter:
    """Parse + schema-validate one OBS ledger record's front-matter.

    :raises RatificationError: on any parse or schema violation.
    """
    fields, _ = _read_frontmatter(path)
    counts_value = _require(fields, "counts", "OBS", path)
    if not isinstance(counts_value, dict):
        raise RatificationError(f"{path.name}: counts must be a nested block")
    for sub in ("epochs", "passes"):
        if not isinstance(counts_value.get(sub), int):
            raise RatificationError(f"{path.name}: counts.{sub} must be an integer")
    return ObsFrontmatter(
        task_family=_require_str(fields, "task_family", "OBS", path),
        arm=_require_str(fields, "arm", "OBS", path),
        counts=ObsCounts(
            epochs=int(counts_value["epochs"]),
            passes=int(counts_value["passes"]),
        ),
        model=_require_str(fields, "model", "OBS", path),
        date=_require_str(fields, "date", "OBS", path),
        evidence=_require_str(fields, "evidence", "OBS", path),
        pi_c=_require_str(fields, "pi_c", "OBS", path),
        estimand=_require_str(fields, "estimand", "OBS", path),
        classification=_require_str(fields, "classification", "OBS", path),
        disposition_of_record=_require_str(fields, "disposition_of_record", "OBS", path),
    )


# ---------------------------------------------------------------------------
# The gate decision (#47 mechanical binding, checks in ratified order)
# ---------------------------------------------------------------------------


class RefusalReason(enum.StrEnum):
    RECORD_MISSING = "record-missing"
    RECORD_INVALID = "record-invalid"
    STATUS_NOT_RATIFIED = "status-not-ratified"
    CAP_MISMATCH = "cap-mismatch"
    SCOPE_MISMATCH = "scope-mismatch"


class GateDecision(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    allowed: bool
    reason: RefusalReason | None
    detail: str


def _refuse(reason: RefusalReason, detail: str) -> GateDecision:
    return GateDecision(allowed=False, reason=reason, detail=detail)


def check_execute_ratification(
    record_path: Path | None,
    *,
    skill_id: str,
    task_family: str,
    estimand: str,
    max_usd: float,
) -> GateDecision:
    """Decide whether an --execute invocation may proceed (#47 binding).

    Pure decision function: no printing, no exiting — the CLI owns the
    refusal surface. Checks run in the ratified order: existence, validity,
    (a) status RATIFIED, (b) record cap == passed budget (compared as integer
    cents; #47 fixes record caps to cent-rounded values), (c) scope match on
    skill id + task family + estimand. Empty-string scope values mean the
    invocation did not declare that axis — refused with the axis named.
    """
    if record_path is None:
        return _refuse(
            RefusalReason.RECORD_MISSING,
            "no ratification record referenced; pass --ratification "
            "docs/ratifications/RAT-NNNN-<skill-slug>.md (see that dir's README)",
        )
    if not record_path.is_file():
        return _refuse(
            RefusalReason.RECORD_MISSING, f"ratification record {record_path} does not exist"
        )
    try:
        record = parse_rat_record(record_path)
    except RatificationError as exc:
        return _refuse(RefusalReason.RECORD_INVALID, str(exc))

    if record.status != "RATIFIED":
        return _refuse(
            RefusalReason.STATUS_NOT_RATIFIED,
            f"{record.rat_id} has status {record.status!r}; only RATIFIED records "
            "authorize spend (operator signs last, pre-spend)",
        )

    if _cents(record.hard_cap_usd) != _cents(max_usd):
        return _refuse(
            RefusalReason.CAP_MISMATCH,
            f"{record.rat_id} ratifies hard_cap_usd {record.hard_cap_usd:.2f} but "
            f"--max-usd passed {max_usd:.2f}; the record cap must equal the "
            "run_budget cap exactly",
        )

    declared = {"skill_id": skill_id, "task_family": task_family, "estimand": estimand}
    ratified = {
        "skill_id": record.skill_id,
        "task_family": record.task_family,
        "estimand": record.estimand,
    }
    problems = []
    for axis, passed in declared.items():
        if not passed:
            problems.append(f"{axis} not declared by the invocation")
        elif passed != ratified[axis]:
            problems.append(f"{axis} mismatch: record {ratified[axis]!r} != run {passed!r}")
    if problems:
        return _refuse(RefusalReason.SCOPE_MISMATCH, f"{record.rat_id}: " + "; ".join(problems))

    return GateDecision(
        allowed=True,
        reason=None,
        detail=f"{record.rat_id} authorizes {skill_id} / {task_family} / {estimand} "
        f"at ${record.hard_cap_usd:.2f}",
    )
