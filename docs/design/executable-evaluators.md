# Executable Evaluators

Executable evaluators are the deterministic evidence layer for atomic evaluation properties.
They do not make Skill Harness deterministic. Skill execution remains stochastic; the
measurement surface becomes deterministic wherever a property is mechanically decidable.

## Contracts

A `Property` is immutable and content-addressed from its statement, type, authority, and
ceiling. The Property Registry is the authority surface.

An `EvaluatorSpec` is immutable and content-addressed from evaluator code identity, version,
and dependency identity. An evaluator returns exactly `PASS`, `FAIL`, or `UNSUPPORTED`.

An `EvaluationReceipt` points to the property, evaluator, and observation set by hash.
Receipts carry structured evidence and the evaluator ceiling.

## Authority

- A mechanically decidable property may register a deterministic evaluator as authoritative.
- A deterministic `FAIL` is final for that atomic property. Judgment cannot overrule it.
- `UNSUPPORTED` means the evaluator makes no claim. Residual judgment may supply a separate
  evidence class with its own ceiling.
- An evaluator cannot establish claims outside the registered property's ceiling.
- Criterion aggregation preserves atomic property states. It does not produce a scalar score.

## First fixture

`tests/fixtures/ts_go/` is the first deterministic fixture. It contains a small TypeScript
source file, its expected Go translation, and normalized observations. Two pure evaluators
operate on those observations:

1. required Go declarations are present;
2. declared TS→Go structural mappings match the fixed mapping table.

The evaluator boundary deliberately accepts normalized observations. A future runner may
populate those observations from real TypeScript and Go AST walks; the evaluator itself does
no I/O and makes no claim about observation extraction.

Semantic preservation is intentionally outside this slice. It remains a residual property
for judgment/oracle evidence.
