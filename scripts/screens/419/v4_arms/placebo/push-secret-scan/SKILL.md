---
name: push-secret-scan
description: Use before `git push` where the repository holds config files. A `.gitignore` entry does NOT stop `git add -f` (silently accepted); a tracked `.env` publishes its credential to every clone. Scan tracked files first.
---

# push-secret-scan

This card ships three parts: an explanation of the trap, prevention by an adopter-owned scanner, and the recovery runbook below. It deliberately ships no executable scanner. Enforcement that must fire belongs in the adopter's environment; the card remains the model-invocable reference.

## The trap

A `.gitignore` entry does **not** remove a file that is already tracked, and it does not stop `git add -f`. The ignore rule applies to *untracked* paths only; once a path is in the index, git keeps recording every change to it, and the ignore rule is silently skipped.

When a credential file has been tracked at any point (e.g., a `.env` added before the ignore rule existed), the push sends that credential to every clone of the remote. Any system that trusted the credential is now exposed and must be rotated.

## When this fires

Any of these conditions:

- `git ls-files` lists a path that also matches a `.gitignore` pattern
- The tree contains `.env`, `*.pem`, `*.key`, `id_rsa`, or `credentials.json`
- A `config` or `settings` file assigns a literal to a name ending in `_KEY`, `_TOKEN`, or `_SECRET`

The trap fires whether the file was added by hand or by a tool: the path is tracked, so the ignore rule is simply skipped and the content is published. **`git check-ignore --no-index` is the exception** — it reports the pattern that *would* match a tracked path (the output format varies by git version) instead of silently skipping it. That makes it a loud diagnostic rather than a silent miss — but not a scanner, since it says nothing about files whose names look harmless.

## Pre-flight (before `git push`)

```bash
git ls-files -ci --exclude-standard
git ls-files | grep -Ei '(\.env|\.pem|\.key|id_rsa|credentials\.json)$'
```

If either prints a path, do NOT push until the file is reviewed. Inspect its content read-only:

```bash
git show HEAD:<path> | head -20   # shows what the push would publish
```

Or, if the file is meant to be public, confirm it holds placeholders only:

```bash
git grep -nE '(_KEY|_TOKEN|_SECRET)\s*=\s*["'"'"'][^"'"'"']{8,}' -- <path>
```

## Preventive versus reactive enforcement

A reactive alert surfaces this card after a secret scanner on the hosting service flags a published credential; it helps recovery but cannot un-publish the value. Prevention must run before the push itself. Model invocation cannot guarantee that check, and a prompt-triggered hook has no turn to fire during an unattended loop.

Install an adopter-owned scanner such as gitleaks or detect-secrets. Claude Code can block the Bash tool call with `PreToolUse`; a native `pre-push` hook covers interactive and automated shells without an agent harness. A scanner run only in CI is too late for this policy.

## Recovery (if a credential was already published)

1. **Identify every credential in the published files.** Search the tracked tree for the value patterns above. The scanner reports path and line:
   ```bash
   git grep -nE '(_KEY|_TOKEN|_SECRET)\s*=' | head -40
   ```
2. **Revoke at the issuer.** Each credential is revoked where it was issued; a new value is generated there.
3. **Record the rotation in one place.** List each revoked credential, its issuer, and the time of revocation together; the record should say explicitly "published credential rotated" so a later audit does not treat the new values as unexplained drift.
4. **Tell the credential's owner explicitly** before closing the incident. Never mark a published credential resolved without the owner's confirmation.

## Why this is non-obvious

- The Git documentation for `.gitignore` states the tracked-file exception in one sentence that most readers skip.
- The skip happens silently — there is no warning that a tracked path matches an ignore rule.
- `.env` in `.gitignore` is a common template recommendation, and many repos adopt it after the file was first committed without the operator realizing it is still tracked.
- The blast radius (every clone and every mirror) is visible only after the fact.

## Anti-patterns

- Adding a path to `.gitignore` as a "fix" — only effective if the path was never tracked.
- Deleting the file in a new commit to "remove the secret." The value is still in the published objects; revocation is the only fix.
- Trusting that a scanner in CI protects the credential. It detects the leak; it does not prevent the push that caused it.
