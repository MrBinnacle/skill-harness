"""The Pi paired-lane production driver: the one path from spec to evidence.

This module is the missing driver, not a new abstraction. Before it existed
the Pi lane was a set of individually-tested building blocks with no caller:
``run_epoch`` had zero callers anywhere in the repository, and the two
pre-spend controls (``verify_parser_identity``, ``verify_pair_symmetry``)
were exported, unit-tested, and invoked by nothing. Their docstrings
described a pre-spend guarantee that no executable path delivered.

``run_paired_evaluation`` is that path. It owns sequencing and refusal only;
every check it performs is an existing function called by name. It
deliberately implements no scientific semantics of its own: evidence
admissibility, exposure, Null contamination, pair validity, scoring and
Gate-2 all remain downstream, behind ``write_paired_evidence``, which this
module treats as the scientific boundary.

The lifecycle, and the invariant that orders it:

    PRE-SPEND ......... parser identity, runtime version, both rosters,
                        cross-arm symmetry, arm-shared pin
    SPEND ............. the Pi subprocess, once per (epoch, arm)
    POST-SPEND ........ oracle, capture parse, ParsedEvalLog, ingest

Everything checkable without a provider request happens above the SPEND
line. ``validate_pre_spend`` performs exactly that set and returns; it is
the whole of the driver's dry-run mode, so the checks are reachable and
assertable without spending anything.

Two structural constraints come from the layers this driver sits between,
and both shape the spec rather than being worked around:

``pin.cwd`` is part of the arm-shared fingerprint, and
``ingest._pin_admissibility`` writes every verdict of a run inadmissible
when the fingerprints of the two arms differ. So both arms run in ONE
workspace path, re-materialised from ``workspace_template`` before each
epoch, rather than in per-arm directories. Identical environment across
arms is therefore a property of the layout, not of operator discipline.

``build_roster`` validates one arm in isolation; the Full-vs-Null
comparison lives only in ``verify_pair_symmetry``. The driver calls both,
and calls symmetry before the first subprocess starts.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from skill_harness.subject.ingest import (
    IngestResult,
    ParsedSample,
    write_paired_evidence,
)
from skill_harness.subject.pi.launcher import (
    CAPTURE_EXTENSION_PATH,
    ContainerSpec,
    LaunchSpec,
    build_runner_block,
    measure_pi_version,
    run_epoch,
    run_oracle_command,
    verify_pair_symmetry,
    verify_parser_identity,
)
from skill_harness.subject.pi.parser import (
    EpochSpec,
    build_parsed_log,
    parse_epoch,
)
from skill_harness.subject.pi.pin import BaselineSkill, PiHarnessPin
from skill_harness.subject.pi.roster import RosterEntry, build_roster

__all__ = [
    "EpochExecutionError",
    "PairedRunSpec",
    "PiPairedRunError",
    "PreSpendValidation",
    "RuntimeVersionMismatchError",
    "run_paired_evaluation",
    "spec_from_config",
    "validate_pre_spend",
]


class PiPairedRunError(Exception):
    """Base apparatus refusal for the paired driver.

    Apparatus errors only. Scientific refusals (unexposed Full epoch, Null
    contamination, pair mismatch) are raised downstream by the existing
    ingest layer and are deliberately not re-implemented here.
    """


class RuntimeVersionMismatchError(PiPairedRunError):
    """The live Pi runtime is not the declared one. Refuses before spend."""


class EpochExecutionError(PiPairedRunError):
    """An epoch's subprocess did not complete cleanly.

    Raised after spend and before any evidence is assembled, so a defective
    epoch never reaches ``write_paired_evidence``.
    """


@dataclass(frozen=True)
class PairedRunSpec:
    """The complete declared inputs for one Pi paired evaluation.

    Everything is pinned or derived; nothing is read from the ambient
    environment. ``declared_parser_identity`` is the ratified identity a
    sized run must match; ``None`` is the apparatus-smoke posture, in which
    the live identity is measured and recorded instead of compared.
    """

    pi_bin: str
    provider: str
    model: str
    thinking_level: str
    tool_allowlist: tuple[str, ...]
    baseline_dirs: tuple[Path, ...]
    treatment_dir: Path
    skill_name: str
    prompt: str
    oracle_command: str
    workspace_template: Path
    workspace: Path
    artifact_root: Path
    n_pairs: int
    declared_env: Mapping[str, str]
    secret_env: Mapping[str, str]
    container: ContainerSpec | None
    expected_runtime_version: str | None
    declared_parser_identity: Mapping[str, str] | None
    route: str
    rat_fields: Mapping[str, str] | None = None
    scorer_name: str = "command_succeeds"
    timeout_s: int = 1800
    oracle_timeout_s: int = 600


@dataclass(frozen=True)
class PreSpendValidation:
    """What the pre-spend gate established, and nothing it did not.

    Returned by ``validate_pre_spend`` so the same object serves the dry-run
    report and the executing path. Holding it is proof the checks ran: the
    driver cannot reach its subprocess without one, because the epoch runner
    takes it as a required argument.
    """

    parser: Mapping[str, str]
    runtime_version: str
    full_roster: tuple[RosterEntry, ...]
    null_roster: tuple[RosterEntry, ...]
    treatment: RosterEntry
    pin: PiHarnessPin
    checks: tuple[str, ...] = field(default=())


def _pin_for(
    spec: PairedRunSpec, runtime_version: str, baseline: tuple[RosterEntry, ...]
) -> PiHarnessPin:
    """The arm-shared pin.

    The treatment is excluded by construction (see ``pin.py``): including it
    would make the two arms' fingerprints differ and write every verdict
    inadmissible. ``cwd`` is the shared workspace, which is why both arms
    run in one.
    """
    container = spec.container
    return PiHarnessPin(
        harness="pi",
        runtime_version=runtime_version,
        provider=spec.provider,
        model=spec.model,
        thinking_level=spec.thinking_level,
        tool_allowlist=tuple(spec.tool_allowlist),
        cwd=str(spec.workspace),
        image_digest=(
            container.image_digest if container is not None else "local-host:no-container"
        ),
        network_policy=(container.network_policy if container is not None else "host-default"),
        declared_env=dict(spec.declared_env),
        secret_env_names=tuple(sorted(spec.secret_env)),
        baseline_roster=tuple(
            BaselineSkill(e.name, str(e.path), e.skill_md_sha256) for e in baseline
        ),
        capture_extension_sha256=hashlib.sha256(CAPTURE_EXTENSION_PATH.read_bytes()).hexdigest(),
    )


def validate_pre_spend(spec: PairedRunSpec) -> PreSpendValidation:
    """Every check that can be made without a provider request. Fail-closed.

    Ordered cheapest-first so the most common misconfiguration refuses
    before anything is executed at all:

    1. parser/capture identity vs the declared identity (no subprocess);
    2. the live runtime version (``pi --version`` is a subprocess, but not a
       provider request: it measures the binary and spends nothing);
    3. each arm's roster, built and validated independently;
    4. cross-arm symmetry, which no other caller performs;
    5. the arm-shared pin, constructed once and reused by both arms.

    :raises ParserIdentityMismatchError: the live evidence pipeline is not
        the declared one.
    :raises RuntimeVersionMismatchError: the live runtime is not the pinned
        one.
    :raises PiRosterError: an arm's roster is invalid, or the two arms are
        not Full = Null + treatment.
    """
    parser = verify_parser_identity(spec.declared_parser_identity)

    runtime_version = measure_pi_version(spec.pi_bin, container=spec.container)
    if (
        spec.expected_runtime_version is not None
        and runtime_version != spec.expected_runtime_version
    ):
        raise RuntimeVersionMismatchError(
            f"live Pi runtime {runtime_version!r} != declared "
            f"{spec.expected_runtime_version!r}; the subject is not the pinned "
            "one, so REFUSE"
        )

    full_roster = build_roster(tuple(spec.baseline_dirs), spec.treatment_dir, "full")
    null_roster = build_roster(tuple(spec.baseline_dirs), None, "null")
    treatment = full_roster[-1]
    verify_pair_symmetry(full_roster, null_roster, treatment)

    pin = _pin_for(spec, runtime_version, null_roster)

    return PreSpendValidation(
        parser=parser,
        runtime_version=runtime_version,
        full_roster=full_roster,
        null_roster=null_roster,
        treatment=treatment,
        pin=pin,
        checks=(
            "parser_identity",
            "runtime_version",
            "roster_full",
            "roster_null",
            "pair_symmetry",
            "pin_constructed",
        ),
    )


def _materialize_workspace(template: Path, workspace: Path) -> None:
    """Re-create the epoch's cwd from the template. Same for both arms."""
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(template, workspace)


def _run_one_epoch(
    spec: PairedRunSpec,
    validated: PreSpendValidation,
    *,
    condition: Literal["full", "null"],
    epoch: int,
) -> tuple[ParsedSample, str]:
    """Spend on one epoch, then normalise it. Fail-closed on both halves.

    Returns the sample and the runtime's own session id. The session id is
    not decoration: ``build_parsed_log`` derives ``task_id`` from the arm's
    session ids, so a re-ingested pair reproduces the same deterministic run
    id and ``AlreadyIngestedError`` keeps its idempotency semantics. A
    synthetic id here would silently break that.
    """
    artifact_dir = spec.artifact_root / f"epoch-{epoch:03d}" / condition
    session_dir = spec.artifact_root / f"epoch-{epoch:03d}" / f"{condition}-session"
    roster = validated.full_roster if condition == "full" else validated.null_roster

    _materialize_workspace(spec.workspace_template, spec.workspace)

    launch_spec = LaunchSpec(
        pi_bin=spec.pi_bin,
        provider=spec.provider,
        model=spec.model,
        thinking_level=spec.thinking_level,
        tool_allowlist=tuple(spec.tool_allowlist),
        baseline_dirs=tuple(spec.baseline_dirs),
        treatment_dir=spec.treatment_dir if condition == "full" else None,
        condition=condition,
        prompt=spec.prompt,
        workspace=spec.workspace,
        artifact_dir=artifact_dir,
        session_dir=session_dir,
        declared_env=spec.declared_env,
        secret_env=spec.secret_env,
        container=spec.container,
        expected_runtime_version=spec.expected_runtime_version,
        timeout_s=spec.timeout_s,
    )

    # -----------------------------------------------------------------
    # SPEND. Every check above this line has already run and passed.
    # Nothing below it may gate the launch, because the launch has
    # happened; post-spend refusals discard evidence, they do not
    # prevent cost.
    # -----------------------------------------------------------------
    launch = run_epoch(launch_spec, validated.pin)

    if launch.returncode != 0:
        raise EpochExecutionError(
            f"{condition} epoch {epoch} exited {launch.returncode}; "
            "an epoch that did not complete is apparatus failure, not a "
            "measured outcome, so the pair is refused before any evidence "
            "is assembled"
        )

    score = run_oracle_command(
        spec.oracle_command,
        cwd=spec.workspace,
        env=spec.declared_env,
        container=spec.container,
        timeout_s=spec.oracle_timeout_s,
    )

    sample, report = parse_epoch(
        EpochSpec(
            artifact_dir=artifact_dir,
            condition=condition,
            epoch=epoch,
            scorer_name=spec.scorer_name,
            score_value=score,
            skill_name=spec.skill_name,
            skill_dir=spec.treatment_dir,
            pin=validated.pin,
            expected_roster=roster,
            expected_provider=spec.provider,
            expected_model=spec.model,
            expected_thinking_level=spec.thinking_level,
        )
    )
    return sample, report.session_id


def run_paired_evaluation(
    spec: PairedRunSpec,
    conn: sqlite3.Connection,
    *,
    validated: PreSpendValidation | None = None,
) -> IngestResult:
    """The one production path for a Pi paired evaluation.

    Validates, spends, parses, normalises, and hands the pair to the
    existing scientific write path. Responsibility ends at two
    ``ParsedEvalLog`` objects; everything downstream of
    ``write_paired_evidence`` is unchanged and unconsulted here.

    ``validated`` exists so a caller that has already run the dry-run gate
    can pass its result rather than repeating the checks. Omitted, the gate
    runs here. There is no path to the subprocess that skips it.

    :raises PiPairedRunError: any apparatus failure, before or after spend.
    :raises PiParseError: a defective capture, raised before the sample
        exists.
    """
    if validated is None:
        validated = validate_pre_spend(spec)

    full_samples: list[ParsedSample] = []
    null_samples: list[ParsedSample] = []
    full_sessions: list[str] = []
    null_sessions: list[str] = []
    for epoch in range(spec.n_pairs):
        sample, session_id = _run_one_epoch(spec, validated, condition="full", epoch=epoch)
        full_samples.append(sample)
        full_sessions.append(session_id)
        sample, session_id = _run_one_epoch(spec, validated, condition="null", epoch=epoch)
        null_samples.append(sample)
        null_sessions.append(session_id)

    created = datetime.now(UTC).isoformat()
    full_log = build_parsed_log(
        "full",
        tuple(full_samples),
        session_ids=tuple(full_sessions),
        created=created,
        status="success",
        skill_name=spec.skill_name,
    )
    null_log = build_parsed_log(
        "null",
        tuple(null_samples),
        session_ids=tuple(null_sessions),
        created=created,
        status="success",
        skill_name=spec.skill_name,
    )

    runner_block: dict[str, Any] = build_runner_block(
        pin=validated.pin,
        parser=validated.parser,
        treatment=validated.treatment,
        route=spec.route,
        n_pairs=spec.n_pairs,
        rat_fields=spec.rat_fields,
    )

    return write_paired_evidence(
        full=full_log,
        null=null_log,
        skill_dir=spec.treatment_dir,
        conn=conn,
        runner_config=runner_block,
    )


def spec_from_config(config: Mapping[str, Any], *, base_dir: Path) -> PairedRunSpec:
    """Build a run spec from a declared JSON config.

    Relative paths resolve against ``base_dir`` (the config file's own
    directory), so a config travels with its fixture tree and does not
    depend on the operator's cwd.

    Absent optional keys keep the spec's defaults. ``container`` is a nested
    object or absent; absent means host execution, which the pin records
    honestly as ``local-host:no-container`` rather than leaving blank.

    :raises KeyError: a required key is absent. The caller reports it; this
        function does not substitute a default for something the operator
        was required to declare.
    """

    def _path(value: str) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else (base_dir / candidate)

    container_cfg = config.get("container")
    container: ContainerSpec | None = None
    if container_cfg is not None:
        container = ContainerSpec(
            argv_prefix=tuple(container_cfg["argv_prefix"]),
            image_digest=str(container_cfg["image_digest"]),
            network_policy=str(container_cfg["network_policy"]),
        )

    secret_env_names: tuple[str, ...] = tuple(config.get("secret_env_names", ()))
    secret_env: dict[str, str] = {
        name: os.environ[name] for name in secret_env_names if name in os.environ
    }
    missing = [name for name in secret_env_names if name not in os.environ]
    if missing:
        raise PiPairedRunError(
            f"declared secret env name(s) absent from the environment: {sorted(missing)}; "
            "the epoch would run without a credential it was declared to receive"
        )

    return PairedRunSpec(
        pi_bin=str(config["pi_bin"]),
        provider=str(config["provider"]),
        model=str(config["model"]),
        thinking_level=str(config["thinking_level"]),
        tool_allowlist=tuple(config.get("tool_allowlist", ())),
        baseline_dirs=tuple(_path(d) for d in config.get("baseline_dirs", ())),
        treatment_dir=_path(str(config["treatment_dir"])),
        skill_name=str(config["skill_name"]),
        prompt=str(config["prompt"]),
        oracle_command=str(config["oracle_command"]),
        workspace_template=_path(str(config["workspace_template"])),
        workspace=_path(str(config["workspace"])),
        artifact_root=_path(str(config["artifact_root"])),
        n_pairs=int(config["n_pairs"]),
        declared_env=dict(config.get("declared_env", {})),
        secret_env=secret_env,
        container=container,
        expected_runtime_version=config.get("expected_runtime_version"),
        declared_parser_identity=config.get("declared_parser_identity"),
        route=str(config["route"]),
        rat_fields=config.get("rat_fields"),
        scorer_name=str(config.get("scorer_name", "command_succeeds")),
        timeout_s=int(config.get("timeout_s", 1800)),
        oracle_timeout_s=int(config.get("oracle_timeout_s", 600)),
    )
