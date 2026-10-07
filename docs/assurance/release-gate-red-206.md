# Release gate RED demonstration (#206, amended #735)

The 0.3 assurance checks (G7 and G8 in `scripts/release_gate.py`) were
falsified before they were trusted. The gate ran against a seeded tree that
declares version `0.3.0` in `pyproject.toml`,
`src/skill_harness/__init__.py`, the `CHANGELOG.md` section and link
reference, and the README status banner, and that carries one SHA-pinned
workflow. Checks G1 through G6 therefore pass on that tree, so every failure
the run prints comes from the assurance checks and from nothing else.

A local HTTP server answered the GitHub read the gate performs on this ref:
assurance issue #169 `open`, the remaining issues in #167-#174 `closed`. Off
a tag ref there is no release candidate, so G8 self-skips (#735) and is not
asked for a run list.

Command:

```console
$ RELEASE_GATE_GITHUB_API_URL=http://127.0.0.1:<port> \
    python scripts/release_gate.py --root <seeded-0.3.0-tree>
```

Exit code: `1`

Output, verbatim:

```text
G6: not a tag ref (local run) — tag-match check self-skips.
G8: SKIPPED, not a tag ref, no release candidate commit.
RELEASE GATE: BLOCKED (6 of 8 gates ran; skipped G6, G8), 1 stale surface(s) at version 0.3.0:
  FAIL  G7: assurance issue #169 is open
```

Finding: the gate refuses a `0.3.0` release while an assurance issue is open,
and it names the cause. G8 does not contribute a failure on this ref because
there is no release candidate to assure; that is a skip, not a pass, and the
summary counts it.

What this run does not show: that the live GitHub API returns these answers
today — the issue read was seeded locally; that any real `assurance.yml` run
has ever finished green at a release candidate commit; that a maintainer
cannot bypass the gate by editing `publish.yml` or by pointing
`RELEASE_GATE_GITHUB_API_URL` at another server. This gate is
blocked-by-default, not tamper-proof, on the same terms as the six checks
that preceded it.

Next: `tests/test_release_gate_206.py` re-runs this scenario on every CI run
and compares the transcript above line-for-line against the gate's output, so
the record cannot drift from the program. G8's live-API path is first
exercised at a tag ref, where `GITHUB_SHA` names the release candidate.

Amended 2026-09-14 under #576. The gate now states how many of its eight
checks ran and names each one it skipped.

Amended 2026-10-06 under #735. G7 and G8 are no longer scoped by
`_is_zero_three`. They read a declared requirements table keyed by minor
line; an undeclared line is NOT RUN and blocks. G8 off a tag ref self-skips
with "not a tag ref, no release candidate commit" instead of accepting any
historical green `assurance.yml` run. The transcript above is the re-recorded
output of the identical seeded scenario: one failure (the open issue), two
self-skips (G6 and G8). The finding is unchanged in shape — the same open
issue still blocks the same release — and the coverage claim now counts G8
as skipped rather than as a failure the API never answered.
