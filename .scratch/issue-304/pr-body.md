# Issue #304: Vale Taste style rules and CI

## Acceptance Criteria Progress

### Criterion 1: Six rule files with the message naming row and file

**Status**: Complete

Six rule files exist in `styles/Taste/`:
- `Dressing.yml` — message: "Dressing: '%s' is not allowed in prose."
- `Evidence.yml` — message: "Evidence: '%s' needs backing."
- `Generic-ness.yml` — message: "Generic-ness: '%s' is too vague."
- `Voice.yml` — message: "Voice: use active voice, not '%s'."
- `Register.yml` — message: "Register: avoid '%s'."
- `Brevity-and-order.yml` — message: "Brevity-and-order: '%s' is verbose."

Each rule file's message names the row (rule name) as required. All six rules
use `extends: existence` so `%s` expands to the matched text (the phrase the
reader wrote), not a substitution suggestion.

**Test**: `tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_rule_messages_name_existing_rows`

### Criterion 2: Twelve fixtures with poison control

**Status**: Complete

Twelve fixtures exist in `fixtures/vale/`:
- Pass fixtures: `Dressing-pass.md`, `Evidence-pass.md`, `Generic-ness-pass.md`, `Voice-pass.md`, `Register-pass.md`, `Brevity-and-order-pass.md`
- Fail fixtures: `Dressing-fail.md`, `Evidence-fail.md`, `Generic-ness-fail.md`, `Voice-fail.md`, `Register-fail.md`, `Brevity-and-order-fail.md`

Each fail fixture triggers exactly one finding for its associated rule, and the
finding's `Check` and message name that rule. A poison control fixture
(`poison-empty.md`) produces zero findings. Dressing uses `nonword: true` so
emoji tokens survive Vale's word tokenizer and fire on `Dressing-fail.md`.

**Test**: `tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_fail_fixtures_have_exactly_one_finding_for_named_row`
**Test**: `tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_pass_fixtures_have_zero_findings`
**Test**: `tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_poison_control_has_zero_findings`

### Criterion 3: Doctrine-to-rule agreement test

**Status**: Complete

Test `tests/test_vale_doctrine_agreement.py` contains 7 tests:
- `test_all_rule_files_exist` — every expected doctrine row has a corresponding rule file
- `test_rule_messages_name_existing_rows` — every rule file's message names an existing row
- `test_no_landing_rule` — no rule or fixture is named "Landing"
- `test_all_fixtures_are_parseable` — every fixture can be parsed by Vale
- `test_pass_fixtures_have_zero_findings` — pass fixtures produce zero findings (not merely exit 0; Vale exits 0 on warnings)
- `test_fail_fixtures_have_exactly_one_finding_for_named_row` — fail fixtures trigger exactly 1 warning whose Check and message name the row
- `test_poison_control_has_zero_findings` — poison control fixture produces zero findings

**Mutation**: Deleting `Voice.yml` causes `test_all_rule_files_exist` to fail with "Missing rule files for rows: {'Voice'}". The test asserts external behavior (file presence and Vale JSON output), not internal branching.

**Test**: `tests/test_vale_doctrine_agreement.py` (all 7 tests)

### Criterion 4: Vale CI job at warning level

**Status**: Complete

Vale CI job added to `.github/workflows/ci.yml`:
- Runs Vale at warning level (configured in `.vale.ini` with `MinAlertLevel = warning`)
- Runs fixtures and prose in two steps
- Added to `all-green` job dependencies
- The `test` job also installs the same pinned Vale binary so the doctrine-agreement tests can shell out on every matrix cell

**Test**: CI workflow runs Vale on all prose and fixtures on every push/PR; pytest runs the doctrine agreement suite.

### Criterion 5: Vale binary version pinned

**Status**: Complete

Vale version 3.9.1 pinned in both the `vale` job and the `test` job:
```yaml
VALE_VERSION=3.9.1
curl -sL "https://github.com/errata-ai/vale/releases/download/v${VALE_VERSION}/vale_${VALE_VERSION}_Linux_64-bit.tar.gz"
```

## Evidence

### Test Results

```
tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_all_rule_files_exist PASSED
tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_no_landing_rule PASSED
tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_all_fixtures_are_parseable PASSED
tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_pass_fixtures_have_zero_findings PASSED
tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_fail_fixtures_have_exactly_one_finding_for_named_row PASSED
tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_rule_messages_name_existing_rows PASSED
tests/test_vale_doctrine_agreement.py::TestDoctrineToRuleAgreement::test_poison_control_has_zero_findings PASSED
7 passed
```

### Per-rule hit counts on main (before gate)

Vale run at warning level over all prose (`README.md` + `docs/**/*.md`) — 33 warnings total:

| Rule | Hits |
|------|------|
| Brevity-and-order | 1 |
| Dressing | 6 |
| Evidence | 1 |
| Generic-ness | 25 |
| Register | 0 |
| Voice | 0 |
| **Total** | **33** |

### Fixture hit counts (fail fixtures only)

Each fail fixture triggers exactly one finding for its rule:

| Rule | Fixture | Hits | Check |
|------|---------|------|-------|
| Brevity-and-order | Brevity-and-order-fail.md | 1 | Taste.Brevity-and-order |
| Dressing | Dressing-fail.md | 1 | Taste.Dressing |
| Evidence | Evidence-fail.md | 1 | Taste.Evidence |
| Generic-ness | Generic-ness-fail.md | 1 | Taste.Generic-ness |
| Register | Register-fail.md | 1 | Taste.Register |
| Voice | Voice-fail.md | 1 | Taste.Voice |

### Mutation Campaign

| Mutation | Assertion killed | Result |
|----------|-----------------|--------|
| Delete `Voice.yml` | `test_all_rule_files_exist` | FAIL — "Missing rule files for rows: {'Voice'}" |

The `test_all_rule_files_exist` assertion pins the contract: every expected row must have a corresponding rule file. Removing any rule file turns this test red.

## Files Changed

- `styles/Taste/*.yml` — 6 rule files (existence-based; Dressing sets `nonword: true`)
- `fixtures/vale/*.md` — 12 fixtures + poison control
- `tests/test_vale_doctrine_agreement.py` — 7 tests (zero-finding pass/poison; fail asserts named row)
- `.github/workflows/ci.yml` — Vale CI job + Vale install in the test matrix, pinned v3.9.1
- `.scratch/issue-304/pr-body.md` — this file
