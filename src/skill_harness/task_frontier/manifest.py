"""The frozen, versioned task-family manifest (spec #89).

A manifest is the pre-registration for one task family: what was measured,
against which frozen generator/oracle/fixture/harness/code, and which semantic
lineages belong to which phase. Nothing downstream may re-derive a lineage's
phase from anything else — `admit` reads it out of here once, at write time,
and the answer is stamped on the record forever.

#90 SCOPE — this loader carries a SUBSET of the manifest shape spec #89
specifies. It parses the identity, the freeze hashes, the phase partition and
`confirmation_attempt_budget`, and it REFUSES any key it does not carry rather
than dropping it: an operator who writes `hard_budget` into a manifest must not
be told it loaded when nothing registered it. The remaining fields (`skill`,
`claimed_domain`, `model_agent_pin`, `estimand`, `difficulty_definition`,
`lineage_generator_family_of`, `thresholds`, `expected_cost`, `hard_budget`,
`kill_conditions`) land with #92, which owns total manifest validation.

One #92 guard is here early and deliberately: a semantic lineage claimed by two
phases is refused at load. Accepting it would mean the tracer's own firewall was
already breached — last-writer-wins on the partition is the exact leak this unit
exists to prevent — so it cannot wait for a later ticket. It is tested here
(pass → induce → refuse) per #89's prove-the-rules-bite rule; the rest of #92's
guard set (unfrozen hash, semantic surrogacy, unassigned lineage, off-manifest
admission) is NOT built.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from skill_harness.storage.models import TaskFrontierArm, TaskFrontierPhase

# The seam's public names for the storage-layer enums. Re-exported rather than
# redefined so the SQL CHECK literals, the Pydantic write model and this
# interface are one definition — there is no second copy to drift.
Phase = TaskFrontierPhase
Arm = TaskFrontierArm

# Keys this loader carries. Anything else is refused (see the module docstring).
_KNOWN_KEYS: Final[frozenset[str]] = frozenset(
    {
        "task_family_id",
        "task_family_version",
        "frozen_hashes",
        "phase_partition",
        "confirmation_attempt_budget",
    }
)
_KNOWN_HASH_KEYS: Final[frozenset[str]] = frozenset(
    {"generator", "fixture", "oracle", "harness", "code"}
)


@dataclass(frozen=True)
class FrozenHashes:
    """The pre-treatment freeze: what the family was pinned to before any run.

    Locked BEFORE the first treatment observation so a skill's text cannot
    retrofit the task to flatter itself after the fact (spec #89, user story 2).
    #90 stores these; COMPARING an observation's fingerprints against them is
    #92's admission check and is not built.
    """

    generator: str
    fixture: str
    oracle: str
    harness: str
    code: str


@dataclass(frozen=True)
class TaskFamilyManifest:
    """A loaded, frozen manifest. Construct via `load_manifest`, never directly.

    `_phase_by_lineage` is a read-only mapping view rather than a plain dict:
    a frozen dataclass freezes the *binding*, not the dict behind it, and a
    mutable partition would make the "frozen freeze" claim false.

    It is deliberately private and there is deliberately no method that lists
    the lineages of a phase. Lineage ids for the walled-off phases are not
    something the interface hands out — with no way to obtain them, the by-id
    audit read cannot be turned into a way to walk calibration evidence.
    """

    task_family_id: str
    task_family_version: str
    frozen_hashes: FrozenHashes
    confirmation_attempt_budget: int
    _phase_by_lineage: Mapping[str, Phase]

    def phase_of(self, semantic_lineage_id: str) -> Phase | None:
        """Return the lineage's declared phase, or None if it is off-manifest."""
        return self._phase_by_lineage.get(semantic_lineage_id)


def _reject_unknown_keys(data: Mapping[str, Any], known: frozenset[str], where: str) -> None:
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(
            f"{where}: unrecognised key(s) {unknown} — this loader carries only "
            f"{sorted(known)}. Keys are refused rather than dropped so a manifest "
            "cannot appear to register a field that nothing read (the remaining "
            "spec-#89 manifest fields land with #92)."
        )


def _require(data: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise ValueError(f"{where}: missing required key {key!r}")
    return data[key]


def _require_str(data: Mapping[str, Any], key: str, where: str) -> str:
    value = _require(data, key, where)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: key {key!r} must be a non-empty string; got {value!r}")
    return value


def _load_frozen_hashes(raw: Any) -> FrozenHashes:
    if not isinstance(raw, Mapping):
        raise ValueError(f"manifest key 'frozen_hashes' must be a mapping; got {raw!r}")
    _reject_unknown_keys(raw, _KNOWN_HASH_KEYS, "frozen_hashes")
    return FrozenHashes(
        generator=_require_str(raw, "generator", "frozen_hashes"),
        fixture=_require_str(raw, "fixture", "frozen_hashes"),
        oracle=_require_str(raw, "oracle", "frozen_hashes"),
        harness=_require_str(raw, "harness", "frozen_hashes"),
        code=_require_str(raw, "code", "frozen_hashes"),
    )


def _load_partition(raw: Any) -> dict[str, Phase]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"manifest key 'phase_partition' must be a mapping; got {raw!r}")
    _reject_unknown_keys(raw, frozenset(member.value for member in Phase), "phase_partition")

    phase_by_lineage: dict[str, Phase] = {}
    for phase in Phase:
        lineages = raw.get(phase.value, ())
        if isinstance(lineages, str) or not isinstance(lineages, (list, tuple)):
            raise ValueError(
                f"phase_partition[{phase.value!r}] must be a list of lineage ids; got {lineages!r}"
            )
        for lineage in lineages:
            if not isinstance(lineage, str) or not lineage:
                raise ValueError(
                    f"phase_partition[{phase.value!r}] contains a non-string lineage id: "
                    f"{lineage!r}"
                )
            if lineage in phase_by_lineage:
                raise ValueError(
                    f"semantic lineage {lineage!r} is claimed by both "
                    f"{phase_by_lineage[lineage].value!r} and {phase.value!r} — a phase "
                    "partition must assign every lineage to exactly one phase, or the "
                    "calibration/effect firewall is already breached"
                )
            phase_by_lineage[lineage] = phase
    return phase_by_lineage


def load_manifest(data: Mapping[str, Any]) -> TaskFamilyManifest:
    """Parse and freeze a task-family manifest.

    :param data: The raw manifest mapping (as loaded from JSON/TOML/a fixture).
    :returns: A frozen `TaskFamilyManifest`.
    :raises ValueError: If a required key is absent or mistyped, if an
        unrecognised key is present (refused, never dropped), or if one semantic
        lineage is claimed by more than one phase.
    """
    _reject_unknown_keys(data, _KNOWN_KEYS, "manifest")

    budget = _require(data, "confirmation_attempt_budget", "manifest")
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise ValueError(
            f"manifest key 'confirmation_attempt_budget' must be an int; got {budget!r}"
        )

    return TaskFamilyManifest(
        task_family_id=_require_str(data, "task_family_id", "manifest"),
        task_family_version=_require_str(data, "task_family_version", "manifest"),
        frozen_hashes=_load_frozen_hashes(_require(data, "frozen_hashes", "manifest")),
        confirmation_attempt_budget=budget,
        _phase_by_lineage=MappingProxyType(
            _load_partition(_require(data, "phase_partition", "manifest"))
        ),
    )
