"""words_to_avoid drift check - the vendored word list against the live
collection file it was copied from.

Why this exists (#462): the operator's 2026-09-06 ruling puts every line of
prose in every repository under one set of rules, and the rules are the
collection's ``copy.words_to_avoid`` list. ``MrBinnacle/skills`` owns that
list. This repository vendors a copy in ``assets/words_to_avoid.json`` so its
per-commit ban (``scripts/drift_check.py`` DC-16) reads no network. A vendored
copy goes stale the moment the owner edits the list, and nothing in this tree
can see that happen. This script is the half that can.

What it guards: the 15 words this repository refuses must be the 15 words the
collection publishes. It fetches ``assets/tokens.json`` from the collection,
reads ``copy.words_to_avoid``, canonicalizes it as
``json.dumps(words, separators=(",",":")).encode()``, digests that with
sha256, and compares against the same digest recomputed from the vendored
array. It recomputes from the array on both sides rather than reading a
published digest field: a published field is a second source of truth, and a
second source of truth cannot catch itself lying.

The digest is over the LIST, not over the file that carries it. A file digest
changes whenever ``assets/tokens.json`` is edited for any reason - a color
token, a spacing scale, a new ``known_gaps`` entry. A contract that reddens on
unrelated edits gets muted, and a muted contract is worse than none.

Exit codes:
  0 = the live list and the vendored list digest identically. Prints
      ``WORDS_TO_AVOID SYNC: PASS``.
  1 = they disagree. Prints ``WORDS_TO_AVOID SYNC: DRIFT``, both digests, and
      the words added and removed upstream, so the repair is one edit.
  2 = the live list could not be read (network error, non-200 response,
      unparseable JSON, missing or malformed ``copy.words_to_avoid``), or the
      vendored manifest is unreadable. This is a FAILURE, not a skip: an
      unreadable surface is a refusal to report, never a pass. Prints
      ``WORDS_TO_AVOID SYNC: REFUSED``. Same doctrine as the house SERS
      receipts, and as ``scripts/repo_description_check.py``.

Run locally: ``python scripts/words_to_avoid_drift_check.py [--repo OWNER/NAME]
[--path assets/tokens.json] [--root <repo-root>]``. Set ``GITHUB_TOKEN`` to
authenticate (raises the rate limit); the script also runs unauthenticated.

Deliberately NOT part of ``scripts/drift_check.py``: that guard is hermetic -
every contract it holds reads state from the tree, never the network - and
folding a live HTTP call into it would break that property for every one of
its other rows. This script is a separate, scheduled check for exactly that
reason, and it runs on the schedule
``.github/workflows/words-to-avoid-drift.yml`` sets, the way
``repo_description_check.py`` runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

# scripts/ carries no __init__.py and is not a package (see
# tests/test_repo_description_check.py for the same note). The digest and the
# manifest reader are shared with the per-commit ban on purpose: the two
# guards must canonicalize identically or they invent drift that is not there,
# so there is one definition of each, in drift_check.py, and this script
# imports it rather than restating it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from drift_check import (
    WordListManifestError,
    canonical_word_list_digest,
    read_word_list_manifest,
)

_TIMEOUT_SECONDS = 15.0
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (2.0, 4.0)
_DEFAULT_REPO = "MrBinnacle/skills"
_DEFAULT_PATH = "assets/tokens.json"
_MANIFEST_REL = "assets/words_to_avoid.json"


class LiveWordListUnavailable(Exception):
    """Raised by a fetcher when the live word list could not be read.

    Any raise of this (or a subclass) from the injected fetcher is treated as
    exit code 2 by ``main`` -- the refusal path, not a crash."""


def _extract_words(payload: object, where: str) -> list[str]:
    """Pull ``copy.words_to_avoid`` out of a parsed tokens document.

    Every shape failure raises ``LiveWordListUnavailable``: a tokens file that
    no longer carries the list is an unreadable surface, not an empty one."""
    if not isinstance(payload, dict):
        raise LiveWordListUnavailable(f"{where}: top level is not an object")
    copy_block = payload.get("copy")
    if not isinstance(copy_block, dict):
        raise LiveWordListUnavailable(f"{where}: 'copy' is absent or not an object")
    words = copy_block.get("words_to_avoid")
    if not isinstance(words, list) or not all(isinstance(word, str) for word in words):
        raise LiveWordListUnavailable(
            f"{where}: 'copy.words_to_avoid' is absent or not an array of strings"
        )
    if not words:
        raise LiveWordListUnavailable(f"{where}: 'copy.words_to_avoid' is empty")
    return [str(word) for word in words]


def fetch_live_words(
    repo: str, path: str, token: str | None, timeout: float = _TIMEOUT_SECONDS
) -> list[str]:
    """Fetch ``copy.words_to_avoid`` from the collection's tokens file.

    Raises ``LiveWordListUnavailable`` for every failure mode: transport
    error, non-200 response, unparseable JSON, or a missing/malformed list.
    Retries transport failures and 5xx responses up to ``_MAX_ATTEMPTS`` times
    with the ``_BACKOFF_SECONDS`` schedule; a 404 (or any other 4xx) is final
    and is not retried."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "skill-harness-words-to-avoid-drift-check",
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
            raise LiveWordListUnavailable(f"GitHub API returned HTTP {exc.code} for {url}") from exc
        except urllib.error.URLError as exc:
            if attempt < _MAX_ATTEMPTS - 1:
                last_error = exc
                time.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise LiveWordListUnavailable(
                f"transport error contacting {url}: {exc.reason}"
            ) from exc

        if status != 200:
            if status >= 500 and attempt < _MAX_ATTEMPTS - 1:
                last_error = RuntimeError(f"HTTP {status}")
                time.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise LiveWordListUnavailable(f"GitHub API returned HTTP {status} for {url}")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LiveWordListUnavailable(f"unparseable JSON from {url}: {exc}") from exc

        return _extract_words(payload, url)

    # Unreachable in practice (every branch above either returns or raises),
    # but keeps the function total for mypy --strict.
    raise LiveWordListUnavailable(f"exhausted {_MAX_ATTEMPTS} attempts against {url}") from (
        last_error
    )


def _default_fetch(repo: str, path: str, token: str | None) -> list[str]:
    """Module-level default fetcher bound to the real API. Kept separate from
    ``main`` so the injected-fetch seam never shadows a same-named parameter."""
    return fetch_live_words(repo, path, token)


def compare_word_lists(live: list[str] | None, vendored: list[str]) -> int:
    """Pure comparison over the canonical digests.

    Returns 0 (match), 1 (drift) or 2 (live unreadable, signalled by ``live is
    None``). Takes no I/O so it is exercised directly by tests. Order is part
    of the digest by construction: the collection publishes an ordered array,
    and a reordering is a change to the artifact both repositories read."""
    if live is None:
        return 2
    if canonical_word_list_digest(live) == canonical_word_list_digest(vendored):
        return 0
    return 1


def _print_result(
    code: int, live: list[str] | None, vendored: list[str], repo: str, path: str
) -> None:
    vendored_digest = canonical_word_list_digest(vendored)
    if code == 0:
        print("WORDS_TO_AVOID SYNC: PASS")
        print(f"words:  {len(vendored)}")
        print(f"sha256: {vendored_digest}")
        return
    if code == 1:
        assert live is not None
        added = [word for word in live if word not in vendored]
        removed = [word for word in vendored if word not in live]
        print("WORDS_TO_AVOID SYNC: DRIFT")
        print(f"live ({repo}:{path}):            {canonical_word_list_digest(live)}")
        print(f"vendored ({_MANIFEST_REL}):  {vendored_digest}")
        print(f"added upstream:   {added}")
        print(f"removed upstream: {removed}")
        print(
            f"repair: copy the live list into {_MANIFEST_REL}, recompute 'sha256' "
            "from it, and rewrite any prose the new words now refuse"
        )
        return
    print("WORDS_TO_AVOID SYNC: REFUSED")
    print(
        "the live word list could not be read; an unreadable live surface is a "
        "refusal to report, never a pass"
    )
    print(f"vendored ({_MANIFEST_REL}):  {vendored_digest}")


def main(
    argv: list[str] | None = None,
    fetch: Callable[[str, str, str | None], list[str]] | None = None,
) -> int:
    """Entry point. ``fetch`` is injectable so tests never touch the network;
    it defaults to ``fetch_live_words`` bound to ``GITHUB_TOKEN``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=_DEFAULT_REPO,
        help=f"owner/name of the collection that owns the list (default: {_DEFAULT_REPO})",
    )
    parser.add_argument(
        "--path",
        default=_DEFAULT_PATH,
        help=f"path to the tokens file inside that repo (default: {_DEFAULT_PATH})",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repo root holding the vendored manifest (default: this script's repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    try:
        vendored, recorded = read_word_list_manifest(root / _MANIFEST_REL)
    except WordListManifestError as exc:
        print("WORDS_TO_AVOID SYNC: REFUSED")
        print(f"the vendored manifest is unreadable: {exc}")
        return 2

    recomputed = canonical_word_list_digest(vendored)
    if recomputed != recorded:
        print("WORDS_TO_AVOID SYNC: REFUSED")
        print(
            f"{_MANIFEST_REL}: recorded sha256 {recorded} does not match {recomputed} "
            "recomputed from 'words'. The vendored copy disagrees with itself, so a "
            "comparison against the live list would report on the wrong list. "
            "scripts/drift_check.py DC-16 fails on this too."
        )
        return 2

    token = os.environ.get("GITHUB_TOKEN")
    active_fetch = fetch if fetch is not None else _default_fetch

    live: list[str] | None
    try:
        live = active_fetch(args.repo, args.path, token)
    except LiveWordListUnavailable:
        live = None

    code = compare_word_lists(live, vendored)
    _print_result(code, live, vendored, args.repo, args.path)
    return code


if __name__ == "__main__":
    sys.exit(main())
