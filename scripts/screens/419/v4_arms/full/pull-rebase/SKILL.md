---
name: pull-rebase
description: Use before `git pull` where `pull.rebase` may be `true`. `--no-ff` does NOT stop a rebase under `pull.rebase=true` (silently ignored); it rewrites every local commit SHA. Check config first.
---

# pull-rebase

This card ships three parts: an explanation of the trap, prevention-by-recipe for adopter-owned enforcement, and the recovery runbook below. It deliberately ships no executable hook. Enforcement that must fire belongs in the adopter's environment; the card remains the model-invocable reference.

## The trap

`git pull --no-ff` does **not** override `pull.rebase=true`. The `--no-ff` flag applies to *merge* operations; when the effective pull strategy is rebase, `--no-ff` is silently ignored and the rebase proceeds anyway.

When local has diverged from origin (e.g., 22 local commits + N remote commits), this rewrites every local commit with a new SHA. Any artifact that referenced the old SHAs — state files, gate-event ledgers, retrospection logs, release notes — is now stale and must be backfilled.

## When this fires

Any of these conditions:

- `git config pull.rebase` returns `true` (globally or per-repo)
- `git config branch.<current>.rebase` is `true`
- A `[pull] rebase = true` block exists in `.git/config` or `~/.gitconfig`

The trap fires whether you pass `--no-ff` or no flag at all: the configured pull strategy is rebase, so a merge-side flag is simply ignored and your commits are rebased. **`--ff-only` is the exception** — on diverged history it refuses outright (git aborts with a "cannot fast-forward" message; the exact wording varies by git version) instead of silently rebasing. That makes `--ff-only` a loud guard rail rather than a silent SHA rewrite — but not a usable everyday pull, since it also refuses every legitimate diverged sync.

## Pre-flight (before `git pull`)

```bash
git config --get pull.rebase
git config --get branch.$(git branch --show-current).rebase
```

If either returns `true`, do NOT use `git pull` for divergence resolution. Use the explicit two-step:

```bash
git fetch origin <branch>
git merge --no-ff origin/<branch>   # produces a real merge commit
```

Or, if a linear history is actually wanted:

```bash
git fetch origin <branch>
git rebase origin/<branch>   # explicit rebase — at least the intent is recorded
```

## Preventive versus reactive enforcement

A reactive hook surfaces this card after an error or bad pull; it helps recovery but cannot preserve the old SHAs. Prevention must run before the pull itself. Model invocation cannot guarantee that check, and a prompt-triggered hook has no turn to fire during an unattended loop.

Install an adopter-owned guard using [the runtime recipes and required case table](preventive-recipes.md). Claude Code can block the Bash tool call with `PreToolUse`; a shell wrapper covers interactive and automated shells without an agent harness. Native Git hooks do not provide a pre-pull interception point, so `pre-rebase` is too late for this policy.

## Recovery (if you already pulled and triggered a rebase)

1. **Identify SHAs that need backfilling.** Grep state files / gate ledgers / release notes for the OLD SHAs. The reflog has both:
   ```bash
   git reflog --pretty='%h %s' | head -40
   ```
2. **Map old → new.** The new SHAs are HEAD-relative; pair them with old SHAs in order from the reflog.
3. **Backfill in a single commit.** Stage the state-file and audit-trail updates together; commit message should explicitly call out "post-rebase SHA backfill" so future audit-state checks don't flag the changes as drift.
4. **Authorize the force-push explicitly** before pushing. Never force-push to a protected branch without explicit user authorization.

## Why this is non-obvious

- The Git documentation for `pull --no-ff` doesn't mention that the flag is a no-op under `pull.rebase=true`.
- The rebase happens silently — there's no warning that `--no-ff` was ignored.
- `pull.rebase=true` is a common Git-config recommendation for "clean history" workflows, and many repos inherit it from team `.gitconfig` templates without the operator realizing it's set.
- The blast radius (22 SHA rewrites + 5 state-file backfills + force-push pressure) is visible only after the fact.

## Anti-patterns

- `git pull --no-ff` as a "safe default" — only safe if you've verified `pull.rebase` is unset or `false`.
- Running `git pull` to "investigate divergence." Use `git fetch` + `git log HEAD..origin/<branch>` for read-only divergence inspection.
- Trusting that `--no-ff` documentation describes the full behavior. It describes `git merge --no-ff` behavior; `git pull --no-ff` behaves differently under rebase.

