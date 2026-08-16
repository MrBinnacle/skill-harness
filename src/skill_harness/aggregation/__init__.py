"""Aggregation engine for Skill Harness (Track E.2).

Public API surface consumed by E.3 CLI integration:

    from skill_harness.aggregation import aggregate_skill, SkillReport

Design:
- ``aggregate_skill()`` is a pure read-side function: no API calls, no sampling,
  no writes. Caller supplies already-opened DB connections.
- ``SkillReport`` (and sub-dataclasses) are frozen dataclasses for safe sharing.
- Serialisation: ``to_json_dict()`` / ``to_json_bytes()`` in ``aggregation.report``.
- Exceptions: ``PreconditionError`` / ``MalformedRunConfig`` in ``aggregation.errors``.
"""

from skill_harness.aggregation.engine import aggregate_skill
from skill_harness.aggregation.errors import (
    ConvergenceFailure,
    MalformedRunConfig,
    PreconditionError,
)
from skill_harness.aggregation.matched_bridge import (
    MatchedCellObservationIds,
    MatchedGate2Result,
    aggregate_matched_gate2,
)
from skill_harness.aggregation.report import (
    ClauseReport,
    ContributionSummary,
    SkillReport,
    VectorSummary,
    to_json_bytes,
    to_json_dict,
)
from skill_harness.aggregation.status import ClauseStatus, UnmeasuredSubReason

__all__ = [
    "ClauseReport",
    "ClauseStatus",
    "ContributionSummary",
    "ConvergenceFailure",
    "MalformedRunConfig",
    "MatchedCellObservationIds",
    "MatchedGate2Result",
    "PreconditionError",
    "SkillReport",
    "UnmeasuredSubReason",
    "VectorSummary",
    "aggregate_matched_gate2",
    "aggregate_skill",
    "to_json_bytes",
    "to_json_dict",
]
