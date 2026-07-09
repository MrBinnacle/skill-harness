# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- v0.2 subject layer (`skill_harness.subject`, optional `[inspect]` extra):
  `HarnessPin.capture()` — the subject-harness configuration captured from the live
  environment as an admissibility field (refuses `version="auto"`), and
  `build_paired_tasks()` — the Full-vs-Null contrast as two Inspect tasks identical
  except for the skill under test (`inspect_swe.claude_code(skills=…)`), with
  `file_contains` / `command_succeeds` outcome oracles resolved against the agent's
  pinned cwd. Supply-chain review: `docs/supply-chain/inspect-audit-2026-07-09.md`.
- `skill-harness skill audit <SKILL.md>` — fully offline preflight (no API key, no DB,
  no cost): structural lint against Anthropic's published authoring spec plus an
  evaluability report stating which axes a paid run could mechanically measure and
  which claims would return UNMEASURED. `--strict` exits 1 on warnings for CI.

### Fixed
- **Installed copies of v0.1 were broken** (worked only from a source checkout);
  caught by a fresh-venv install test:
  - `hedge_index` loaded its wordlist from `tests/…` (not shipped in the wheel) —
    now package data at `src/skill_harness/oracles/tier1/fixtures/`.
  - SQL migrations resolved from the repo root — now package data at
    `src/skill_harness/storage/migrations_sql/`; installed copies can bootstrap DBs.
  - `tiktoken` and `statsmodels` were imported at runtime but declared only in dev
    extras — now runtime dependencies.
- `examples/README.md` still claimed the extractor had no OpenRouter fallback
  (stale since `b5b9fe6`).
- Repaired all references left dangling by the 2026-07-08 privacy scrub
  (COUNCIL_FINDINGS.md, root CLAUDE.md) across CONTRIBUTING, CODEOWNERS, PR/issue
  templates, CHANGELOG, PRD, PLAN, release notes, and the case study.

### Changed
- README rewritten for its actual audience (Claude Code users with a skills folder):
  value proposition first, two-command keyless quickstart, honest pre-alpha status,
  fact-checked comparison table (skill-eval-harness, promptfoo, Inspect).
- `PRD.md`, `PLAN.md`, `RELEASE-NOTES-v0.1.md` moved under `docs/`.
- `docs/findings/v0.2-reaim-gate.md` amended after the 2026-07-09 competitive sweep:
  adds "Harness pin" and "Differentiation vs field" pre-registration fields and a
  correction block recording that the original lock predated the sweep.

## [0.1.0] — Released 2026-06-08

v0.1 delivers a complete deterministic evaluation framework for clause-level
ablation testing of LLM skills. Five build tracks (A–E), two-database
append-only evidence model, Tier-1 mechanical oracle library, Tier-2 pairwise
judge module, full CLI surface, and JSON report wire format v1.2.0.

**v0.1 thesis-validation evidence**: live ablation re-run on ai-slop-sentinel
produced 1 FAILED clause (`f9771fd8b5a9cff80999c80ca1f31d7a56d31f1dc1647f33b39113b26931dba7`;
axis `citation_presence_per_flag`; `p_win_gt_threshold=0.005`; `n=30`;
runs `073dd0da` + `19e85593` + `c3481f27`). The harness surfaced a
well-intentioned discipline clause that empirically fails to deliver on its
claimed axis — the central claim of the evidentiary framework, demonstrated
rather than asserted. Methodology precedent: Chandra et al. arXiv:2602.19141.

### Added (Tracks A–E, doc-lock, council)
- Five build tracks completed:
  - **Track A** — Two-DB partition, append-only triggers, SHA-256 migration ledger
  - **Track B** — Clause extractor, vacuity classifier, rendering-index reorder
  - **Track C** — Tier-1 scorer registry (5 scorers) + Tier-2 pairwise judge module
  - **Track D** — Ablation runner: sequential stopping, cost caps, dry-run default, confound monitoring
  - **Track E** — EB-MoM hierarchical pooling, JSON wire format, six CLI commands
- 47 PRD v1.1 amendments from 7 council fires; full provenance in the internal council findings log (not published).
- 9-seat pre-tag launch council fire; 2 BLOCKERs (OPERATOR-DX-1 + M3 coverage_warnings)
  cleared in fix-sprint `3f6b0a9`.
- Live ablation re-run on ai-slop-sentinel: 1 FAILED clause empirically demonstrated
  (`f9771fd...`; `p_win_gt_threshold=0.005`; n=30; runs `073dd0da` + `19e85593` + `c3481f27`).
  See `docs/path-b-verified-2026-06-08.md`.
- `coverage_warnings` field on `VectorSummary` / §16 vector wire format (additive; schema
  bumped to `1.2.0` for `run evaluate-skill` report).
- `pythonhashseed` sub-key in `aggregation_provenance` for all three aggregation methods (PRD §16.1).
- `skill-harness calibrate` documented in README Quick Start and PRD §18 CLI surface.

### Fixed
- Windows cp1252 crash on UNMEASURED render: replaced non-ASCII glyphs (`⚠`, `≠`, `->`) with ASCII equivalents in `cli/main.py`.
- `skill clauses` command now emits a descriptive placeholder rather than crashing with `ClickException("not implemented")`.
- `--daily-cap` help string now documents per-runtime.db scope; parallel worktrees with separate DBs do not share the cap.

### Changed
- PRD §16.1 wire-format version documentation updated: `run evaluate-skill` ships `"1.2.0"`; `diff skill` ships `"1.0.0"` (independent schemas, documented separately).

### Known v0.1.x Carry-Forwards
- **SCHEMA-7** — `mechanical_validity_test_passed` validity-flag bypass migration deferred; council-approved local-trust scope for v0.1.
- **EVR-3/EVR-7** — Oracle surface limit (5 Tier-1 scorers); documented in RELEASE-NOTES. FAILED verdict confirms discrimination is real when scorer matches.
- `tie_count`/`win_count`/`loss_count` absent from per-clause wire format — v0.2 carry-forward.
- Coverage Law Reading B (tested/non-vacuous) deferred to v0.2 per A62.

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
- Comprehensive architectural decision record in the internal council findings log (not published) (17 adopted decisions, 16 PRD amendments queued for v1.1)
- Implementation plan at `docs/PLAN.md` (5 build tracks A–E with exit criteria)
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

[0.1.0]: https://github.com/MrBinnacle/skill-harness/compare/v0.1.0a0...v0.1.0
[0.1.0a0]: https://github.com/MrBinnacle/skill-harness/releases/tag/v0.1.0a0
