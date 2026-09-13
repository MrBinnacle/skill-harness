"""Seam tests for the Pi subject adapter (subject/pi).

Synthetic artifacts only — no Pi process, no model calls, no spend. The
fixtures mirror the measured artifact shapes from the 0.85.1 capability
probe: session JSONL v3, capture events.jsonl, agent_start.json with
systemPromptOptions.skills, requests/request-001.json with an Anthropic
Messages-shaped payload (top-level ``system``).

The seam under test: artifacts -> parse_epoch -> ParsedSample ->
write_paired_evidence (the REAL write path) with the existing refusal
predicates downstream and the adapter-owned refusals upstream.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from skill_harness.storage.migrations import open_evidence
from skill_harness.subject.ingest import (
    IngestResult,
    NullArmContaminationError,
    UnexposedFullEpochError,
    write_paired_evidence,
)
from skill_harness.subject.pi import (
    BaselineSkill,
    CaptureIncompleteError,
    EpochSpec,
    MidEpochIdentityChangeError,
    PiHarnessPin,
    PiRosterError,
    RosterAttestationError,
    build_parsed_log,
    build_roster,
    build_runner_block,
    parse_epoch,
    parser_identity,
    verify_pair_symmetry,
    verify_parser_identity,
)
from skill_harness.subject.pi.launcher import ParserIdentityMismatchError

SKILL_DESCRIPTION = "Never run git pull --rebase on a shared branch; merge instead."
SKILL_BODY = "# Rebase Trap\n\nWhen asked to pull, use git merge.\n"
SKILL_MD = f"---\nname: rebase-trap\ndescription: {SKILL_DESCRIPTION}\n---\n\n{SKILL_BODY}"
LISTING = (
    "The following skills provide specialized instructions.\n\n"
    "<available_skills>\n  <skill>\n    <name>rebase-trap</name>\n"
    f"    <description>{SKILL_DESCRIPTION}</description>\n"
    "    <location>/work/rebase-trap/SKILL.md</location>\n  </skill>\n</available_skills>"
)
PROVIDER = "openrouter"
MODEL = "anthropic/claude-3-haiku"
SUBJECT = f"{PROVIDER}/{MODEL}"
THINKING = "off"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_evidence(tmp_path / "evidence.db")
    yield connection
    connection.close()


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    d = tmp_path / "rebase-trap"
    d.mkdir()
    (d / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    return d


@pytest.fixture
def baseline_dir(tmp_path: Path) -> Path:
    d = tmp_path / "baseline-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: baseline-skill\ndescription: A baseline member.\n---\nbody\n",
        encoding="utf-8",
    )
    return d


def _pin(tmp_path: Path, baseline_dir: Path) -> PiHarnessPin:
    baseline = build_roster((baseline_dir,), None, "null")
    return PiHarnessPin(
        harness="pi",
        runtime_version="0.85.1",
        provider=PROVIDER,
        model=MODEL,
        thinking_level=THINKING,
        tool_allowlist=("read", "bash", "edit", "write"),
        cwd=str(tmp_path / "ws"),
        image_digest="local-host:no-container",
        network_policy="host",
        declared_env={"PATH": "/usr/bin"},
        secret_env_names=("OPENROUTER_API_KEY",),
        baseline_roster=tuple(
            BaselineSkill(e.name, str(e.path), e.skill_md_sha256) for e in baseline
        ),
        capture_extension_sha256="0" * 64,
    )


# ---------------------------------------------------------------------------
# Synthetic artifact builders (shapes measured on pi 0.85.1)
# ---------------------------------------------------------------------------


def _payload(*, exposed: bool) -> dict[str, object]:
    system = LISTING if exposed else "You are an assistant.\nCurrent working directory: /work"
    return {
        "model": MODEL,
        "system": system,
        "messages": [{"role": "user", "content": "Do the task."}],
        "tools": [{"type": "function", "function": {"name": n}} for n in ("read", "bash")],
        "max_tokens": 1024,
        "stream": True,
    }


def _session_entries(
    *,
    invoked: bool,
    slash: bool = False,
    model_changes: int = 1,
    wrong_initial_model: bool = False,
    stop: bool = True,
    skill_dir: Path,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {
            "type": "model_change",
            "id": "m0",
            "parentId": None,
            "timestamp": "2026-09-09T20:07:25Z",
            "provider": PROVIDER,
            "modelId": "anthropic/claude-3-opus" if wrong_initial_model else MODEL,
        },
        {
            "type": "thinking_level_change",
            "id": "t0",
            "parentId": "m0",
            "timestamp": "2026-09-09T20:07:25Z",
            "thinkingLevel": THINKING,
        },
        {
            "type": "message",
            "id": "u0",
            "parentId": "t0",
            "timestamp": "2026-09-09T20:07:25Z",
            "message": {
                "role": "user",
                "content": ("/skill:rebase-trap\n" + SKILL_BODY) if slash else "Do the task.",
                "timestamp": 1,
            },
        },
    ]
    if invoked and not slash:
        entries.append(
            {
                "type": "message",
                "id": "a0",
                "parentId": "u0",
                "timestamp": "2026-09-09T20:07:26Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "id": "c1",
                            "name": "read",
                            "arguments": {"path": str(skill_dir / "SKILL.md")},
                        }
                    ],
                    "provider": PROVIDER,
                    "model": MODEL,
                    "api": "anthropic-messages",
                    "usage": {"input": 100, "output": 5, "cacheRead": 0, "cacheWrite": 0},
                    "stopReason": "toolUse",
                    "timestamp": 2,
                },
            },
        )
        entries.append(
            {
                "type": "message",
                "id": "r0",
                "parentId": "a0",
                "timestamp": "2026-09-09T20:07:26Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "c1",
                    "toolName": "read",
                    "content": [{"type": "text", "text": SKILL_BODY}],
                    "isError": False,
                    "timestamp": 3,
                },
            },
        )
    # A SECOND change entry with the SAME subject: only the count guard may
    # fire, so the receipt mutant against that guard discriminates.
    for i in range(1, model_changes):
        entries.append(
            {
                "type": "model_change",
                "id": f"m{i}",
                "parentId": "u0",
                "timestamp": "2026-09-09T20:07:27Z",
                "provider": PROVIDER,
                "modelId": MODEL,
            },
        )
    entries.append(
        {
            "type": "message",
            "id": "a9",
            "parentId": "u0",
            "timestamp": "2026-09-09T20:07:28Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
                "provider": PROVIDER,
                "model": MODEL,
                "api": "anthropic-messages",
                "usage": {"input": 120, "output": 2, "cacheRead": 0, "cacheWrite": 0},
                "stopReason": "stop" if stop else "error",
                "timestamp": 4,
            },
        },
    )
    return entries


def make_epoch_dir(
    root: Path,
    name: str,
    *,
    exposed: bool,
    invoked: bool,
    skill_dir: Path,
    slash: bool = False,
    model_changes: int = 1,
    wrong_initial_model: bool = False,
    stop: bool = True,
    roster: list[str] | None = None,
    with_shutdown: bool = True,
    with_requests: bool = True,
) -> Path:
    capture = root / name
    (capture / "requests").mkdir(parents=True)
    session_dir = root / f"{name}-sessions"
    session_dir.mkdir()
    session_file = session_dir / "2026-09-09T20-07-25Z_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl"
    header = {
        "type": "session",
        "version": 3,
        "id": f"aaaaaaaa-bbbb-cccc-dddd-{name[:12].ljust(12, '0')}",
        "timestamp": "2026-09-09T20:07:25Z",
        "cwd": str(root),
    }
    lines = [json.dumps(header)] + [
        json.dumps(e)
        for e in _session_entries(
            invoked=invoked,
            slash=slash,
            model_changes=model_changes,
            wrong_initial_model=wrong_initial_model,
            stop=stop,
            skill_dir=skill_dir,
        )
    ]
    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    (capture / "session_start.json").write_text(
        json.dumps({"sessionFile": str(session_file), "cwd": str(root), "mode": "print"})
    )
    (capture / "agent_start.json").write_text(
        json.dumps(
            {
                "model": {"provider": PROVIDER, "id": MODEL},
                "thinkingLevel": THINKING,
                "systemPrompt": LISTING if exposed else "no listing",
                "systemPromptOptions": {
                    "skills": [
                        {"name": n, "filePath": str(root / n / "SKILL.md")} for n in (roster or [])
                    ],
                },
            }
        )
    )
    if with_requests:
        (capture / "requests" / "request-001.json").write_text(
            json.dumps(
                {"t": "2026-09-09T20:07:25Z", "index": 1, "payload": _payload(exposed=exposed)}
            )
        )
    events = [
        {"t": "2026-09-09T20:07:25Z", "name": "before_agent_start", "data": {}},
        {"t": "2026-09-09T20:07:28Z", "name": "agent_end", "data": {}},
    ]
    if slash:
        events.insert(
            0,
            {
                "t": "2026-09-09T20:07:25Z",
                "name": "input",
                "data": {"text": "/skill:rebase-trap", "source": "interactive"},
            },
        )
    if with_shutdown:
        events.append(
            {"t": "2026-09-09T20:07:28Z", "name": "session_shutdown", "data": {"reason": "quit"}}
        )
    (capture / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    return capture


def _spec(
    capture: Path,
    condition: str,
    *,
    skill_dir: Path,
    baseline_dir: Path,
    pin: PiHarnessPin,
    score: float = 1.0,
    epoch: int = 1,
) -> EpochSpec:
    roster = build_roster(
        (baseline_dir,),
        skill_dir if condition == "full" else None,
        condition,  # type: ignore[arg-type]
    )
    return EpochSpec(
        artifact_dir=capture,
        condition=condition,  # type: ignore[arg-type]
        epoch=epoch,
        scorer_name="command_succeeds",
        score_value=score,
        skill_name="rebase-trap",
        skill_dir=skill_dir,
        pin=pin,
        expected_roster=roster,
        expected_provider=PROVIDER,
        expected_model=MODEL,
        expected_thinking_level=THINKING,
    )


# ---------------------------------------------------------------------------
# Parser identity (gate 3)
# ---------------------------------------------------------------------------


def test_parser_identity_shape() -> None:
    identity = parser_identity()
    assert identity["version"]
    assert len(identity["content_hash"]) == 64
    assert len(identity["semantic_digest"]) == 64
    assert identity["digest_algo_version"] == "ast-shape-1"


def test_verify_parser_identity_refuses_mismatch() -> None:
    live = parser_identity()
    declared = dict(live)
    declared["content_hash"] = "0" * 64
    with pytest.raises(ParserIdentityMismatchError, match="content_hash"):
        verify_parser_identity(declared)


def test_verify_parser_identity_accepts_live() -> None:
    assert verify_parser_identity(parser_identity()) == parser_identity()


# ---------------------------------------------------------------------------
# Roster construction (adapter-owned apparatus validation)
# ---------------------------------------------------------------------------


def test_roster_full_is_baseline_plus_treatment(skill_dir: Path, baseline_dir: Path) -> None:
    roster = build_roster((baseline_dir,), skill_dir, "full")
    assert [e.name for e in roster] == ["baseline-skill", "rebase-trap"]


def test_roster_null_excludes_treatment(skill_dir: Path, baseline_dir: Path) -> None:
    roster = build_roster((baseline_dir,), None, "null")
    assert [e.name for e in roster] == ["baseline-skill"]
    with pytest.raises(PiRosterError, match="Null arm"):
        build_roster((baseline_dir,), skill_dir, "null")


def test_roster_refuses_duplicate_names(tmp_path: Path, skill_dir: Path) -> None:
    other = tmp_path / "other-dir"
    other.mkdir()
    (other / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    with pytest.raises(PiRosterError, match="collides"):
        build_roster((other,), skill_dir, "full")


def test_roster_refuses_missing_skill_md(tmp_path: Path) -> None:
    empty = tmp_path / "empty-skill"
    empty.mkdir()
    with pytest.raises(PiRosterError, match=r"no SKILL\.md"):
        build_roster((empty,), None, "null")


def test_pair_symmetry_checks(skill_dir: Path, baseline_dir: Path, tmp_path: Path) -> None:
    full = build_roster((baseline_dir,), skill_dir, "full")
    null = build_roster((baseline_dir,), None, "null")
    verify_pair_symmetry(full, null, full[-1])
    # A genuinely different baseline member (same layout, different bytes)
    # must refuse: the arms no longer share the baseline.
    drifted = tmp_path / "baseline-drifted"
    drifted.mkdir()
    (drifted / "SKILL.md").write_text(
        "---\nname: baseline-drifted\ndescription: Different bytes.\n---\nbody\n",
        encoding="utf-8",
    )
    drifted_null = build_roster((drifted,), None, "null")
    with pytest.raises(PiRosterError, match="baseline asymmetry"):
        verify_pair_symmetry(full, drifted_null, full[-1])
    with pytest.raises(PiRosterError, match="extra member"):
        verify_pair_symmetry(full, null, null[0])


# ---------------------------------------------------------------------------
# Parse: exposure, invocation, identity
# ---------------------------------------------------------------------------


def test_parse_full_exposed_invoked(tmp_path: Path, skill_dir: Path, baseline_dir: Path) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep1",
        exposed=True,
        invoked=True,
        skill_dir=skill_dir,
        roster=["baseline-skill", "rebase-trap"],
    )
    sample, report = parse_epoch(
        _spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin)
    )
    assert sample.exposed_skill is True
    assert sample.invoked_skill is True
    assert sample.subject_model == SUBJECT
    assert sample.harness_pin_fingerprint == pin.fingerprint()
    assert report.provider_requests == 1
    assert report.invocation_channels_fired == ("read-tool:skill-md-path",)


def test_parse_full_exposed_not_invoked(
    tmp_path: Path, skill_dir: Path, baseline_dir: Path
) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep2",
        exposed=True,
        invoked=False,
        skill_dir=skill_dir,
        roster=["baseline-skill", "rebase-trap"],
    )
    sample, _ = parse_epoch(
        _spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin)
    )
    assert sample.exposed_skill is True
    assert sample.invoked_skill is False


def test_parse_slash_skill_expansion_counts_as_invocation(
    tmp_path: Path, skill_dir: Path, baseline_dir: Path
) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep3",
        exposed=True,
        invoked=False,
        slash=True,
        skill_dir=skill_dir,
        roster=["baseline-skill", "rebase-trap"],
    )
    sample, report = parse_epoch(
        _spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin)
    )
    assert sample.invoked_skill is True
    assert "slash-skill-expansion" in report.invocation_channels_fired


def test_parse_relative_read_path_resolves_against_cwd(
    tmp_path: Path, skill_dir: Path, baseline_dir: Path
) -> None:
    """A read call with a RELATIVE path still resolves to the treatment SKILL.md."""
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep4",
        exposed=True,
        invoked=True,
        skill_dir=skill_dir,
        roster=["baseline-skill", "rebase-trap"],
    )
    # Rewrite the read call to a relative path (session cwd = tmp_path).
    session_file = json.loads((capture / "session_start.json").read_text())["sessionFile"]
    lines = Path(session_file).read_text().splitlines()
    entries = [json.loads(line) for line in lines]
    for e in entries:
        if e.get("type") == "message" and e["message"]["role"] == "assistant":
            for block in e["message"]["content"]:
                if block.get("type") == "toolCall":
                    block["arguments"]["path"] = "rebase-trap/SKILL.md"
    Path(session_file).write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    sample, _ = parse_epoch(
        _spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin)
    )
    assert sample.invoked_skill is True


def test_parse_null_clean(tmp_path: Path, skill_dir: Path, baseline_dir: Path) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep5",
        exposed=False,
        invoked=False,
        skill_dir=skill_dir,
        roster=["baseline-skill"],
    )
    sample, report = parse_epoch(
        _spec(capture, "null", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin, score=0.0)
    )
    assert sample.exposed_skill is False
    assert sample.invoked_skill is False
    assert report.status == "success"


def test_parse_refuses_mid_epoch_model_change(
    tmp_path: Path, skill_dir: Path, baseline_dir: Path
) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep6",
        exposed=True,
        invoked=True,
        skill_dir=skill_dir,
        model_changes=2,
        roster=["baseline-skill", "rebase-trap"],
    )
    with pytest.raises(MidEpochIdentityChangeError, match="model_change entries"):
        parse_epoch(_spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin))


def test_parse_refuses_initial_model_mismatch(
    tmp_path: Path, skill_dir: Path, baseline_dir: Path
) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep6b",
        exposed=True,
        invoked=True,
        skill_dir=skill_dir,
        wrong_initial_model=True,
        roster=["baseline-skill", "rebase-trap"],
    )
    with pytest.raises(MidEpochIdentityChangeError, match="!="):
        parse_epoch(_spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin))


def test_parse_refuses_missing_first_request(
    tmp_path: Path, skill_dir: Path, baseline_dir: Path
) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep7",
        exposed=True,
        invoked=True,
        skill_dir=skill_dir,
        roster=["baseline-skill", "rebase-trap"],
        with_requests=False,
    )
    with pytest.raises(CaptureIncompleteError, match="first provider request"):
        parse_epoch(_spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin))


def test_parse_refuses_incomplete_capture(
    tmp_path: Path, skill_dir: Path, baseline_dir: Path
) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep8",
        exposed=True,
        invoked=True,
        skill_dir=skill_dir,
        roster=["baseline-skill", "rebase-trap"],
        with_shutdown=False,
    )
    with pytest.raises(CaptureIncompleteError, match="session_shutdown"):
        parse_epoch(_spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin))


def test_parse_refuses_roster_mismatch(tmp_path: Path, skill_dir: Path, baseline_dir: Path) -> None:
    pin = _pin(tmp_path, baseline_dir)
    capture = make_epoch_dir(
        tmp_path,
        "ep9",
        exposed=True,
        invoked=True,
        skill_dir=skill_dir,
        roster=["baseline-skill", "unexpected-skill"],
    )
    with pytest.raises(RosterAttestationError, match="runtime roster"):
        parse_epoch(_spec(capture, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin))


# ---------------------------------------------------------------------------
# The seam: parsed epochs through the REAL write path
# ---------------------------------------------------------------------------


def _write_pi_pair(
    tmp_path: Path,
    conn: sqlite3.Connection,
    skill_dir: Path,
    baseline_dir: Path,
    *,
    full_exposed: bool = True,
    full_invoked: bool = True,
    null_exposed: bool = False,
    null_invoked: bool = False,
) -> IngestResult:
    pin = _pin(tmp_path, baseline_dir)
    full_cap = make_epoch_dir(
        tmp_path,
        "pairf",
        exposed=full_exposed,
        invoked=full_invoked,
        skill_dir=skill_dir,
        roster=["baseline-skill", "rebase-trap"],
    )
    null_cap = make_epoch_dir(
        tmp_path,
        "pairn",
        exposed=null_exposed,
        invoked=null_invoked,
        skill_dir=skill_dir,
        roster=["baseline-skill"],
    )
    full_sample, full_report = parse_epoch(
        _spec(full_cap, "full", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin)
    )
    null_sample, null_report = parse_epoch(
        _spec(null_cap, "null", skill_dir=skill_dir, baseline_dir=baseline_dir, pin=pin, score=0.0)
    )
    full_log = build_parsed_log(
        "full",
        (full_sample,),
        session_ids=(full_report.session_id,),
        created="2026-09-09T20:07:25Z",
        status=full_report.status,
        skill_name="rebase-trap",
    )
    null_log = build_parsed_log(
        "null",
        (null_sample,),
        session_ids=(null_report.session_id,),
        created="2026-09-09T20:07:25Z",
        status=null_report.status,
        skill_name="rebase-trap",
    )
    runner = build_runner_block(
        pin=pin,
        parser=parser_identity(),
        treatment=build_roster((skill_dir,), None, "null")[0],
        route="openrouter",
        n_pairs=1,
    )
    return write_paired_evidence(
        full=full_log,
        null=null_log,
        skill_dir=skill_dir,
        conn=conn,
        runner_config=runner,
    )


def test_seam_exposed_invoked_pair_writes(
    tmp_path: Path, conn: sqlite3.Connection, skill_dir: Path, baseline_dir: Path
) -> None:
    result = _write_pi_pair(tmp_path, conn, skill_dir, baseline_dir)
    assert result.admissibility_state == "admissible"
    assert result.pi_c.invocations == 1
    assert result.exposure.exposed_count == 1
    config = json.loads(
        conn.execute("SELECT config_json FROM runs WHERE run_id = ?", (result.run_id,)).fetchone()[
            0
        ]
    )
    assert config["runner"]["runtime"]["name"] == "pi"
    assert config["runner"]["runtime"]["version"] == "0.85.1"
    assert config["runner"]["delivery_realization"]["exposure_surface"] == (
        "before_provider_request.payload.system"
    )
    assert config["runner"]["parser"]["version"]
    assert config["runner"]["environment"]["treatment"]["name"] == "rebase-trap"


def test_seam_exposed_not_invoked_pair_writes_with_zero_pi_c(
    tmp_path: Path, conn: sqlite3.Connection, skill_dir: Path, baseline_dir: Path
) -> None:
    result = _write_pi_pair(tmp_path, conn, skill_dir, baseline_dir, full_invoked=False)
    assert result.admissibility_state == "admissible"
    assert result.pi_c.invocations == 0
    assert result.exposure.exposed_count == 1


def test_seam_unexposed_full_refuses(
    tmp_path: Path, conn: sqlite3.Connection, skill_dir: Path, baseline_dir: Path
) -> None:
    with pytest.raises(UnexposedFullEpochError):
        _write_pi_pair(tmp_path, conn, skill_dir, baseline_dir, full_exposed=False)


def test_seam_exposed_null_refuses(
    tmp_path: Path, conn: sqlite3.Connection, skill_dir: Path, baseline_dir: Path
) -> None:
    with pytest.raises(NullArmContaminationError):
        _write_pi_pair(tmp_path, conn, skill_dir, baseline_dir, null_exposed=True)


def test_seam_invoked_null_refuses(
    tmp_path: Path, conn: sqlite3.Connection, skill_dir: Path, baseline_dir: Path
) -> None:
    with pytest.raises(NullArmContaminationError):
        _write_pi_pair(tmp_path, conn, skill_dir, baseline_dir, null_invoked=True)
