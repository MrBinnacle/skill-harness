# What SERS is

Status: descriptive statement of record, 2026-08-28. Measured, not quoted.

This document exists because two questions were being answered inconsistently: *what does SERS
require*, and *which artifact is the answer*. It states what SERS is today. It does not change
SERS, and it does not freeze it.

## The one-sentence answer

**SERS is a machine-readable vocabulary for publishing one skill efficacy verdict, whose central
rule is that a missing number is a typed refusal and never an invented score, and it is a
candidate representation under test rather than a settled contract.**

## Why this is not a freeze

An external proposal's Phase 0 lists "current SERS contract" among the items to freeze before
further work. That line is **not adopted**. The operator ruled on 2026-08-28:

> *"Do not proceed with downstream implementation until the contract conflict is resolved... treat
> SERS as a candidate contract under resolution, not silently freeze either version."*

Freezing requires knowing which distinctions the receipt must preserve. That is the output of a
decision-set elicitation which has been written and has not run. Until it does, freezing would
lock in a representation whose adequacy nothing has established. **This document therefore
describes; it does not ratify.**

For the same reason, this document makes **no claim that SERS preserves the distinctions the
harness's decisions require.** That question is open. Anyone who needs that claim needs the
elicitation, not this file.

## Where SERS actually lives: three artifacts, not one

SERS is not published in a single place. Three artifacts each enforce part of it, and they are
not equivalent.

| Artifact | What it is | What it enforces |
|---|---|---|
| [`sers.schema.json`](sers.schema.json) | JSON Schema draft 2020-12, `additionalProperties: false` | Field presence, types, enum membership, and the `CUT` <-> `cut_sub_reason` biconditional |
| [`README.md`](README.md) | Prose specification | States every schema rule, **plus rules the schema does not carry**, and in two places describes the shape in terms that would produce a rejected receipt |
| `tests/test_sers_conformance.py` | Conformance harness | Schema validity of every shipped receipt, **equality** of schema enums to the code enums, rejection of the poison fixtures, and one rule found in neither spec: `source.prose_path` must resolve to a file that exists |

**The schema is the operative contract.** It is the artifact that mechanically decides whether a
receipt conforms, and it is the artifact the conformance harness runs. The README is
authoritative on *intent* and is the only place the rules are written down at all. The
harness is authoritative on *drift*: it is what makes a silent divergence between schema and code
enums fail CI.

## The measured divergences

Five README statements were tested against the schema on 2026-08-28. Each test constructs a
receipt from the shipped `synthetic-control-keep-2026-07-27.json` and mutates one field. The
control passes first: the unmutated receipt validates.

| # | README statement | Schema behaviour | Direction |
|---|---|---|---|
| 1 | "`wrong_instrument` ... Never `true` on a `KEEP` or `CUT`." | Accepts `wrong_instrument: true` on a `KEEP` | prose stricter |
| 2 | "`unmeasured_sub_reason` ... `null` when the receipt is a measured `KEEP`/`CUT`" | Accepts `unmeasured_sub_reason: "no_data"` on a measured `KEEP` | prose stricter |
| 3 | "`declared_synthetic_control` ... Must be `true` when the underlying effect is a declared synthetic positive control" | Accepts the synthetic-control receipt with the field removed entirely | prose stricter |
| 4 | "The cost triple, each leg a `token_figure`: **standing** / **fired** / **aux**" | Requires the keys `standing_tokens`, `fired_tokens`, `aux_tokens`; a receipt using the README's names is rejected | prose misleading |
| 5 | `value_class` table lists `null` as a row among string values | Accepts JSON `null` only; the string `"null"` is rejected | prose misleading |

Three prose rules are unenforced. Two prose formulations, followed literally by an implementer
who read only the README, produce a non-conforming receipt.

Rows 1-3 are the more consequential direction. A rule that exists only in prose is a rule that
holds only while every author reads the prose, and row 3 governs the field that separates an
instrument validation from a production claim about a skill.

### Reproducing this table

Run against the repository root:

```python
import json, pathlib
from jsonschema import Draft202012Validator

schema = json.loads(pathlib.Path("docs/sers/sers.schema.json").read_text("utf-8"))
v = Draft202012Validator(schema)
base = json.loads(
    pathlib.Path("docs/sers/receipts/synthetic-control-keep-2026-07-27.json").read_text("utf-8")
)
assert v.is_valid(base), "control failed: baseline receipt does not validate"

def probe(label, mutate):
    r = json.loads(json.dumps(base))
    mutate(r)
    print(("UNENFORCED" if v.is_valid(r) else "enforced  "), label)

def keep(r):
    r["verdict"] = "KEEP"
    r["cut_sub_reason"] = None

probe("1 wrong_instrument on KEEP", lambda r: (keep(r), r.update(wrong_instrument=True)))
probe("2 unmeasured_sub_reason on measured KEEP",
      lambda r: (keep(r), r.update(unmeasured_sub_reason="no_data")))
probe("3 declared_synthetic_control removed",
      lambda r: r.pop("declared_synthetic_control", None))
probe("4 README cost leg names",
      lambda r: r.update(cost={"standing": {"tokens": 10},
                               "fired": {"tokens": 20},
                               "aux": {"tokens": 0}}))
probe("5 value_class as the string \"null\"", lambda r: r.update(value_class="null"))
```

Observed 2026-08-28: rows 1, 2 and 3 print `UNENFORCED`; rows 4 and 5 print `enforced`.

## What SERS requires today

Read off the schema, which is the operative artifact.

**Always present** (eleven required fields): `sers_version`, `skill_name`, `verdict`,
`cut_sub_reason`, `unmeasured_sub_reason`, `value_class`, `evidence_admissibility`, `cost`,
`instrument_identity`, `source`, `summary`. `cut_sub_reason`, `unmeasured_sub_reason` and
`value_class` are required *keys* that may hold `null`; presence is mandatory, a value is not.

**Optional:** `wrong_instrument`, `declared_synthetic_control`, `measurements`.
`subject_identity` is optional on `1.0.0` and required on `1.1.0` and `1.2.0`.
`delivery` is required on `1.2.0` and absent on `1.0.0` and `1.1.0`.

**Closed vocabularies**, each checked for equality against the code enum in CI:

- `verdict`: `KEEP`, `CUT`, `CANT_TELL_YET`
- `cut_sub_reason`: `subsumed`, `no_lift`, `harmful`, `null`
- `unmeasured_sub_reason`: `no_data`, `inadmissible`, `underpowered`, `falsifying_case_missing`,
  `budget_exhausted`, `falsifying_case_stale`, `fdr_correction_failed`, `mechanical_vacuous`,
  `null`
- `value_class`: `transformative-lift`, `trap-discipline`, `calibration`, `null`
- `evidence_admissibility.status`: `admissible`, `inadmissible`, `mixed`, `not_applicable`
- `delivery.channel` (from 1.2.0): `description_only`, `body_and_description`, `not_instrumented`

**Conditionals the schema enforces:** `cut_sub_reason` is a non-null member when
`verdict` is `CUT`, and is `null` when `verdict` is `KEEP` or `CANT_TELL_YET`. When
`sers_version` is `1.1.0` or `1.2.0`, `subject_identity` is required. When
`sers_version` is `1.2.0`, `delivery` is required and must carry `channel`,
`exposure`, and `pi_c`. Cross-field rules on `delivery.channel` (`description_only`
requires `pi_c.hat = 0`; `body_and_description` requires `pi_c.invocations > 0`)
are schema-enforced. Every other cross-field rule in the README is prose only.

**The refusal shape.** Every numeric leg is one of two closed object forms -- a measured value,
or an object carrying `refusal` from a fixed vocabulary. There is no third form. Omitting the
figure, substituting a placeholder, or free-typing a reason string is non-conforming.

**The delivery block (1.2.0).** The `delivery` block attributes value to one of the skill's two
products: the standing description or the body. Required from `sers_version` 1.2.0; absent on
earlier versions. Carries `channel` (closed vocabulary: `description_only`, `body_and_description`,
`not_instrumented`), `exposure` (treated-arm exposure rate or refusal), and `pi_c` (invocation
rate with Clopper-Pearson interval or refusal). Cross-field rules: `description_only` requires
`pi_c.hat = 0`; `body_and_description` requires `pi_c.invocations > 0`. The receipt minting
path reads `pi_c` and `exposure` from the run's `config_json` and never recomputes them.

**The gate term.** `evidence_admissibility` is the only permitted spelling. The bare form is
rejected, and a poison fixture holds that line in CI.

**Version semantics.** `sers_version` is one of `"1.0.0"`, `"1.1.0"`, or `"1.2.0"`. Receipts
carrying different values are declared non-comparable. From `1.1.0`, `subject_identity` is
required. From `1.2.0`, `delivery` is required.

## What this document does not settle

- **Whether the three artifacts should be reconciled, and in which direction.** Rows 1-3 could be
  closed by adding schema conditionals, or by demoting the prose to guidance. Both are changes to
  the contract, and the ruling stops downstream contract changes until the decision set is known.
- **Whether the current field set is adequate.** That is the elicitation's question.
- **Any new refusal or inability state.** None is added here, and none should be added ahead of
  the elicitation: a state introduced before a decision is shown to need it is the manufactured
  distinction that [ADR 0001](../adr/0001-architecture-admitted-on-demonstrated-decision-requirement.md)
  refuses.

*Revisit if:* the schema, the README, or the conformance harness changes -- the divergence table
is a measurement with a date on it, and an edit to any of the three invalidates it.
