"""DC-16 internals: the vendored word list, the matcher, and the scan scope.

tests/test_drift_check.py drives ``scripts/drift_check.py`` exclusively as a
subprocess, by the seam ratified in spec #49. Three claims DC-16 makes cannot
be read off that surface, so they are tested here against the functions
directly:

1. The vendored digest is the canonical digest of the vendored array, computed
   the way ``MrBinnacle/skills`` computes it. If the two repositories
   canonicalize differently, the scheduled cross-repository check invents
   drift that is not there.
2. Every excluded file really carries a hit. An exclusion that hides nothing
   is an unearned carve-out, and the same discipline
   ``test_public_copy_exclusion_list_is_minimal`` applies to the public-copy
   scan.
3. The scanned set is EXACTLY the tracked markdown minus the declared
   exclusions. The row claims the tracked set, and both directions of that
   claim are measured against git's own list: a file the scan misses, and a
   file the scan reaches that no commit here publishes (#471).

``scripts/`` carries no ``__init__.py`` and is not a package, so the module is
loaded from its path -- the same seam
``tests/test_repo_description_check.py`` uses, and for the same reason.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST = _REPO_ROOT / "assets" / "words_to_avoid.json"


def _load_script(name: str, rel_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / rel_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec_module: @dataclass resolves a field annotation by
    # looking its defining module up in sys.modules, and a module that is not
    # there yet resolves to None -- an AttributeError inside dataclasses, at
    # import time, that reads like a bug in the script and is not one.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_drift_check = _load_script("drift_check_for_words", "scripts/drift_check.py")


def _dc16_row() -> Any:
    rows = [row for row in _drift_check.LIVE_ROWS if row.dc_id == "DC-16"]
    assert len(rows) == 1, "DC-16 is not registered in the contract table"
    return rows[0]


def _dc16_ban() -> Any:
    ban = _dc16_row().word_list_ban
    assert ban is not None
    return ban


def test_vendored_digest_is_the_canonical_digest_of_the_vendored_array() -> None:
    words, recorded = _drift_check.read_word_list_manifest(_MANIFEST)
    assert _drift_check.canonical_word_list_digest(words) == recorded


def test_canonical_digest_is_sha256_over_the_compact_json_array() -> None:
    """Pins the canonicalization itself, independently of the implementation.

    The collection digests the same array the same way; this test states that
    rule in one place so a change to it is a deliberate edit here rather than
    a silent divergence between two repositories."""
    words, _ = _drift_check.read_word_list_manifest(_MANIFEST)
    expected = hashlib.sha256(json.dumps(words, separators=(",", ":")).encode()).hexdigest()
    assert _drift_check.canonical_word_list_digest(words) == expected


def test_manifest_names_its_source_and_the_ruling() -> None:
    """A vendored copy with no provenance cannot be repaired by whoever finds
    it stale."""
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert payload["source"].startswith("MrBinnacle/skills@main:assets/tokens.json")
    assert "2026-09-06" in payload["ruling"]


@pytest.mark.parametrize(
    "text",
    [
        "we learn from this",
        "the door is unlocked",
        "yearning for a result",
        "an earnest reading",
        "curatorial judgement",
        "robustness testing",
        "a powerless argument",
    ],
)
def test_matcher_ignores_words_that_merely_contain_a_listed_one(text: str) -> None:
    words, _ = _drift_check.read_word_list_manifest(_MANIFEST)
    pattern = _drift_check.word_list_pattern(words)
    assert pattern.search(text) is None, text


@pytest.mark.parametrize(
    "text",
    [
        "the guard is load-bearing",
        "## Load-Bearing seams",
        "a curated watch",
        "skills that EARN their keep",
        "it earned its slot",
        "transcripts unlock the oracles",
    ],
)
def test_matcher_fires_on_the_listed_word_in_any_case(text: str) -> None:
    words, _ = _drift_check.read_word_list_manifest(_MANIFEST)
    pattern = _drift_check.word_list_pattern(words)
    assert pattern.search(text) is not None, text


def test_every_excluded_path_carries_a_hit() -> None:
    """Minimality. An excluded file that no longer carries a listed word has
    stopped needing the exclusion, and the entry goes."""
    words, _ = _drift_check.read_word_list_manifest(_MANIFEST)
    pattern = _drift_check.word_list_pattern(words)
    unnecessary = []
    for rel in _dc16_ban().excluded_paths:
        path = _REPO_ROOT / rel
        if not path.is_file():
            unnecessary.append(f"{rel} (file absent)")
            continue
        if not pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            unnecessary.append(rel)
    assert unnecessary == [], f"DC-16 exclusions hiding no current hit: {unnecessary}"


def _tracked_markdown() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("git is unavailable or this tree is not a repository")
    return [rel for rel in result.stdout.split("\0") if rel]


def test_scan_is_exactly_the_tracked_markdown_minus_the_exclusions() -> None:
    """The row claims every markdown file this repository TRACKS. This measures
    that claim against git's own list, in both directions.

    Both directions matter, and #471 is why. The assertion used to be
    one-directional -- every tracked file must be scanned, while the walk was
    allowed to reach more -- and that slack was exactly where the defect lived:
    the walk reached 261 markdown files inside a gitignored worktree and three
    inside a gitignored CLAUDE.md, and this test could not see any of it. An
    untracked file in the scan is now a failure, not licence."""
    ban = _dc16_ban()
    scanned = {
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _drift_check.iter_word_list_files(_REPO_ROOT, ban)
    }
    excluded = set(ban.excluded_paths)
    expected = {rel for rel in _tracked_markdown() if rel not in excluded}
    missed = sorted(expected - scanned)
    extra = sorted(scanned - expected)
    assert missed == [], f"tracked markdown outside the DC-16 scan: {missed}"
    assert extra == [], f"untracked or excluded markdown inside the DC-16 scan: {extra}"


def test_scan_selection_refuses_outside_a_repository(tmp_path: Path) -> None:
    """A tree git cannot describe is a refusal, never an empty clean scan.

    The alternative -- fall back to a filesystem walk -- would run a different
    check under the same row name, which is what #471 found DC-16 doing on
    every working clone."""
    inside_a_repo = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        cwd=str(tmp_path),
        check=False,
    )
    if inside_a_repo.returncode == 0:
        pytest.skip("the temp directory is itself inside a repository; the refusal cannot fire")
    (tmp_path / "note.md").write_text("the guard is load-bearing\n", encoding="utf-8")
    with pytest.raises(_drift_check.WordListSelectionError) as caught:
        _drift_check.iter_word_list_files(tmp_path, _dc16_ban())
    assert "cannot select the scanned set" in str(caught.value)


def test_the_live_tree_has_no_hit() -> None:
    """The end state the rewrite in #462 produced, asserted directly rather
    than only through the script's exit code."""
    words, _ = _drift_check.read_word_list_manifest(_MANIFEST)
    pattern = _drift_check.word_list_pattern(words)
    hits = []
    for path in _drift_check.iter_word_list_files(_REPO_ROOT, _dc16_ban()):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in pattern.finditer(line):
                hits.append(
                    f"{path.relative_to(_REPO_ROOT).as_posix()}:{lineno} {match.group(0)!r}"
                )
    assert hits == [], f"words_to_avoid hits in the tree: {hits}"


def test_manifest_word_list_matches_the_ban_the_pattern_builds() -> None:
    """The pattern is built from the manifest, so a word added to the file is
    a word the scan refuses -- no second list to keep in step."""
    words, _ = _drift_check.read_word_list_manifest(_MANIFEST)
    pattern = _drift_check.word_list_pattern(words)
    for word in words:
        assert pattern.fullmatch(word) is not None, word
    assert isinstance(pattern, re.Pattern)
