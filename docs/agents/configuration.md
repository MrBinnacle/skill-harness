# Agent and configuration baseline

The shared agent contract is [`../../AGENTS.md`](../../AGENTS.md). This page identifies the
configuration surfaces and their owners so a session does not invent a second contract.
It records the baseline inspected on 2026-11-07 from `92cc08d`; Git records the changes that
establish it. It does not freeze product development or claim that configuration cannot improve.

## Authority and loading

Measurement semantics belong to [`../PRD.md`](../PRD.md),
[`../INVARIANTS.md`](../INVARIANTS.md) and accepted [`../adr/`](../adr/) records.
In particular, ADR 0002 reconciles the earlier cost-only framing with scoped causal verdicts.
Do not revive the earlier framing as a ban on verdicts.

`AGENTS.md` is the public, self-contained operating contract. A local `CLAUDE.md` imports it
with `@AGENTS.md` and retains private workflow references. Shared rules must not live only
in that ignored file. Pi selects `AGENTS.md` ahead of `CLAUDE.md` in the same directory;
it does not combine them. This was checked against the installed Pi 1.5.0
`docs/configuration.md` and `dist/core/resource-loader.js` on 2026-11-07.
User-level and ancestor instructions can still apply. Reload or restart a runtime after
instruction changes; the text already loaded into an active session does not update itself.

Private agent skills may supply a workflow, but the public contract must state its required
result without assuming those skills are installed. No other repository administers this one.
Keep session continuity in the active runtime and private records, not a public checkpoint.

## Tracked configuration inventory

| Surface | Responsibility and authority |
|---|---|
| `AGENTS.md`, `CONTRIBUTING.md`, `GLOSSARY.md`, `docs/agents/`, `docs/adr/` | Shared instructions, contribution procedure, vocabulary and accepted decisions. |
| `pyproject.toml` | Package metadata; Hatch build settings; pytest markers, options and coverage; Ruff, mypy and Pyright settings. Ruff and strict mypy are the CI authorities, not editor diagnostics. |
| `requirements-ci.txt` | CI dependency constraints. Compare actual installed versions before describing a local run as equivalent. |
| `.pre-commit-config.yaml` | Formatting, parsing, key detection, residue and structural bans. The config is tracked; installation in each checkout is separate. |
| `.gitattributes`, `.gitignore`, `.dockerignore` | Git text handling, publication exclusions and assurance-container build exclusions. An ignore rule does not protect an existing file from checkout or deletion. |
| `.github/workflows/ci.yml` | Lint, types, test matrix, calibration, residue, structural bans, drift, release, dependency and prose gates. Read the current commands rather than copying a second gate list into agent instructions. |
| `.github/workflows/assurance.yml`, `dependency-audit.yml`, `accessibility.yml` | Assurance, dependency and accessibility workflows. |
| `.github/workflows/publish.yml`, `release-authorize.yml`, `pages.yml`, `repo-description-sync.yml` | Package release, release authorization and public-site/repository publication. Configuration work does not authorize a release. |
| `.github/workflows/depersonalization-gate.yml`, `schedule-staleness.yml`, `scorecard.yml`, `triage-label-on-open.yml` | Publication-boundary checks, schedule freshness, security reporting and issue triage. |
| `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/` | Review ownership and contribution templates. Live branch protection, not the template, determines required checks. |
| `.github/dependabot.yml` | Dependency-update scheduling and grouping. Do not merge unrelated update PRs as configuration maintenance. |
| `.config/vale/.vale.ini`, `.config/vale/styles/Taste/*.yml` | Public prose rules. These implement the register stated in `AGENTS.md`. |
| `.github/a11y/axe.json`, `htmlcs.json`, `package.json`, `package-lock.json` | Accessibility runner configuration and its pinned JavaScript dependency tree. |
| `Dockerfile.assurance`, `requirements-assurance-container.txt` | Assurance-container environment. Not an instruction to build or deploy it. |

Paths abbreviated after a directory-qualified entry in the same row share that directory.
Implementation-owned data such as evaluator declarations, migrations, ratifications and frozen
receipts remain under their existing specification and tests; this inventory does not reclassify
them as editable agent preferences.

## Local and inherited surfaces

These were present in the inspected checkout. They are not missing public deliverables.
Do not force-add them, copy their contents into a PR, or relocate credentials.

| Surface | Disposition |
|---|---|
| `CLAUDE.md`, `.claude/reference/` | Ignored private adapter and on-demand workflow detail. Shared requirements route to `AGENTS.md`; older explanations do not override current specifications. |
| `.claude/settings.local.json` | Machine-local permissions and MCP selection. Retain deliberate server exclusions; remove obsolete one-command grants rather than copying them to shared settings. |
| `.claude/state/`, `.claude/worktrees/`, runtime locks | Private or historical runtime material, not shared execution authority. Do not resume from an archived checkpoint merely because it is present. |
| `.vscode/settings.json` | This checkout's Windows `.venv` interpreter path. Not a cross-platform project default. |
| `.editorconfig` | Local editor defaults. `.gitattributes` and executable formatter settings remain the public authorities. |
| `.gitnexusrc`, `.gitnexus/` | Local graph configuration and generated index. Index freshness must be checked before graph evidence is used. Lexical inspection does not require a rebuild. |
| `.git/config`, `.git/info/exclude`, `.git/hooks/` | Per-checkout Git settings, local publication exclusions and installed hooks. Never copy machine paths into tracked configuration. |
| `.venv/`, `uv.lock`, tool caches, local databases and backups | Local environment, resolver output and evidence artifacts excluded by the existing publication boundary. Do not delete them as cleanup. |
| User-level Claude and Pi configuration | Inherited settings, authentication, skills and hooks. Outside this repository's freeze; no project override is added merely to shadow them. |

No project `.pi/` directory, shared `.claude/settings.json`, project MCP configuration,
`AGENTS.override.md`, `GEMINI.md` or `.github/copilot-instructions.md` was found in this checkout.
None is required for the inspected workflow. Pi already loads `AGENTS.md`; adding another
instruction file would create another place for the contract to drift. Add a runtime-specific
file only for a demonstrated need that the shared contract and inherited settings cannot meet.

## Settled baseline and reopening

Keep the shared contract, local adapter and executable settings aligned. Do not undertake
speculative harness work after this baseline lands. A later change needs a concrete failure,
a changed upstream contract or an explicitly authorized capability; identify the owning file
and the evidence that justifies the change. Use the existing PR, checks and independent
exact-head verification procedure. This is a maintenance boundary, not a new hook or judge.

Validation of this change must establish:

- a fresh Pi context load selects the shared contract;
- the local Claude adapter imports it without restating conflicting public rules;
- tracked configuration parses and the existing applicable checks pass;
- the local pre-commit hook resolves the installed checkout environment;
- private files remain excluded from the public diff;
- an independent verifier reviews the exact public head before merge.

Tests establish mechanical behavior, not that these instructions will always be followed.
No paid model evaluation, evidence-store mutation, release, branch-protection change or
statistical-rule change is part of this baseline. Reopen only the surface a demonstrated
problem requires, then verify that change through its existing owner and checks.
