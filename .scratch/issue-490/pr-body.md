# Evidence body — issue #490

## What changed

Added a `Subject identity` section to `skill.html`, populated from the receipt's
`subject_identity` block. The section renders with the same absent/refusal
discipline `_identity_rows` uses for instrument identity. Three code artifacts:

- `_subject_identity_section()` in `src/skill_harness/sitegen/render.py` — new
  function, parallel to `_delivery_section()`.
- `$subject_identity_section` template variable added to
  `src/skill_harness/sitegen/templates/skill.html`, between Instrument identity
  and Source of record.
- `render_skill_page()` passes the new variable to the template.

## Acceptance criteria

### AC1: 1.4.0 receipt with `subject_identity` including `subject_model` renders the identity block

**What I built:** `_subject_identity_section()` renders all six fields
(`skill_id`, `harness_version`, `metric_version`, `implementation_hash`,
`subject_model`, `arms`) when the block exists. The section heading is
"Subject identity", matching the ticket's decision.

**Test:** `test_subject_identity_section_v14_renders_subject_model` — asserts
`"anthropic/claude-sonnet-5"` and `"subject_model"` appear in the HTML.
`test_subject_identity_section_v14_renders_all_fields` — asserts all six keys
appear. `test_full_render_v14_shows_subject_identity_section` — integration:
`render_skill_page` with a 1.4.0 receipt includes "Subject identity" and the
subject model value.

**Observation:** Before the change, `_subject_identity_section` did not exist
and these tests raised `ImportError`. After, all three pass.

### AC2: 1.1.0–1.3.0 receipt with `subject_identity` but no `subject_model` renders the block and shows `subject_model` absent

**What I built:** The function iterates a fixed key list including
`subject_model`. When the key is absent from the mapping, it renders
`ABSENT_TEXT` ("absent from this receipt") — not a claim.

**Test:** `test_subject_identity_section_v11_shows_subject_model_absent` —
asserts `"absent from this receipt"` appears, that `"subject_model"` appears as
a key, and that the other fields (`skill_id` etc.) render their values.
`test_full_render_v11_shows_subject_identity_section` — integration: full page
render includes the section with the absent marker. `test_v11_receipt_does_not
_render_pointer` — asserts the pointer text does NOT appear (the block exists, so
the pointer path is not taken).

**Observation:** A 1.1.0 receipt with `subject_identity` but no
`subject_model` renders the provenance fields and a single absent row for
`subject_model`. A reader sees the receipt carries the block without a subject
pin.

### AC3: 1.0.0 receipt with no `subject_identity` renders a compact pointer

**What I built:** When `receipt.get("subject_identity")` is not a Mapping, the
function renders a one-line paragraph: "subject not recorded in this receipt;
the prose source may name it (`source.prose_path`)". This is the compact
pointer the decision (S443) specified — not silence, not a restatement of the
interpretation rule.

**Test:** `test_subject_identity_section_v10_renders_pointer` — asserts
`"subject not recorded"` and `"README.md"` (the prose path) appear.
`test_full_render_v10_shows_subject_pointer` — integration: full page render
includes the pointer. `test_v14_receipt_does_not_render_pointer` — asserts a
1.4.0 receipt does NOT render the pointer (both arms covered).

**Observation:** A 1.0.0 receipt renders the pointer. The prose path is
visible and clickable in context. A reader who does not need it skips one line;
the cost is mild redundancy and it is self-correcting.

## Mutation receipt

No mutation receipt is required by this ticket's acceptance criteria. The tests
are fixture-only and pin external behaviour (rendered HTML content) rather than
internal branching, which satisfies the standard without mutation testing.

## Gate

```
ruff check src tests          ✅
ruff format --check src tests ✅
mypy --strict src/ tests/     ✅
```

All 9 new tests pass. All 8 existing `test_sitegen_delivery.py` tests pass.
