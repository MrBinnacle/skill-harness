# GitHub Actions workflow audit

Audit date: 2026-08-15. Scope: every YAML file in `.github/workflows/` at issue #172.

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

No branch-protection setting was changed; maintainers alone decide whether either new check
becomes required.
