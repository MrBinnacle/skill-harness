"""Build the SERS 1.1.0 ``subject_identity`` block from harness sources.

Each field is the value the harness already computes elsewhere; none is free-typed:

- ``skill_id`` — SHA-256 of the exact ``SKILL.md`` bytes (ingest key)
- ``harness_version`` — installed package / ``__version__`` fallback
- ``metric_version`` — ``ORACLE_METRIC_VERSION`` on the subject ingest module
- ``implementation_hash`` — SHA-256 of the oracle module source at mint time
- ``arms`` — which arms ran (``null``, ``full``, or both)
- ``subject_model`` (SERS 1.4.0): the model that executed the epochs

``subject_model`` is the one field this helper cannot derive from a file on disk.
It names the model the run was launched against, which is a property of the launch
and not of the tree, so it is a caller argument rather than a computed pin. It is
omitted entirely when the caller does not supply one, which yields a pre-1.4.0
block; the schema, not this helper, is what refuses a 1.4.0 receipt that lacks it.
A blank pin is refused for the same reason empty skill bytes are: a blank is a
manufactured record, not a missing one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_ARM_VALUES = frozenset({"null", "full"})


def build_subject_identity(
    *,
    skill_md: Path | bytes,
    arms: Sequence[str] | str,
    subject_model: str | None = None,
) -> dict[str, Any]:
    """Return a complete ``subject_identity`` block populated by the harness.

    :param skill_md: path to the measured ``SKILL.md``, or its exact bytes
    :param arms: ``"null"``, ``"full"``, or a sequence of those (both arms)
    :param subject_model: pin of the model that executed the epochs (SERS 1.4.0).
        Omit for a pre-1.4.0 block; the key is then absent rather than blank.
    :raises ValueError: empty skill bytes, arms outside the closed set, or a
        ``subject_model`` that is supplied but blank
    """
    from skill_harness.cli.main import _resolve_harness_version
    from skill_harness.subject.ingest import ORACLE_METRIC_VERSION, _oracle_implementation_hash

    source_bytes = skill_md if isinstance(skill_md, bytes) else Path(skill_md).read_bytes()
    if not source_bytes:
        raise ValueError("skill_md bytes are empty; refusing to mint a skill_id")

    normalized_arms = _normalize_arms(arms)
    block: dict[str, Any] = {
        "skill_id": hashlib.sha256(source_bytes).hexdigest(),
        "harness_version": _resolve_harness_version(),
        "metric_version": ORACLE_METRIC_VERSION,
        "implementation_hash": _oracle_implementation_hash(),
        "arms": normalized_arms,
    }
    if subject_model is not None:
        if not subject_model.strip():
            raise ValueError("subject_model is blank; refusing to mint a blank subject pin")
        block["subject_model"] = subject_model
    return block


def _normalize_arms(arms: Sequence[str] | str) -> str | list[str]:
    if isinstance(arms, str):
        if arms not in _ARM_VALUES:
            raise ValueError(f"arms must be 'null' or 'full', got {arms!r}")
        return arms
    values = list(arms)
    if not values:
        raise ValueError("arms sequence is empty")
    if len(values) != len(set(values)):
        raise ValueError(f"arms sequence has duplicates: {values!r}")
    unknown = [a for a in values if a not in _ARM_VALUES]
    if unknown:
        raise ValueError(f"arms contains values outside {{null, full}}: {unknown!r}")
    if len(values) == 1:
        return values[0]
    return values
