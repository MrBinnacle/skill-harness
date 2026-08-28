"""Repo description sync check - verifies the live GitHub About text against
the declared ``pyproject.toml`` description.

Why this exists: ``tests/test_structural_bans.py`` pins the ``pyproject.toml``
side of this pair to a fixed literal
(``test_pyproject_description_matches_approved_repo_description``), but
nothing in the tree reads the live GitHub repository description field. The
claimed byte-for-byte lockstep between the declared description and the
public-facing one was therefore one-sided: the file was checked, the public
surface was not. This script closes that other half.

What it guards: the GitHub repository "About" description - a public surface
edited through the GitHub web UI, entirely out-of-band from any commit - must
read identically, byte for byte, to ``[project].description`` in
``pyproject.toml``. No whitespace normalization, no case folding: a trailing
space is drift.

Exit codes:
  0 = the live description and the declared description match, byte for byte.
      Prints ``DESCRIPTION SYNC: PASS``.
  1 = they disagree. Prints ``DESCRIPTION SYNC: DRIFT`` and both strings in
      full, each on its own labelled line.
  2 = the live description could not be read (network error, non-200
      response, unparseable JSON, or a missing/null ``description`` field).
      This is a FAILURE, not a skip: an unreadable live surface is a refusal
      to report, never a pass. Prints ``DESCRIPTION SYNC: REFUSED``. (Same
      doctrine as the house SERS receipts: a missing figure is a typed
      refusal, never an invented score.)

Run locally: ``python scripts/repo_description_check.py [--repo OWNER/NAME]
[--root <repo-root>]``. Set ``GITHUB_TOKEN`` in the environment to authenticate
(raises the rate limit); the script also runs unauthenticated.

Deliberately NOT part of ``scripts/drift_check.py``: that guard is hermetic -
every contract it holds reads state from the tree, never the network - and
folding a live HTTP call into it would break that property for every one of
its other rows. This script is a separate, scheduled check for exactly that
reason.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

_TIMEOUT_SECONDS = 15.0
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (2.0, 4.0)


class LiveDescriptionUnavailable(Exception):
    """Raised by a fetcher when the live description could not be read.

    Any raise of this (or a subclass) from the injected fetcher is treated as
    exit code 2 by ``main`` -- the refusal path, not a crash."""


def _read_declared_description(root: Path) -> str:
    pyproject_path = root / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    description = data["project"]["description"]
    if not isinstance(description, str):
        raise LiveDescriptionUnavailable(f"{pyproject_path}: [project].description is not a string")
    return description


def fetch_live_description(repo: str, token: str | None, timeout: float = _TIMEOUT_SECONDS) -> str:
    """Fetch the live GitHub repository description via the REST API.

    Raises ``LiveDescriptionUnavailable`` for every failure mode: transport
    error, non-200 response, unparseable JSON, or an absent/null
    ``description`` field. Retries transport failures and 5xx responses up to
    ``_MAX_ATTEMPTS`` times with the ``_BACKOFF_SECONDS`` schedule; a 404 (or
    any other 4xx) is final and is not retried.
    """
    url = f"https://api.github.com/repos/{repo}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "skill-harness-repo-description-check",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        request = urllib.request.Request(  # noqa: S310 - fixed API origin or test stub
            url, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                status = response.status
                body = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code >= 500 and attempt < _MAX_ATTEMPTS - 1:
                last_error = exc
                time.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise LiveDescriptionUnavailable(
                f"GitHub API returned HTTP {exc.code} for {url}"
            ) from exc
        except urllib.error.URLError as exc:
            if attempt < _MAX_ATTEMPTS - 1:
                last_error = exc
                time.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise LiveDescriptionUnavailable(
                f"transport error contacting {url}: {exc.reason}"
            ) from exc

        if status != 200:
            if status >= 500 and attempt < _MAX_ATTEMPTS - 1:
                last_error = RuntimeError(f"HTTP {status}")
                time.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise LiveDescriptionUnavailable(f"GitHub API returned HTTP {status} for {url}")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LiveDescriptionUnavailable(f"unparseable JSON from {url}: {exc}") from exc

        description = payload.get("description")
        if description is None:
            raise LiveDescriptionUnavailable(
                f"{url}: 'description' field is absent or null in the response"
            )
        if not isinstance(description, str):
            raise LiveDescriptionUnavailable(f"{url}: 'description' field is not a string")
        return description

    # Unreachable in practice (every branch above either returns or raises),
    # but keeps the function total for mypy --strict.
    raise LiveDescriptionUnavailable(f"exhausted {_MAX_ATTEMPTS} attempts against {url}") from (
        last_error
    )


def _default_fetch(repo: str, token: str | None) -> str:
    """Module-level default fetcher bound to the real API. Kept separate from
    ``main`` so the injected-fetch seam never shadows a same-named parameter."""
    return fetch_live_description(repo, token)


def compare_descriptions(live: str | None, declared: str) -> int:
    """Pure comparison: byte-for-byte equality, no normalization.

    Returns 0 (match), 1 (drift) or 2 (live unreadable, signalled by
    ``live is None``). Takes no I/O so it is exercised directly by tests."""
    if live is None:
        return 2
    if live == declared:
        return 0
    return 1


def _print_result(code: int, live: str | None, declared: str) -> None:
    if code == 0:
        print("DESCRIPTION SYNC: PASS")
        print(f"description: {declared!r}")
    elif code == 1:
        print("DESCRIPTION SYNC: DRIFT")
        print(f"live (GitHub About):        {live!r}")
        print(f"declared (pyproject.toml):  {declared!r}")
    else:
        print("DESCRIPTION SYNC: REFUSED")
        print(
            "the live GitHub description could not be read; an unreadable "
            "live surface is a refusal to report, never a pass"
        )
        print(f"declared (pyproject.toml):  {declared!r}")


def main(
    argv: list[str] | None = None,
    fetch: Callable[[str, str | None], str] | None = None,
) -> int:
    """Entry point. ``fetch`` is injectable so tests never touch the network;
    it defaults to ``fetch_live_description`` bound to ``GITHUB_TOKEN``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default="MrBinnacle/skill-harness",
        help="owner/name of the canonical repo to check (default: MrBinnacle/skill-harness)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repo root holding pyproject.toml (default: this script's repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    declared = _read_declared_description(root)

    token = os.environ.get("GITHUB_TOKEN")
    active_fetch = fetch if fetch is not None else _default_fetch

    live: str | None
    try:
        live = active_fetch(args.repo, token)
    except LiveDescriptionUnavailable:
        live = None

    code = compare_descriptions(live, declared)
    _print_result(code, live, declared)
    return code


if __name__ == "__main__":
    sys.exit(main())
