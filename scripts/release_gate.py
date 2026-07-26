"""Release gate — public-surface lockstep checks that block a stale release.

Why this exists: v0.2.1 (the first PyPI release, 2026-07-26) was tagged while
known-stale surfaces existed — the shipped wheel carried
``__version__ = "0.2.0"``, the README led with a v0.2.0 status banner and a
pip-from-git install path, and CHANGELOG ``[Unreleased]`` was never rolled.
The process failure was not any one literal: it was that NOTHING enforced
version/claims lockstep at tag time. This script is that enforcement.

Where it runs (blocked-by-default, not impossible — a maintainer can still
edit the workflows, and this script cannot see surfaces outside the repo,
e.g. an already-frozen PyPI description):

- ``ci.yml`` on every push/PR (early feedback; tag check self-skips).
- ``publish.yml`` as the first job of the release pipeline: the build and
  PyPI upload jobs depend on it, so a release of a stale tree fails before
  an artifact exists.

Checks (all must pass; failures are listed, not first-fail):

  G1  pyproject.toml version == skill_harness.__init__.__version__
  G2  CHANGELOG.md has a rolled ``## [X.Y.Z] - `` section for the current
      version (an entry under [Unreleased] alone does not count) and a
      ``[X.Y.Z]:`` compare-link reference.
  G3  README.md status banner names the current version (``Status: vX.Y.Z``).
  G4  README.md is PyPI-render-safe: no relative Markdown link targets and
      no relative ``src=``/``srcset=`` attributes (PyPI renders the README
      verbatim as the project description; relative targets 404 there).
  G5  Every ``uses:`` in .github/workflows/ is pinned to a full 40-hex
      commit SHA (mutable tag/branch refs are not provenance).
  G6  When running on a tag ref (GITHUB_REF_NAME=vX.Y.Z), the tag matches
      the pyproject version exactly.

Run locally: ``python scripts/release_gate.py`` from the repo root.
Exit code 0 = releasable; 1 = at least one surface is stale (each listed).
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def gate_versions_lockstep(errors: list[str]) -> str:
    """G1: pyproject and package __version__ agree; returns the version."""
    pyproject = tomllib.loads(_read("pyproject.toml"))
    version: str = pyproject["project"]["version"]

    init_text = _read("src/skill_harness/__init__.py")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', init_text, re.MULTILINE)
    if m is None:
        errors.append("G1: no __version__ in src/skill_harness/__init__.py")
    elif m.group(1) != version:
        errors.append(
            f"G1: version drift — pyproject.toml={version!r} but "
            f"src/skill_harness/__init__.py __version__={m.group(1)!r} "
            "(this exact drift shipped in the v0.2.1 wheel)"
        )
    return version


def gate_changelog_rolled(version: str, errors: list[str]) -> None:
    """G2: CHANGELOG has a rolled section + compare link for this version."""
    changelog = _read("CHANGELOG.md")
    section = re.compile(
        rf"^## \[{re.escape(version)}\] [-—] \d{{4}}-\d{{2}}-\d{{2}}", re.MULTILINE
    )
    if section.search(changelog) is None:
        errors.append(
            f"G2: CHANGELOG.md has no rolled '## [{version}] - YYYY-MM-DD' section — "
            "roll [Unreleased] before tagging"
        )
    if re.search(rf"^\[{re.escape(version)}\]:\s+http", changelog, re.MULTILINE) is None:
        errors.append(
            f"G2: CHANGELOG.md is missing the '[{version}]: <compare-url>' link reference"
        )


def gate_readme_status_banner(version: str, errors: list[str]) -> None:
    """G3: the README status banner names the released version."""
    readme = _read("README.md")
    if f"Status: v{version}" not in readme:
        banner = re.search(r"Status: v[\d.]+[0-9a-z]*", readme)
        found = f" (found {banner.group(0)!r})" if banner else ""
        errors.append(f"G3: README.md status banner does not say 'Status: v{version}'{found}")


def gate_readme_pypi_render_safe(errors: list[str]) -> None:
    """G4: README carries no relative targets (they 404 on the PyPI page)."""
    readme = _read("README.md")
    for lineno, line in enumerate(readme.splitlines(), start=1):
        for m in re.finditer(r"\]\(([^)]+)\)", line):
            target = m.group(1)
            if not target.startswith(("http://", "https://", "#")):
                errors.append(
                    f"G4: README.md:{lineno} relative link target {target!r} breaks on PyPI"
                )
        for m in re.finditer(r'(?:src|srcset)="([^"]+)"', line):
            if not m.group(1).startswith(("http://", "https://")):
                errors.append(
                    f"G4: README.md:{lineno} relative image ref {m.group(1)!r} breaks on PyPI"
                )


def gate_workflows_sha_pinned(errors: list[str]) -> None:
    """G5: every workflow action is pinned to a full commit SHA."""
    pinned = re.compile(r"^\s*-?\s*uses:\s*\S+@[0-9a-f]{40}(\s+#.*)?$")
    for wf in sorted((REPO / ".github" / "workflows").glob("*.yml")):
        for lineno, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), start=1):
            if re.match(r"^\s*-?\s*uses:", line) and pinned.match(line) is None:
                errors.append(
                    f"G5: {wf.name}:{lineno} action not SHA-pinned: {line.strip()!r} "
                    "(mutable refs are not provenance)"
                )


def gate_tag_matches(version: str, errors: list[str]) -> None:
    """G6: on a tag ref, the tag must be exactly v<version>."""
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    ref_type = os.environ.get("GITHUB_REF", "")
    if ref_type.startswith("refs/tags/"):
        if ref_name != f"v{version}":
            errors.append(
                f"G6: tag {ref_name!r} does not match pyproject version {version!r} "
                f"(expected 'v{version}')"
            )
    else:
        print(f"G6: not a tag ref ({ref_name or 'local run'}) — tag-match check self-skips.")


def main() -> int:
    errors: list[str] = []
    version = gate_versions_lockstep(errors)
    gate_changelog_rolled(version, errors)
    gate_readme_status_banner(version, errors)
    gate_readme_pypi_render_safe(errors)
    gate_workflows_sha_pinned(errors)
    gate_tag_matches(version, errors)

    if errors:
        print(f"RELEASE GATE: BLOCKED — {len(errors)} stale surface(s) at version {version}:")
        for e in errors:
            print(f"  FAIL  {e}")
        return 1
    print(f"RELEASE GATE: PASS — public surfaces in lockstep at version {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
