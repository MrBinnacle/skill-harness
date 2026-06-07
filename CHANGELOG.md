# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `coverage_warnings` field on `VectorSummary` / §16 vector wire format (additive; schema bumped to `1.2.0` for `run evaluate-skill` report).
- `pythonhashseed` sub-key in `aggregation_provenance` for all three aggregation methods (PRD §16.1).
- `skill-harness calibrate` documented in README Quick Start and PRD §18 CLI surface.

### Fixed
- Windows cp1252 crash on UNMEASURED render: replaced non-ASCII glyphs (`⚠`, `≠`, `->`) with ASCII equivalents in `cli/main.py`.
- `skill clauses` command now emits a descriptive placeholder rather than crashing with `ClickException("not implemented")`.
- `--daily-cap` help string now documents per-runtime.db scope; parallel worktrees with separate DBs do not share the cap.

### Changed
- PRD §16.1 wire-format version documentation updated: `run evaluate-skill` ships `"1.2.0"`; `diff skill` ships `"1.0.0"` (independent schemas, documented separately).

## [0.1.0a0] — 2026-06-03

Initial scaffold. Pre-alpha — schema realized and trigger-enforced, CLI surface stubbed, per-track build pending.

### Added
- Project structure: `src/skill_harness/` Python package, `tests/`, `migrations/`
- Two-database SQLite architecture:
  - `evidence.db` — append-only via `BEFORE UPDATE`/`BEFORE DELETE` triggers on 9 evidence tables
  - `runtime.db` — mutable state (run progress, calibration pointers, cost ledger)
- SHA-256 migration ledger with tamper-evidence (`MigrationTamperedError` on mutated migration files)
- CLI entry point with 6 PRD §18 commands stubbed
- 8 smoke tests including append-only trigger verification + `runs.completed_at` single-shot mutation
- Comprehensive architectural decision record at `docs/COUNCIL_FINDINGS.md` (17 adopted decisions, 16 PRD amendments queued for v1.1)
- Implementation plan at `PLAN.md` (5 build tracks A–E with exit criteria)
- Supply-chain audit at `.supply-chain-risk-auditor/results.md` — PROCEED-WITH-MITIGATIONS
- Standard repo docs: `README.md`, `LICENSE` (MIT), `CONTRIBUTING.md`, `SECURITY.md`
- CI workflow: ruff + mypy --strict + pytest matrix on Ubuntu + Windows x Python 3.11/3.12/3.13
- CodeQL security scanning (push, PR, weekly)
- Dependabot config (pip + github-actions, grouped updates)
- Pre-commit hooks (ruff, mypy, gitleaks, standard hygiene)
- CODE_OF_CONDUCT.md (Contributor Covenant 2.1)
- `.github/` infrastructure: CODEOWNERS, PR template, issue templates (bug + feature + config)
- `.editorconfig` for cross-editor consistency

### Security
- `anthropic` pin tightened from `>=0.39` to `>=0.87` to enforce post-patch for GHSA-q5f5-3gjm-7mfm and GHSA-w828-4qhx-vxx3 (Memory Tool CVEs, 2026-03-31)

[Unreleased]: https://github.com/MrBinnacle/skill-harness/compare/v0.1.0a0...HEAD
[0.1.0a0]: https://github.com/MrBinnacle/skill-harness/releases/tag/v0.1.0a0
