# Skill Efficacy Reporting Standard (SERS)

Machine-readable vocabulary for publishing a skill efficacy result so a third
party can validate the shape, and so this repo's own documented results stay
tied to the same enums the instrument emits.

- **What SERS is, and where the three artifacts disagree:** [`what-sers-is.md`](what-sers-is.md)
- **Schema:** [`sers.schema.json`](sers.schema.json) (JSON Schema draft 2020-12,
  `additionalProperties: false`)
- **Conforming instances:** [`receipts/`](receipts/)
- **Conformance harness:** `tests/test_sers_conformance.py`

## Core rule

**A missing number is a typed refusal, never an invented score.**

Every numeric field on a receipt is either:

1. a measured value (rate in `[0, 1]`, non-negative token count, …), or
2. an object carrying `refusal` with a closed vocabulary.

There is no third path. Omitting a figure silently, filling it with a
placeholder like `0.0` "for completeness", or free-typing a reason string is
non-conforming. The refusal vocabularies are fixed by this schema and drift-
checked against the code enums in CI.

## Fields

### `sers_version`

Vocabulary generation of the receipt. Receipts that disagree on
`sers_version` are not comparable. Supported values: `"1.0.0"`, `"1.1.0"`,
`"1.2.0"`, `"1.3.0"`, `"1.4.0"`.

### `skill_name`

The skill the verdict is about. Prefer the store/card `skill_name` string when
one exists so the receipt lines up with `value_class_for`.

### `verdict`

One of:

| Value | Meaning |
| --- | --- |
| `KEEP` | Measurably worth its slot under the registered estimand. |
| `CUT` | Remove from the library; see `cut_sub_reason`. |
| `CANT_TELL_YET` | Evidence does not support a keep/cut call. |

These strings are exactly the members of `KeepCutVerdict` in
`src/skill_harness/aggregation/verdict.py`.

### `cut_sub_reason`

Qualifies `CUT`. **Non-null if and only if `verdict` is `CUT`.**

| Value | Meaning |
| --- | --- |
| `subsumed` | Model already does the task without the skill (screen path; includes total ceiling `p0 = 1`). |
| `no_lift` | Measured where the model needed help; the skill did not deliver a transformative lift. |
| `harmful` | Skill made outcomes measurably worse (matched Gate-2 path only). |

Refusal semantics: a `CUT` without a sub-reason is invalid. A non-`CUT`
verdict with a non-null sub-reason is invalid.

### `unmeasured_sub_reason`

Qualifies an unmeasured / cannot-score path when the receipt is reporting one.
Members mirror `UnmeasuredSubReason` in
`src/skill_harness/aggregation/status.py` exactly — do not invent, rename, or
subset:

- `no_data`
- `inadmissible`
- `underpowered`
- `falsifying_case_missing`
- `budget_exhausted`
- `falsifying_case_stale`
- `fdr_correction_failed`
- `mechanical_vacuous`

`null` when the receipt is a measured `KEEP`/`CUT` (or a `CANT_TELL_YET` that
is not an aggregation-UNMEASURED path, e.g. wrong-instrument withhold).

### `value_class`

Skill value kind. Members mirror `ValueClass`:

| Value | Meaning |
| --- | --- |
| `transformative-lift` | Skill is meant to let the model succeed where it fails unaided. Screen-path `CUT(subsumed)` is valid only here. |
| `trap-discipline` | Guards one wrong action; high Null pass-rate does not mean "subsumed". |
| `calibration` | Makes a measurement trustworthy; same wrong-instrument rule as trap-discipline. |
| `null` | Unclassified — guard defaults to withhold `CUT`. |

### `outcome_type`

Scoring-oracle kind the record authorises (#424). Members mirror the
registered set in `ratification.py`:

| Value | Meaning |
| --- | --- |
| `pass_fail` | Legacy conjunction oracle (Full pass AND Null fail). |
| `invariant` | Split oracle: invariant_oracle (I) + completion_oracle (C). |

`null` on `pass_fail` records (absent from the record). Required for
trap-discipline; refused by name when absent.

### `wrong_instrument`

Optional boolean. `true` when a path **withheld** a `CUT` because
`value_class` is not `transformative-lift`. Never `true` on a `KEEP` or `CUT`.

**The field-evidence lane this flag names is UNBUILT.** It was deferred on
2026-09-02 under [#335](https://github.com/MrBinnacle/skill-harness/issues/335)
rather than built, because a lane whose only members are wrong-instrument
withholds needs the false-green outcome variable defined first, and that
variable does not exist
([#403](https://github.com/MrBinnacle/skill-harness/issues/403)). Nothing in this
repository consumes `wrong_instrument` today. Read it as a recorded reason for
a withheld verdict, not as a pointer to a destination. Receipts minted before that date carry summary text promising the
lane; they are append-only evidence and are not rewritten.

### `declared_synthetic_control`

Optional boolean. Must be `true` when the underlying effect is a declared
synthetic positive control (effect real by construction). A synthetic-control
`KEEP` is an instrument validation, not a production-skill KEEP.

### `evidence_admissibility`

**This is the only permitted form of the gate term.** A shorter un-qualified
form collides with a published framework's action-governance usage; SERS and
all companion text use the qualified term **evidence admissibility** only.

| `status` | Meaning |
| --- | --- |
| `admissible` | Cited evidence cleared the evidence admissibility gate and may enter aggregation. |
| `inadmissible` | Evidence exists but was gated out of aggregation (kept append-only). |
| `mixed` | Receipt cites both admissible and inadmissible evidence. |
| `not_applicable` | No store-backed evidence (prose-only encoding, mechanical audit, etc.). |

Refusal semantics: there is no silent default. A receipt that cannot state an
evidence admissibility status is non-conforming.

### `cost` (standing / fired / aux)

The cost triple, each leg a `token_figure`:

- **standing** — tokens charged every turn for the skill's listing/router line.
- **fired** — tokens charged when the skill body is loaded.
- **aux** — progressive-disclosure / side-doc tokens.

Each leg is either `{ "tokens": <non-negative int> }` or
`{ "refusal": "unmeasured" | "not_applicable" | "not_instrumented", ... }`.
A missing leg, a negative count, or a free-typed excuse is non-conforming.

### `delivery` (required from `sers_version` 1.2.0)

Value-delivery attribution: which of the skill's two products carried the
measured value. Required when `sers_version` is `1.2.0`; absent on `1.0.0`
and `1.1.0` receipts.

The delivery block carries three required fields:

| Field | Shape | Meaning |
| --- | --- | --- |
| `channel` | enum: `description_only`, `body_and_description`, `not_instrumented` | Which product carried the value. |
| `exposure` | `{ "value": 0..1, "passes"?, "epochs"? }` or refusal | Exposure rate in the treated arm. |
| `pi_c` | `{ "invocations", "trials", "hat", "ci_low", "ci_high", "confidence", "detector" }` or refusal | Invocation rate with Clopper-Pearson interval. |

The receipt field is `hat`. Ingest's `config_json` records the same figure as
`pi_c_hat`; the mint path renames on read and does not recompute.

Channel vocabulary:

| Value | Meaning |
| --- | --- |
| `description_only` | The standing description was read; the body was never loaded (`pi_c.hat = 0` with full exposure). |
| `body_and_description` | Invocations are present; the body was read in addition to the description. |
| `not_instrumented` | Receipts minted before detector v2; no delivery measurement available. |

Cross-field rules:
- `channel: description_only` requires `pi_c.hat == 0` (or `pi_c` as a refusal).
- `channel: body_and_description` requires `pi_c.invocations > 0` (or `pi_c` as a refusal).

Each sub-block (`exposure`, `pi_c`) is either a measured object or a typed
refusal — never a null number. The refusal vocabulary is
`"not_instrumented" | "not_applicable"`.

The receipt minting path reads `pi_c` and `exposure` from the run's
`config_json` and never recomputes them.

### `instrument_identity`

Generation stamp so any figure carries the generation that produced it.
Figures from different identities are **visibly non-comparable**.

| Field | Meaning |
| --- | --- |
| `extractor_model` | Model pin for the **extraction stage**: the model that read the run artifacts and produced the figures. Never the subject. Or a typed refusal. |
| `prompt_fingerprint` | Fingerprint of the exact prompt/system bytes (typically SHA-256 hex). |
| `schema_fingerprint` | Fingerprint of the tool schema or harness pin used. |

Refusal semantics: instrument identity is **required**, not optional. A
receipt without it cannot be validated. Legacy prose that predates the triple
must still record the best available pins rather than omit the object.

`extractor_model` is either a non-empty string or
`{ "refusal": "not_applicable" | "not_instrumented", "detail"? }`. A paired run
scored by a deterministic oracle has no model-based extraction stage, and the
refusal is how it says so. Repeating the subject pin here to fill the slot is
non-conforming: it would record an extraction that did not happen.

#### Which model was the subject? (`sers_version` 1.4.0 and the receipts before it)

Through 1.3.0 this field was documented as *"Extractor (or subject) model pin
that produced the figures"*. One field named two instruments answering two
different questions, and which one it named was not recorded. That is
[#479](https://github.com/MrBinnacle/skill-harness/issues/479).

From 1.4.0 the roles are separate fields:

| Question | Field |
| --- | --- |
| Which model was measured? | `subject_identity.subject_model` |
| Which model produced the figures from the run artifacts? | `instrument_identity.extractor_model` |

**Reading a receipt at 1.3.0 or earlier.** Its `extractor_model` carries one pin
for both roles and the receipt does not say which. Do not infer the subject from
it. Go to `source.prose_path`, which is the record that names what ran. Those
receipts are **not back-filled**: each is a dated record of a measurement that was
made, the store is append-only, and adding a `subject_model` to one would assert a
role assignment nobody wrote down. `sers_version` is the field that tells a reader
which generation's rules apply, and it is doing that job here.

### `measurements` (optional object)

Optional rates and apparatus gates. Each rate field is a `rate_or_refusal`:
either `{ "value": 0..1, "passes"?, "epochs"?, "detail"? }` or
`{ "refusal": <UnmeasuredSubReason \| "not_applicable">, "detail"? }`.

`go_nogo` is the pre-stated apparatus gate when one was registered
(`GO` / `NO_GO` / `NOT_APPLICABLE`).

New in 1.3.0 — trap-discipline measurement keys (#424):

| Field | Meaning |
| --- | --- |
| `hazard_entry_null` | Null-arm hazard-entry rate: fraction of Null epochs where the hazard pattern was entered. |
| `hazard_entry_full` | Full-arm hazard-entry rate: fraction of Full epochs where the hazard pattern was entered. |
| `null_completion_rate` | Null-arm completion rate: fraction of Null epochs where the completion oracle scored pass. |
| `full_completion_rate` | Full-arm completion rate: fraction of Full epochs where the completion oracle scored pass. |
| `silent_violation_rate` | Silent violation rate: fraction of epochs where completion held but invariant failed (C=1, I=0). |

Each is a `rate_or_refusal`. Absent on 1.2.0 and earlier receipts.

### `source`

Pointer at the prose source of record.

| Field | Meaning |
| --- | --- |
| `prose_path` | Repo-relative path (required). |
| `date` | ISO date of the underlying result when known. |
| `notes` | Free-text lineage note. |

v1 receipts are **hand-encoded** from already-documented results (no DB
exporter). Revisit when store-backed receipts multiply.

### `summary`

One-paragraph operator-facing summary. Must not invent numbers that are absent
from `measurements` / `cost`.

### `subject_identity` (required from `sers_version` 1.1.0)

Provenance block identifying the subject under test. Absent on 1.0.0
hand-encoded receipts; required from `sers_version` 1.1.0 onward.
Populate via `skill_harness.sers.build_subject_identity` — do not free-type
the fields.

| Field | Meaning |
| --- | --- |
| `skill_id` | SHA-256 hex of the exact `SKILL.md` bytes measured. |
| `harness_version` | Harness version that produced the receipt. |
| `metric_version` | Oracle metric version (e.g. `0.3.0`). |
| `implementation_hash` | SHA-256 hex of the oracle module source at mint/ingest time. |
| `arms` | Which arms ran: `null`, `full`, or both as an array. |
| `subject_model` | Model pin of the model that **executed the epochs**. Required from 1.4.0; absent before it. |

`subject_model` sits here rather than in `instrument_identity` because it is a
property of what was measured, not of what did the measuring. A skill is measured
*on* a model: the `(skill_id, subject_model)` pair is the subject, and `arms` says
which conditions that subject ran under. `instrument_identity` stamps the apparatus
that produced the figures, which is a different instrument answering a different
question.

It is the one field in the block the harness cannot derive from a file on disk, so
`build_subject_identity` takes it as an argument rather than computing it. A blank
pin is refused: a blank is a manufactured record, not a missing one.

## Conformance

```text
pytest tests/test_sers_conformance.py
```

The harness asserts:

1. every file in `receipts/` validates against the schema;
2. schema verdict / cut-sub-reason / unmeasured-sub-reason / value-class enums
   are **equal** to the code enums (silent drift fails CI);
3. poisoned fixtures under `tests/fixtures/sers/poison_*.json` **fail**
   validation (wrong verdict vocabulary, missing instrument identity, bare
   gate term where the qualified term is required, a 1.4.0 receipt whose
   `subject_identity` omits `subject_model`, and a free-typed `extractor_model`
   refusal outside the closed vocabulary);
4. no receipt minted before 1.4.0 has gained a `subject_model`. The store is
   append-only, so a back-fill is a rewritten record, not a repair.

## Hand-encoded v1 receipts

| Receipt | Verdict | Prose source |
| --- | --- | --- |
| `synthetic-control-keep-2026-07-27.json` | `KEEP` (declared synthetic control) | `README.md` / `docs/FAQ.md` |
| `double-ceiling-nogo-2026-07-09.json` | `CANT_TELL_YET` (NO-GO / structurally unmeasured) | `docs/case-studies/double-ceiling-structurally-unmeasured.md` |
| `reclass-append-only-evidence-design.json` | `CANT_TELL_YET` (wrong instrument, calibration) | `README.md` + `docs/observations/OBS-0005-*.md` |
| `gitpull-paired-n32-2026-09-03-sized.json` | `CANT_TELL_YET` (unresolved, trap-discipline; sized paired run n=32 under RAT-0001; the Null arm never met the hazard, `delivery.channel=body_and_description`) | `docs/ratifications/RAT-0001-git-pull-rebase-trap.md` |
| `superseded/gitpull-paired-k8-2026-09-01-detector-v2.json` | `CANT_TELL_YET` (underpowered, trap-discipline; admissible under detector v2; paired k=8, GO on discordance, `delivery.channel=description_only`); superseded 2026-09-03 by the sized-run receipt; it stays the GO datum that run was sized on | `docs/findings/pi-c-detector-blind-to-description-channel.md` |
| `superseded/gitpull-paired-k8-2026-09-01.json` | `CANT_TELL_YET` (inadmissible, wrong instrument, trap-discipline; refused at write time on zero detected invocations under detector v1); superseded 2026-09-02 | `docs/findings/pi-c-detector-blind-to-description-channel.md` |
| `superseded/reclass-git-pull-rebase-trap.json` | `CANT_TELL_YET` (wrong instrument, trap-discipline); superseded 2026-09-01, screen row D4-voided | `README.md` |

A 1.1.0 mint of the synthetic-control KEEP (same measurements, harness-populated
`subject_identity`) lives at
`tests/fixtures/sers/minted_synthetic_control_v1_1_0.json` and is pinned by
`tests/test_sers_conformance.py`. It is not published under `receipts/` because
the site generator keys pages by `skill_name` and refuses two receipts for one
skill; the 1.0.0 instance remains the published card.
