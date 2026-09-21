"""Declared arms — the composition-study unit of comparison (#554).

A declared-arm run's unit of comparison is a named arm: a whole prompt
assembly, not one clause of one card. Each arm resolves to a distinct
system-prompt assembly built from the base system prompt plus the skill bodies
the arm includes. An arm's bodies are either inline text or a SKILL.md named by
path (a sibling skill's body swappable in; frontmatter stripped, body
verbatim).

This module is data + resolution only. It never calls a model. The runner
(samples), the renderer (block layout) and storage (arm_samples, migration
1200) own the rest.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skill_harness.ablation.render import ConditionRenderer
from skill_harness.extractor.errors import MalformedSkillError
from skill_harness.extractor.parser import parse_skill_file
from skill_harness.storage.models import ARM_NAME_PATTERN, is_valid_arm_name


class ArmSpecError(ValueError):
    """Raised when a declared-arm set is malformed (#554 AC1).

    Covers: an empty set, ill-formed or duplicate arm names, a body path that
    cannot be read, a blank inline body, and two arms that resolve to the same
    assembly. Raised before any run row is written, so a refused declaration
    spends nothing.
    """


@dataclass(frozen=True)
class ArmSpec:
    """One declared arm of a run: a name and the bodies its assembly includes.

    Fields
    ------
    name : str
        Declared arm name. Must match ``ARM_NAME_PATTERN`` (lowercase slug) and
        be unique across the run's declared set. Receipts carry these names in
        ``subject_identity.arms``.
    body_texts : tuple[str, ...]
        Inline body texts, verbatim, in declared order.
    skill_body_paths : tuple[str, ...]
        Paths to SKILL.md files whose BODY text joins the assembly, in declared
        order, read after the inline texts. Frontmatter is metadata and is not
        sent; the body is passed verbatim (#554 AC2).
    """

    name: str
    body_texts: tuple[str, ...] = ()
    skill_body_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArmAssembly:
    """One declared arm resolved to its wire prompt shape."""

    name: str
    system_text: str
    system_blocks: list[dict[str, Any]]


def validate_arm_specs(arms: Sequence[ArmSpec]) -> None:
    """Refuse a malformed declared-arm set before anything is resolved.

    :raises ArmSpecError: empty set, ill-formed or duplicate names.
    """
    if not arms:
        raise ArmSpecError(
            "a declared-arm run must declare at least one arm; an empty arm set "
            "declares no unit of comparison"
        )
    seen: set[str] = set()
    for arm in arms:
        if not is_valid_arm_name(arm.name):
            raise ArmSpecError(
                f"arm name {arm.name!r} is not a valid declared-arm name "
                f"(must match {ARM_NAME_PATTERN})"
            )
        if arm.name in seen:
            raise ArmSpecError(f"duplicate arm name {arm.name!r} in the declared set")
        seen.add(arm.name)


def resolve_arm_assemblies(
    arms: Sequence[ArmSpec],
    renderer: ConditionRenderer,
) -> dict[str, ArmAssembly]:
    """Resolve every declared arm to its system-prompt assembly.

    Bodies are read once per path. Each assembly is the base system block plus
    one text block per body (inline texts first, then path-read bodies, in
    declared order). Two arms that resolve to the same assembly are refused: a
    declared-arm run contrasts distinct assemblies, so a duplicate would spend
    the budget twice on one condition.

    :returns: name -> ArmAssembly, in declared order.
    :raises ArmSpecError: malformed set, unreadable body path, blank body, or
        two arms resolving to the same assembly.
    """
    validate_arm_specs(arms)
    assemblies: dict[str, ArmAssembly] = {}
    body_cache: dict[str, str] = {}
    for arm in arms:
        texts = [t for t in arm.body_texts]
        for text in texts:
            if not text.strip():
                raise ArmSpecError(
                    f"arm {arm.name!r} declares a blank inline body; an empty text "
                    "block would be refused at the wire"
                )
        for path in arm.skill_body_paths:
            key = str(path)
            if key not in body_cache:
                try:
                    parsed = parse_skill_file(Path(path))
                except (OSError, MalformedSkillError) as exc:
                    raise ArmSpecError(
                        f"arm {arm.name!r} body path {key!r} cannot be read as a SKILL.md: {exc}"
                    ) from exc
                body_cache[key] = parsed.body
            texts.append(body_cache[key])
        rendered = renderer.render_arm_assembly(texts)
        assembly = ArmAssembly(
            name=arm.name,
            system_text=str(rendered["system_text"]),
            system_blocks=list(rendered["system_blocks"]),
        )
        for prior_name, prior in assemblies.items():
            if prior.system_blocks == assembly.system_blocks:
                raise ArmSpecError(
                    f"arms {prior_name!r} and {arm.name!r} resolve to the same "
                    "system-prompt assembly; a declared-arm run needs distinct "
                    "assemblies to contrast"
                )
        assemblies[arm.name] = assembly
    return assemblies


def arm_to_json_dict(arm: ArmSpec) -> dict[str, Any]:
    """Serialize an ArmSpec for runs.config_json."""
    return {
        "name": arm.name,
        "body_texts": list(arm.body_texts),
        "skill_body_paths": list(arm.skill_body_paths),
    }


def arm_from_json_dict(d: Mapping[str, Any]) -> ArmSpec:
    """Deserialize an ArmSpec from runs.config_json."""
    return ArmSpec(
        name=str(d["name"]),
        body_texts=tuple(str(t) for t in d.get("body_texts", ())),
        skill_body_paths=tuple(str(p) for p in d.get("skill_body_paths", ())),
    )


# ---------------------------------------------------------------------------
# Factorial designs (#554 AC4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmLevel:
    """One level of one factor: the bodies present when that level is active."""

    label: str
    body_texts: tuple[str, ...] = ()
    skill_body_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArmFactor:
    """One crossed factor of a factorial design: a name and its levels."""

    name: str
    levels: tuple[ArmLevel, ...]


def cross_factorial(factors: Sequence[ArmFactor]) -> tuple[ArmSpec, ...]:
    """Expand crossed factors into the full factorial arm set (#554 AC4).

    The cartesian product of the factor levels, in factor order, is the
    declared arm set: a two-factor two-level design yields four arms, so a
    2x2 factorial is one data declaration and no runner edit. Arm names are
    composed from the design itself: ``factor_label`` fragments joined by
    ``__`` in factor order (e.g. ``parent_present__specialist_absent``), so a
    receipt reader can read the design off the arm names.

    :raises ArmSpecError: any composed arm name is not a valid declared-arm
        name, or the design composes duplicate names.
    """
    specs: list[ArmSpec] = []
    for combo in itertools.product(*(f.levels for f in factors)):
        name_parts: list[str] = []
        texts: list[str] = []
        paths: list[str] = []
        for factor, level in zip(factors, combo, strict=True):
            name_parts.append(f"{factor.name}_{level.label}")
            texts.extend(level.body_texts)
            paths.extend(level.skill_body_paths)
        specs.append(
            ArmSpec(
                name="__".join(name_parts),
                body_texts=tuple(texts),
                skill_body_paths=tuple(paths),
            )
        )
    validate_arm_specs(specs)
    return tuple(specs)
