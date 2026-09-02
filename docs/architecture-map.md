# Architecture map

A one-page orientation for working on this codebase: what the modules are, how
the measurement pipeline flows through them, and which seams are load-bearing.
Structural statistics come from a GitNexus call-graph index measured on
2026-08-31 (9,409 symbols, 16,148 edges, 348 clusters, 238 execution flows at
that day's HEAD); everything else is verifiable by reading the named files.
This page orients; it does not govern. Where it disagrees with the tree, the
tree is right and this page needs the edit.

## The pipeline in one picture

```
Inspect .eval logs (Full arm / Null arm)
        |
        v
subject/ingest.py        parse -> validate pair -> refuse or write
        |                (arm/epoch/scorer checks, exposure/contamination
        |                 gates, pi_c + exposure stratifier record)
        v
evidence store (SQLite)  storage/: migrations, repositories, append-only
        |                oracle_verdicts + samples + frozen_cases
        v
aggregation/             fit.py (EB-MoM -> BH-FDR fallback -> unpooled)
        |                status.py (locked PASS/FAIL thresholds, currency gate)
        |                engine.py (aggregate_skill: reads views, derives status)
        v
verdict / report         paired_verdict, CLI report surfaces, SERS receipts
        |
        v
docs/sers/receipts/      minted receipts -> sitegen -> published pages
```

Two lanes feed the same evidence store:

- **Paired ingest lane** (`subject/`): external Inspect eval logs, Full vs
  Null, joined by epoch. The refusal surface in `_validate_pair` (unexposed
  Full; Null contamination on exposure or invocation) is the boundary; what
  it cannot see is recorded in
  `docs/findings/paired-ingest-boundary-undetectables.md`. pi_c is a recorded
  stratifier, not a write gate (#384/#387).
- **Ablation runner lane** (`ablation/`): the harness's own sampling loop
  (runner.py) with the A42 budget gate, A25 evidence-first writes, and the
  A41 cost ledger. Budget correctness rests on single-threaded serialisation
  (REL-7), pinned by `tests/test_budget_ledger_reconciliation.py`.

Beside them, the **OC lane** (`oc/`, `task_frontier/`, `calibration/`)
computes operating characteristics: exact Beta/Beta-binomial primitives
(`oc/exact.py`, cross-checked against SciPy by
`tests/test_oc_exact_scipy_grid.py`), Gate-1/Gate-2 decisions over the
discordant table, and frontier assembly. The longest measured execution flows
in the index are exactly these joins: receipt writing and frontier assembly
reaching down into `Beta_cdf` / `Beta_binomial_pmf` (8-10 call steps,
cross-community).

## Modules, as measured

Cluster inventory from the index (symbol counts and cohesion as measured on
2026-08-31; directory names are the ground truth):

| Module | Symbols | Cohesion | What it is |
| --- | --- | --- | --- |
| Tests | 1207 | 88% | The detector corpus; includes the ten falsification-plan detectors |
| Ablation | 283 | 78% | Sampling runner, stopping rule, budget gate, subject client |
| Extractor | 253 | 84% | Skill-card clause extraction |
| Calibration | 114 | 97% | Anytime-valid confidence sequences and coverage checks |
| Storage | 79 | 92% | Migrations, repositories, dual-write, transaction discipline |
| Sitegen | 76 | 77% | SERS receipt pages |
| Tier2 | 60 | 94% | Judge oracle with position-swap calibration |
| Cli | 49 | 73% | Command surfaces |
| Subject | 45 | 91% | Paired eval-log ingest and its refusal surface |
| Aggregation | 40 | 84% | EB-MoM fit, status machine, engine |
| Oc | 39 | 88% | Exact operating-characteristic primitives, Gate-1/2 |
| Task_frontier | 37 | 77% | Frontier assembly and feasibility |
| Evidence | 29 | 79% | Evidence-layer helpers |
| Tier1 | 21 | 100% | Mechanical metric oracles |

(Smaller clusters omitted; `gitnexus://repo/skill-harness/clusters` lists all
348 when the local index is present.)

## Load-bearing seams

The falsification plan (`docs/assurance/falsification-plan.md`) registered ten
ways this instrument could be wrong while green; as of 2026-08-31 every row
has a detector and the ratchet baseline
(`docs/assurance/falsification-detector-baseline.json`) is empty. The seams
those detectors pin are the ones to treat carefully when editing:

1. **The p-value transform** in `fit.py`'s BH-FDR fallback
   (`test_aggregation_fit_fdr_calibration.py`: null-world FDR within the
   registered bound).
2. **The moment inversion** in `_ebmom` — currently biased (no
   sampling-variance peel); repair is #360, finding
   `docs/findings/ebmom-missing-sampling-variance-peel.md`.
3. **The epoch join and arm labels** in `subject/ingest.py`
   (`test_paired_arm_epoch_adversarial.py`: swap surface closed, within-set
   epoch permutation documented as structurally invisible).
4. **The tie encoding** feeding stopping and fit — dilution measured, estimand
   ruled discordant-table on #368
   (`test_halfupdate_tie_sensitivity.py`, strict xfails until migration).
5. **The budget/ledger identity** in `ablation/runner.py`
   (`test_budget_ledger_reconciliation.py`).
6. **The confound status path** — CONFOUNDED currently unreachable; repair is
   #366, finding `docs/findings/confound-status-silent-understatement.md`.
7. **The frozen-case currency gate** (`frozen_cases_with_currency` view +
   `derive_clause_status`) and the mint-path allowlist
   (`test_mint_path_allowlist.py`, pre-commit mirror
   `ban-unpinned-verdict-insert`).
8. **The oracle identity hash** (`_oracle_implementation_hash`): a SHA-256
   over `subject/ingest.py`'s raw bytes. Byte-exact means line-ending-exact;
   see the build-context warning in `Dockerfile.assurance`.

## Working on it

- Environment: `PYTHONHASHSEED=0` always; the Linux assurance container
  (`Dockerfile.assurance`) is the reproducible baseline and the only home of
  mutmut/atheris.
- Registered documents: adding a file under a receipt directory requires an
  entry in `docs/receipts-index.md` in the same change;
  `tests/test_receipts_index.py` gates it.
- Structural bans and their pre-commit mirrors: `tests/test_structural_bans.py`
  and `tests/test_mint_path_allowlist.py` cross-check their own allowlists
  against `.pre-commit-config.yaml`, so an allowlist edit is always a
  two-place edit.
- An interactive version of everything in this page: index the repo with
  GitNexus (`npx gitnexus analyze`) and use `query`/`impact`/`context`; this
  page is the curated, committed distillation and does not require that
  tooling.

*Revisit if:* a module is added or a lane re-routed (update the picture), the
ratchet baseline stops being empty (a new registered detector is owed), or the
measured cluster inventory drifts far enough from this table that the
orientation misleads (re-measure and re-date).
