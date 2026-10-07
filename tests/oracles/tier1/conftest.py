"""Tier-1 oracle test configuration.

Two session-scoped guards per A33:

1. PYTHONHASHSEED=0 assertion — bit-equality tests require deterministic
   hash randomisation.  If the seed is not explicitly set to '0', the
   conftest module fails loudly at collection time rather than silently
   producing flaky results.

2. _no_network autouse fixture — wraps every test in this package with
   pytest-socket's ``socket_disabled`` fixture so any accidental network
   call raises SocketBlockedError rather than silently succeeding.
   Scope is 'function' (not module/session) so individual tests can
   override with @pytest.mark.enable_socket if needed in future subtracks
   (e.g. C.2 live-judge tests must NOT be in this package).
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# PYTHONHASHSEED=0 guard (A33)
# ---------------------------------------------------------------------------


def _assert_pythonhashseed_zero() -> None:
    """Fail collection if PYTHONHASHSEED != '0'.

    Tier-1 bit-equality tests assert ``metric(case) == metric(case)``
    across invocations.  Python's hash randomisation (default since 3.3)
    can affect str/bytes hash values used in set ordering and dict
    iteration.  The Tier-1 metrics are pure deterministic functions, but
    we assert the seed explicitly so future maintainers cannot accidentally
    rely on hash-random behaviour.

    Run with: PYTHONHASHSEED=0 pytest tests/oracles/tier1/
    """
    seed = os.environ.get("PYTHONHASHSEED", "")
    assert seed == "0", (
        f"PYTHONHASHSEED must be '0' for Tier-1 bit-equality tests; got {seed!r}. "
        "Run: PYTHONHASHSEED=0 pytest tests/oracles/tier1/"
    )


_assert_pythonhashseed_zero()


# ---------------------------------------------------------------------------
# Network block (A33)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network(socket_disabled: None) -> None:
    """Block all network I/O for every Tier-1 test.

    pytest-socket provides the ``socket_disabled`` fixture; requesting it
    here as a parameter causes it to run for every test in this package
    (autouse=True).  Any call to socket.socket() raises SocketBlockedError.

    Scope intentionally 'function' so tests outside this conftest (e.g.
    Track B extractor tests) are not affected.
    """
