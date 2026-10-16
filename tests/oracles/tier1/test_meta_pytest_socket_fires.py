"""Meta-test: verify pytest-socket actually blocks network calls in Tier-1 tests.

This test attempts a real urllib.request.urlopen and asserts that
pytest-socket raises SocketBlockedError (not that the URL is unreachable).
The distinction matters: SocketBlockedError means the socket was blocked
at the Python level, not that DNS failed or the host refused the connection.

Implementation note: pytest-socket 0.8 calls warnings.warn() inside
SocketBlockedError.__init__ before super().__init__.  With
filterwarnings=["error"] in pyproject.toml that UserWarning would be
promoted to an error BEFORE the RuntimeError propagates, causing this test
to fail with UserWarning instead of SocketBlockedError.  The
filterwarnings mark below suppresses the UserWarning so pytest.raises
sees the RuntimeError hierarchy it expects.  This is NOT weakening the
test — we still assert the SocketBlockedError is raised.

Per A33 exit criteria.
"""

from __future__ import annotations

import urllib.request

import pytest
from pytest_socket import SocketBlockedError


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_socket_blocked_error_raised_on_urllib_open() -> None:
    """urllib.request.urlopen must raise SocketBlockedError, not connect."""
    with pytest.raises(SocketBlockedError):
        urllib.request.urlopen("http://example.com", timeout=1)
