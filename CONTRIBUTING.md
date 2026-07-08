# Contributing to Skill Harness

Thanks for your interest. This project is pre-alpha and changing fast, but contributions that respect the architectural discipline are welcome.

## Before you start

Read these in order:

1. [`PRD.md`](PRD.md) — what the harness is and what it claims to measure
2. [`PRD.md`](PRD.md) §3 / §6 / §14 — the locked invariants (evaluation shape, admissibility, pass rules) that gate every design choice; the full internal ADR log is not published
3. [`PLAN.md`](PLAN.md) — the locked v0.1 implementation plan; tracks A–E
4. [`CLAUDE.md`](CLAUDE.md) — operating rules (these apply to AI assistants and human contributors alike)

If your contribution conflicts with a load-bearing invariant in `CLAUDE.md` or a decision in `COUNCIL_FINDINGS.md`, open an issue **before** writing code. Re-litigating those decisions is fine; re-litigating them in a PR is expensive.

## Development setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\pip install -e ".[dev]"
# macOS / Linux
.venv/bin/pip install -e ".[dev]"

# install pre-commit hooks
pre-commit install
```

Verify everything works:

```bash
pytest -q                              # 8 passed
mypy --strict src tests                # 0 errors
ruff check src tests                   # 0 issues
ruff format --check src tests          # 0 reformats needed
```

## The discipline

### TDD is not optional

Every feature and bugfix follows RED → GREEN → REFACTOR:

1. Write a failing test that captures the intent
2. Confirm it fails for the right reason (assertion, not import error)
3. Write the minimum code to pass
4. Refactor without changing behavior; tests still pass

PRs that add code without tests are rejected. PRs that disable tests to make code pass are rejected. PRs that add tests *after* the implementation are accepted but flagged for review.

### Append-only invariant is load-bearing

Code that writes to evidence tables MUST go through the repository APIs in `src/skill_harness/storage/`. Direct SQL against `oracle_verdicts`, `samples`, `frozen_cases`, `calibration_events`, or `confound_events` from anywhere else in the codebase is a bug.

If you find yourself reaching for a workaround to "fix" an inadmissible historical verdict, the system is working as designed — admissibility is snapshotted at write time and gated via VIEW, never recomputed (see `PRD.md` §6).

### Statistical claims need citations

Code paths that compute posteriors, apply thresholds, or claim "PASSED" are subject to higher scrutiny. New defaults need a citation to the LLM eval / statistics literature in the PR description. The `bayesian-eval-discipline` skill in `~/.claude/skills/` documents the existing positions; PRs that change them must engage with the prior art, not just propose a different number.

### Judge protocols are pairwise-only

Tier-2 judges output `{A, B, tie}` for one named axis. Scalar grading and Likert-scale templates are explicitly forbidden (`PRD.md` §3.1). Position swap is mandatory; length control is part of calibration (`PRD.md` §6).

## PR conventions

- **Title**: conventional-commit format. `feat(scope): description`, `fix(scope): description`, etc. Scopes match the build tracks: `storage`, `extractor`, `oracle`, `runner`, `aggregation`, `cli`, `docs`, `ci`.
- **Description**: state what changes and why. Link the council finding ID or PRD section if applicable.
- **Tests**: every PR runs `ruff check`, `mypy --strict`, `pytest -q` in CI. All three must pass.
- **Scope**: small PRs preferred. If you're touching more than 3 files, consider whether the change should be split.
- **Breaking changes**: tag with `BREAKING CHANGE:` in the PR body. Acceptable in pre-alpha; documented in `CHANGELOG.md`.

## Issue conventions

Use the issue templates:

- **Bug report** — for reproducible defects
- **Feature request** — for new functionality (must engage with PRD §18 scope or propose extension)

For architectural changes, open a discussion before an issue.

## Code style

`ruff` and `mypy --strict` are the source of truth. Their configs live in `pyproject.toml`. Don't introduce per-file overrides without justification in the PR.

- Line length: 100
- Target: Python 3.11
- Imports: sorted by `ruff` (`I` rules)
- Type annotations: required on every function and method body (`mypy --strict`)
- Docstrings: brief; the WHY (non-obvious invariants), not the WHAT (which the code already shows)

## What goes in `~/.claude/skills/` vs the repo

The harness ships three reusable global skills derived from its own discipline:

- `bayesian-eval-discipline`
- `llm-judge-calibration`
- `append-only-evidence-design`

These live in the user's `~/.claude/skills/` directory, not in the repo. If you want to contribute updates to them, send a PR with the skill files in a `contrib/skills/` directory and they'll be reviewed for promotion.

## Reporting security issues

See [`SECURITY.md`](SECURITY.md). Do not file public issues for vulnerabilities.

## Code of conduct

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
