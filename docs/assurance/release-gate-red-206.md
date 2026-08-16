# Release gate RED demonstration (#206)

This receipt records the test-first RED run for the `0.3.0` assurance release
gate. The gate was run against a local HTTP seed with issue #169 open, the other
issues in #167-#174 closed, and no assurance workflow runs. The production gate
uses the GitHub API at release time; only the data source was replaced for this
deterministic falsification.

Command under test:

```console
RELEASE_GATE_VERSION=0.3.0 python scripts/release_gate.py
```

Exit code: `1`

Relevant output:

```text
RELEASE GATE: BLOCKED
FAIL  G7: assurance issue #169 is open
FAIL  G8: no successful assurance.yml workflow run recorded
```

The executable demonstration remains automated in
`tests/test_release_gate_206.py`: the test starts the seed server, invokes the
release gate as a subprocess, and asserts the nonzero exit and named failures.
