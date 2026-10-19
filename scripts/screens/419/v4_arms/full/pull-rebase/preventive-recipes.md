# Preventive recipes

These are recipes, not executable artifacts. Implement and test the guard where it must fire. The decision table is stable; language, paths, and messages are replaceable.

## Shared predicate

Parse shell syntax and then Git arguments. Never search the raw string for a `git` token followed later by a `pull` token: prose, paths, substitutions, and quoted data can contain both.

For each actual `git pull` invocation:

1. Pass if its arguments contain `--rebase`, `--rebase=<mode>`, or `--no-rebase`; that records intent.
2. Otherwise resolve the current branch and effective `branch.<name>.rebase`, then `pull.rebase`, using normal config scope/includes. Block only when the value selects rebase (`true`, `merges`, `interactive`, or documented aliases).
3. On parse failure, config error, missing Git, or outside a work tree, pass. A preventive guard must fail open rather than wedge the session.

Do not evaluate config except for an actual `pull`. Config reads/writes and text merely naming this skill or guard must pass.

## Required acceptance table

Both recipes below MUST pass this table before use.

| Expected | Case |
|---|---|
| MUST BLOCK | Bare `git pull` with effective rebase config true |
| MUST PASS | `git pull --rebase` (intent recorded) |
| MUST PASS | `git pull --no-rebase` (intent recorded) |
| MUST PASS | Reading or setting `pull.rebase` or `branch.<name>.rebase` |
| MUST PASS | Any command merely naming `pull-rebase` or the guard file, including a path glob or reading the guard source |
| MUST PASS | A refspec whose path contains the subcommand word, such as `git fetch origin pull/506/head:probe506`, `git ls-remote origin 'pull/*/head'`, or `git push origin HEAD:refs/pull/12/head`. This is GitHub's documented form for a pull request head, so any adopter who reviews pull requests will run it |
| MUST PASS | A commit whose message body spells the subcommand in prose, such as `git commit -F msg.txt` where the file describes this trap |
| MUST PASS | Guard internal error, missing Git, or outside a repository (fail open; never wedge the session) |

## Claude Code `PreToolUse`

In `~/.claude/settings.json` (all projects) or `.claude/settings.local.json` (one project), register a synchronous command handler under `hooks.PreToolUse` with matcher `Bash`. Read `tool_input.command` from stdin and emit this only for the block case:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Bare git pull blocked: effective rebase config is enabled; pass --rebase or --no-rebase explicitly."
  }
}
```

For every pass or error, exit zero silently. Do not rely on the optional `if` filter: run for Bash and let a shell-aware parser identify actual pulls. This is loop-native because `PreToolUse` fires before each tool call and can deny it.

Verified 2026-08-12 against the live [Claude Code hooks reference](https://code.claude.com/docs/en/hooks): `PreToolUse`, Bash input, deny output, and silent exit-zero behavior.

## Shell wrapper without an agent harness

Put a function named `git` in the operator or automation shell startup. Preserve the real Git path before defining it. Inspect the argument vector: if the subcommand is not `pull`, exec real Git unchanged; otherwise apply the predicate, refuse only the block case, and exec real Git for every pass/error. Never rebuild and rescan a string.

This covers that shell, not programs invoking real Git directly or non-loading shells. Guard every required entry point. Git has no pre-pull client hook: `pre-rebase` runs after `pull` fetched and misses merge-configured pulls. The shell is the non-harness interception point.

Verified 2026-08-12 against Git 2.54.0's live [`githooks`](https://git-scm.com/docs/githooks/2.54.0), [`pull`](https://git-scm.com/docs/git-pull/2.54.0), and [`config`](https://git-scm.com/docs/git-config/2.54.0) manuals. Re-check later versions.

No repository test executes adopter-owned enforcement. Before relying on either form, run every table row in a disposable repository.
