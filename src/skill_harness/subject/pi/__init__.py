"""Pi paired subject lane — a thin runtime adapter into the ParsedEvalLog seam.

Pi (the pi-coding-agent runtime) is a SECOND runtime for the existing
delivery-verified treatment-policy contrast, not a new scientific layer.
This package owns only what the evidence layer must not know about:

* ``roster``   — Full/Null effective-roster construction and verification
                 (apparatus validation, before any epoch runs);
* ``pin``      — the Pi-namespaced harness pin (``harness: "pi"``), carried
                 through the existing opaque pin fields;
* ``capture.ts`` — the read-only Pi extension that persists the assembled
                 system prompt, the serialized provider requests, and the
                 runtime event stream;
* ``parser``   — epoch artifacts -> ParsedSample/ParsedEvalLog, reusing the
                 EXISTING exposure detector over a normalized provider
                 payload and implementing the registered Pi invocation
                 realization (#46 branch b + /skill: expansion);
* ``launcher`` — pinned subprocess execution, pre-spend parser-identity
                 check, oracle command execution, runner-block assembly.

Downstream is untouched: ``write_paired_evidence`` and everything below it
(pair validation, refusal predicates, evidence admissibility, metric identity,
aggregation, SERS, Gate-2) remain the scientific authority. Pi evidence is
runtime-attributed through the runner block (``runtime.name == "pi"``) and
is not pooled with Inspect-lane evidence.
"""

from skill_harness.subject.pi.launcher import (
    LaunchResult,
    LaunchSpec,
    ParserIdentityMismatchError,
    PiExecutableNotFoundError,
    PiLaunchError,
    build_runner_block,
    measure_pi_version,
    run_epoch,
    run_oracle_command,
    verify_pair_symmetry,
    verify_parser_identity,
)
from skill_harness.subject.pi.parser import (
    EXPOSURE_REALIZATION_VERSION,
    EXPOSURE_SURFACE,
    INVOCATION_CHANNELS,
    INVOCATION_REALIZATION_VERSION,
    PI_PARSER_VERSION,
    CaptureIncompleteError,
    EpochSpec,
    MidEpochIdentityChangeError,
    ParseReport,
    PiParseError,
    RosterAttestationError,
    build_parsed_log,
    parse_epoch,
    parser_identity,
)
from skill_harness.subject.pi.pin import BaselineSkill, PiHarnessPin
from skill_harness.subject.pi.roster import PiRosterError, RosterEntry, build_roster
from skill_harness.subject.pi.runner import (
    EpochExecutionError,
    PairedRunSpec,
    PiPairedRunError,
    PreSpendValidation,
    RuntimeVersionMismatchError,
    run_paired_evaluation,
    spec_from_config,
    validate_pre_spend,
)

__all__ = [
    "EXPOSURE_REALIZATION_VERSION",
    "EXPOSURE_SURFACE",
    "INVOCATION_CHANNELS",
    "INVOCATION_REALIZATION_VERSION",
    "PI_PARSER_VERSION",
    "BaselineSkill",
    "CaptureIncompleteError",
    "EpochExecutionError",
    "EpochSpec",
    "LaunchResult",
    "LaunchSpec",
    "MidEpochIdentityChangeError",
    "PairedRunSpec",
    "ParseReport",
    "ParserIdentityMismatchError",
    "PiExecutableNotFoundError",
    "PiHarnessPin",
    "PiLaunchError",
    "PiPairedRunError",
    "PiParseError",
    "PiRosterError",
    "PreSpendValidation",
    "RosterAttestationError",
    "RosterEntry",
    "RuntimeVersionMismatchError",
    "build_parsed_log",
    "build_roster",
    "build_runner_block",
    "measure_pi_version",
    "parse_epoch",
    "parser_identity",
    "run_epoch",
    "run_oracle_command",
    "run_paired_evaluation",
    "spec_from_config",
    "validate_pre_spend",
    "verify_pair_symmetry",
    "verify_parser_identity",
]
