# Release Notes — Skill Harness v0.1.0a0

## Headline

Skill Harness v0.1 ships a complete deterministic evaluation framework for
clause-level ablation testing of LLM skills: five build tracks, two-database
append-only evidence model, Tier-1 mechanical oracle library, Tier-2 pairwise
judge module, full CLI surface, and JSON report wire format v1.0.0.

---

## What's in v0.1

### Five build tracks completed

| Track | Scope |
|---|---|
| A — Storage | Two-DB partition, append-only triggers, SHA-256 migration ledger |
| B — Extractor | Clause extraction, vacuity classification, rendering-index reorder |
| C — Oracle library | Tier-1 scorer registry + Tier-2 pairwise judge module |
| D — Ablation runner | Sequential stopping, cost caps, dry-run default, confound monitoring |
| E — Aggregation + reporting + CLI | EB-MoM hierarchical pooling, JSON wire format, six CLI commands |

### Two-database partition (A2)

Evidence state lives in `evidence.db` (append-only, `PRAGMA synchronous = FULL`).
Mutable operational state lives in `runtime.db` (`synchronous = NORMAL`). Cross-DB
FK enforcement is at the application layer via `open_db()`. Bypassing `open_db()`
to call `sqlite3.connect()` directly is a review-block (drops FK enforcement +
degrades durability).

### Tier-1 scorer library

Five registered mechanical scorers (deterministic, offline, versioned):

1. `verbosity` — token count via tiktoken `cl100k_base` (offline; implementation hash pinned)
2. `hedge_index` — hedge-word density (frozen wordlist SHA-256 pinned)
3. `structure_score` — heading + paragraph-break density
4. `compliance_proxy` — directive-keyword density (explicit heuristic label)
5. `citation_presence_per_flag` — flag-citation ratio for sentinel-style review outputs (ai-slop-sentinel clause 0)

Note: if the Path B scorer-add agent lands before v0.1 tag, this list extends by one scorer;
release notes to be updated at tag-cut time.

### Tier-2 judge module (A5 / A6 / A7)

- Pairwise-only mode: output `{A, B, tie}` for one named axis; numeric scores forbidden.
- Mandatory position swap: `(A, B)` and `(B, A)` both required; disagreement sets
  `position_swap_agreement = 0` → `admissibility_state = 'inadmissible'`.
- Length-controlled agreement tracking per AlpacaEval-2 pattern.
- `calibrate` command shipped; minimum calibration set 50 pairs per `(judge_id, axis)`.
- Live judge wiring deferred per D22 (operator provides JSONL calibration set; v0.2 ships a starter set).

### CLI surface (PRD §18)

All six commands from PRD §18 are implemented:

```
skill init             — import a skill artifact and extract clauses
skill clauses          — inspect clause inventory
run ablation           — execute single-clause ablation (dry-run default; --execute required)
run evaluate-skill     — full suite with sequential stopping
diff skill             — compare skill revisions; --exit-on-divergence exits 2 on regression
freeze                 — promote a failure into the regression suite
```

### Statistical model

- Sequential stopping + N_min = 8 / N_inc = 4 / N_max = 40 (A8).
- Pass rule: `P(win_rate > 0.60) >= 0.95` under `Beta(1,1)` prior. Both thresholds
  are `[values decisions]`; changing either requires user approval.
- EB-MoM hierarchical Beta-Binomial multiplicity correction (A9 / A53); BH-FDR
  fallback when K < 10 or fit fails.

### Append-only invariants (A1 / A4 / A18–A23)

Eleven council-adopted invariants codified: BEFORE UPDATE/DELETE triggers on all
evidence tables, SHA-256 tamper-evidence migration ledger, per-DB synchronous
pragma split, `runs.completed_at` single-shot trigger, `schema_migrations` append-only
triggers on both DBs.

### JSON report wire format v1.0.0 (A60)

Per-clause fields: `clause_id`, `status`, `sub_reason`, `posterior_mean`,
`credible_interval_95`, `p_win_gt_threshold`, `frozen_case_count_at_current_metric_version`,
`metric_id_per_axis`, `metric_version_per_axis`, `ablation_operator_hash`,
`run_ids_aggregated`. Top-level: `report_schema_version = "1.1.0"`, `aggregation_provenance`
block (method + family size + K clauses). Output is sorted-key, compact-separator JSON
(byte-stable for identical evidence).

---

## What's NOT in v0.1 (explicit non-goals)

- **Tier 3 real-world consequence oracle** (D1) — no v0.1 path; requires external deployment.
- **Live Tier-2 judge calibration set** (D22) — `calibrate` command ships; operator provides
  JSONL. v0.2 ships a starter calibration set.
- **Random-subset / ContextCite surrogate estimator** — LOO ablation only; redundancy
  cancellation is a documented v0.1 limitation (JoPA / Chang et al. arXiv:2405.20404).
- **Multi-process sampling** (D11) — single-process only; parallel sampling deferred.
- **Operator-self-label calibration tier** (C2) — explicitly refused for v0.1.
- **Per-(extractor_id, skill_genre) calibration** (D4) — single extractor; cross-genre
  calibration deferred.
- **Coverage Law two-numerator** (D3) — v0.1 reports Reading A (tested/total clauses) per A62.
  Reading B (tested/non-vacuous) is a v0.2 carry-forward.

---

## Known limitations + workarounds

### Oracle surface limit

Only 5 hand-registered Tier-1 scorers cover specific axes (`verbosity`,
`hedge_index`, `structure_score`, `compliance_proxy`, `citation_presence_per_flag`).
Skills whose extracted axes do not match these names AND do not have a calibrated
Tier-2 judge record will return all-UNMEASURED. This is expected behavior, not a
harness error.

**Workaround**: register a custom Tier-1 scorer for your skill's axis
(`oracles/tier1/`) OR provide a calibrated Tier-2 `(judge_id, axis)` record via
the `calibrate` command. v0.2 explores per-skill scorer injection.

**Dogfooding signal (Phase 4.4)**: all three dogfooding runs (ai-slop-sentinel,
bayesian-eval-discipline, verbatim-content-subagent-dispatch) returned all-UNMEASURED
because extracted axes are custom to each skill. This validated the BLOCKER-1 gate
behavior but left zero PASSED demonstrations at v0.1 tag time. Path B (scorer-add agent,
in flight) targets at least one PASSED demonstration before final tag.

### Windows cp1252 Rich-render crash

Terminal output on Windows with non-ASCII glyphs (`->`, `warning`) crashes the
legacy Rich renderer when `PYTHIOENCODING` is not set. Confirmed in Phase 4.4
verbatim-content-subagent-dispatch dogfooding.

**Workaround**: set `PYTHONUTF8=1` (Python 3.7+ UTF-8 mode) or set
`PYTHONIOENCODING=utf-8`, or use `--format=json` to bypass Rich entirely.

### Extractor stochasticity

Clause counts drift ~15% between dry-run and `--execute` runs due to LLM sampling
variance. The `--execute` run is canonical; dry-run counts are projections only.
v0.2 explores deterministic extractor seeding.

### CI gate-scope difference

Local gate is `mypy --strict src/` (67 files, 0 issues). `tests/` mypy cleanup
(119 errors) is a documented v0.2 carry-forward. CI enforces `src/` only; this
matches local gate intent.

### `tie_count` absent from wire format (v0.2 carry-forward, Phase 4.1 finding A)

`tie_count`, `win_count`, and `loss_count` are not in the §16.1 per-clause wire
format. The §14.3 drop-ties flexibility is aspirational for v0.1 (no calibrated
Tier-2 judge configured). v0.2 adds raw observation counts.

---

## Migration / install

```
# Python 3.11+ required; 3.13 recommended (CI matrix)
pip install -e ".[dev]"

# Required for live ablation runs
export ANTHROPIC_API_KEY=<your key>

# Required on Windows for non-ASCII terminal output
set PYTHONUTF8=1

# Required for Tier-1 bit-equality test discipline
set PYTHONHASHSEED=0  # before running pytest tests/oracles/tier1/
```

Full development workflow: `CLAUDE.md` ENV RECIPE section.

---

## Citations

- 17 council-adopted decisions (A1–A23, C1–C3, D1–D11) + 47 PRD v1.1 amendments
  documented in `docs/COUNCIL_FINDINGS.md` (main table + Appendices B–G).
- 47 amendments derived from 7 council fires; full provenance preserved.
- Sclar et al. arXiv:2310.11324 (FormatSpread / component ablation),
  Longpre et al. arXiv:2301.13688 (FLAN component ablations),
  Chang et al. arXiv:2405.20404 (JoPA redundancy cancellation): referenced in PRD §1.

---

## Acknowledgments

v0.1 was developed using an orchestrator + multi-seat cross-talk council pattern
(5-seat council, 2026-06-03; 7 total council fires). Design integrity was verified
via adversarial-spec pass (Phase 4.1, 0 blockers), insecure-defaults sweep
(Phase 4.3, 0 critical/high), and three-skill dogfooding (Phase 4.4). All
architectural decisions are traceable to `docs/COUNCIL_FINDINGS.md`.
