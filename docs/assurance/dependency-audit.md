# Dependency audit (#172)

Parent: assurance-pass spec (#160). Sibling: workflow audit (`workflows-audit.md`).

`pip-audit` runs in CI as the `dependency-audit` job of `.github/workflows/ci.yml`:

```bash
python -m pip install -c requirements-ci.txt -e ".[dev]" pip-audit
python -m pip_audit --local
```

The job declares no `continue-on-error:`, so the audit step's exit status is the
job's result.

**A scanner that cannot fail is indistinguishable from a scanner that found
nothing.** A green step is therefore not the deliverable; the exit status was
exercised in both directions and both runs are recorded below.

## Environment

Linux container, CPython 3.13.14, pip 26.2.1, **pip-audit 2.10.1** — the version
pinned in `requirements-ci.txt`, so the runs below exercise the same scanner
version CI installs. Advisory data comes from pip-audit's default PyPI service.
Run date: 2026-08-15.

## Runs

| # | Environment | Result | Exit |
|---|-------------|--------|-----:|
| A | This repo's dev environment: 86 distributions, every one of the 61 `requirements-ci.txt` pins matched exactly, `skill-harness` 0.2.2 installed editable | `No known vulnerabilities found` | **0** |
| B | Fresh venv: `pip-audit==2.10.1` + `urllib3==1.26.4` | `ModuleNotFoundError: No module named 'urllib3.packages.six.moves'` | **1** |
| C | Fresh venv: `pip-audit==2.10.1` + `jinja2==2.11.3` | `Found 4 known vulnerabilities in 1 package` | **1** |

Every run used the CI command verbatim: `python -m pip_audit --local`.

Run C's findings, as printed:

| Name | Version | ID | Fix versions |
|------|---------|----|--------------|
| jinja2 | 2.11.3 | PYSEC-2026-1473 | 3.1.3 |
| jinja2 | 2.11.3 | PYSEC-2026-1471 | 3.1.6 |
| jinja2 | 2.11.3 | PYSEC-2026-1474 | 3.1.4 |
| jinja2 | 2.11.3 | PYSEC-2026-1475 | 3.1.5 |

### Run B is recorded as a *rejected* demonstration

Run B exited non-zero for the wrong reason. `urllib3` 1.26.4 is old enough that
pip-audit's own import of `requests` fails on it, so the process never reached an
advisory lookup: the exit status came from a traceback, not from a finding.

It is kept here because it is the near-miss this deliverable is exposed to. **A
non-zero exit is not by itself evidence that the scanner can report a
vulnerability**, and a demonstration that only recorded "exit 1" would have
passed with nothing behind it. Run C's pin was chosen so the process reaches the
advisory service: pip-audit reads installed metadata and never imports `jinja2`,
so a decade-old release of it cannot break the scanner on the way to the lookup.

## How to reproduce

```bash
# Run C — the accepted demonstration. Expect exit 1 and a findings table.
python -m venv /tmp/pip-audit-demo
/tmp/pip-audit-demo/bin/python -m pip install "pip-audit==2.10.1" "jinja2==2.11.3"
/tmp/pip-audit-demo/bin/python -m pip_audit --local; echo "exit=$?"

# Run A — the current dependency set. Expect exit 0.
pip install -c requirements-ci.txt -e ".[dev]" pip-audit
python -m pip_audit --local; echo "exit=$?"
```

## What these runs do not show

- **Not that GitHub Actions honours the exit status.** That follows from the step
  carrying no `continue-on-error:` — pinned by
  `tests/test_assurance_supply_chain_172.py` — and would only be *observed* by a
  CI run that goes red.
- **Not a byte-identical reproduction of the CI environment.** 25 of run A's 86
  distributions are outside `requirements-ci.txt` and resolve at install time,
  pip-audit's own dependency tree among them.
- **Not an absence of vulnerabilities.** pip-audit reports *published* advisories
  known to its service at the moment of the run; run A's clean result is a
  statement about that database on that date, not about the code.
- **Not a stable finding set.** The same command run later can return different
  IDs and fix versions for the same pin, in either direction.
- **Nothing about this repository's own source.** The audit reads the installed
  dependency set only.
