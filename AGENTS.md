# AGENTS.md

Shared operating contract for agents working in this repository. Read this file in both
Pi and Claude Code; machine-local instructions may add workflow details, not replace the
public specification. The configuration inventory and settled baseline are in
[`docs/agents/configuration.md`](docs/agents/configuration.md).

## Purpose and authority

Skill Harness is a Python evaluation harness for reusable AI agent skills. The reader-facing
record is exact token cost, evidence grade and, when a preregistered causal test has been
completed, a verdict scoped to that test. The reader makes the deployment decision; `KEEP`
is not an instruction to deploy. See [ADR 0002](docs/adr/0002-reader-facing-record-cost-grade-scoped-verdict.md).

Before changing behavior, read `GLOSSARY.md`, `docs/PRD.md`, `docs/INVARIANTS.md`, the relevant
accepted records in `docs/adr/`, and `CONTRIBUTING.md`. The specification and accepted decisions
govern measurement semantics. Executable configuration governs tool settings and gate scope;
this file does not introduce another copy of statistical thresholds or dependency pins.
Surface a conflict rather than silently changing either side.

[ADR 0001](docs/adr/0001-architecture-admitted-on-demonstrated-decision-requirement.md)
admits architecture only when a downstream decision demonstrably requires it. Do not add
registries, state, hooks, services or agent configuration merely for completeness.

## Safety and measurement boundaries

- Preserve existing edits, local-only files and untracked artifacts. Inspect Git status before
  work. This public repository does not carry private session state, credentials or local
  agent permissions. Keep continuity in the active runtime's native session facilities;
  private workflow records stay private.
- Do not spend on model calls or run live tests without authorization. Dry-run is not a
  universal no-spend promise: `skill init` calls a model in both modes. The command-specific
  boundaries are in `docs/INVARIANTS.md` §2 and the CLI implementation.
- Write evidence through `src/skill_harness/storage/` repository APIs, never direct SQL.
  Preserve append-only records and write-time admissibility. No admissible evidence means
  `UNMEASURED`, not `PASSED`.
- Tier-2 judges are pairwise-only (`A`, `B`, `tie`) on one named axis, with position swap.
  Statistical-claim code paths need a literature citation in the PR. Do not change thresholds,
  evaluators or acceptance rules to make an implementation pass.
- Published findings, case studies and preregistrations are frozen. Correct forward with a new
  dated entry; do not rewrite them or regenerate their frozen hashes.
- Ask before schema changes unless the authorized task specifies the migration. Changes under
  `migrations_sql/` require the schema and security review assigned in `.github/CODEOWNERS`.

## Development and delivery

Use the isolated repo-local `.venv` with Python 3.12 or 3.13. Set `PYTHONHASHSEED=0` for tests
and `PYTHONUTF8=1` on Windows. Do not use `--system-site-packages`. Run commands from a clean
checkout path, not an abandoned nested factory worktree.

Code changes follow RED → GREEN → REFACTOR, including a test that fails for the intended
reason before the fix. Do not disable tests to get a pass. Prose-only changes need document,
link and configuration checks, not manufactured code tests.

The gate definitions are `.github/workflows/ci.yml`; tool settings are in `pyproject.toml`,
and CI dependency constraints are in `requirements-ci.txt`. `CONTRIBUTING.md` explains local
commands and seeded replay. Run the applicable gates with their full configured scope,
including calibration, structural bans, drift and release checks. A host run with different
pins is a smoke test, not a CI-equivalent verdict. Never rename a required job without
checking live branch protection.

Use conventional commits and small, bounded PRs as described in `CONTRIBUTING.md`. Before
merging, obtain an independent non-author verifier's `PASS` or `PASS+NOTES` naming the exact
head SHA, in addition to required checks. A local shipping skill may implement this procedure,
but its absence does not waive it. Merge only that verified head into the intended base;
confirm the merge in destination history. A commit, push or queued merge is not delivery.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`MrBinnacle/skill-harness`), operated via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles plus a disposition axis, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root, maintained by `/domain-modeling`. See `docs/agents/domain.md`.

`GLOSSARY.md` is the vocabulary of record: use its terms in prose and identifiers, respect its Avoid-notes, and when code and glossary disagree, the code is the primary source — fix the glossary, then decide whether the code's term deserves a rename of its own.

## Interface and experience

Remove redundant UI copy. Use clear hierarchy, intuitive controls, and contextual cues to make interfaces self-explanatory. If users need extra text, redesign the interaction.

Optimize UX, DX, and AX as one system. Maximize usability, clarity, and reliability without compromising security, accessibility, or existing functionality.

## Prose voice — literal-humanist register

Instance of the **Register** row of the taste doctrine, class 2 (public prose in `skill-harness`). Its private source is `TASTE.md`. The complete working rules for this repository are below;
access to the private source is not required.

Default register for every substantive prose artifact in this repo: README, docs, ADRs,
issues, pull requests, release notes, review comments, commit bodies, diagnostics. It does
not restyle source code.

For substantive prose:

1. State what happened — dates, amounts, versions, quoted terms.
2. Name the mechanism — translate each label into the action it performs.
3. State the consequence and its allocation — who gained, who paid.
4. State the finding. Never leave the operative conclusion for the reader to infer.
5. Attach uncertainty only to the proposition that is actually uncertain.
6. End with the next action, test, or decision.

Syntax: short sentences, concrete nouns, direct verbs, active voice, one step per
sentence. Never: euphemism after the underlying action is known; speculative qualifiers
as cushioning for a supported claim; leaving a finding for the reader to infer;
sarcasm or victory laps; passive voice that hides the responsible
component; abstractions that erase the person affected.
