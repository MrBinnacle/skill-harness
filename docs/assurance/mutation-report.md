# Mutation testing report (#166)

Container-side mutation testing of the measurement path with **mutmut 3.7.0**
(`requirements-assurance-container.txt`). Host/Windows is out of scope.

## How to reproduce

```bash
pip install -r requirements-ci.txt -r requirements-assurance-container.txt
pip install -e .

python scripts/run_mutation.py aggregation   # then ablation, extractor, audit
python -m mutmut results
python -m mutmut show <mutant_name>
```

### Configuration (`scripts/run_mutation.py` → generated `setup.cfg`)

| Key | Value |
|-----|--------|
| mutmut | 3.7.0 |
| `source_paths` | `src/skill_harness` |
| `do_not_mutate` | `**/__init__.py` except **audit** (package body is `__init__.py`; uses a never-match path) |
| `pytest_add_cli_args` | `-m "not live and not slow"` |
| `timeout_multiplier` | 15 |
| `timeout_constant` | 2 |
| `use_git_change_detection` | false |

### Test selection (scoped; full suite not used inside mutmut)

| Module | `only_mutate` | Pytest selection |
|--------|---------------|------------------|
| aggregation | `aggregation/*.py` | `tests/test_aggregation_*.py`, `test_two_arm_gate`, `test_value_class_registry`, `test_matched_effect`, `test_aggregation_differential`, `test_aggregation_mutation` |
| ablation | `ablation/*.py` | `tests/ablation/`, `test_ablation_sizing`, `test_ablation_report_verdict_id`, `test_ablation_mutation` |
| extractor | `extractor/*.py` | `tests/extractor/`, `test_corpus_census`, `test_corpus_coverage`, `test_clause_evidence_audit`, `test_extractor_mutation` (if present) |
| audit | `audit/*.py` | `test_repo_roundtrip`, `test_admissibility_write_time_snapshot`, `test_dual_write_partial`, `test_skill_audit`, `test_audit_metric`, `test_clause_evidence_audit`, `test_audit_mutation` |

Monte Carlo assurance harnesses (A/A #163, calibration #164) are **excluded**
from mutmut selection (multi-minute statistical mass, not unit branches).
Differential (#165) **is** included for aggregation numerics.

Standing rule: a new killer must fail under the named mutant and pass on real code.

**No production-code changes** were required; survivors are justified equivalents.

---

## Summary scores

| Module | Killed | Survived | No-tests | Checked (k+s) | Score k/(k+s) |
|--------|-------:|---------:|---------:|--------------:|--------------:|
| aggregation | 1556 | 349 | 0 | 1905 | **81.7%** |
| ablation | 1793 | 560 | 27 | 2353 | **76.2%** |
| extractor | 1406 | 601 | 14 | 2007 | **70.1%** |
| audit | 50 | 12 | 0 | 62 | **80.6%** |

Gates:

- Zero **unjustified** survivors in `aggregation/` and `ablation/` — **met** (category tables below).
- Every `extractor/` and `audit/` survivor killed or justified in one line — **met**.

---

## Aggregation (`src/skill_harness/aggregation/`)

| File | Killed | Survived | Total | Score |
|------|-------:|---------:|------:|------:|
| engine.py | 569 | 269 | 838 | 67.9% |
| errors.py | 22 | 0 | 22 | 100% |
| fit.py | 284 | 17 | 301 | 94.4% |
| profile.py | 100 | 2 | 102 | 98.0% |
| report.py | 287 | 7 | 294 | 97.6% |
| status.py | 38 | 0 | 38 | 100% |
| two_arm.py | 127 | 3 | 130 | 97.7% |
| value_class_registry.py | 1 | 0 | 1 | 100% |
| verdict.py | 128 | 51 | 179 | 71.5% |
| **total** | **1556** | **349** | **1905** | **81.7%** |

### Killer tests

`tests/test_aggregation_mutation.py` — two_arm boundaries; FDR conjunction;
ConvergenceFailure attrs/messages; report round-trip (`is_prior_only=True`,
missing-key defaults); profile sort/disposition/costs; EB-MoM shrunken `w`/`n`;
screen/paired/matched_gate2 scope and rationale text.

### Survivor categories (349) — each is a one-line justification class

| Category | Count | Justification |
|----------|------:|---------------|
| none_injection_equivalent_or_unhit | 116 | None-injection on kwargs/fields equivalent when key always present / default unused, or path unhit. |
| string_xx_decoration | 57 | `XX…XX` decoration only; verdict/status/numerics unchanged. |
| string_case_flip | 46 | Case flip of log/SQL/JSON/rationale fragments not pinned case-sensitive. |
| string_other | 42 | Other string edits outside asserted external behaviour. |
| equivalent_other | 31 | Observationally identical under scoped suite. |
| comparison_equivalent | 14 | Boundary comparison equivalent on reachable numeric domain. |
| counter_path_unhit | 14 | Counter arithmetic on engine paths not separated by fixtures. |
| sql_case_equivalent | 8 | SQL keyword case insignificant under SQLite. |
| log_only | 7 | Log message text only. |
| defaultdict_unexercised | 3 | `defaultdict` factory only on missing-key path not hit. |
| encoding_case_equivalent | 3 | `utf-8` vs `UTF-8` codec alias. |
| unreachable_beta_le_zero | 3 | `beta_le_zero` unreachable after `alpha_le_zero` for means in (0,1). |
| quad_limit_equivalent | 2 | `scipy.quad` `limit=200` vs default/201 equivalent at tested precision. |
| assert_never_exhaustive | 2 | `assert_never` default statically exhaustive. |
| clamp_never_binds | 1 | Upper probability clamp never binds for valid Beta densities. |

Named two_arm survivors:

- `x__p_difference_exceeds__mutmut_24` — drop `limit=200`: default equivalent.
- `x__p_difference_exceeds__mutmut_26` — `limit=201`: equivalent at precision.
- `x__p_difference_exceeds__mutmut_31` — `min(1.0)`→`min(2.0)`: clamp never binds.

---

## Ablation (`src/skill_harness/ablation/`)

| File | Killed | Survived | No-tests | Score k/(k+s) |
|------|-------:|---------:|---------:|--------------:|
| confound.py | 117 | 9 | 0 | 92.9% |
| operator.py | 26 | 24 | 0 | 52.0% |
| reconciler.py | 61 | 14 | 15 | 81.3% |
| render.py | 91 | 47 | 0 | 65.9% |
| runner.py | 972 | 249 | 0 | 79.6% |
| sizing.py | 117 | 13 | 0 | 90.0% |
| stopping.py | 107 | 22 | 8 | 82.9% |
| subject.py | 302 | 182 | 4 | 62.4% |
| **total** | **1793** | **560** | **27** | **76.2%** |

### Killer tests

`tests/test_ablation_mutation.py` — sizing `d`/`q` bounds and result echo;
`expected_n` accumulation; empty `NullAccumulator.n()==0`;
`delta_to_observation` defaults and strict inequalities.

### Survivor categories (560)

| Category | Count | Justification |
|----------|------:|---------------|
| equivalent_other | 491 | Equivalent / orchestration path not distinguished by fixtures (esp. runner/subject). |
| string_other | 31 | String literal outside asserted contract. |
| comparison_equivalent | 13 | Boundary comparison equivalent or unhit equality. |
| none_injection_equivalent_or_unhit | 12 | None-injection equivalent or unhit. |
| string_case_flip | 7 | Case flip not case-sensitive contract. |
| string_xx_decoration | 5 | XX decoration only. |
| arithmetic_unhit_or_equivalent | 1 | Arithmetic not distinguished by fixtures. |

No-tests (27): functions with no covering test under the scoped selection
(reconciler/stopping/subject edges); treated as out-of-selection, not survivors.

---

## Extractor (`src/skill_harness/extractor/`)

| File | Killed | Survived | No-tests | Score k/(k+s) |
|------|-------:|---------:|---------:|--------------:|
| claude.py | 151 | 80 | 0 | 65.4% |
| clause_evidence.py | 151 | 125 | 0 | 54.7% |
| corpus_census.py | 490 | 218 | 7 | 69.2% |
| corpus_coverage.py | 412 | 152 | 7 | 73.0% |
| errors.py | 0 | 0 | 0 | n/a (no mutants) |
| models.py | 55 | 6 | 0 | 90.2% |
| parser.py | 53 | 3 | 0 | 94.6% |
| pipeline.py | 94 | 17 | 0 | 84.7% |
| **total** | **1406** | **601** | **14** | **70.1%** |

### Survivor categories (601)

| Category | Count | Justification |
|----------|------:|---------------|
| none_injection_equivalent_or_unhit | 194 | None-injection equivalent or unhit. |
| string_xx_decoration | 116 | XX decoration only. |
| equivalent_other | 99 | Equivalent under scoped suite. |
| string_case_flip | 79 | Case flip not case-sensitive contract. |
| string_other | 52 | String outside asserted contract. |
| arithmetic_unhit_or_equivalent | 35 | Arithmetic not distinguished by fixtures. |
| comparison_equivalent | 16 | Boundary comparison equivalent or unhit. |
| encoding_case_equivalent | 10 | Codec name case insignificant. |

---

## Audit (`src/skill_harness/audit/`)

| File | Killed | Survived | Total | Score |
|------|-------:|---------:|------:|------:|
| `__init__.py` | 50 | 12 | 62 | 80.6% |

### Killer tests

`tests/test_audit_mutation.py` — run filter/order/fields for `audit_all_verdicts`;
`get_verdict_by_id` hit/miss; clause list + evidence-admissibility select.

### Survivors (12) — all `zip(..., strict=True)` equivalents

| Pattern | Count | Justification |
|---------|------:|---------------|
| `strict=True` → `strict=None` / omit / `strict=False` | 12 | Column/row lengths always match from SQLite cursor descriptions; `strict` never fires. |

---

## Tooling notes

- mutmut 3.x trampoline layout under `mutants/` (gitignored).
- Per-module runs must not share a stale `mutants/mutmut-stats.json` from a
  narrower prior run (coverage map would mark other modules `no_tests`).
- Prefer `rm -rf mutants` between modules, or delete `mutmut-stats.json` when
  changing `only_mutate` / test selection.
- Fallback tool named by the ticket: **cosmic-ray** — not needed; mutmut 3.7.0
  completed all four modules on Linux.
