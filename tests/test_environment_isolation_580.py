"""#580 — host environment isolation: user-site packages must not leak into the venv.

`thinc` 8.3.10 registers an entry point in the `pytest_randomly.random_seeder`
group pointing at `thinc.api:fix_random_seed`. That function calls
`numpy.random.seed(seed)` with no modulo guard. `pytest-randomly` passes it the
per-test value `base_seed + offset`, which exceeds 2**32 - 1 whenever the sum
overflows, and numpy's legacy MT19937 seeding rejects it.

The fix is an isolated virtual environment. These tests verify that the current
environment is clean enough for the test suite to run.
"""

from __future__ import annotations

import site
from importlib.metadata import entry_points


def test_user_site_packages_disabled() -> None:
    """User-site packages must not be on the path.

    A venv disables user-site by default (site.ENABLE_USER_SITE is False).
    If this fails, the venv was created with --system-site-packages or the
    interpreter is not a venv at all.
    """
    assert not site.ENABLE_USER_SITE, (
        "USER_SITE_CONTAMINATION: user-site packages are enabled in this Python"
        " environment. Create a venv with `python -m venv .venv` (without"
        " --system-site-packages) and install into it. User-site packages like"
        " thinc register unguarded pytest-randomly seeders that fail when seeds"
        " exceed 2**32 - 1 (#580)."
    )


def test_no_thinc_seeder_registered() -> None:
    """thinc.api:fix_random_seed must not be registered as a pytest-randomly seeder.

    thinc's seeder calls numpy.random.seed(seed) without a modulo guard.
    pytest-randomly passes base_seed + offset, which can exceed 2**32 - 1.
    numpy's MT19937 rejects seeds above that range, producing non-deterministic
    test failures.

    If this fails, uninstall thinc from the current environment or use an
    isolated venv (CONTRIBUTING.md documents the setup).
    """
    seeders = entry_points(group="pytest_randomly.random_seeder")
    for ep in seeders:
        assert "thinc" not in ep.value, (
            f"THINC_SEEDER_REGISTERED: {ep.value} is registered as a"
            f" pytest-randomly random seeder. This function calls"
            f" numpy.random.seed(seed) without a modulo guard, and"
            f" pytest-randomly passes it seeds that can exceed 2**32 - 1."
            f" Uninstall thinc or use an isolated venv (#580)."
        )
