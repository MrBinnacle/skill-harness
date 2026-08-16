# Release gate RED demonstration (#206)

The 0.3 assurance checks (G7 and G8 in `scripts/release_gate.py`) were
falsified before they were trusted. The gate ran against a seeded tree that
declares version `0.3.0` in `pyproject.toml`,
`src/skill_harness/__init__.py`, the `CHANGELOG.md` section and link
reference, and the README status banner, and that carries one SHA-pinned
workflow. Checks G1 through G6 therefore pass on that tree, so every failure
the run prints comes from the assurance checks and from nothing else.

A local HTTP server answered the two GitHub reads the gate performs:
assurance issue #169 `open`, the remaining issues in #167-#174 `closed`, and
no `assurance.yml` workflow runs at all.

Command:

```console
$ RELEASE_GATE_GITHUB_API_URL=http://127.0.0.1:<port> \
    python scripts/release_gate.py --root <seeded-0.3.0-tree>
```

Exit code: `1`

Output, verbatim:

```text
G6: not a tag ref (local run) — tag-match check self-skips.
RELEASE GATE: BLOCKED — 2 stale surface(s) at version 0.3.0:
  FAIL  G7: assurance issue #169 is open
  FAIL  G8: no successful assurance.yml workflow run recorded
```

Finding: the gate refuses a `0.3.0` release while an assurance issue is open
and while no successful assurance lane run is on record, and it names each
cause. The two lines above are the complete failure list, so the exit code is
attributable to the assurance checks alone.

What this run does not show: that the live GitHub API returns these answers
today — both reads were seeded locally; that any real `assurance.yml` run has
ever finished green; that a maintainer cannot bypass the gate by editing
`publish.yml` or by pointing `RELEASE_GATE_GITHUB_API_URL` at another server.
This gate is blocked-by-default, not tamper-proof, on the same terms as the
six checks that preceded it.

Next: `tests/test_release_gate_206.py` re-runs this scenario on every CI run
and compares the transcript above line-for-line against the gate's output, so
the record cannot drift from the program. The live-API path is first exercised
at the `0.3.0` tag.
