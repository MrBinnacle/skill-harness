"""Pi epoch artifacts -> ParsedEvalLog: the Pi lane's parse layer.

This module is the Pi realization of the role ``parse_eval_log`` plays for
the Inspect lane: project one runtime's native artifacts into the
runtime-neutral :class:`ParsedSample` / :class:`ParsedEvalLog` models that
``write_paired_evidence`` consumes. Everything scientific stays downstream:
this module computes per-epoch ``exposed_skill`` and ``invoked_skill``
verdicts and everything else is measurement plumbing.

Realizations (declared in the runner block, per the registration contract):

* **Exposure** — the SAME construct and the SAME detector function as the
  Inspect lane (``subject.ingest.detect_skill_exposure``, channel c), run
  over a message-normalized view of the FIRST captured provider request
  payload. The observation surface is Pi-specific:
  ``before_provider_request.payload`` (system field / system-role message),
  captured read-only by ``capture.ts``. It is not an Inspect transcript and
  is never labeled as one.
* **Invocation** — the #46 branch-(b) construct (a file-read of the
  treatment SKILL.md), which is the live body-load channel under Pi,
  plus explicit ``/skill:<name>`` expansion. The Claude ``Skill``-tool
  channel (v1 branch a) does not exist under Pi and is not claimed. Shell
  commands that read the file (``bash cat SKILL.md``) may go undetected;
  that undercount is the registered conservative direction.
* **Identity** — the session's model/thinking entries and per-message
  provider/model are verified against the launch identity; any post-initial
  change invalidates the epoch BEFORE ingest.

Parser identity (gate 3 of the registration): ``parser_identity()`` returns
this pipeline's version, content hash (parser + capture extension bytes)
and AST semantic digest (parser source, via the existing
``subject.implementation_identity`` machinery — no new algorithm). The
launcher refuses to spend when the live identity differs from the declared
one; the identity travels in ``config_json["runner"]["parser"]`` on every
Pi run.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from skill_harness.subject.implementation_identity import (
    IDENTITY_DIGEST_ALGO_VERSION,
    semantic_digest,
)
from skill_harness.subject.ingest import (
    ParsedEvalLog,
    ParsedSample,
    _extract_skill_description,
    detect_skill_exposure,
)
from skill_harness.subject.pi.pin import PiHarnessPin
from skill_harness.subject.pi.roster import RosterEntry

__all__ = [
    "EXPOSURE_REALIZATION_VERSION",
    "EXPOSURE_SURFACE",
    "INVOCATION_CHANNELS",
    "INVOCATION_REALIZATION_VERSION",
    "PI_PARSER_VERSION",
    "CaptureIncompleteError",
    "EpochSpec",
    "MidEpochIdentityChangeError",
    "ParseReport",
    "PiParseError",
    "RosterAttestationError",
    "build_parsed_log",
    "parse_epoch",
    "parser_identity",
]

PI_PARSER_VERSION: str = "0.1.0"

#: Declared exposure observation surface (construct = the registered
#: v2-description-channel; this string names the Pi realization of it).
EXPOSURE_SURFACE: str = "before_provider_request.payload.system"
EXPOSURE_REALIZATION_VERSION: str = "v2-description-channel:pi-payload-1"

#: Declared invocation channels (construct = #46 branch (b) + explicit
#: command; the Claude Skill-tool channel does not exist under Pi).
INVOCATION_CHANNELS: tuple[str, ...] = (
    "read-tool:skill-md-path",
    "slash-skill-expansion",
)
INVOCATION_REALIZATION_VERSION: str = "v1-branch-b:pi-read-1"

_CAPTURE_EXTENSION = Path(__file__).with_name("capture.ts")


class PiParseError(Exception):
    """Base refusal for the Pi parse layer — apparatus errors, not evidence."""


class CaptureIncompleteError(PiParseError):
    """The capture directory is missing artifacts an epoch requires."""


class RosterAttestationError(PiParseError):
    """The runtime-reported roster differs from the launcher-built roster."""


class MidEpochIdentityChangeError(PiParseError):
    """Model/provider/thinking identity moved after epoch initialization."""


@dataclass(frozen=True)
class EpochSpec:
    """Everything the launcher knows about one epoch before parsing it."""

    artifact_dir: Path
    condition: Literal["full", "null"]
    epoch: int
    scorer_name: str
    score_value: float  # existing oracle outcome: 1.0 pass, 0.0 fail
    skill_name: str
    skill_dir: Path
    pin: PiHarnessPin
    expected_roster: tuple[RosterEntry, ...]
    expected_provider: str
    expected_model: str
    expected_thinking_level: str


@dataclass(frozen=True)
class ParseReport:
    """The adapter-side audit trail for one parsed epoch.

    Not a scientific object: it records HOW the ParsedSample fields were
    obtained so a later reader can audit the classification without
    re-walking the raw artifacts.
    """

    session_id: str
    status: str
    exposed_skill: bool
    exposure_surface: str
    invoked_skill: bool
    invocation_channels_fired: tuple[str, ...]
    distinct_subject_models: tuple[str, ...]
    assistant_messages: int
    provider_requests: int
    roster_attested: tuple[str, ...] = field(default=())


def parser_identity() -> dict[str, str]:
    """This pipeline's identity: version + content hash + AST digest.

    ``content_hash`` covers this module's bytes AND the capture extension's
    bytes (NUL-joined, fixed order) — the capture half is TypeScript and has
    no canonicalizer, so its identity is byte-level tamper evidence only.
    ``semantic_digest`` covers this module's Python source through the
    existing ``subject.implementation_identity`` machinery (ast-shape-1):
    a comment-only edit moves the content hash but not the digest, the same
    two-layer split the oracle identity uses (#209).
    """
    parser_bytes = Path(__file__).read_bytes()
    capture_bytes = _CAPTURE_EXTENSION.read_bytes()
    content_hash = hashlib.sha256(parser_bytes + b"\0" + capture_bytes).hexdigest()
    return {
        "name": "skill_harness.subject.pi",
        "version": PI_PARSER_VERSION,
        "content_hash": content_hash,
        "semantic_digest": semantic_digest(parser_bytes.decode("utf-8")),
        "digest_algo_version": IDENTITY_DIGEST_ALGO_VERSION,
    }


# ---------------------------------------------------------------------------
# Capture/session loading
# ---------------------------------------------------------------------------


def _load_json(path: Path, *, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CaptureIncompleteError(f"missing {what}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CaptureIncompleteError(f"malformed {what}: {path}: {exc}") from exc


def _load_session_entries(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (header, entries) from a native Pi session JSONL."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise CaptureIncompleteError(f"missing session JSONL: {path}") from exc
    header: dict[str, Any] | None = None
    entries: list[dict[str, Any]] = []
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CaptureIncompleteError(
                f"malformed session JSONL {path} line {lineno}: {exc}"
            ) from exc
        if entry.get("type") == "session" and header is None:
            header = entry
        else:
            entries.append(entry)
    if header is None:
        raise CaptureIncompleteError(f"session JSONL {path} has no header entry")
    return header, entries


def _request_payloads(capture_dir: Path) -> list[dict[str, Any]]:
    requests_dir = capture_dir / "requests"
    first = requests_dir / "request-001.json"
    if not first.is_file():
        raise CaptureIncompleteError(f"missing mandatory first provider request: {first}")
    payloads: list[dict[str, Any]] = []
    for path in sorted(requests_dir.glob("request-*.json")):
        record = _load_json(path, what="provider request")
        payload = record.get("payload") if isinstance(record, dict) else None
        if not isinstance(payload, dict):
            raise CaptureIncompleteError(f"provider request {path} has no payload object")
        payloads.append(payload)
    return payloads


# ---------------------------------------------------------------------------
# Payload normalization for the SHARED exposure detector
# ---------------------------------------------------------------------------


def _payload_as_messages(payload: dict[str, Any]) -> list[object]:
    """Normalize a serialized provider payload to message-shaped objects.

    The shared detector (``detect_skill_exposure``) duck-types on
    ``message.content`` being a string or a list of text parts. Both known
    provider shapes are covered: Anthropic Messages (top-level ``system``,
    string or list of text blocks) and OpenAI-style (a ``system`` role
    entry in ``messages``). All roles are passed through, matching the
    detector's role-agnostic scan; anything unrecognized simply yields no
    match, which is the detector's conservative direction.
    """
    messages: list[object] = []
    system = payload.get("system")
    if isinstance(system, str | list):
        messages.append(SimpleNamespace(content=system))
    for message in payload.get("messages") or ():
        if isinstance(message, dict):
            messages.append(SimpleNamespace(content=message.get("content")))
    return messages


# ---------------------------------------------------------------------------
# Invocation: the registered Pi realization of #46 branch (b) + /skill:
# ---------------------------------------------------------------------------


def _canonical(path_text: str, *, cwd: Path) -> str:
    """Case-normalized absolute form for path comparison (Windows-safe)."""
    p = Path(path_text)
    if not p.is_absolute():
        p = cwd / p
    return os.path.normcase(str(p.resolve() if p.exists() else Path(os.path.abspath(p))))


def _skill_md_body(skill_dir: Path) -> str:
    """The post-frontmatter body of the treatment SKILL.md (for /skill:
    expansion detection: Pi inlines the body into the user message)."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    return parts[2].strip()


def _detect_invocation(
    *,
    session_entries: list[dict[str, Any]],
    events: list[dict[str, Any]],
    skill_md_path: Path,
    skill_body: str,
    session_cwd: Path,
) -> tuple[bool, tuple[str, ...]]:
    fired: list[str] = []

    # Channel 1: a read-tool call resolving to the treatment SKILL.md.
    target = _canonical(str(skill_md_path), cwd=session_cwd)
    for entry in session_entries:
        if entry.get("type") != "message":
            continue
        message = entry.get("message") or {}
        if message.get("role") != "assistant":
            continue
        for block in message.get("content") or ():
            if not isinstance(block, dict) or block.get("type") != "toolCall":
                continue
            if block.get("name") != "read":
                continue
            args = block.get("arguments") or {}
            path_text = args.get("path")
            if isinstance(path_text, str) and _canonical(path_text, cwd=session_cwd) == target:
                fired.append("read-tool:skill-md-path")
                break
        if fired:
            break

    # Channel 2: /skill:<name> expansion. Two observations of the same event:
    # the raw input text (pre-expansion, captured) and the expanded body in
    # the user message (persisted in the session). Either is sufficient;
    # neither can be produced by ordinary filesystem activity.
    skill_name = skill_md_path.parent.name
    for event in events:
        if event.get("name") != "input":
            continue
        text = ((event.get("data") or {}).get("text") or "").strip()
        if text.startswith(f"/skill:{skill_name}"):
            fired.append("slash-skill-expansion")
            break
    if "slash-skill-expansion" not in fired and skill_body:
        for entry in session_entries:
            if entry.get("type") != "message":
                continue
            message = entry.get("message") or {}
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str) and skill_body in content:
                fired.append("slash-skill-expansion")
                break
            if isinstance(content, list):
                for part in content:
                    if (
                        isinstance(part, dict)
                        and isinstance(part.get("text"), str)
                        and skill_body in part["text"]
                    ):
                        fired.append("slash-skill-expansion")
                        break
            if "slash-skill-expansion" in fired:
                break

    return bool(fired), tuple(fired)


# ---------------------------------------------------------------------------
# Identity verification (fail closed, pre-ingest)
# ---------------------------------------------------------------------------


def _verify_identity(
    *,
    session_entries: list[dict[str, Any]],
    events: list[dict[str, Any]],
    agent_start: dict[str, Any],
    expected_provider: str,
    expected_model: str,
    expected_thinking: str,
) -> tuple[str, ...]:
    """Refuse on any post-initialization identity movement.

    Returns the distinct ``provider/model`` subjects observed on assistant
    messages (exactly one on success — the measured subject, which is what
    lands on the ParsedSample, not the configured one).
    """
    expected_subject = f"{expected_provider}/{expected_model}"

    # The agent-start capture must agree with the launch identity.
    observed = agent_start.get("model") or {}
    if observed.get("provider") != expected_provider or observed.get("id") != expected_model:
        raise MidEpochIdentityChangeError(
            f"agent-start model {observed.get('provider')}/{observed.get('id')} "
            f"!= launch identity {expected_subject}"
        )
    if agent_start.get("thinkingLevel") != expected_thinking:
        raise MidEpochIdentityChangeError(
            f"agent-start thinking level {agent_start.get('thinkingLevel')!r} "
            f"!= launch identity {expected_thinking!r}"
        )

    # Session entries: the initial model_change / thinking_level_change pair
    # is expected (Pi records the launch selection); anything after it, or
    # any value disagreeing with the launch identity, invalidates the epoch.
    model_changes = [e for e in session_entries if e.get("type") == "model_change"]
    for i, change in enumerate(model_changes):
        subject = f"{change.get('provider')}/{change.get('modelId')}"
        if subject != expected_subject:
            raise MidEpochIdentityChangeError(
                f"session model_change #{i} set {subject} != {expected_subject}"
            )
        if i > 0:
            raise MidEpochIdentityChangeError(
                f"session carries {len(model_changes)} model_change entries; "
                "a mid-epoch change is an apparatus error, not metadata"
            )
    thinking_changes = [e for e in session_entries if e.get("type") == "thinking_level_change"]
    for i, change in enumerate(thinking_changes):
        if change.get("thinkingLevel") != expected_thinking:
            raise MidEpochIdentityChangeError(
                f"session thinking_level_change #{i} set "
                f"{change.get('thinkingLevel')!r} != {expected_thinking!r}"
            )
        if i > 0:
            raise MidEpochIdentityChangeError(
                f"session carries {len(thinking_changes)} thinking_level_change "
                "entries; a mid-epoch change is an apparatus error"
            )

    # Runtime events must not report a change either (defense in depth: the
    # capture stream and the session are independent records of the same run).
    for event in events:
        if event.get("name") == "model_select":
            data = event.get("data") or {}
            subject = f"{data.get('provider')}/{data.get('model')}"
            if subject != expected_subject:
                raise MidEpochIdentityChangeError(
                    f"model_select event reported {subject} != {expected_subject}"
                )
        if event.get("name") == "thinking_level_select":
            data = event.get("data") or {}
            if data.get("level") != expected_thinking:
                raise MidEpochIdentityChangeError(
                    f"thinking_level_select event reported "
                    f"{data.get('level')!r} != {expected_thinking!r}"
                )

    # Per-message identity: exactly one distinct subject across all
    # assistant messages, equal to the launch identity.
    subjects = {
        f"{(entry.get('message') or {}).get('provider')}/"
        f"{(entry.get('message') or {}).get('model')}"
        for entry in session_entries
        if entry.get("type") == "message"
        and (entry.get("message") or {}).get("role") == "assistant"
    }
    subjects.discard("None/None")
    if subjects and subjects != {expected_subject}:
        raise MidEpochIdentityChangeError(
            f"assistant messages carry subjects {sorted(subjects)}; "
            f"expected exactly {expected_subject}"
        )
    return tuple(sorted(subjects))


# ---------------------------------------------------------------------------
# Roster attestation (runtime-reported vs launcher-built)
# ---------------------------------------------------------------------------


def _attest_roster(
    agent_start: dict[str, Any], expected: tuple[RosterEntry, ...]
) -> tuple[str, ...]:
    options = agent_start.get("systemPromptOptions")
    if not isinstance(options, dict):
        raise RosterAttestationError(
            "capture carries no systemPromptOptions; the runtime roster cannot be attested"
        )
    skills = options.get("skills")
    if not isinstance(skills, list):
        raise RosterAttestationError(
            "systemPromptOptions.skills is absent; the runtime roster cannot be attested"
        )
    reported: dict[str, str] = {}
    for skill in skills:
        if not isinstance(skill, dict) or not isinstance(skill.get("name"), str):
            raise RosterAttestationError(
                f"systemPromptOptions.skills carries an unrecognized entry: {skill!r}"
            )
        reported[skill["name"]] = str(skill.get("filePath") or "")
    expected_names = {entry.name for entry in expected}
    if set(reported) != expected_names:
        raise RosterAttestationError(
            f"runtime roster {sorted(reported)} != launcher roster {sorted(expected_names)}"
        )
    for entry in expected:
        reported_path = reported[entry.name]
        if reported_path:
            reported_dir = str(Path(reported_path).parent)
            if os.path.normcase(reported_dir) != os.path.normcase(str(entry.path)):
                raise RosterAttestationError(
                    f"roster member {entry.name!r} reported at {reported_path}, "
                    f"expected under {entry.path}"
                )
    return tuple(sorted(reported))


# ---------------------------------------------------------------------------
# The parse entry point
# ---------------------------------------------------------------------------


def parse_epoch(spec: EpochSpec) -> tuple[ParsedSample, ParseReport]:
    """Parse one epoch's artifacts into a ParsedSample (+ audit report).

    Pure: reads artifacts, writes nothing. Every refusal is a PiParseError
    subclass raised BEFORE the sample exists, so a defective epoch never
    reaches ``write_paired_evidence`` at all.

    :param spec: the launcher's complete prior knowledge of the epoch,
        including the oracle outcome (``score_value``) measured against the
        epoch's final filesystem.
    """
    capture_dir = spec.artifact_dir
    session_start = _load_json(capture_dir / "session_start.json", what="session_start")
    agent_start = _load_json(capture_dir / "agent_start.json", what="agent_start")
    events_path = capture_dir / "events.jsonl"
    if not events_path.is_file():
        raise CaptureIncompleteError(f"missing events stream: {events_path}")
    events: list[dict[str, Any]] = []
    for lineno, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise CaptureIncompleteError(
                f"malformed events stream {events_path} line {lineno}: {exc}"
            ) from exc
    if not any(e.get("name") == "session_shutdown" for e in events):
        raise CaptureIncompleteError(
            f"events stream {events_path} has no session_shutdown; the epoch "
            "did not terminate cleanly"
        )

    payloads = _request_payloads(capture_dir)

    session_file = session_start.get("sessionFile")
    if not isinstance(session_file, str) or not session_file:
        raise CaptureIncompleteError("session_start.json records no sessionFile")
    header, session_entries = _load_session_entries(Path(session_file))
    session_id = str(header.get("id") or "")
    session_cwd = Path(str(session_start.get("cwd") or header.get("cwd") or "."))

    # --- adapter-owned pre-ingest gates (fail closed) ----------------------
    roster_attested = _attest_roster(agent_start, spec.expected_roster)
    subjects = _verify_identity(
        session_entries=session_entries,
        events=events,
        agent_start=agent_start,
        expected_provider=spec.expected_provider,
        expected_model=spec.expected_model,
        expected_thinking=spec.expected_thinking_level,
    )

    # --- status ------------------------------------------------------------
    assistant = [
        (e.get("message") or {})
        for e in session_entries
        if e.get("type") == "message" and (e.get("message") or {}).get("role") == "assistant"
    ]
    agent_ended = any(e.get("name") == "agent_end" for e in events)
    completed = any(m.get("stopReason") == "stop" for m in assistant)
    status = "success" if (agent_ended and completed) else "error"

    # --- exposure: shared detector, Pi-declared surface ---------------------
    description = _extract_skill_description(spec.skill_dir)
    exposed = detect_skill_exposure(_payload_as_messages(payloads[0]), description)

    # --- invocation: registered Pi realization -------------------------------
    invoked, channels_fired = _detect_invocation(
        session_entries=session_entries,
        events=events,
        skill_md_path=spec.skill_dir / "SKILL.md",
        skill_body=_skill_md_body(spec.skill_dir),
        session_cwd=session_cwd,
    )

    # --- usage + output ------------------------------------------------------
    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    cache_write = 0
    usd = 0.0
    have_usd = False
    for message in assistant:
        usage = message.get("usage") or {}
        input_tokens += int(usage.get("input") or 0)
        output_tokens += int(usage.get("output") or 0)
        cache_read += int(usage.get("cacheRead") or 0)
        cache_write += int(usage.get("cacheWrite") or 0)
        cost = usage.get("cost") or {}
        if isinstance(cost.get("total"), int | float):
            usd += float(cost["total"])
            have_usd = True

    final_text = ""
    for message in reversed(assistant):
        if message.get("stopReason") == "stop":
            final_text = "".join(
                block.get("text", "")
                for block in (message.get("content") or ())
                if isinstance(block, dict) and block.get("type") == "text"
            )
            break

    subject_model = subjects[0] if subjects else f"{spec.expected_provider}/{spec.expected_model}"

    sample = ParsedSample(
        condition=spec.condition,
        skill_name=spec.skill_name,
        epoch=spec.epoch,
        scorer_name=spec.scorer_name,
        score_value=spec.score_value,
        invoked_skill=invoked,
        exposed_skill=exposed,
        output_text=final_text,
        subject_model=subject_model,
        harness_pin_json=spec.pin.canonical_json(),
        harness_pin_fingerprint=spec.pin.fingerprint(),
        input_tokens=input_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
        output_tokens=output_tokens,
        usd=usd if have_usd else None,
    )
    report = ParseReport(
        session_id=session_id,
        status=status,
        exposed_skill=exposed,
        exposure_surface=EXPOSURE_SURFACE,
        invoked_skill=invoked,
        invocation_channels_fired=channels_fired,
        distinct_subject_models=tuple(subjects),
        assistant_messages=len(assistant),
        provider_requests=len(payloads),
        roster_attested=roster_attested,
    )
    return sample, report


def build_parsed_log(
    spec_condition: Literal["full", "null"],
    samples: tuple[ParsedSample, ...],
    *,
    session_ids: tuple[str, ...],
    created: str,
    status: str,
    skill_name: str,
) -> ParsedEvalLog:
    """Assemble one arm's ParsedEvalLog from its parsed epoch samples.

    ``task_id`` derives from the arm's session ids, so a re-ingested pair
    reproduces the same deterministic run id and ``AlreadyIngestedError``
    keeps its idempotency semantics.
    """
    task_id = (
        "pi-" + hashlib.sha256(("|".join(sorted(session_ids))).encode("utf-8")).hexdigest()[:32]
    )
    return ParsedEvalLog(
        task_name=f"pi:{skill_name}-{spec_condition}",
        task_id=task_id,
        created=created,
        status=status,
        samples=samples,
    )
