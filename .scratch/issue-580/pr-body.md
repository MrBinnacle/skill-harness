# PR: Host environment isolation — guard against user-site package contamination (#580)

`thinc` 8.3.10 registers an entry point in the `pytest_randomly.random_seeder`
group pointing at `thinc.api:fix_random_seed`. That function calls
`numpy.random.seed(seed)` with no modulo guard. `pytest-randomly` passes it
the per-test value `base_seed + offset`, which exceeds 2^32 - 1 whenever the
sum overflows, and numpy's legacy MT19937 seeding rejects it:

```
E   ValueError: Seed must be between 0 and 2**32 - 1
numpy/random/_mt19937.pyx:182: ValueError
```

The failure count is non-deterministic because it depends on which per-test
offsets overflow. The same file with `-p no:randomly` produces 48 passed.

## Scope

This is host environment contamination, not a defect in this repository.
`thinc` is not declared in `pyproject.toml`. A contributor without thinc or
spaCy installed does not reproduce this. The maintainer pays: plain `pytest`
on the development machine produces a varying number of errors in code nobody
touched, so the local suite cannot be used as a verification signal without
a flag that is not written down anywhere.

## Files changed

- `tests/test_environment_isolation_580.py` — two tests that verify the
  current environment is clean enough for the test suite to run
- `CONTRIBUTING.md` — venv isolation note added to the Development setup
  section

## Acceptance criteria

### AC1: Isolated venv passes the test suite

Acceptance: in a fresh virtual environment created from `pyproject.toml`,
`python -m pytest tests/test_sers_conformance.py -q` exits 0 with no errors
across three consecutive runs.

**Before this change:** `tests/test_environment_isolation_580.py` did not
exist. No test pinned the venv isolation requirement. A contributor with thinc
installed at user site saw non-deterministic failures; the suite could not be
used as a verification signal.

**After this change:** Two tests in `tests/test_environment_isolation_580.py`
verify the environment is clean:

1. `test_user_site_packages_disabled` — asserts `site.ENABLE_USER_SITE` is
   False. A venv disables user-site by default; if this fails, the venv was
   created with `--system-site-packages` or the interpreter is not a venv.

2. `test_no_thinc_seeder_registered` — checks `importlib.metadata.entry_points(group='pytest_randomly.random_seeder')` for any entry whose value
   contains "thinc". If thinc is installed and its seeder is registered, this
   test fails with a message naming the mechanism and the fix.

**Test results (clean venv, Python 3.13.15, pytest 9.1.1, pytest-randomly 5.0.0):**

- `test_user_site_packages_disabled` — PASSED
- `test_no_thinc_seeder_registered` — PASSED
- `test_sers_conformance.py` — 52 passed (three consecutive runs, all green)

**Red-phase verification:** In a contaminated environment (thinc 8.3.10
installed at user site, pytest-randomly 4.1.0), the SERS conformance suite
produces 8-48 non-deterministic `ValueError` failures depending on seed
offsets. The same file with `-p no:randomly` produces 48 passed. The isolation
tests would also fail: `test_user_site_packages_disabled` if the venv inherits
user-site, `test_no_thinc_seeder_registered` if thinc's seeder is registered.

### AC2: CONTRIBUTING.md documents the venv isolation requirement

The Development setup section now includes a note explaining:
- User-site packages leak into virtual environments
- `thinc` registers an unguarded pytest-randomly seeder
- `python -m venv .venv` does not inherit user-site packages
- Do not use `--system-site-packages`
- The `ValueError: Seed must be between 0 and 2**32 - 1` symptom and the fix

### AC3: Gate is green

```
ruff check src tests scripts           — passed
ruff format --check src tests scripts  — passed
mypy --strict src/ tests/ scripts/     — passed
```

## Mutation campaign

No mutation receipt was requested by this ticket. The tests are environment
checks, not measurement logic — they verify a property of the runtime
environment, not a branch in code.
