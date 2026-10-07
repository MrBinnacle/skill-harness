"""Launcher for one isolated Pi paired-lane epoch.

Owns everything the evidence layer must not know about: subprocess
invocation of the Pi CLI in ``--print`` mode with a pinned flag surface,
the declared environment (secrets by name only), the capture directory
layout, the pre-spend parser-identity check, and execution of the existing
oracle command against the epoch's final filesystem.

Flag surface (identical across arms except the treatment ``--skill``):

    pi --provider P --model M --thinking T --tools <csv>
       --no-skills --skill <baseline...> [--skill <treatment>]   # Full only
       --no-context-files --no-prompt-templates
       --no-extensions -e <capture.ts>
       --session-dir <deterministic> -p <prompt>

``--no-skills`` disables all ambient discovery (user, project, package,
settings); explicit ``--skill`` paths are additive on top of it, so the
effective roster is exactly what this launcher enumerates — verified by
``roster.build_roster`` before launch and attested from the runtime's own
``systemPromptOptions.skills`` after it (parser.py). ``--no-extensions``
plus a single explicit ``-e`` makes the capture extension the ONLY
extension, which is what makes the payload capture trustworthy.

Container execution is a command-prefix concern: ``container_argv`` in the
launch spec, when set, wraps both the Pi invocation and the oracle command
(e.g. ``docker run --rm --network none -v ... <image@sha256>``). The image
digest and network policy are pinned into the harness pin regardless of
which side of the boundary the process runs on.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from skill_harness.subject.pi.parser import (
    EXPOSURE_REALIZATION_VERSION,
    EXPOSURE_SURFACE,
    INVOCATION_CHANNELS,
    INVOCATION_REALIZATION_VERSION,
    parser_identity,
)
from skill_harness.subject.pi.pin import BaselineSkill, PiHarnessPin
from skill_harness.subject.pi.roster import PiRosterError, RosterEntry, build_roster

__all__ = [
    "ContainerSpec",
    "LaunchResult",
    "LaunchSpec",
    "ParserIdentityMismatchError",
    "PiExecutableNotFoundError",
    "PiLaunchError",
    "build_runner_block",
    "measure_pi_version",
    "run_epoch",
    "run_oracle_command",
    "verify_pair_symmetry",
    "verify_parser_identity",
]

CAPTURE_EXTENSION_PATH = Path(__file__).with_name("capture.ts")


class PiLaunchError(Exception):
    """Base refusal for the Pi launcher — apparatus errors, before evidence."""


class ParserIdentityMismatchError(PiLaunchError):
    """The live parser/capture identity differs from the declared identity."""


class PiExecutableNotFoundError(PiLaunchError):
    """The pinned Pi binary cannot be executed at all."""


@dataclass(frozen=True)
class ContainerSpec:
    """External execution boundary for both the epoch and the oracle.

    ``argv_prefix`` wraps the command line (e.g. docker run flags + the
    digest-pinned image reference). ``image_digest`` and ``network_policy``
    are pinned into the harness pin. When None the epoch runs on the host
    and the pin records that honestly.
    """

    argv_prefix: tuple[str, ...]
    image_digest: str
    network_policy: str


@dataclass(frozen=True)
class LaunchSpec:
    """Complete pinned inputs for one epoch. Nothing ambient."""

    pi_bin: str
    provider: str
    model: str
    thinking_level: str
    tool_allowlist: tuple[str, ...]
    baseline_dirs: tuple[Path, ...]
    treatment_dir: Path | None
    condition: Literal["full", "null"]
    prompt: str
    workspace: Path  # prepared task filesystem; the epoch's cwd
    artifact_dir: Path  # capture output root for this epoch
    session_dir: Path  # deterministic session storage for this epoch
    declared_env: Mapping[str, str]
    secret_env: Mapping[str, str]  # values used, NAMES only pinned
    container: ContainerSpec | None
    expected_runtime_version: str | None  # pin from the ratified declaration
    timeout_s: int = 1800


@dataclass(frozen=True)
class LaunchResult:
    """What one epoch's execution produced (pre-parse)."""

    artifact_dir: Path
    session_file: Path | None
    roster: tuple[RosterEntry, ...]
    runtime_version: str
    returncode: int


def measure_pi_version(pi_bin: str, *, container: ContainerSpec | None = None) -> str:
    """The live runtime version, measured from the binary, never assumed.

    Measured ACROSS THE SAME EXECUTION BOUNDARY the epoch will use. When
    ``container`` is set the probe is wrapped in the same ``argv_prefix``
    that ``run_epoch`` and ``run_oracle_command`` apply, so the version
    pinned into the harness pin is the version of the binary that actually
    runs.

    Without the prefix the probe measures whatever ``pi_bin`` resolves to on
    the HOST, while the epoch executes the container's copy. The pin would
    then carry a runtime identity for a process that never ran: a silent
    provenance error, because both values are real versions of a real Pi and
    nothing downstream can tell them apart.

    Fails closed. A probe that cannot run, exits nonzero, or prints nothing
    raises rather than falling back to an assumed or host-measured value.
    """
    argv: list[str] = []
    if container is not None:
        argv.extend(container.argv_prefix)
    argv.extend([pi_bin, "--version"])
    where = "container" if container is not None else "host"
    try:
        proc = subprocess.run(  # noqa: S603 -- pi_bin is operator-pinned
            argv,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PiExecutableNotFoundError(
            f"Pi binary not found on the {where} execution boundary: {pi_bin}"
        ) from exc
    if proc.returncode != 0 or not proc.stdout.strip():
        raise PiExecutableNotFoundError(
            f"{pi_bin} --version failed on the {where} execution boundary "
            f"(rc={proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout.strip().splitlines()[0].strip()


def verify_parser_identity(declared: Mapping[str, str] | None) -> dict[str, str]:
    """Fail-closed parser identity check. Runs BEFORE any model spend.

    With a declared (ratified) identity, every identity field must equal the
    live pipeline's; any mismatch refuses. Without one (apparatus smoke
    tests only) the live identity is measured and returned for recording.
    """
    live = parser_identity()
    if declared is not None:
        for key in ("version", "content_hash", "semantic_digest", "digest_algo_version"):
            if declared.get(key) != live[key]:
                raise ParserIdentityMismatchError(
                    f"parser identity field {key!r}: declared "
                    f"{str(declared.get(key))[:16]!r} != live {live[key][:16]!r}; "
                    "the evidence pipeline is not the declared one — REFUSE"
                )
    return live


def verify_pair_symmetry(
    full: tuple[RosterEntry, ...],
    null: tuple[RosterEntry, ...],
    treatment: RosterEntry,
) -> None:
    """Full = Null + treatment, every baseline member identical across arms."""
    if full[:-1] != null:
        raise PiRosterError(
            "cross-arm baseline asymmetry: the Full roster's baseline members "
            "are not identical to the Null roster"
        )
    if full[-1] != treatment:
        raise PiRosterError(
            f"the Full roster's extra member {full[-1].name!r} is not the "
            f"treatment {treatment.name!r}"
        )
    if any(entry.name == treatment.name for entry in null):
        raise PiRosterError("the treatment skill is present in the Null roster")


def _epoch_env(spec: LaunchSpec) -> dict[str, str]:
    env: dict[str, str] = dict(spec.declared_env)
    env.update(spec.secret_env)
    env["PI_CAPTURE_DIR"] = str(spec.artifact_dir)
    return env


def run_epoch(spec: LaunchSpec, pin: PiHarnessPin) -> LaunchResult:
    """Execute one epoch. All refusals fire before the subprocess starts
    except process failure itself, which surfaces as a nonzero returncode
    for the pair runner to refuse on.
    """
    roster = build_roster(spec.baseline_dirs, spec.treatment_dir, spec.condition)
    spec.artifact_dir.mkdir(parents=True, exist_ok=True)
    spec.session_dir.mkdir(parents=True, exist_ok=True)

    argv: list[str] = []
    if spec.container is not None:
        argv.extend(spec.container.argv_prefix)
    argv.extend(
        [
            spec.pi_bin,
            "--provider",
            spec.provider,
            "--model",
            spec.model,
            "--thinking",
            spec.thinking_level,
            "--no-skills",
        ]
    )
    for entry in roster:
        argv.extend(["--skill", str(entry.path)])
    argv.extend(
        [
            "--no-context-files",
            "--no-prompt-templates",
            "--no-extensions",
            "-e",
            str(CAPTURE_EXTENSION_PATH),
            "--session-dir",
            str(spec.session_dir),
        ]
    )
    if spec.tool_allowlist:
        argv.extend(["--tools", ",".join(spec.tool_allowlist)])
    argv.extend(["-p", spec.prompt])

    try:
        proc = subprocess.run(  # noqa: S603 -- argv is launcher-constructed
            argv,
            cwd=spec.workspace,
            env=_epoch_env(spec),
            capture_output=True,
            text=True,
            timeout=spec.timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PiExecutableNotFoundError(f"Pi binary not found: {spec.pi_bin}") from exc

    (spec.artifact_dir / "process.json").write_text(
        json.dumps(
            {
                "argv": argv,
                "returncode": proc.returncode,
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-2000:],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    session_start = spec.artifact_dir / "session_start.json"
    session_file: Path | None = None
    if session_start.is_file():
        try:
            recorded = json.loads(session_start.read_text(encoding="utf-8"))
            if isinstance(recorded.get("sessionFile"), str):
                session_file = Path(recorded["sessionFile"])
        except json.JSONDecodeError:
            session_file = None

    return LaunchResult(
        artifact_dir=spec.artifact_dir,
        session_file=session_file,
        roster=roster,
        runtime_version=pin.runtime_version,
        returncode=proc.returncode,
    )


def run_oracle_command(
    command: str,
    *,
    cwd: Path,
    env: Mapping[str, str],
    container: ContainerSpec | None,
    timeout_s: int = 600,
) -> float:
    """The existing ``command_succeeds`` oracle semantics: exit 0 -> 1.0.

    Same command shape as the Inspect lane's scorer (``bash -lc <command>``
    at the pinned cwd); only the executor location differs, which is
    environment, pinned in the harness pin. Any execution failure is a 0.0
    outcome only if the COMMAND ran and failed; an executor-level failure
    (no shell, container dead) raises PiLaunchError — apparatus, not a
    measured failure.
    """
    argv: list[str] = []
    if container is not None:
        argv.extend(container.argv_prefix)
    argv.extend(["bash", "-lc", command])
    try:
        proc = subprocess.run(  # noqa: S603 -- command is operator-authored
            argv,
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PiLaunchError(f"oracle executor unavailable: {exc}") from exc
    return 1.0 if proc.returncode == 0 else 0.0


def build_runner_block(
    *,
    pin: PiHarnessPin,
    parser: Mapping[str, str],
    treatment: RosterEntry,
    route: str,
    n_pairs: int,
    rat_fields: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """The registration-contract runner block, recorded verbatim at ingest.

    Base ratification fields (rat_id, ratification_path, skill_id,
    task_family, estimand) come from the ratified record when one exists and
    are absent otherwise — the same absent-vs-null convention the existing
    runner block keeps. ``model`` carries the measured provider/model form;
    ``route`` is declared separately (the route ambiguity precedent).
    """
    block: dict[str, object] = dict(rat_fields or {})
    block.update(
        {
            "route": route,
            "model": f"{pin.provider}/{pin.model}",
            "n_pairs": n_pairs,
            "runtime": {
                "name": pin.harness,
                "version": pin.runtime_version,
                "subject_layer": "pi-print",
            },
            "delivery_realization": {
                "exposure_construct": "v2-description-channel",
                "exposure_surface": EXPOSURE_SURFACE,
                "exposure_detector_version": EXPOSURE_REALIZATION_VERSION,
                "exposure_detector_digest": parser["semantic_digest"],
            },
            "invocation_realization": {
                "construct": "v1-branch-b",
                "channels": list(INVOCATION_CHANNELS),
                "detector_version": INVOCATION_REALIZATION_VERSION,
                "detector_digest": parser["semantic_digest"],
            },
            "parser": dict(parser),
            "environment": {
                "cwd": pin.cwd,
                "tool_allowlist": sorted(pin.tool_allowlist),
                "image_digest": pin.image_digest,
                "network_policy": pin.network_policy,
                "declared_env_hash": hashlib.sha256(
                    json.dumps(
                        dict(sorted(pin.declared_env.items())),
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "baseline_roster": [
                    BaselineSkill(s.name, s.path, s.skill_md_sha256).as_dict()
                    for s in pin.baseline_roster
                ],
                "treatment": {
                    "name": treatment.name,
                    "path": str(treatment.path),
                    "skill_md_sha256": treatment.skill_md_sha256,
                },
            },
        }
    )
    return block
