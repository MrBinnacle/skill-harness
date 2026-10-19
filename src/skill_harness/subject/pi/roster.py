"""Effective skill-roster construction for the Pi paired lane.

Apparatus validation owned by the adapter; it runs BEFORE any epoch launch
and never substitutes for the scientific pair validation downstream
(``subject/ingest.py::_validate_pair``). The contract it enforces is the
Full/Null symmetry rule:

    Full roster = baseline + {treatment}
    Null roster = baseline

with every baseline member byte-identical across arms, the treatment skill
present in exactly one arm, no duplicate names anywhere, and every member a
readable directory containing SKILL.md. Any violation raises
:class:`PiRosterError` — fail closed, no spend has happened yet.

Roster membership is verified HERE, from the filesystem the launcher will
mount; what the runtime actually presented is verified separately, per
epoch, from the captured ``systemPromptOptions.skills`` (parser.py). The
two checks answer different questions: "what was mounted" vs "what the
runtime reported as loaded".
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, NamedTuple

__all__ = ["PiRosterError", "RosterEntry", "build_roster"]


class PiRosterError(Exception):
    """Refusal: the requested Full/Null rosters cannot be constructed as
    specified — apparatus error, before any epoch runs."""


class RosterEntry(NamedTuple):
    """One verified roster member."""

    name: str
    path: Path
    skill_md_sha256: str


def _read_frontmatter_name(skill_md: Path) -> str | None:
    """The ``name:`` scalar from a SKILL.md frontmatter block, or None.

    Deliberately minimal: a roster check needs the declared name only to
    cross-check directory identity; malformed or missing frontmatter simply
    yields None and the directory name stands (matching Pi's own fallback:
    ``name = frontmatter.name || parentDirName``, dist/core/skills.js).
    """
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    for line in parts[1].splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            value = stripped[len("name:") :].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            return value or None
    return None


def _entry(skill_dir: Path) -> RosterEntry:
    resolved = skill_dir.resolve()
    if not resolved.is_dir():
        raise PiRosterError(f"roster member {skill_dir} is not a directory")
    skill_md = resolved / "SKILL.md"
    if not skill_md.is_file():
        raise PiRosterError(f"roster member {resolved} has no SKILL.md")
    try:
        content = skill_md.read_bytes()
    except OSError as exc:
        raise PiRosterError(f"roster member {resolved}: SKILL.md unreadable: {exc}") from exc
    if not content:
        raise PiRosterError(f"roster member {resolved}: SKILL.md is empty")
    declared = _read_frontmatter_name(skill_md)
    name = declared if declared is not None else resolved.name
    return RosterEntry(
        name=name, path=resolved, skill_md_sha256=hashlib.sha256(content).hexdigest()
    )


def build_roster(
    baseline_dirs: tuple[Path, ...],
    treatment_dir: Path | None,
    condition: Literal["full", "null"],
) -> tuple[RosterEntry, ...]:
    """Verify and return the effective roster for one arm, in flag order.

    Flag order is load-bearing: Pi renders ``<available_skills>`` in load
    order, so the launcher passes these paths to ``--skill`` in exactly this
    order in both arms; the treatment entry is appended LAST in the Full arm
    so the baseline occupies identical listing positions in both arms.

    :raises PiRosterError: duplicate names across members, a baseline
        directory whose name equals the treatment's (a collision Pi would
        resolve silently first-wins), or a treatment dir requested for the
        Null arm.
    """
    if condition == "null" and treatment_dir is not None:
        raise PiRosterError("the Null arm must not receive the treatment skill")
    if condition not in ("full", "null"):
        raise PiRosterError(f"condition must be 'full' or 'null', got {condition!r}")

    entries = [_entry(d) for d in baseline_dirs]
    if condition == "full":
        if treatment_dir is None:
            raise PiRosterError("the Full arm requires the treatment skill directory")
        treatment = _entry(treatment_dir)
        for entry in entries:
            if entry.name == treatment.name:
                raise PiRosterError(
                    f"baseline member {entry.path} collides with the treatment "
                    f"skill name {treatment.name!r}: Pi resolves name collisions "
                    "first-wins, so the mounted treatment would not be the one tested"
                )
            if entry.path == treatment.path:
                raise PiRosterError(
                    f"baseline already contains the treatment directory {entry.path}"
                )
        entries.append(treatment)

    seen: dict[str, Path] = {}
    for entry in entries:
        prior = seen.get(entry.name)
        if prior is not None:
            raise PiRosterError(f"duplicate skill name {entry.name!r}: {prior} and {entry.path}")
        seen[entry.name] = entry.path
    return tuple(entries)
