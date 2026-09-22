# PR: Document isolated local pytest environments (#580)

`thinc` 8.3.10 registers `thinc.api:fix_random_seed` in pytest-randomly's
random-seeder entry-point group. It calls `numpy.random.seed(seed)` without a
modulo guard. pytest-randomly supplies `base_seed + offset`, which can exceed
`2**32 - 1`; numpy then raises `ValueError` and makes local test results
non-deterministic.

This is host-environment contamination. `thinc` is not declared in
`pyproject.toml`. The repository cannot remove a package from a contributor's
global or user site. It can state the isolated virtual-environment setup that
keeps those packages out of the project's interpreter.

## Acceptance criterion

In a fresh virtual environment installed from `pyproject.toml`,
`python -m pytest tests/test_sers_conformance.py -q` must exit 0 without errors
across three consecutive runs.

`pytest-randomly` loads and invokes third-party seeders during collection and
before each test phase. A test that inspects its own active interpreter runs
after that mechanism and cannot protect the suite. The source-level coverage
therefore pins the repository-controlled contributor interface instead:

- `tests/test_environment_isolation_580.py::test_contributing_documents_an_isolated_venv_for_pytest`
  asserts that the Development setup section keeps the standard `python -m venv
  .venv` command, rejects `--system-site-packages`, and names the observed
  numpy error.
- `tests/test_environment_isolation_580.py::test_sers_conformance_passes_without_user_site_three_times`
  starts three Python subprocesses with `PYTHONNOUSERSITE=1` and runs the
  specified SERS conformance suite in each. This supplies the acceptance
  outcome without inheriting packages installed in the user site.
- `CONTRIBUTING.md` states that an unisolated interpreter can expose packages
  installed with `pip install --user`, explains the `thinc` mechanism, and
  directs the contributor to recreate an isolated venv.

No mutation receipt was requested. This ticket changes contributor
documentation, not measurement logic.
