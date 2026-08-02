# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`skill_harness.oc` — Gate-2 four-outcome lattice machinery** (#55, PR-2
  continuation; rule forms ratified on #37, dual MME on #40, architecture on
  #42). Three-sided paired decision rule {BENEFIT/HARM/EQUIVALENT}+UNRESOLVED
  in the Goeman-partition form: the reference-prior Dirichlet over the four
  paired cells (tie cells pooled) partitions the net lift δ = p_f − p_n at
  the registered margin δ_min into three disjoint regions whose posterior
  masses sum to 1 — γ stays the only confidence knob, and the zero-discordant
  case is the #37-defined UNRESOLVED branch. New exact primitive
  `dirichlet_delta_tail` (rational polygon integration of the integer-
  parameter Dirichlet density — stdlib-exact, no quadrature, no simulation).
  Dual-MME registration `MMESpec` (δ_min AND q_min) with the conforming-
  region predicate H1 = {(d,q): δ ≥ δ_min ∧ q ≥ q_min} for #56's frontier
  power target. Exact OC at any true (d, q) in two deliberately different
  walks — trinomial convolution vs per-pair (x_f, x_n) lattice-DP curtailment
  (#37 item 6, default-on; the scalar half-update state is ratified-
  insufficient per #42) — pinned decision-identical differentially.
  `gate2_worst_false_direction` reports the null false-direction rate as a
  d-grid maximum PLUS the certified Bernstein-coefficient upper bound rather
  than conflating a grid max with a supremum. Frequentist cross-checks per
  #37 item 4: mid-p McNemar (exact conditional banned by name, FLL 2013),
  Newcombe 1998 paired interval (method 10, anchored to the published Altman
  2000 worked example), Tango 1998 score interval by deterministic bisection
  inversion (anchored to a published clinical literal). Gate-2 floor items
  from the banked prototype suite (trinomial sum-to-one, harm/benefit
  symmetry, v3 curtailment identity) land as tests with independent
  exact-fraction reference literals (order-swapped integration route);
  boundary rows n=6 and n=40 covered. Drift-check row **DC-11** activated
  live in this PR per the #43 same-PR extension rule (banned-methods tokens
  scoped to oc/, with the printed E1b definition-site exemption for
  `crosschecks.py`) — 9 live contracts, 4 PLANNED; `TokenBan` rows gain
  per-row scoping (`roots` + `scan_repo_level`) and `LiveRow` carries a
  tuple of token bans. Frontier assembly + live cost projection stays #56
  (ZERO cost constants in this change, #42 convention 3).
- **`skill_harness.oc` — pure-math OC engine, Gate-1 machinery** (#54, PR-2
  opener of the instrument upgrade; architecture ratified on #42, rule forms
  on #37, grid on #40). New top-level package importing NOTHING from the
  ablation or subject layers (the legacy `sizing.py`/`stopping.py` stay
  untouched as characterized legacy artifacts — parallel machinery, not a
  refactor). Gate-1 two-point indifference-zone rule (QUALIFIES tests
  p0 ≤ θ_lo, REJECTED tests p0 ≥ θ_hi, declared don't-care zone between; the
  one-point rule is refused at construction), Lee-Liu-style predictive-
  probability extension governor (one-step beta-binomial PP against a
  registered floor, bounded by an outer batch cap, fully inside the exact OC
  characterization), exact binomial OC enumeration reporting ATTAINED (never
  nominal) zone-edge errors, and deterministic curtailment default-on —
  determination against the full design tree so the decision-identity holds
  under extension, pinned differentially by test (per-trial DP vs batch
  convolution). Grid constants `GRID_N_MIN=6`/`GRID_N_MAX=40` are `oc`'s own
  registered conventions with the #40-provenance comment, deliberately not
  imported from legacy stopping constants; new locked INVARIANTS §4 entry.
  The banked prototype suite (#42 convention 4) lands as the Gate-1 test
  floor with independent exact-fraction reference literals; boundary rows
  n=6 and n=40 covered. Drift-check rows **DC-7** (grid constants + doc
  quotes + provenance comment) and **DC-8** (import-direction ban, new
  `ImportScanBan` check kind) activated live in this PR per the #43 same-PR
  extension rule — 8 live contracts, 5 PLANNED. Gate-2 four-outcome lattice
  DP is #55; frontier assembly + live cost projection is #56 (costs never
  enter below the frontier-assembly layer, #42 convention 3).
- **Drift-check CI — declarative contract table** (#53, PR-1 of the instrument
  upgrade; contract list ratified on #43). New `scripts/drift_check.py` in the
  release-gate pattern: contract rows are DATA, so adding a locked contract is
  a table row, not new code. Six live rows — DC-1 pass-rule thresholds
  0.60/0.95/0.05 (cross-site equality across `aggregation/fit.py`,
  `ablation/stopping.py`, `aggregation/status.py` + `INVARIANTS.md` quotes,
  previously assumed, never enforced) · DC-2 sampling schedule N_MIN=8 /
  N_INC=4 / N_MAX=40 · DC-3 the banned decision term, repo-wide with an EMPTY
  allowlist (the CI enforcement of record the registry module pre-announced) ·
  DC-4 estimand vocabulary (registry enum == the registered pair; no other
  token in docs) · DC-5 the README launch-trigger sentence, both sites,
  registered verbatim · DC-6 the spend-gating sentence + enforcement-pointer
  liveness. Seven registered PLANNED rows (DC-7..DC-13) print as PLANNED until
  the PR landing each surface activates them; DC-13's line records that its
  surface (docs/observations/, PR #60) landed before this script existed and
  activation is owed. Green output prints every covered contract, the coverage
  boundary line, the PLANNED rows, and the allowlist even when empty; failures
  are all listed, never first-fail. New `drift-check` job wired into the CI
  all-green set.
- **π_c invocation detection + zero-invocation refusal at subject ingest**
  (#52, PR-1 of the instrument upgrade; feasibility record #46). Every parsed
  sample now carries `invoked_skill` — the v1 detector
  (`detect_skill_invocation`, `v1-skill-tool-call`) fires iff the parsed
  message stream contains a Skill tool-call naming the skill under test; the
  SKILL.md-read branch is dead code under the `inspect_swe.claude_code` solver
  and stays excluded. Every paired write reports π̂_c over the Full arm with a
  mandatory exact Clopper-Pearson interval (`IngestResult.pi_c`, mirrored into
  the run's `config_json`), so a "skill had no effect" result can never hide
  "skill was never invoked". A treated arm with ZERO detected invocations
  refuses the write (`ZeroInvocationError`) and surfaces as an INSTRUMENTATION
  FINDING, never a null effect; a detected invocation in the Null arm refuses
  as control-arm contamination (structurally impossible per #46 — 0/22 Null
  epochs fired, now a regression fixture). Ingestion stays exclusively on the
  `read_eval_log` reader API (eval logs are zstd-compressed zip entries — raw
  archive handling stays banned). `ORACLE_METRIC_VERSION` bumped to `0.3.0`
  (pairing semantics gained the refusal rules).
- **Estimand registry + decision-semantics vocabulary** (#51, PR-1 of the
  instrument upgrade; resolution record #36). New `skill_harness.semantics`
  module: the two named estimands (`treatment-policy` = agentic paired subject
  layer, production default; `hypothetical` = ablation forced-injection,
  diagnostic — ICH E9(R1) vocabulary), the 4-class delivery-mechanism taxonomy
  (`model-pull` / `hand-invoked` / `hook-nudged` / `hook-blocked`) registered as
  part of the treatment, per-mechanism π_c handling (detector lanes vs
  structural π_c ≡ 1), and `RegisteredScope` — the
  (skill × task family × estimand × delivery mechanism) claim boundary every
  verdict now carries (`VerdictResult.scope`). Hand-invoked treatment-policy
  registrations are the frozen-task design and refuse to register without a
  declared Null-arm semantic. Verdict render surfaces (`screen verdict`,
  `screen profile`) gained an enum-backed estimand column; verdicts without a
  registered scope render `n/a (pre-registry observation)` — historical records
  are never retrofitted. The E9(R1)-superseded analysis-population term
  (`skill_harness.semantics.BANNED_DECISION_TERMS`) is banned repo-wide with an
  EMPTY allowlist (pytest scan now; drift-check CI row DC-3 to follow).
- **Paired-path (`full_vs_null`) freeze branch — A′** (S86 frozen-case design
  council, operator-ratified). `freeze` now accepts a WINNING paired verdict
  (`observation = 1.0`) under a metric registered as binary
  (`PAIRED_FREEZE_BINARY_METRIC_IDS`: `subject:file_contains`,
  `subject:command_succeeds`) and stores the Null-arm sample as the falsifying
  case — closing the structural gap where a clean paired winner produced
  nothing freezable and A57 Rule 6 made KEEP unreachable (live-confirmed by
  the r3 positive control: 8/8 vs 0/8, p_win 0.9899 → CANT_TELL_YET).
  The ablation path (`full_vs_ablated`) eligibility is byte-unchanged. No
  schema change. Normative caveat added to the PRD `freeze` section: a paired
  frozen case is the Null half of the winning evidence re-encoded, not
  independent falsification.

### Fixed
- **Paired both-PASS-tie freeze hazard.** Previously a paired verdict with
  `observation = 0.5` was freezable via the FAILING-side rule, but on the
  paired path `0.5` also covers both-PASS ties — freezing one stored a
  PASSING Null sample as a falsifying case. Paired ties and losses
  (`0.5`/`0.0`) now refuse explicitly; graded (non-binary-registered) metrics
  refuse rather than minting a possibly-passing artifact.

## [0.2.2] — 2026-07-26

Surface-consistency fix release, cut same-day as 0.2.1. The 0.2.1 wheel and
its frozen PyPI description shipped with internally inconsistent surfaces
(details under Fixed); the PyPI description cannot be corrected without a new
upload, so this release exists to make every public surface tell one current
story — and to install the release gate that blocks this class of drift from
recurring. No functional changes to measurement, storage, or verdicts, and no
change to the measured record: still zero measured KEEPs, paired path still
unfired.

### Added
- **Release gate (`scripts/release_gate.py`)** — enforced surface-lockstep
  check run on every CI push/PR AND as the first job of `publish.yml` (the
  build and PyPI-upload jobs depend on it, so a stale tag is blocked before
  an artifact exists — blocked by default, not impossible). Checks: pyproject
  version == `__version__` (G1), CHANGELOG rolled for the current version
  (G2), README status banner current (G3), README PyPI-render-safe — no
  relative link/image targets (G4), every workflow action SHA-pinned (G5),
  tag name matches the version (G6). v0.2.1 was tagged with G1–G4 all stale;
  the gate is the process fix, this release's other entries are the instance
  fixes. The v0.2.2 cut itself is the gate's first live exercise.

### Fixed
- **Shipped `__version__` drift (G1's motivating instance).** The 0.2.1 wheel
  carried `skill_harness.__version__ == "0.2.0"` while
  `skill-harness --version` (importlib.metadata) correctly said 0.2.1 — the
  installed library disagreed with its own CLI. `__init__.py` also still
  carried the retired v0.1 "clause-ablation differential testing" one-liner;
  docstring now matches the shipped keep/cut positioning.
- **README stale on PyPI's frozen description and GitHub.** Status banner
  said v0.2.0; the 60-second start led with pip-from-git although
  `pip install skill-harness` now exists; the banner image and every
  docs/examples/LICENSE/CONTRIBUTING link were relative paths, which 404 or
  vanish when PyPI renders the README as the project description. Install
  path now leads with PyPI, all link/image targets are absolute, and the
  comparison table's maturity cell no longer hardcodes a version.
- **SECURITY.md pinned itself to `0.2.0`.** The supported-versions statement
  now says pre-1.0 / `main`-only without naming a literal version — removing
  a drift surface instead of gating it.
- **`publish.yml` actions were tag-pinned against repo convention.** Every
  other workflow SHA-pins actions; the publish pipeline — the one with PyPI
  OIDC credentials — rode mutable refs (`@v4`, `@release/v1`) and carried a
  stale comment claiming a SHA pin was intended. All five actions now pinned
  to full commit SHAs (gate G5 blocks regressions repo-wide), workflow-level
  `permissions: contents: read` added, and the gate job fronts the pipeline.

## [0.2.1] — 2026-07-26

First release distributed on PyPI (`pip install skill-harness`, trusted
publishing via OIDC). No change to the measured record: still zero measured
KEEPs; the paired Full-vs-Null path remains coded but unfired.

### Added
- **PyPI trusted publishing** — OIDC release workflow (`publish.yml`);
  installs no longer require pip-from-GitHub.
- **Per-sample `setup` hook on `build_paired_tasks`** (`skill_harness.subject.inspect_adapter`):
  an optional `setup: str | None` carrying bash-script *contents* run in the sandbox before the
  agent starts (Inspect `Sample.setup`) — the delivery mechanism for anything the bytes-only
  `files` path cannot express (e.g. the +x bit on a planted stub CLI). The SAME script goes to
  both arms, so cross-arm environment equality is preserved by construction, and it is serialized
  into the `.eval` log so ingest provenance (`source_eval_sha256`) covers it. Guarded like the
  existing `files_as_data_uris` footgun: NUL bytes rejected, and a path-shaped value (naming an
  existing file) is refused outright — contents only, never a path.

### Fixed
- **`skill audit` now works fully offline on a cold cache.** The Tier-1 verbosity
  module loaded tiktoken's `cl100k_base` encoding at import time, and `skill audit`
  imports that module just to enumerate axis names — so the "fully offline, no cost"
  command crashed on air-gapped machines with a network fetch to
  `openaipublic.blob.core.windows.net`. The encoding now loads lazily on first
  tokenization; audit never touches the network, and only paid measurement paths
  fetch (pre-seed `TIKTOKEN_CACHE_DIR` for air-gapped measurement runs).
- **Launch-surface fact corrections from a pre-launch readiness review.** README/
  CHANGELOG/docstring claims brought back in line with the repo's own registered
  record: the paired Full-vs-Null path is described as shaken down via the
  pre-registered k=8 NO-GO apparatus run (≈$6.17), not "never fired /
  cost-free-validated"; "~26 screen verdicts" corrected to the registered
  denominator (26/26 Null epochs across 6 screened tasks) in README, CHANGELOG
  0.2.0 entry, and `screen_backfill.py`; the audit sample's summary line corrected
  from "3 pass" to the tool's real "2 pass" output; pyproject's description now
  names the shipped verdict trio (KEEP / CUT / CAN'T-TELL-YET); the stale
  "extractor has no OpenRouter fallback" claim in the ai-slop-sentinel case study
  updated to record the 2026-06-09 fix; the FAQ's "one screen" 14/14 phrasing
  corrected to "two screens and a paired run" with the data-skepticism aside marked
  as an unpublished observation; four scorers → five in `why-unmeasured.md`;
  `docs/INVARIANTS.md` replaces dead `CLAUDE.md` references in the PR template and
  issue chooser; unpublished internal paths in case studies and concepts docs
  marked as private provenance markers per `docs/PLAN.md`'s convention; SECURITY.md
  Dependabot/pre-commit claim and dead profile-email fallback channel corrected;
  `inspect-swe` maintainer-org provenance corrected in the supply-chain audit;
  CONTRIBUTING's Python target (3.11 → 3.12), stale "8 passed" count, and verify
  commands (now `PYTHONHASHSEED=0 pytest -q -m "not live"`, mirroring CI) fixed;
  `live` marker text no longer claims deselect-by-default.
- **Non-deterministic ordering in `calibration_events` audit queries.**
  `list_calibration_events_for_judge_axis` (and its sibling
  `select_calibration_events_by_state`) ordered by `validated_at DESC` with no
  secondary key. On an append-only audit table, same-`validated_at` events then
  tie-break on SQLite's hidden rowid (physical insertion order) — not stable
  across a DB restore/repack, so the "newest calibration" could silently flip
  between runs, breaking audit reproducibility. Both queries now carry a
  deterministic `, calibration_event_id DESC` tie-break. NOTE: the tie-break is
  deterministic but not chronological — production ids are random UUIDv4 — and
  the repository docstrings now say so.
- **Placebo regression test on the by-state tie-break query.** The originally
  shipped RED test for `select_calibration_events_by_state` passed even
  WITHOUT the fix: that query is unindexed (full scan + temp-B-tree sort, tied
  rows emitted in insertion order), so the descending-id insert that makes the
  indexed judge/axis test a genuine RED made the by-state test collude with
  the pre-fix order. The test now inserts in ascending-id order (per query
  plan), and the RED-TEST DESIGN NOTE's inverted rowid explanation — which
  caused the placebo — is corrected. Verified empirically: both tests now fail
  without the tie-break and pass with it.
- **Same rowid-tie-break defect fixed across every timestamp-ordered query.**
  The `calibration_events` fix covered 2 of ~27 structurally identical
  timestamp-only `ORDER BY`s on append-only/audit tables (`oracle_verdicts`
  in `audit/`, `runs`, `samples`, `frozen_cases`, `confound_events`,
  `metric_versions`, `judges`, `skills`, plus runtime `cost_ledger`,
  `run_budget`, `skill_imports_staging`). All now carry a deterministic
  unique-key tie-break matching the timestamp's sort direction, and a new
  structural ban (E3: pytest mirror + `ban-timestamp-final-order-by`
  pre-commit hook, wired into the F-8 drift cross-check and the CI
  structural-bans job) blocks reintroducing a timestamp-final `ORDER BY`
  in `src/`.

### Changed
- **Local pre-commit hooks now mirror CI verdicts.** `mirrors-mypy` bumped
  v1.10.0 → v2.3.0 (the requirements-ci.txt pin), its default
  `--ignore-missing-imports` overridden (it flipped CI-required `type: ignore`
  comments to "unused"), and hook deps extended with the runtime stack
  (openai/scipy/statsmodels/tiktoken/pytest-socket); ruff hook bumped to the CI
  pin v0.15.22. `pre-commit run mypy --all-files` previously failed with 10
  errors on a fresh clone; now green.
- Packaging metadata: `pre-commit` added to the `dev` extras (CONTRIBUTING's
  setup uses it), and `Changelog`/`Documentation` project URLs added for PyPI.

## [0.2.0] — 2026-07-21

### Added
- **Operator-facing keep/cut verdict layer** (`skill_harness.aggregation.verdict`):
  maps a measured outcome to the decision an operator actually has — KEEP / CUT /
  CAN'T-TELL-YET — under the pre-registration's locked transformative bar
  (Null ≤ ~0.3 & Full ≥ ~0.8). `screen_verdict(p0)` (Stage-0 screen path, the
  dominant path) and `paired_verdict(ClauseStatus)` (paired path, prospective);
  `CUT(harmful)` defined but deferred (needs a signed-delta CI).
- **Stage-0 Null-only screen store** (migration `0501`, `screen_runs` /
  `screen_trials`): an additive, append-only store firewalled from the paired
  evidence model (pre-reg: "screen data never enters verdicts"), keyed by skill
  name. `p0` (the bare-arm pass rate) is DERIVED from admissible trials, never
  stored. Voided screens are ingested but marked inadmissible (with a cited
  reason) and excluded from `p0`. `skill_harness.subject.screen_ingest` writes it;
  `skill-harness screen verdict` / `screen backfill` surface it.
- **Batch-1 screen backfill** (`skill_harness.subject.screen_backfill`): a curated,
  cited manifest that makes the batch-1 Stage-0 screens store-auditable — deriving
  each keep/cut verdict from append-only evidence instead of prose. All backfilled
  screens ceiling (p0=1) → CUT(subsumed); `llm-judge-calibration` is deferred
  (its canonical 3/3 needs per-trial cross-log assembly over a credit-exhaustion
  incident).

### Changed
- **README moved onto the keep/cut vocabulary.** The status/maturity block now leads
  with the three operator verdicts (KEEP / CUT · subsumed | no-lift / CAN'T-TELL-YET),
  shows the two live end-to-end receipts (`append-only-evidence-design` and a hardened
  `git-pull-rebase-trap`, both **CUT (subsumed)** at a bare-arm pass rate of 1.00), and
  states the honest maturity plainly: **zero measured KEEPs in the program to date**, and
  store-backed coverage is partial (a handful of the program's screen verdicts — a record
  resting on 26/26 Null epochs across 6 screened tasks — the rest prose-backed pending
  backfill). Replaces the earlier "v0.1 measures style-level effects" framing.
- **Paired KEEP path annotated as coded-but-never-fired, with a named firing trigger.**
  `aggregation.verdict` (Path B docstring) now records that the paired Full-vs-Null mapping
  launches only on the first task whose Null screen returns a pass rate below 1, and that
  no such task has appeared yet (every screened skill ceilings at 1). The mapping is coded
  and $0-validated (7/7 oracle-discrimination cases) but unexercised on live paired data.

## [0.2.0a0] — 2026-07-20

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
- **Hostile-review hardening pass** on the unreleased v0.2 subject, aggregation,
  and Tier-1 oracle layers: 39 confirmed findings fixed across the
  ablation / aggregation / calibration / extractor / CLI / storage paths —
  direction-aware ablation wins, BH-FDR gate consumption, scorer-crash
  inadmissibility, resume cost attribution, sentinel-verdict exclusion from
  statistics, and single-source pricing/tokenizer. The four remaining
  test-quality findings are tracked, not silently dropped.
- Citation oracle no longer arm-differentially deflates hyperlink references:
  lowercase prose is no longer miscounted as a flag emission (flag matching is
  now case-sensitive), and an external `http(s)` markdown-link target is
  preserved as a citation rather than stripped away with its link text.

### Changed
- README rewritten for its actual audience (Claude Code users with a skills folder):
  value proposition first, two-command keyless quickstart, honest pre-alpha status,
  fact-checked comparison table (skill-eval-harness, promptfoo, Inspect).
- `PRD.md`, `PLAN.md`, `RELEASE-NOTES-v0.1.md` moved under `docs/`.
- `docs/findings/v0.2-reaim-gate.md` amended after the 2026-07-09 competitive sweep:
  adds "Harness pin" and "Differentiation vs field" pre-registration fields and a
  correction block recording that the original lock predated the sweep.

### Security
- Untrusted skill names and model output are escaped with `rich.markup.escape`
  and asserted NUL/control-free before terminal rendering, so bracketed text
  cannot inject Rich markup into CLI output.
- CI workflow actions are pinned by commit SHA, and structural enforcement bans
  (e.g. raw `sqlite3.connect`) are wired as tests rather than left as convention.

## [0.1.0] — Released 2026-06-08

> **Release-hygiene note (added 2026-07-19):** the `v0.1.0` tag ships `pyproject.toml`
> version string `0.1.0a0` (pre-alpha) rather than `0.1.0` — the version bump was
> missed at tag time. Acknowledged gap; a corrected version string ships with the
> next actual release rather than being rewritten retroactively into this historical tag.

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
- Supply-chain audit run via `supply-chain-risk-auditor` — PROCEED-WITH-MITIGATIONS (output directory `.supply-chain-risk-auditor/` is local-only and gitignored, not a tracked artifact)
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

[Unreleased]: https://github.com/MrBinnacle/skill-harness/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/MrBinnacle/skill-harness/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/MrBinnacle/skill-harness/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/MrBinnacle/skill-harness/compare/v0.2.0a0...v0.2.0
[0.2.0a0]: https://github.com/MrBinnacle/skill-harness/releases/tag/v0.2.0a0
[0.1.0]: https://github.com/MrBinnacle/skill-harness/releases/tag/v0.1.0

Note: `[0.1.0a0]` above intentionally has no link — no `v0.1.0a0` tag exists on the
remote (`git ls-remote --tags origin`, checked 2026-07-19; only `v0.1.0` is a real
ref). The pre-alpha scaffold predates this project's tagging discipline.
