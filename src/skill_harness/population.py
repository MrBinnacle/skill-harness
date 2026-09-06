"""Population integrity for enumeration-driven controls (#453).

An enumeration-driven control discovers its own inputs -- it globs a directory,
walks a tree, or reads a register -- and then submits what it found to a
detector. Such a control can execute perfectly against the wrong universe: the
assertion is strong, the fixture is sound, and the answer is still
uninterpretable, because the set of cases that reached the detector was not the
set the control was supposed to analyse.

    negative control present   !=   negative control exercised

This module makes that set explicit, so a control can state which cases it
analysed and refuse to report an object-level result when it cannot establish
them as the declared cases.

The validity lattice this sits in
---------------------------------
::

    SOURCE / INPUT INTEGRITY
            v
    POPULATION INTEGRITY      <- this module
            v
    EXECUTION INTEGRITY
            v
    RESULT VALIDITY
            v
    CLAIM VALIDITY

Each layer gates the one above it, which yields the rule this module enforces:
**a downstream result cannot repair an upstream validity failure.** A perfect
assertion cannot repair an incomplete population. That is why :func:`interpret`
discards the detector's own outcome when the population is invalid rather than
combining the two.

The third verdict, and why it is not a FAIL
-------------------------------------------
A population failure is reported as ``UNINTERPRETABLE``, never as ``PASS`` and
never as an ordinary ``FAIL``::

    population_valid = false   ->   verdict = UNINTERPRETABLE     (correct)
    population_valid = false   ->   verdict = PASS                (the defect)
    population_valid = false   ->   verdict = FAIL                (a false finding)

``FAIL`` is wrong for the same reason ``PASS`` is: both are object-level claims
about the subject, and neither is available when the analysed universe is
unknown. This is the discipline already applied one layer up by
``ClauseStatus.UNMEASURED`` and ``KeepCutVerdict.CANT_TELL_YET``, which refuse
to interpret rather than manufacture a result; ``UNINTERPRETABLE`` is that rule
one layer down.

A detector saying "no defect found in the cases I received" may not become "no
defect exists" unless the system proves it received the complete declared
population.

Digest canonicalisation, specified rather than assumed
------------------------------------------------------
``population_digest`` is SHA-256 over::

    "population-v1\\n" + json.dumps(sorted(ids), ensure_ascii=False, separators=(",", ":"))

encoded UTF-8. Four properties, each chosen against a way the digest could
otherwise disagree between two honest runs of the same population:

- **Sorted.** Enumeration order -- ``glob`` order, filesystem order, dict
  insertion order -- must not change the digest. Only membership may.
- **JSON-encoded, not joined by a separator.** A separator-joined encoding is
  not injective: an identifier containing the separator makes two different
  populations hash the same. JSON escaping makes the encoding injective for
  every string.
- **Version-prefixed.** A future change to the canonicalisation is then a
  different digest by construction, rather than a silent collision with a
  digest computed under the old rule.
- **``ensure_ascii=False`` with an explicit UTF-8 encode.** The bytes hashed do
  not depend on the platform's default encoding.

Identifiers are opaque strings and the caller owns their platform stability.
For filesystem populations use :func:`posix_relative_ids`, which is the one
correct implementation of the path case: it makes paths relative to a root and
emits ``/`` separators, so a population enumerated on Windows and the same
population enumerated on Linux produce the same digest.

Duplicate identifiers are refused rather than de-duplicated. A duplicate means
the enumeration counted a case twice, and silently collapsing it would hide the
very defect a population record exists to surface.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

__all__ = [
    "DIGEST_VERSION",
    "PopulationInvalidError",
    "PopulationRecord",
    "PopulationVerdict",
    "UninterpretableSubReason",
    "build_population_record",
    "interpret",
    "population_digest",
    "posix_relative_ids",
    "require_valid_population",
]

#: Prefix over which :func:`population_digest` hashes. Changing the
#: canonicalisation requires changing this, so an old digest and a new one
#: cannot silently agree.
DIGEST_VERSION = "population-v1"


class PopulationVerdict(StrEnum):
    """The verdict an enumeration-driven control may report.

    ``UNINTERPRETABLE`` is not a severity between ``PASS`` and ``FAIL``. It is a
    refusal to make an object-level claim at all.
    """

    # S105 is a wordlist false positive: "PASS" is a verdict, not a credential.
    PASS = "PASS"  # noqa: S105
    FAIL = "FAIL"
    UNINTERPRETABLE = "UNINTERPRETABLE"


class UninterpretableSubReason(StrEnum):
    """Why a control refused to interpret its own result."""

    POPULATION_INVALID = "population_invalid"


@dataclass(frozen=True)
class PopulationRecord:
    """The cases a control actually submitted to its detector, and their identity.

    ``declared_*`` fields are ``None`` when the control ran without a
    declaration. That is a recorded population, not a validated one: the record
    then says what was analysed and makes no claim that it was the right set.
    ``population_valid`` is ``False`` in that case, because a population that
    was never declared cannot be established as the declared population -- which
    is the fail-closed half of the contract.
    """

    population_count: int
    population_ids: tuple[str, ...]
    population_digest: str
    declared_count: int | None
    declared_digest: str | None
    missing: tuple[str, ...]
    """Declared members the enumeration did not reach. The #453 failure mode."""
    unexpected: tuple[str, ...]
    """Enumerated members no declaration named."""
    population_valid: bool

    @property
    def sub_reason(self) -> UninterpretableSubReason | None:
        """The typed reason a consumer must not interpret this run, if any."""
        if self.population_valid:
            return None
        return UninterpretableSubReason.POPULATION_INVALID

    def as_dict(self) -> dict[str, object]:
        """The record as plain data, for a receipt or a failure message.

        Field names are the ones #453 specifies, so two controls' records are
        comparable without reading either control.
        """
        return {
            "population_count": self.population_count,
            "population_ids": list(self.population_ids),
            "population_digest": self.population_digest,
            "declared_count": self.declared_count,
            "declared_digest": self.declared_digest,
            "missing": list(self.missing),
            "unexpected": list(self.unexpected),
            "population_valid": self.population_valid,
            "sub_reason": None if self.sub_reason is None else str(self.sub_reason),
        }


class PopulationInvalidError(AssertionError):
    """Raised when a control's analysed population is not its declared population.

    Derives from ``AssertionError`` so a pytest consumer reports it as a failure
    rather than an error, while still carrying the typed record. The message
    names the missing and unexpected members, because "five tests failed" and
    "the universe those five tests ran over was wrong" are different findings
    and the second one explains the first.
    """

    def __init__(self, record: PopulationRecord, context: str) -> None:
        self.record = record
        self.context = context
        detail = []
        if record.missing:
            detail.append(
                f"declared but not enumerated ({len(record.missing)}): " + ", ".join(record.missing)
            )
        if record.unexpected:
            detail.append(
                f"enumerated but not declared ({len(record.unexpected)}): "
                + ", ".join(record.unexpected)
            )
        if record.declared_count is None:
            detail.append("no declaration was supplied, so the population cannot be established")
        super().__init__(
            f"{PopulationVerdict.UNINTERPRETABLE} "
            f"({UninterpretableSubReason.POPULATION_INVALID}): "
            f"{context} analysed {record.population_count} case(s), digest "
            f"{record.population_digest}. "
            + " | ".join(detail)
            + ". Any verdict from this run is about the wrong universe, so it is "
            "reported as uninterpretable rather than as a pass or a failure."
        )


def population_digest(ids: Iterable[str]) -> str:
    """SHA-256 of the canonicalised membership set. See the module docstring.

    Order-insensitive by construction; duplicate identifiers are refused.
    """
    ordered = sorted(_checked_ids(ids))
    payload = DIGEST_VERSION + "\n" + json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def posix_relative_ids(paths: Iterable[Path], root: Path) -> tuple[str, ...]:
    """Stable identifiers for a filesystem population, sorted.

    Uses ``/`` separators and paths relative to ``root``, so the same population
    enumerated on Windows and on Linux yields the same digest. ``root`` is not
    resolved: resolving follows a link and would report the real on-disk casing
    rather than the casing the caller enumerated.
    """
    return tuple(sorted(path.relative_to(root).as_posix() for path in paths))


def build_population_record(
    analyzed: Iterable[str],
    declared: Iterable[str] | None = None,
) -> PopulationRecord:
    """Record what a control analysed and whether it is what was declared.

    ``declared=None`` records the population without validating it, and yields
    ``population_valid=False``. An undeclared population is the fail-closed
    case, not the permissive one: a control that never said what it expected
    cannot demonstrate it got it.
    """
    analyzed_ids = tuple(sorted(_checked_ids(analyzed)))
    analyzed_digest = population_digest(analyzed_ids)

    if declared is None:
        return PopulationRecord(
            population_count=len(analyzed_ids),
            population_ids=analyzed_ids,
            population_digest=analyzed_digest,
            declared_count=None,
            declared_digest=None,
            missing=(),
            unexpected=(),
            population_valid=False,
        )

    declared_ids = tuple(sorted(_checked_ids(declared)))
    missing = tuple(sorted(set(declared_ids) - set(analyzed_ids)))
    unexpected = tuple(sorted(set(analyzed_ids) - set(declared_ids)))
    return PopulationRecord(
        population_count=len(analyzed_ids),
        population_ids=analyzed_ids,
        population_digest=analyzed_digest,
        declared_count=len(declared_ids),
        declared_digest=population_digest(declared_ids),
        missing=missing,
        unexpected=unexpected,
        population_valid=not missing and not unexpected,
    )


def require_valid_population(record: PopulationRecord, context: str) -> None:
    """Fail closed: raise unless the analysed population is the declared one.

    ``context`` names the control, so the failure says which universe was wrong.
    """
    if not record.population_valid:
        raise PopulationInvalidError(record, context)


def interpret(record: PopulationRecord, detector_failures: Sequence[str]) -> PopulationVerdict:
    """Combine a population record with a detector's own outcome.

    The population is checked FIRST and its failure is terminal. A detector
    result is an object-level claim about the subject, and no such claim is
    available when the analysed universe is unknown -- so an invalid population
    yields ``UNINTERPRETABLE`` whether the detector passed or failed. Reading
    the detector first is exactly the defect this contract exists to prevent.
    """
    if not record.population_valid:
        return PopulationVerdict.UNINTERPRETABLE
    return PopulationVerdict.FAIL if detector_failures else PopulationVerdict.PASS


def _checked_ids(ids: Iterable[str]) -> list[str]:
    """Materialise identifiers, refusing duplicates.

    A duplicate means the enumeration counted one case twice. De-duplicating it
    would repair the symptom and hide the defect, so it is refused instead.
    """
    materialised = list(ids)
    seen: set[str] = set()
    duplicates: list[str] = []
    for identifier in materialised:
        if identifier in seen:
            duplicates.append(identifier)
        seen.add(identifier)
    if duplicates:
        raise ValueError(
            "duplicate population identifier(s): "
            + ", ".join(sorted(set(duplicates)))
            + ". A duplicate means the enumeration counted a case twice; it is "
            "refused rather than de-duplicated so the defect stays visible."
        )
    return materialised
