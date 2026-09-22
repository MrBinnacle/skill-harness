"""Pre-flight check: refuse a dependency bump an exact-pinned anchor cannot satisfy.

Dependabot groups coordinate releases that exist.  It cannot hold back a
follower whose anchor has nothing new to bump to, so a follower bump above
an exact-pinned anchor wastes the entire CI matrix before pip fails with
ResolutionImpossible at install time.

For each requirement the diff changes, this check reads the anchor's
published PyPI metadata and refuses when an anchor pins the changed package
with ``==`` at a version below the proposed one.  The probe is one read
per candidate pair::

    curl -s https://pypi.org/pypi/<anchor>/json

Network failure reaching the index is a refusal with a distinct message,
never a pass.

Usage::

    python scripts/check_dependency_anchor.py \\
        --requirements pyproject.toml \\
        --diff <(git diff HEAD~1 -- pyproject.toml)

Or in CI::

    python scripts/check_dependency_anchor.py \\
        --requirements pyproject.toml \\
        --diff <(git diff origin/main -- pyproject.toml)
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

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

PYPI_URL: Final[str] = "https://pypi.org/pypi/{package}/json"
REQUIREMENT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)\s*"
)


def parse_requirement(line: str) -> tuple[str, str] | None:
    """Parse ``package==version`` or ``package>=version`` from a requirement line.

    Returns ``(canonical_name, version_string)`` for lines that pin or bound
    a version, or ``None`` for comment lines, extras, or bare names.
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
    version specifier is used.
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
    is extracted.
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
    ``-`` is a removal; ``+`` is an addition.  ``old_version`` is ``None``
    when a requirement is added (no previous version).
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


def fetch_pypi_metadata(package: str) -> dict[str, object]:
    """Fetch package metadata from PyPI.

    Returns the parsed JSON on success.  Raises ``NetworkError`` on any
    failure reaching the index — a check that cannot read its input must
    not report a clean result.
    """
    url = PYPI_URL.format(package=package)
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


class NetworkError(Exception):
    """Raised when PyPI is unreachable."""


def check_exact_pin_constraint(
    requires_dist: list[str] | None,
    target_package: str,
    proposed_version: str,
) -> str | None:
    """Check whether any version constraint on *target_package* blocks *proposed_version*.

    Returns the constraint string (e.g. ``">=2.46.5,<2.47.0"``) if it blocks
    the proposed version, or ``None`` if no blocking constraint exists.
    """
    if requires_dist is None:
        return None
    target_normalized = target_package.lower().replace("-", "_")
    for req in requires_dist:
        match = REQUIREMENT_PATTERN.match(req.strip())
        if not match:
            continue
        req_name = match.group(1).lower().replace("-", "_")
        if req_name != target_normalized:
            continue
        rest = req.strip()[match.end() :].strip()
        # Strip trailing markers (extras, comments, semicolons)
        rest = re.split(r"[;#\[]", rest)[0].strip().rstrip(",")
        if not rest:
            continue
        try:
            spec = SpecifierSet(rest)
        except InvalidVersion:
            continue
        try:
            version = Version(proposed_version)
        except InvalidVersion:
            continue
        if version not in spec:
            return rest
    return None


def find_anchors_for_package(
    changed_package: str,
    current_requirements: dict[str, str],
) -> list[str]:
    """Find packages in *current_requirements* that might pin *changed_package*.

    Returns all package names as a candidate list.  The caller fetches
    metadata for each and checks ``requires_dist``.
    """
    return sorted(current_requirements.keys())


def check_anchors(
    changed_package: str,
    proposed_version: str,
    current_requirements: dict[str, str],
) -> list[dict[str, str]]:
    """Check whether any anchor pins *changed_package* below *proposed_version*.

    Returns a list of refusal dicts, each containing:
    - ``anchor``: the package doing the pinning
    - ``pin``: the ``==`` constraint that blocks the bump
    - ``proposed``: the version that was proposed
    """
    refusals: list[dict[str, str]] = []
    candidates = find_anchors_for_package(changed_package, current_requirements)
    for anchor in candidates:
        if anchor == changed_package:
            continue
        try:
            metadata = fetch_pypi_metadata(anchor)
        except NetworkError:
            raise
        if not metadata:
            continue
        info_raw = metadata.get("info", {})
        if not isinstance(info_raw, dict):
            continue
        info: dict[str, object] = info_raw
        requires_dist = info.get("requires_dist")
        if not isinstance(requires_dist, list):
            continue
        blocking_pin = check_exact_pin_constraint(requires_dist, changed_package, proposed_version)
        if blocking_pin is not None:
            refusals.append(
                {
                    "anchor": anchor,
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

    all_refusals: list[dict[str, str]] = []
    for package, (_old, new_version) in sorted(changes.items()):
        try:
            refusals = check_anchors(package, new_version, current_requirements)
        except NetworkError as exc:
            print(
                f"REFUSE: network error checking {package}: {exc}",
                file=sys.stderr,
            )
            return 1
        all_refusals.extend(refusals)

    if all_refusals:
        print("REFUSE: dependency bump blocked by exact-pinned anchor(s):")
        for r in all_refusals:
            print(
                f"  - anchor '{r['anchor']}' pins {r['anchor']}==... "
                f"with {r['pin']}; proposed {r['proposed']} exceeds the pin"
            )
        print(
            "\nNo published anchor satisfies the proposed version. "
            "Wait for the anchor to release a compatible version, or "
            "bump the anchor first.",
            file=sys.stderr,
        )
        return 1

    print("PASS: no exact-pinned anchor blocks the proposed bump(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
