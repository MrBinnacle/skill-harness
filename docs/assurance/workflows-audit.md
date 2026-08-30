# GitHub Actions workflow audit

Audit date: 2026-08-15. Scope: every YAML file in `.github/workflows/` at issue #172.

Rows added after that date carry their own date. The 2026-08-15 sweep is a point-in-time
record and is not restated by a later addition; `tests/test_assurance_supply_chain_172.py`
holds every row, original and added, to the same four conditions.

Method: inspect every `uses:` reference for an exact 40-character commit SHA; inspect
workflow- and job-level `permissions:` for the minimum access needed by their steps; and
inspect all triggers for `pull_request_target` or another untrusted-code privilege boundary.

| Workflow | Action pinning | Effective permissions | Trigger review | Result |
|---|---|---|---|---|
| `.github/workflows/assurance.yml` | All actions pinned to commit SHAs | Workflow `contents: read`; no job elevation | Manual dispatch only; no `pull_request_target` | Pass |
| `.github/workflows/ci.yml` | All actions pinned to commit SHAs | Workflow `contents: read`; no job elevation | `push`, `pull_request`, and manual dispatch; no `pull_request_target` | Pass |
| `.github/workflows/depersonalization-gate.yml` | All actions pinned to commit SHAs | Workflow `contents: read`; no job elevation | `push` and `pull_request`; no `pull_request_target` | Pass |
| `.github/workflows/pages.yml` | All actions pinned to commit SHAs | Workflow `contents: read`; deploy job alone adds `pages: write` and `id-token: write` | Default-branch push and manual dispatch; no `pull_request_target` | Pass |
| `.github/workflows/publish.yml` | All actions pinned to commit SHAs | Workflow `contents: read`; publish job alone replaces that with `id-token: write` for PyPI trusted publishing | Published releases only; no `pull_request_target` | Pass |
| `.github/workflows/scorecard.yml` | All actions pinned to commit SHAs | Workflow `read-all`; analysis job alone adds `security-events: write` and `id-token: write` for SARIF and published results | Default-branch push and weekly schedule; no `pull_request_target` | Pass |
| `.github/workflows/repo-description-sync.yml` (added 2026-08-28) | All actions pinned to commit SHAs | Workflow `contents: read`; no job elevation. Reads `secrets.GITHUB_TOKEN` for GitHub API rate limit only | Daily schedule, `push` on `main` limited to `pyproject.toml`, and manual dispatch; no `pull_request_target` | Pass |
| `.github/workflows/triage-label-on-open.yml` (added 2026-08-30) | No `uses:` reference; a single `gh issue edit` shell step | Workflow `contents: read`; the one job alone adds `issues: write`, which `gh issue edit --add-label` consumes | `issues: opened` only, gated on the issue carrying zero labels; no `pull_request_target`. Not on the merge path: it acts on an issue event, never on a pull request | Pass |

## Findings

- No unpinned GitHub Action reference was found.
- Every workflow has an explicit least-privilege permission baseline. Write access exists
  only on the job that consumes it and only for Pages deployment, PyPI OIDC publishing, or
  Scorecard SARIF/OIDC result publication.
- No workflow uses `pull_request_target`.
- Shell `run:` dependencies are outside the action-pinning check. The release workflow's
  `python -m pip install build` is not a GitHub Action reference and is therefore recorded
  as out of scope rather than silently represented as SHA-pinned.

## Required-check boundary

No existing job was renamed. The new `dependency-audit` job is intentionally absent from
`all-green`'s `needs` list, and Scorecard is a separate workflow.

`repo description sync` (added 2026-08-28) is a separate workflow for the same reason, and
deliberately so. It reads a live GitHub API field, so it is the one check in this
repository that cannot be hermetic. Placing it on the merge path would make a network
round-trip a condition of merging while still failing to catch the drift it exists for:
the About-box text is edited through the web UI, out-of-band from every commit, so no pull
request diff can contain the change that causes the drift. A schedule observes that
surface; a merge gate cannot.

No branch-protection setting was changed; maintainers alone decide whether either new check
becomes required.
