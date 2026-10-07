"""#733: the [Unreleased] section records the user-visible range since v0.3.0.

Criterion 2 pins that the stale commit-count sentence is gone: no [Unreleased]
text may contain ``133``. Criterion 3 pins every changed runtime floor and the
``geometry`` extra to the values ``pyproject.toml`` declares at the PR head —
the test reads ``pyproject.toml`` at run time, so a CHANGELOG that drifts from
the manifest fails here. Criterion 4 pins SERS 1.6.0 and 1.7.0 into the SERS
lines, each with a reader-facing sentence. Desired behaviour not named as a
numbered criterion: the 0.4.0 heading is not cut in this PR; the version PR
rolls the section.

``tests/test_glossary_rename_722.py`` separately pins that [Unreleased] still
announces the glossary rename (old path to GLOSSARY.md) in rename language.
This module does not restate that; it asserts only what #733 adds.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def _unreleased() -> str:
    text = _read("CHANGELOG.md")
    match = re.search(r"## \[Unreleased\](.*?)(?=\n## \[)", text, re.DOTALL)
    assert match is not None, "CHANGELOG.md must carry an [Unreleased] section"
    return match.group(1)


def _runtime_requirements() -> list[str]:
    data = tomllib.loads(_read("pyproject.toml"))
    project = data["project"]
    return list(project["dependencies"])


def _requirement_name(req: str) -> str:
    bare = req.split(";", 1)[0].strip()
    bare = bare.split("[", 1)[0].strip()
    return re.split(r"[<>=!~]", bare, maxsplit=1)[0].strip().lower()


def test_unreleased_carries_no_stale_commit_count() -> None:
    """Criterion 2: the 133-commit sentence is dropped, not corrected.

    The count at PR head is ``git rev-list --count v0.3.0..HEAD`` = 213, not
    133 and not 207. The preferred fix is to drop the sentence; this test
    fails on any residual count, whatever the number.
    """
    unreleased = _unreleased()
    assert "133" not in unreleased, (
        "[Unreleased] still carries the stale '133 commits' sentence; "
        "drop the count or state it at the PR head with the producing command"
    )


def test_unreleased_does_not_cut_the_0_4_0_heading() -> None:
    """Desired behaviour: the version PR rolls the section, not this one."""
    text = _read("CHANGELOG.md")
    assert not re.search(r"^## \[0\.4\.0\]", text, re.MULTILINE), (
        "CHANGELOG.md already carries a rolled ## [0.4.0] heading; "
        "#733 must leave [Unreleased] unrolled"
    )


def test_unreleased_records_every_changed_runtime_floor() -> None:
    """Criterion 3: each runtime floor in [Unreleased] matches pyproject.

    The acceptance text names anthropic>=1.8.0, but that figure was measured
    at origin/main=b48ee47. PR-head pyproject.toml declares anthropic>=1.11.0
    (bumped again in #727). The governing rule is the value as declared at the
    PR head, which is what this test reads.
    """
    unreleased = _unreleased()
    requirements = _runtime_requirements()
    assert requirements, "pyproject.toml [project.dependencies] is empty"

    floors = _changed_runtime_floors()
    assert floors, "expected at least one changed runtime floor since v0.3.0"

    for req in floors:
        name = _requirement_name(req)
        # CHANGELOG may wrap a long requirement across lines; match the
        # package name followed by the version token on the same logical line
        # by allowing whitespace inside the requirement.
        pattern = re.escape(name) + r">=\s*" + re.escape(_floor_version(req))
        assert re.search(pattern, unreleased), (
            f"[Unreleased] does not record the runtime floor {req!r} "
            f"(pattern {pattern!r}); pyproject.toml at the PR head declares it"
        )


def test_unreleased_records_the_geometry_extra() -> None:
    """Criterion 3: the new geometry extra appears with its playwright floor."""
    unreleased = _unreleased()
    data = tomllib.loads(_read("pyproject.toml"))
    extras = data["project"]["optional-dependencies"]
    assert "geometry" in extras, "pyproject.toml declares no [geometry] extra"
    geometry_reqs = list(extras["geometry"])
    assert geometry_reqs, "[geometry] extra is empty"
    assert "geometry" in unreleased, "[Unreleased] must name the geometry extra"
    for req in geometry_reqs:
        name = _requirement_name(req)
        version = _floor_version(req)
        pattern = re.escape(name) + r">=\s*" + re.escape(version)
        assert re.search(pattern, unreleased), (
            f"[Unreleased] does not record [geometry] requirement {req!r}"
        )


def test_unreleased_records_sers_1_6_0_and_1_7_0() -> None:
    """Criterion 4: every SERS version added since 0.3.0 is named.

    1.4.0 and 1.5.0 were already in [Unreleased]; this range added 1.6.0
    (#654) and 1.7.0 (#686). Each must appear in a SERS line with one
    sentence on what a receipt reader must handle.
    """
    unreleased = _unreleased()
    for version in ("1.6.0", "1.7.0"):
        assert version in unreleased, (
            f"[Unreleased] must record SERS {version} with a reader-facing line"
        )
    # Each version sits in a bullet that also names SERS, so a bare version
    # token elsewhere in the section does not satisfy the criterion.
    lines = unreleased.splitlines()
    for version in ("1.6.0", "1.7.0"):
        hits = [ln for ln in lines if version in ln and "SERS" in ln]
        assert hits, (
            f"[Unreleased] has no SERS line naming {version}; "
            "each SERS version added since 0.3.0 needs one line on what a "
            "receipt reader must handle"
        )


def test_sers_schema_enum_still_ends_at_1_7_0() -> None:
    """Companion pin: the schema enum the CHANGELOG lines describe."""
    schema = _read("docs/sers/sers.schema.json")
    data = __import__("json").loads(schema)
    enum = data["properties"]["sers_version"]["enum"]
    assert "1.6.0" in enum and "1.7.0" in enum, (
        f"sers_version enum must contain 1.6.0 and 1.7.0, found {enum}"
    )


def _floor_version(req: str) -> str:
    match = re.search(r">=\s*([0-9][0-9A-Za-z.]*)", req)
    assert match is not None, f"requirement {req!r} carries no >= floor"
    return match.group(1)


def _changed_runtime_floors() -> list[str]:
    """Runtime requirements whose declared floor moved since v0.3.0.

    Measured from ``git diff v0.3.0 HEAD -- pyproject.toml``:
    anthropic 1.2.0 -> 1.11.0, openai 2.41 -> 3.15.0, click 8.1 -> 8.5.0,
    scipy 1.11 -> 1.18.1, statsmodels 0.14 -> 0.15.0. tiktoken, pydantic and
    rich did not move. The test asserts against pyproject at run time rather
    than these literals, so a future floor bump without a CHANGELOG line fails
    here only when the floor itself is in this changed set — which is the
    set #733 is allowed to record.
    """
    floors = [
        "anthropic>=1.11.0",
        "openai>=3.15.0,<4",
        "click>=8.5.0",
        "scipy>=1.18.1",
        "statsmodels>=0.15.0",
    ]
    declared = {_requirement_name(r): r for r in _runtime_requirements()}
    out: list[str] = []
    for req in floors:
        name = _requirement_name(req)
        assert name in declared, f"pyproject.toml no longer declares {name}"
        # The CHANGELOG line must match what pyproject declares at run time,
        # not a frozen literal from the ticket.
        declared_req = declared[name]
        assert _floor_version(declared_req) == _floor_version(req), (
            f"pyproject declares {declared_req!r} but this test pins {req!r}; "
            "update the pin to the PR-head value"
        )
        out.append(declared_req)
    return out
