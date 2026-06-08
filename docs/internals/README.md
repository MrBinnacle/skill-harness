# Skill Harness

> Clause-ablation differential testing for LLM skills. Measures whether each clause of a skill artifact produces a measurable directional effect — never asks *"is this output good?"*, asks *"does output A beat output B on the single axis claimed by clause N?"*

[![CI](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml)
[![CodeQL](https://github.com/MrBinnacle/skill-harness/actions/workflows/codeql.yml/badge.svg)](https://github.com/MrBinnacle/skill-harness/actions/workflows/codeql.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type-checked: mypy --strict](https://img.shields.io/badge/type%20checked-mypy%20strict-blue.svg)](http://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange.svg)](#status)

---

## What this is

Skill Harness is a deterministic evaluation framework for LLM skills — instruction files, prompt modules, behavioral overlays, and similar artifacts. Where traditional testing assumes deterministic execution, explicit oracles, and stable function boundaries, skills possess none of these. Skill Harness replaces them with four manufactured primitives:

| Traditional | Skill Harness |
|---|---|
| Oracle | Directional Pairing |
| Isolation | Clause Ablation |
| Determinism | Variance Budgeting |
| Trust | Admissible Oracles |

The harness measures whether a skill clause produces a measurable directional effect when present versus absent. Results are reported as a **vector** (Passed / Failed / Confounded / Unmeasured / Coverage / Contribution) — never as a scalar quality score.

See [`PRD.md`](PRD.md) for the full product spec and [`docs/COUNCIL_FINDINGS.md`](docs/COUNCIL_FINDINGS.md) for the architectural decisions backing v0.1.

## Status

**Pre-alpha (v0.1.0a0).** Schema is realized and trigger-enforced; CLI surface is stubbed; per-track build is in progress. See [`PLAN.md`](PLAN.md) for the locked implementation plan.

## Quick start

### Requirements

- Python ≥ 3.11
- An Anthropic API key (set as `ANTHROPIC_API_KEY` environment variable) — only required for live evaluation; tests run offline.

### Install

```bash
git clone https://github.com/MrBinnacle/skill-harness.git
cd skill-harness
python -m venv .venv
# Windows
.venv\Scripts\pip install -e ".[dev]"
# macOS / Linux
.venv/bin/pip install -e ".[dev]"
```

### Verify

```bash
pytest -q
```

You should see `8 passed`. The critical tests prove the architecture is real:

- `test_evidence_append_only_skills` — confirms SQLite triggers reject UPDATE/DELETE on evidence tables
- `test_runs_completed_at_is_set_once` — confirms the single-shot mutable-field pattern
- `test_runtime_db_is_mutable` — confirms the two-DB partition holds

### CLI (stubs until v0.1.0)

```bash
skill-harness skill init <path-to-SKILL.md>
skill-harness skill clauses <skill-id>
skill-harness run ablation <skill-id>                # defaults to --dry-run (cost projection)
skill-harness run ablation <skill-id> --execute      # real API calls
skill-harness run evaluate-skill <skill-id>
skill-harness diff skill <skill-id-a> <skill-id-b>
skill-harness freeze <verdict-id>
skill-harness calibrate <judge_id> <axis> <pair_set.jsonl>
```

## Architecture

Two SQLite databases:

- **`evidence.db`** — append-only. Every table carries `BEFORE UPDATE` + `BEFORE DELETE` triggers that `RAISE(ABORT)`. Schema migrations are tracked with SHA-256 ledgers; mutated migration files abort startup.
- **`runtime.db`** — mutable. In-flight run progress, current calibration pointers, cost ledger, skill import staging.

The partition is load-bearing: it makes "evidence is never recomputed" enforceable at the database level, not just an aspirational application-layer contract.

Five build tracks land in parallel via worktrees:

| Track | Scope |
|---|---|
| A — Storage | Repository APIs over the two-DB schema |
| B — Extractor | SKILL.md → atomic clauses + axis/comparator inference |
| C — Oracle library | Tier-1 mechanical metrics + Tier-2 pairwise judge with position-swap discipline |
| D — Ablation runner | Full/Ablated/Null orchestration + sequential stopping + prompt-cache strategy |
| E — Aggregation + CLI | Hierarchical Beta-Binomial posterior + skill-vector report + full CLI surface |

## Disciplines this enforces

Skill Harness is opinionated. It bakes in specific positions on questions the LLM-eval literature treats as open:

- **Pairwise preference, not scalar grading** — Tier-2 judges output `{A, B, tie}` for one named axis. G-Eval-style scalar templates are forbidden.
- **Position swap is mandatory** — every Tier-2 verdict invokes the judge twice with swapped orderings; disagreement = inadmissible.
- **Append-only at the database layer** — application-only contracts are insufficient. Triggers, not promises.
- **Admissibility snapshot at write time** — every verdict stores the calibration_event_id valid at write; never recomputed from current state.
- **N_min floor enforced on read** — at the default `(threshold=0.60, confidence=0.95)`, `N_min=5` is structural; below it, status is `UNMEASURED(underpowered)` regardless of win rate.
- **Multiple-comparison correction** — hierarchical Beta-Binomial pooling across clauses within a skill. The naive "Bayesian per-arm threshold + independence" produces 40%+ family-wise false-positive rates at K=10.
- **Falsifying-case requirement for PASSED** — a clause is metadata, not a contract, until ≥1 frozen falsifying case exists at the current metric_library version.

Each of these has a corresponding skill in `~/.claude/skills/` (`bayesian-eval-discipline`, `llm-judge-calibration`, `append-only-evidence-design`) that captures the discipline as reusable agent guidance.

## Repository layout

```
skill-harness/
├── PRD.md                    # product spec (v1.0; v1.1 amendments queued)
├── PLAN.md                   # locked implementation plan
├── CLAUDE.md                 # operating rules for AI assistants in this repo
├── pyproject.toml            # project metadata + tool configs
├── src/skill_harness/        # package source
│   ├── cli/                  # CLI entry point (PRD §18 surface)
│   └── storage/              # SQLite migration runner, repositories
├── tests/                    # pytest suite
├── migrations/
│   ├── evidence/             # append-only schema (triggers + indexes)
│   └── runtime/              # mutable schema
└── docs/
    ├── COUNCIL_FINDINGS.md   # architectural decisions + sources
    └── adr/                  # future ADR home
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup, test discipline, and PR conventions. The bar is high: every PR must pass `ruff check`, `mypy --strict`, and `pytest -q` before merge.

## Security

See [`SECURITY.md`](SECURITY.md) for vulnerability reporting and the supply-chain audit record. Production dependencies are pinned above their CVE-patched versions; the audit lives at `.supply-chain-risk-auditor/results.md` and is re-run quarterly.

## License

MIT. See [`LICENSE`](LICENSE).

## Acknowledgements

The architectural decisions in `docs/COUNCIL_FINDINGS.md` cite specific prior art across the LLM eval, statistics, and SQLite literatures. The discipline embedded in the harness is epistemically isomorphic to the [`ai-slop-sentinel`](https://github.com/MrBinnacle) skill — both treat "every assertion needs a citation" and "trust ages, re-validate on a schedule" as load-bearing.
