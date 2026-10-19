"""words_to_avoid drift check tests.

No test in this file touches the network: ``main``'s ``fetch`` argument is
always a stub callable, never the real ``fetch_live_words``. That is the point
of the injectable-fetch seam in ``scripts/words_to_avoid_drift_check.py`` --
CI has no live network dependency in the test suite, only in the scheduled
workflow that runs the script for real. Same seam, same reason, as
``tests/test_repo_description_check.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str, rel_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / rel_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before exec_module: the module imports drift_check, whose
    # dataclasses resolve their annotations through sys.modules.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_check = _load_script("words_to_avoid_drift_check", "scripts/words_to_avoid_drift_check.py")
LiveWordListUnavailable = _check.LiveWordListUnavailable
compare_word_lists = _check.compare_word_lists
canonical_word_list_digest = _check.canonical_word_list_digest

_VENDORED: list[str] = json.loads(
    (_REPO_ROOT / "assets" / "words_to_avoid.json").read_text(encoding="utf-8")
)["words"]


# ---------------------------------------------------------------------------
# The pure comparison
# ---------------------------------------------------------------------------


def test_identical_lists_match() -> None:
    assert compare_word_lists(list(_VENDORED), list(_VENDORED)) == 0


def test_added_word_upstream_is_drift() -> None:
    assert compare_word_lists([*_VENDORED, "delightful"], list(_VENDORED)) == 1


def test_removed_word_upstream_is_drift() -> None:
    assert compare_word_lists(_VENDORED[:-1], list(_VENDORED)) == 1


def test_reordering_is_drift() -> None:
    """Order is part of the digest by construction. The collection publishes
    an ordered array, and a reordering changes the artifact both repositories
    read, so it is reported rather than normalized away."""
    reordered = list(reversed(_VENDORED))
    assert compare_word_lists(reordered, list(_VENDORED)) == 1


def test_unreadable_live_list_is_a_refusal_not_a_pass() -> None:
    assert compare_word_lists(None, list(_VENDORED)) == 2


# ---------------------------------------------------------------------------
# main() through the injected fetch
# ---------------------------------------------------------------------------


def test_main_passes_against_the_live_list(capsys: pytest.CaptureFixture[str]) -> None:
    code = _check.main([], lambda repo, path, token: list(_VENDORED))
    assert code == 0
    out = capsys.readouterr().out
    assert "WORDS_TO_AVOID SYNC: PASS" in out
    assert canonical_word_list_digest(list(_VENDORED)) in out


def test_main_reports_drift_with_the_added_and_removed_words(
    capsys: pytest.CaptureFixture[str],
) -> None:
    live = [word for word in _VENDORED if word != "robust"] + ["delightful"]
    code = _check.main([], lambda repo, path, token: live)
    assert code == 1
    out = capsys.readouterr().out
    assert "WORDS_TO_AVOID SYNC: DRIFT" in out
    assert "delightful" in out
    assert "robust" in out
    assert "repair:" in out


def test_main_refuses_when_the_live_list_cannot_be_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(repo: str, path: str, token: str | None) -> list[str]:
        raise LiveWordListUnavailable("GitHub API returned HTTP 404")

    code = _check.main([], _raise)
    assert code == 2
    out = capsys.readouterr().out
    assert "WORDS_TO_AVOID SYNC: REFUSED" in out
    assert "never a pass" in out


def test_main_refuses_when_the_vendored_manifest_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _check.main(["--root", str(tmp_path)], lambda repo, path, token: list(_VENDORED))
    assert code == 2
    assert "WORDS_TO_AVOID SYNC: REFUSED" in capsys.readouterr().out


def test_main_refuses_when_the_vendored_digest_disagrees_with_its_own_array(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The vendored copy disagreeing with itself is not drift against the
    collection -- it is an unreadable expectation, so the comparison is
    refused rather than run against the wrong list."""
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "words_to_avoid.json").write_text(
        json.dumps({"words": list(_VENDORED), "sha256": "0" * 64}), encoding="utf-8"
    )
    code = _check.main(["--root", str(tmp_path)], lambda repo, path, token: list(_VENDORED))
    assert code == 2
    out = capsys.readouterr().out
    assert "WORDS_TO_AVOID SYNC: REFUSED" in out
    assert "recomputed from 'words'" in out


# ---------------------------------------------------------------------------
# Shape failures in the fetched document are refusals, never empty lists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"copy": []},
        {"copy": {}},
        {"copy": {"words_to_avoid": []}},
        {"copy": {"words_to_avoid": "earn"}},
        {"copy": {"words_to_avoid": ["earn", 7]}},
    ],
)
def test_malformed_live_document_raises_unavailable(payload: object) -> None:
    with pytest.raises(LiveWordListUnavailable):
        _check._extract_words(payload, "test")


def test_well_formed_live_document_yields_the_list() -> None:
    payload = {"copy": {"words_to_avoid": ["earn", "robust"], "words_to_prefer": ["measured"]}}
    assert _check._extract_words(payload, "test") == ["earn", "robust"]


def test_transport_failure_becomes_a_refusal_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry lane ends in LiveWordListUnavailable, which main() turns into
    exit 2. Sleep is stubbed so the backoff schedule costs no wall clock."""

    def _always_fails(request: object, timeout: float = 0.0) -> object:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(_check.urllib.request, "urlopen", _always_fails)
    monkeypatch.setattr(_check.time, "sleep", lambda seconds: None)
    with pytest.raises(LiveWordListUnavailable):
        _check.fetch_live_words("owner/name", "assets/tokens.json", None)
