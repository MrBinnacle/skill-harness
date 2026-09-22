"""Pre-flight check: refuse a dependency bump an exact-pinned anchor cannot satisfy.

Dependabot groups coordinate releases that exist.  It cannot hold back a
follower whose anchor has nothing new to bump to, so a follower bump above
an exact-pinned anchor wastes the entire CI matrix before pip fails with
``ResolutionImpossible`` at install time.

Some pip pairs are exact-pinned: every ``pydantic`` release pins its core
with ``==``, so ``pydantic-core`` can never move ahead of its anchor.
Dependabot bumps the follower anyway when the follower has a newer release,
and pip then fails at install time.  Two occurrences in twenty-eight days:
2026-08-17 (``pydantic-core`` 2.46.4 -> 2.48.0) and 2026-09-14 (#549,
``pydantic-core`` 2.46.5 -> 2.49.0). One PyPI read at the declared
``pydantic`` version settles it: that version pins
``pydantic-core==2.46.5``, which is what this repository already pins in
``requirements-ci.txt``.

For each requirement the diff changes, this check reads each candidate
anchor's published PyPI metadata at the version the constraints file
declares. It refuses when that anchor pins the changed package with ``==``
at a version below the proposed one. The probe is one read per candidate
anchor::

    curl -s https://pypi.org/pypi/<anchor>/<declared-version>/json

then ``info.requires_dist`` is compared against the proposed version.  The
anchor relationship is discovered from published metadata, not from a
hand-maintained list of known pairs, because ``pydantic`` is not the only
split package that pins with ``==``.

Network failure reaching the index is a refusal with a distinct message,
never a pass: a check that cannot read its input must not report a clean
result.

Usage in CI (against the exact-pinned CI constraints file, where the
``pydantic`` / ``pydantic-core`` ``==`` pins live)::

    python scripts/check_dependency_anchor.py \\
        --requirements requirements-ci.txt \\
        --diff /tmp/dep-anchor.diff
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final

from packaging.version import InvalidVersion, Version

PYPI_URL: Final[str] = "https://pypi.org/pypi/{package}/{version}/json"
REQUIREMENT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)\s*"
)
EXACT_PIN_PATTERN: Final[re.Pattern[str]] = re.compile(r"^==\s*([^\s,]+)")


class NetworkError(Exception):
    """Raised when PyPI is unreachable."""


def parse_requirement(line: str) -> tuple[str, str] | None:
    """Parse ``package==version`` (or any ``<op>version``) from a requirement line.

    Returns ``(canonical_name, version_string)`` for lines that pin or bound a
    version, or ``None`` for comment lines, option lines, extras, or bare names.
    The canonical name is lowercased with hyphens folded to underscores.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    match = REQUIREMENT_PATTERN.match(stripped)
    if not match:
        return None
    name = match.group(1)
    rest = stripped[match.end() :].strip()
    version_match = re.match(r"[=!<>~]=?\s*([^\s,;#\[]+)", rest)
    if not version_match:
        return None
    return name.lower().replace("-", "_"), version_match.group(1)


def parse_requirements_file(path: Path) -> dict[str, str]:
    """Parse a requirements file into ``{canonical_name: version_string}``.

    Handles ``package==version``, ``package>=version``, and comment lines.
    For lines with multiple specifiers (e.g. ``package>=1,<2``), the first
    version specifier is used; only the name matters for anchor discovery.
    """
    requirements: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_requirement(line)
        if parsed is not None:
            name, version = parsed
            requirements[name] = version
    return requirements


def parse_pyproject_requirements(path: Path) -> dict[str, str]:
    """Parse ``[project.dependencies]`` from a pyproject.toml.

    Reads the raw lines between ``dependencies = [`` and the closing ``]``.
    Each non-comment line is a requirement string; the first version specifier
    is extracted.  The exact-pinned CI constraints live in ``requirements-ci.txt``,
    not here, but this parser keeps the check usable against either surface.
    """
    text = path.read_text(encoding="utf-8")
    in_deps = False
    deps: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if "dependencies" in stripped and "=" in stripped and "[" in stripped:
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("]"):
                break
            if stripped.startswith("#") or not stripped:
                continue
            cleaned = stripped.strip('",')
            parsed = parse_requirement(cleaned)
            if parsed is not None:
                name, version = parsed
                deps[name] = version
    return deps


def parse_diff(diff_text: str) -> dict[str, tuple[str | None, str]]:
    """Parse a unified diff into ``{package: (old_version, new_version)}``.

    Only lines touching a requirement are considered.  A line starting with
    ``-`` is a removal; ``+`` is an addition.  ``old_version`` is ``None`` when a
    requirement is added (no previous version).  Unchanged lines are dropped.
    """
    changes: dict[str, tuple[str | None, str]] = {}
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("-") and not line.startswith("--"):
            parsed = parse_requirement(line[1:])
            if parsed is not None:
                name, version = parsed
                if name not in changes:
                    changes[name] = (version, version)
                else:
                    old, _ = changes[name]
                    changes[name] = (old, version)
        elif line.startswith("+") and not line.startswith("+++"):
            parsed = parse_requirement(line[1:])
            if parsed is not None:
                name, version = parsed
                if name in changes:
                    old, _ = changes[name]
                    changes[name] = (old, version)
                else:
                    changes[name] = (None, version)
    return {k: v for k, v in changes.items() if v[1] != v[0] or v[0] is None}


def fetch_pypi_metadata(package: str, version: str) -> dict[str, object]:
    """Fetch metadata for the declared *package* version from PyPI.

    Returns the parsed JSON on success, or ``{}`` for a 404 (a package PyPI does
    not know about cannot be an anchor).  Raises ``NetworkError`` on any other
    failure reaching the index -- a check that cannot read its input must not
    report a clean result.
    """
    url = PYPI_URL.format(package=package, version=version)
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data: dict[str, object] = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        raise NetworkError(f"HTTP {exc.code} fetching {url}: {exc}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise NetworkError(f"network error fetching {url}: {exc}") from exc


def check_exact_pin_constraint(
    requires_dist: list[str] | None,
    target_package: str,
    proposed_version: str,
) -> str | None:
    """Return the ``==`` pin that blocks *proposed_version*, or ``None``.

    The check is exact-pin only: it refuses when an anchor pins the changed
    package with ``==`` at a version *below* the proposed one, which is the
    shape that makes pip raise ``ResolutionImpossible``.  A range cap or a
    lower bound is out of scope -- the dependabot group coordinates ranges,
    and the defect this check exists for is the ``==`` anchor that has nothing
    new to bump to.  Returns the blocking ``==<version>`` string, or ``None``
    when no ``==`` pin on *target_package* is below *proposed_version*.
    """
    if requires_dist is None:
        return None
    target = target_package.lower().replace("-", "_")
    try:
        proposed = Version(proposed_version)
    except InvalidVersion:
        return None
    for req in requires_dist:
        match = REQUIREMENT_PATTERN.match(req.strip())
        if not match:
            continue
        if match.group(1).lower().replace("-", "_") != target:
            continue
        rest = req.strip()[match.end() :].strip()
        # Drop extras, markers and comments; keep the specifier list.
        rest = re.split(r"[;#\[]", rest)[0].strip().rstrip(",")
        for clause in rest.split(","):
            pin_match = EXACT_PIN_PATTERN.match(clause.strip())
            if not pin_match:
                continue
            try:
                pinned = Version(pin_match.group(1))
            except InvalidVersion:
                continue
            if proposed > pinned:
                return f"=={pin_match.group(1)}"
    return None


def collect_anchor_metadata(
    current_requirements: dict[str, str],
) -> dict[str, dict[str, object]]:
    """Fetch metadata for every declared candidate anchor version, once.

    A candidate anchor is any package in *current_requirements*: the anchor
    relationship is discovered from published ``requires_dist`` rather than
    from a hand-maintained list of known pairs.  Fetching each candidate once
    (rather than once per changed package) keeps the probe at one read per
    anchor and minimises the surface on which a network failure can refuse a
    clean run.  Raises ``NetworkError`` on the first unreachable anchor.
    """
    metadata: dict[str, dict[str, object]] = {}
    for anchor, version in sorted(current_requirements.items()):
        fetched = fetch_pypi_metadata(anchor, version)
        if fetched:
            metadata[anchor] = fetched
    return metadata


def check_anchors(
    changed_package: str,
    proposed_version: str,
    anchor_metadata: dict[str, dict[str, object]],
) -> list[dict[str, str]]:
    """Check whether any anchor pins *changed_package* with ``==`` below *proposed*.

    Returns a list of refusal dicts, each carrying the ``anchor``, the changed
    ``package``, the blocking ``pin`` (``==<version>``) and the ``proposed``
    version.  The changed package is never checked against itself.
    """
    refusals: list[dict[str, str]] = []
    for anchor, metadata in anchor_metadata.items():
        if anchor == changed_package:
            continue
        info_raw = metadata.get("info", {})
        if not isinstance(info_raw, dict):
            continue
        requires_dist = info_raw.get("requires_dist")
        if not isinstance(requires_dist, list):
            continue
        blocking_pin = check_exact_pin_constraint(requires_dist, changed_package, proposed_version)
        if blocking_pin is not None:
            refusals.append(
                {
                    "anchor": anchor,
                    "package": changed_package,
                    "pin": blocking_pin,
                    "proposed": proposed_version,
                }
            )
    return refusals


def main(argv: list[str] | None = None) -> int:
    """Entry point.  Returns 0 on pass, 1 on refusal."""
    parser = argparse.ArgumentParser(
        description="Refuse a dependency bump an exact-pinned anchor cannot satisfy.",
    )
    parser.add_argument(
        "--requirements",
        required=True,
        help="path to the requirements file (pyproject.toml or requirements*.txt)",
    )
    parser.add_argument(
        "--diff",
        required=True,
        help="path to the unified diff (or - for stdin)",
    )
    args = parser.parse_args(argv)

    req_path = Path(args.requirements)
    if not req_path.exists():
        print(f"REFUSE: requirements file not found: {req_path}", file=sys.stderr)
        return 1

    if req_path.name == "pyproject.toml":
        current_requirements = parse_pyproject_requirements(req_path)
    else:
        current_requirements = parse_requirements_file(req_path)

    if args.diff == "-":
        diff_text = sys.stdin.read()
    else:
        diff_path = Path(args.diff)
        if not diff_path.exists():
            print(f"REFUSE: diff file not found: {diff_path}", file=sys.stderr)
            return 1
        diff_text = diff_path.read_text(encoding="utf-8")

    changes = parse_diff(diff_text)
    if not changes:
        print("PASS: no dependency changes detected in diff")
        return 0

    try:
        anchor_metadata = collect_anchor_metadata(current_requirements)
    except NetworkError as exc:
        print(f"REFUSE: network error reaching the index: {exc}", file=sys.stderr)
        return 1

    all_refusals: list[dict[str, str]] = []
    for package, (_old, new_version) in sorted(changes.items()):
        all_refusals.extend(check_anchors(package, new_version, anchor_metadata))

    if all_refusals:
        print("REFUSE: dependency bump blocked by an exact-pinned anchor:", file=sys.stderr)
        for r in all_refusals:
            print(
                f"  - anchor '{r['anchor']}' pins '{r['package']}' at {r['pin']}; "
                f"proposed '{r['proposed']}' is above the pin.",
                file=sys.stderr,
            )
        print(
            "No published anchor satisfies the proposed version. "
            "Wait for a compatible anchor release, or bump the anchor first.",
            file=sys.stderr,
        )
        return 1

    print("PASS: no exact-pinned anchor blocks the proposed bump(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
