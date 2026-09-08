"""Tests for the sized-paired-run launch gate (#409, under RAT-0001 / #391).

Every refusal here guards real spend, so each one is tested as an ARM with a
CONTROL beside it: the arm shows the refusal fires, the control shows it is not
simply always on. A refusal that fires unconditionally passes its own arm and
tells you nothing, which is how a broken gate reads as a working one.

The cap tests are the sharp ones. RAT-0001 Amendment 1 measured the ratified
row's true headroom at 129 input tokens per pair, so the pass/refuse boundary
here is one token wide and is asserted on both sides of it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from skill_harness.oc.gate2 import Gate2Design, MMESpec
from skill_harness.ratification import parse_rat_record
from skill_harness.subject.paired_launch import (
    ANTHROPIC_KEY_ENV,
    DIRECT_ROUTE,
    HAZARD_BASH_TOOL,
    HazardEntry,
    HazardVerdict,
    PairedLaunchRefusal,
    classify_hazard_command,
    design_from_record,
    hazard_entry_counts,
    preflight_sized_run,
    resolve_direct_subject,
    runner_config_payload,
    simple_commands,
)

_TS = "2026-09-01T12:00:00+00:00"

REPO = Path(__file__).resolve().parents[1]

#: The shipped RATIFIED record. Tests read the real record rather than a fixture
#: copy: a fixture would keep passing after the record changed, which is the one
#: failure this build exists to prevent.
RAT_0001 = REPO / "docs" / "ratifications" / "RAT-0001-git-pull-rebase-trap.md"

#: Registered figures, from section 6 of the record.
REGISTERED_INPUT_TOKENS = 353721.0
REGISTERED_OUTPUT_TOKENS = 2230.0

#: Amendment 1's measured breakeven. At this figure the projection lands exactly
#: on the cap; one token above it is a breach.
BREAKEVEN_INPUT_TOKENS = 353850.0


def _rat_text(**overrides: str) -> str:
    """Render a RAT record with the ratified front matter, minus overrides."""
    fields = {
        "rat": "RAT-0001",
        "status": "RATIFIED",
        "skill_id": "git-pull-rebase-trap",
        "task_family": "gitpull",
        "estimand": "treatment-policy",
        "gate": "gate2",
        "n": "32",
        "worst_case_cost_usd": "23.351744",
        "hard_cap_usd": "23.36",
        "cost_provenance": "project_pair_usd",
        "sme_status": "self-certified",
        "ratified_date": '"2026-09-02"',
        "gamma": "0.90",
        "delta_min": "0.20",
        "q_min": "0.70",
    }
    fields.update(overrides)
    lines = "\n".join(f"{key}: {value}" for key, value in fields.items())
    # The disclosure line is verbatim and load-bearing: parse_rat_record refuses
    # a self-certified record without it (#45 via #47). A fixture that omitted it
    # would make every case below fail on the parse and never reach the gate the
    # case is about.
    body = "# fixture record\n\ninternally derived, not externally deliberated\n"
    return f"---\n{lines}\n---\n\n{body}"


def _write_rat(tmp_path: Path, **overrides: str) -> Path:
    path = tmp_path / "RAT-0001-fixture.md"
    path.write_text(_rat_text(**overrides), encoding="utf-8")
    return path


def _rat_0001_with_pilot(tmp_path: Path, *, pilot: str = "claude-sonnet-5") -> Path:
    """Real RAT-0001 bytes plus pilot_subject_model so cap tests can launch.

    #421 refuses preflight when pilot_subject_model is missing; RAT-0001 is not
    edited (no launch under it is authorised). Cap-boundary tests need the
    shipped numbers, so they copy the record and inject only the pilot field.
    """
    text = RAT_0001.read_text(encoding="utf-8")
    needle = 'ratified_date: "2026-09-02"\n'
    if needle not in text:
        raise AssertionError("RAT-0001 front-matter shape changed; update the pilot inject")
    if "pilot_subject_model:" in text.split("---", 2)[1]:
        raise AssertionError("RAT-0001 already carries pilot_subject_model; drop the inject")
    text = text.replace(needle, f"{needle}pilot_subject_model: {pilot}\n", 1)
    path = tmp_path / "RAT-0001-with-pilot.md"
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# design_from_record: the design comes from the record, or not at all
# ---------------------------------------------------------------------------


def test_design_matches_the_shipped_ratified_record() -> None:
    """The real record yields exactly the design section 3 registers."""
    design = design_from_record(parse_rat_record(RAT_0001))
    assert design == Gate2Design(n_pairs=32, gamma=0.90, mme=MMESpec(delta_min=0.20, q_min=0.70))


def test_design_carries_no_threshold_table() -> None:
    """n = 32 is expressible. The batch-1 runner raised KeyError here."""
    assert design_from_record(parse_rat_record(RAT_0001)).n_pairs == 32


def test_draft_record_refuses(tmp_path: Path) -> None:
    """ARM: a DRAFT record has no signature, so it authorizes no run."""
    record = parse_rat_record(_write_rat(tmp_path, status="DRAFT"))
    with pytest.raises(PairedLaunchRefusal, match="DRAFT"):
        design_from_record(record)


def test_ratified_record_does_not_refuse(tmp_path: Path) -> None:
    """CONTROL for the arm above: the status check is not always on."""
    record = parse_rat_record(_write_rat(tmp_path))
    assert design_from_record(record).n_pairs == 32


def test_non_gate2_record_refuses(tmp_path: Path) -> None:
    """A Gate-1 record parses cleanly and still authorizes no paired run.

    ``cost_provenance`` moves with the gate because ``parse_rat_record`` binds
    the two: a gate1 record priced by ``project_pair_usd`` is refused at parse
    time, which would make this case pass on the wrong refusal.
    """
    record = parse_rat_record(
        _write_rat(tmp_path, gate="gate1", cost_provenance="project_trial_usd")
    )
    with pytest.raises(PairedLaunchRefusal, match="gate2"):
        design_from_record(record)


def test_missing_design_knob_refuses_by_name(tmp_path: Path) -> None:
    """A knob this module could not read is named, never defaulted."""
    text = _rat_text()
    text = "\n".join(line for line in text.splitlines() if not line.startswith("gamma:"))
    path = tmp_path / "no-gamma.md"
    path.write_text(text + "\n", encoding="utf-8")
    with pytest.raises(PairedLaunchRefusal, match="'gamma'"):
        design_from_record(parse_rat_record(path))


# ---------------------------------------------------------------------------
# resolve_direct_subject: the registered route, or a refusal
# ---------------------------------------------------------------------------


def test_direct_subject_string_is_inspects_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    assert resolve_direct_subject("claude-sonnet-5") == "anthropic/claude-sonnet-5"


def test_absent_key_refuses_and_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """ARM: no key is a refusal, and the message says it will not reroute.

    The failure this prevents is silent, not loud: the repository's own CLI
    rewrites a bare claude-sonnet-5 to an OpenRouter route when the key is
    missing, which here would spend a signed cap on a subject the record does
    not price.
    """
    monkeypatch.delenv(ANTHROPIC_KEY_ENV, raising=False)
    with pytest.raises(PairedLaunchRefusal) as exc:
        resolve_direct_subject("claude-sonnet-5")
    message = str(exc.value)
    assert ANTHROPIC_KEY_ENV in message
    assert "OpenRouter" in message


def test_empty_key_is_treated_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty string is not a credential. Measured on this host: the key was
    present-but-empty at User scope for five sessions while a doc asserted it
    was wired."""
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "   ")
    with pytest.raises(PairedLaunchRefusal, match=ANTHROPIC_KEY_ENV):
        resolve_direct_subject("claude-sonnet-5")


def test_already_routed_name_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    with pytest.raises(PairedLaunchRefusal, match="provider segment"):
        resolve_direct_subject("anthropic/claude-sonnet-5")


# ---------------------------------------------------------------------------
# preflight_sized_run: the cap boundary, one token wide
# ---------------------------------------------------------------------------


def test_preflight_passes_at_the_registered_figures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL for the cap arm: the ratified row launches."""
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    rat = _rat_0001_with_pilot(tmp_path)
    record, design, config, worst_case = preflight_sized_run(
        ratification_path=rat,
        bare_model="claude-sonnet-5",
        input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
        output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
    )
    assert record.rat_id == "RAT-0001"
    assert design.n_pairs == 32
    assert worst_case == pytest.approx(23.351744, abs=1e-6)
    assert worst_case <= record.hard_cap_usd
    assert config.route == DIRECT_ROUTE
    assert config.model == "anthropic/claude-sonnet-5"
    assert config.rat_id == "RAT-0001"


def test_preflight_passes_exactly_at_the_breakeven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At the measured breakeven the projection equals the cap, so it launches.

    This pins the boundary as an equality rather than a near-miss: if the
    comparison ever becomes strict-greater on a rounded figure, this case and
    the one below cannot both hold.
    """
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    _, _, _, worst_case = preflight_sized_run(
        ratification_path=_rat_0001_with_pilot(tmp_path),
        bare_model="claude-sonnet-5",
        input_tokens_per_pair=BREAKEVEN_INPUT_TOKENS,
        output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
    )
    assert worst_case == pytest.approx(23.36, abs=1e-9)


def test_one_token_over_the_breakeven_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ARM: the knife-edge. 129 tokens of headroom, and this is token 130.

    A cent-rounded comparison passes this case, which is why the comparison is
    made in dollars: $23.360064 and $23.36 are the same 2336 cents, and the
    record's words are "above 353,850 input ... the row breaches the cap".
    """
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    with pytest.raises(PairedLaunchRefusal) as exc:
        preflight_sized_run(
            ratification_path=_rat_0001_with_pilot(tmp_path),
            bare_model="claude-sonnet-5",
            input_tokens_per_pair=BREAKEVEN_INPUT_TOKENS + 1,
            output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
        )
    message = str(exc.value)
    assert "23.36" in message
    assert "does not launch" in message


def test_draft_record_refuses_on_status_not_on_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DRAFT record refuses on its status, with no credential present.

    Order matters: the cheap refusals come first, so a misconfigured launch
    fails without reaching the credential or the network. The assertion is on
    WHICH refusal fired -- both conditions hold here, and a gate that reported
    the key would be checking them in the wrong order.
    """
    monkeypatch.delenv(ANTHROPIC_KEY_ENV, raising=False)
    draft = _write_rat(tmp_path, status="DRAFT")
    with pytest.raises(PairedLaunchRefusal) as exc:
        preflight_sized_run(
            ratification_path=draft,
            bare_model="claude-sonnet-5",
            input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
            output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
        )
    message = str(exc.value)
    assert "RATIFIED" in message or "DRAFT" in message
    assert ANTHROPIC_KEY_ENV not in message


def test_runner_config_payload_is_json_shaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The payload the ingest records carries the route and the reference."""
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    rat = _rat_0001_with_pilot(tmp_path)
    _, _, config, _ = preflight_sized_run(
        ratification_path=rat,
        bare_model="claude-sonnet-5",
        input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
        output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
    )
    payload = runner_config_payload(config)
    assert payload["route"] == DIRECT_ROUTE
    assert payload["rat_id"] == "RAT-0001"
    assert payload["estimand"] == "treatment-policy"
    assert payload["n_pairs"] == 32
    assert payload["ratification_path"].endswith("RAT-0001-with-pilot.md")
    assert all(isinstance(value, (str, int)) for value in payload.values())


# ---------------------------------------------------------------------------
# #421: hazard_entry_counts — did the arm ever run the hazard action?
# ---------------------------------------------------------------------------

from importlib.util import find_spec  # noqa: E402
from types import SimpleNamespace  # noqa: E402

_INSPECT_INSTALLED = find_spec("inspect_ai") is not None

#: The oracle identity 0.5.0 implementation hash of subject/ingest.py (#424).
#: If this hash moves, ingest.py was edited and the oracle identity must bump
#: with regenerated mutation receipts.
_INGEST_PY_HASH = "d3064dd5c232d878b5c98a940bf3f7348c23747572f87f68e8cb14bbc31dea48"


def _bash_call(command: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="toolu_bash",
        function="Bash",
        arguments={"command": command},
        type="function",
    )


def _assistant(*calls: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(role="assistant", tool_calls=list(calls) or None)


def _fake_eval_log(
    *, epochs: int, hazard_commands: list[str], non_hazard_commands: list[str]
) -> SimpleNamespace:
    """A duck-typed eval log whose epochs alternate hazard / non-hazard bash calls.

    ``hazard_commands`` is the number of epochs whose bash call matches the
    pattern; the remaining epochs run ``non_hazard_commands`` (e.g. ``git fetch``).
    """
    samples = []
    for i in range(epochs):
        if i < len(hazard_commands):
            cmd = hazard_commands[i]
        else:
            cmd = non_hazard_commands[i % len(non_hazard_commands)]
        samples.append(
            SimpleNamespace(
                id=f"s{i}",
                epoch=i,
                messages=[_assistant(_bash_call(cmd))],
            )
        )
    return SimpleNamespace(samples=samples)


def _patch_read_eval_log(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
    """Make ``read_eval_log`` return ``fake``, with or without the inspect extra.

    The same three-line dance the tests above inline. Factored out here because
    the #438 cases below call it once per assertion and an inlined copy per case
    would bury what each case is actually asserting.
    """
    if _INSPECT_INSTALLED:
        import inspect_ai.log as inspect_log

        monkeypatch.setattr(inspect_log, "read_eval_log", lambda path: fake)
        return
    import sys
    import types

    fake_mod = types.ModuleType("inspect_ai.log")
    fake_mod.read_eval_log = lambda path: fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "inspect_ai", types.ModuleType("inspect_ai"))
    monkeypatch.setitem(sys.modules, "inspect_ai.log", fake_mod)


class TestHazardEntryCounts:
    """hazard_entry_counts counts epochs whose bash commands match the pattern."""

    def test_zero_of_32_when_no_epoch_ran_git_pull(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """0 of 32: no epoch ran `git pull` (all ran `git fetch` + `merge`)."""
        fake = _fake_eval_log(
            epochs=32,
            hazard_commands=[],
            non_hazard_commands=["git fetch origin main && git merge origin/main"],
        )
        if _INSPECT_INSTALLED:
            import inspect_ai.log as inspect_log

            monkeypatch.setattr(inspect_log, "read_eval_log", lambda path: fake)
        else:
            import sys
            import types

            fake_mod = types.ModuleType("inspect_ai.log")
            fake_mod.read_eval_log = lambda path: fake  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, "inspect_ai", types.ModuleType("inspect_ai"))
            monkeypatch.setitem(sys.modules, "inspect_ai.log", fake_mod)

        entry = hazard_entry_counts(tmp_path / "null.eval", r"git.*pull")
        assert entry.pattern == r"git.*pull"
        assert entry.epochs == 32
        assert entry.entered == 0

    def test_three_of_8_when_three_epochs_ran_git_pull(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """3 of 8: three epochs ran `git pull` (the pilot Null rate)."""
        fake = _fake_eval_log(
            epochs=8,
            hazard_commands=[
                "git pull",
                "git pull --rebase",
                "git -C /root pull",
                # with -C <path>
            ],
            non_hazard_commands=["git fetch origin main && git merge origin/main"],
        )
        if _INSPECT_INSTALLED:
            import inspect_ai.log as inspect_log

            monkeypatch.setattr(inspect_log, "read_eval_log", lambda path: fake)
        else:
            import sys
            import types

            fake_mod = types.ModuleType("inspect_ai.log")
            fake_mod.read_eval_log = lambda path: fake  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, "inspect_ai", types.ModuleType("inspect_ai"))
            monkeypatch.setitem(sys.modules, "inspect_ai.log", fake_mod)

        entry = hazard_entry_counts(tmp_path / "null.eval", r"git.*pull")
        assert entry.pattern == r"git.*pull"
        assert entry.epochs == 8
        assert entry.entered == 3

    def test_pattern_is_recorded_on_the_entry(self, tmp_path: Path) -> None:
        """The pattern the count was matched against is on the HazardEntry."""
        entry = HazardEntry(pattern=r"git\s+pull", epochs=32, entered=0)
        assert entry.pattern == r"git\s+pull"
        assert entry.epochs == 32
        assert entry.entered == 0

    def test_hazard_bash_tool_constant_is_bash(self) -> None:
        """The bash tool function name is registered as 'bash' (case-insensitive match)."""
        assert HAZARD_BASH_TOOL == "bash"


# ---------------------------------------------------------------------------
# #421: pilot_subject_model — a pilot on one subject cannot size a run on
# another silently
# ---------------------------------------------------------------------------


class TestPilotSubjectModel:
    """preflight_sized_run refuses when pilot_subject_model is missing or differs."""

    def test_missing_pilot_subject_model_refuses_by_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RAT-0001 refuses on the missing pilot_subject_model with no evidence_db.

        The check is always on (#421): omitting evidence_db must not skip it.
        """
        monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")

        with pytest.raises(PairedLaunchRefusal, match="pilot_subject_model"):
            preflight_sized_run(
                ratification_path=RAT_0001,
                bare_model="claude-sonnet-5",
                input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
                output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
            )

    def test_mismatched_pilot_subject_model_refuses_without_waiver(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pilot_subject_model != bare_model refuses without a subject_change_waiver."""
        monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")

        rat = tmp_path / "RAT-0001-fixture.md"
        text = _rat_text(pilot_subject_model="claude-sonnet-4.5")
        rat.write_text(text, encoding="utf-8")

        with pytest.raises(PairedLaunchRefusal, match="subject_change_waiver"):
            preflight_sized_run(
                ratification_path=rat,
                bare_model="claude-sonnet-5",
                input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
                output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
            )

    def test_mismatched_pilot_subject_model_passes_with_waiver(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pilot_subject_model != bare_model passes with a subject_change_waiver block."""
        monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")

        rat = tmp_path / "RAT-0001-fixture.md"
        text = _rat_text(pilot_subject_model="claude-sonnet-4.5")
        text = text.replace(
            "---\n\n# fixture record",
            "subject_change_waiver:\n"
            "  reason: host had no Anthropic key\n"
            "  measurement: OBS-0007 measured sonnet-5 at the ceiling\n"
            '  date: "2026-09-03"\n'
            "---\n\n# fixture record",
        )
        rat.write_text(text, encoding="utf-8")

        record, _design, _config, _worst = preflight_sized_run(
            ratification_path=rat,
            bare_model="claude-sonnet-5",
            input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
            output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
        )
        assert record.pilot_subject_model == "claude-sonnet-4.5"
        assert _design.n_pairs == 32

    def test_matching_pilot_subject_model_passes_without_waiver(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pilot_subject_model == bare_model launches; no waiver required."""
        monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
        record, design, _config, _worst = preflight_sized_run(
            ratification_path=_rat_0001_with_pilot(tmp_path),
            bare_model="claude-sonnet-5",
            input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
            output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
        )
        assert record.pilot_subject_model == "claude-sonnet-5"
        assert design.n_pairs == 32


# ---------------------------------------------------------------------------
# #421: prior_measurements — ledgered evidence printed before spend
# ---------------------------------------------------------------------------


class TestPriorMeasurements:
    """The dry run of RAT-0001 prints OBS-0007's screen row and refuses on pilot_subject_model."""

    def test_dry_run_prints_screen_row_and_refuses_on_missing_pilot_subject_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The real dry run: prints the screen row, then refuses on pilot_subject_model."""
        monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
        db = tmp_path / "evidence.db"
        from skill_harness.storage.migrations import open_evidence

        conn = open_evidence(db)
        # Seed a screen run matching OBS-0007's parameters:
        # git-pull-rebase-trap, claude-sonnet-5, Null 3 of 3, p0 = 1.
        screen_run_id = "dae60c17" + "0" * 24
        conn.execute(
            "INSERT INTO screen_runs (screen_run_id, skill_name, subject_model, "
            "harness_pin_fingerprint, source_eval_task_id, source_eval_sha256, "
            "admissibility_state, inadmissibility_reason, created_at, ingested_at) "
            "VALUES (?, ?, ?, NULL, ?, ?, 'admissible', NULL, ?, ?)",
            (
                screen_run_id,
                "git-pull-rebase-trap",
                "anthropic/claude-sonnet-5",
                "task-null-1",
                "dae60c17abcdef",
                _TS,
                _TS,
            ),
        )
        for epoch in range(3):
            conn.execute(
                "INSERT INTO screen_trials (screen_trial_id, screen_run_id, epoch, "
                "passed, scorer_name, scorer_explanation, output_sha256, sampled_at) "
                "VALUES (?, ?, ?, 1, 'command_succeeds', NULL, ?, ?)",
                (f"trial-{epoch}", screen_run_id, epoch, f"sha-{epoch}", _TS),
            )
        conn.commit()
        conn.close()

        with pytest.raises(PairedLaunchRefusal, match="pilot_subject_model"):
            preflight_sized_run(
                ratification_path=RAT_0001,
                bare_model="claude-sonnet-5",
                input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
                output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
                evidence_db=db,
            )

        captured = capsys.readouterr()
        assert "prior: screen run dae60c17" in captured.out
        assert "Null 3 of 3" in captured.out
        assert "p0 = 1.0000" in captured.out


# ---------------------------------------------------------------------------
# #421: ingest.py byte-identical — the oracle identity 0.4.1 hash is unchanged
# ---------------------------------------------------------------------------


class TestIngestOracleIdentity050:
    """#424: oracle metric identity 0.5.0 after the split-oracle ingest change."""

    def test_ingest_py_hash_matches_0_5_0_identity(self) -> None:
        """The oracle identity 0.5.0 implementation hash is the live ingest bytes."""
        import hashlib

        from skill_harness.subject import ingest as ingest_module

        live_hash = hashlib.sha256(Path(ingest_module.__file__).read_bytes()).hexdigest()
        assert live_hash == _INGEST_PY_HASH, (
            "subject/ingest.py was modified; the oracle identity 0.5.0 hash "
            f"moved from {_INGEST_PY_HASH} to {live_hash}. "
            "Bump ORACLE_METRIC_VERSION and regenerate mutation receipts."
        )

    def test_oracle_metric_version_is_0_5_0(self) -> None:
        from skill_harness.subject.ingest import ORACLE_METRIC_VERSION

        assert ORACLE_METRIC_VERSION == "0.5.0"


# ---------------------------------------------------------------------------
# #430: the gitpull screen reaches the store through the manifest, the D4
# supersession voids it, and prior_measurements says so instead of printing a
# ceiling the harness has discarded.
# ---------------------------------------------------------------------------

_GITPULL_EVAL_NAME = (
    "2026-07-21T03-05-28-00-00_git-pull-rebase-trap-null_E9uYtKBETxuAQtRHExMsTW.eval"
)
_D4_GITPULL_REASON = (
    "apparatus_void: D4 prompt leak; hit=RELEASING.md; searched=prompt,RELEASING.md"
)


def _gitpull_screen_log(*scores: float) -> object:
    """A ParsedEvalLog shaped like the OBS-0007 Null screen on the priced subject."""
    from skill_harness.subject.ingest import ParsedEvalLog, ParsedSample

    samples = tuple(
        ParsedSample(
            condition="null",
            skill_name="git-pull-rebase-trap",
            epoch=epoch,
            scorer_name="command_succeeds",
            score_value=score,
            invoked_skill=False,
            output_text=f"null-output-{epoch}",
            subject_model="anthropic/claude-sonnet-5",
            harness_pin_json=None,
            harness_pin_fingerprint="fp-obs-0007",
            input_tokens=100,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            output_tokens=10,
            usd=None,
        )
        for epoch, score in enumerate(scores, start=1)
    )
    return ParsedEvalLog(
        task_name="git-pull-rebase-trap-null",
        task_id="E9uYtKBETxuAQtRHExMsTW",
        created="2026-07-21T03:05:28+00:00",
        status="success",
        samples=samples,
    )


class TestPriorScreenVoidedByD4:
    """#430: seeded through the production writer, never by hand."""

    def _seed_through_manifest(self, tmp_path: Path, *, supersede: bool) -> tuple[Path, str]:
        """Apply the gitpull manifest entry into a temporary store; return (db, sha prefix)."""
        import hashlib

        from skill_harness.storage.migrations import open_evidence
        from skill_harness.subject.screen_backfill import (
            BATCH1_MANIFEST,
            apply_manifest,
            supersede_d4_screen_runs,
        )

        (entry,) = [e for e in BATCH1_MANIFEST if e.expected_skill == "git-pull-rebase-trap"]
        assert entry.rel_path.endswith(_GITPULL_EVAL_NAME)
        assert entry.admissibility_state == "admissible"
        root = tmp_path / "screens"
        log_path = root / entry.rel_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_bytes(b"obs-0007 stub bytes")
        sha_prefix = hashlib.sha256(b"obs-0007 stub bytes").hexdigest()[:8]

        db = tmp_path / "evidence.db"
        conn = open_evidence(db)
        try:
            report = apply_manifest(
                root,
                conn,
                manifest=(entry,),
                parse=lambda _path: _gitpull_screen_log(1.0, 1.0, 1.0),  # type: ignore[arg-type,return-value]
            )
            assert report.mismatches == ()
            if supersede:
                superseded = supersede_d4_screen_runs(conn)
                assert len(superseded) == 1
            conn.commit()
        finally:
            conn.close()
        return db, sha_prefix

    def test_voided_screen_prints_as_voided_not_as_a_ceiling(self, tmp_path: Path) -> None:
        """ARM: ingested and D4-superseded, exactly one voided line, no p0."""
        from skill_harness.subject.paired_launch import prior_measurements

        db, sha_prefix = self._seed_through_manifest(tmp_path, supersede=True)
        lines = prior_measurements(parse_rat_record(RAT_0001), db, "claude-sonnet-5")
        screen_lines = [line for line in lines if "screen run" in line]
        assert screen_lines == [
            f"prior: screen run {sha_prefix}, claude-sonnet-5, VOIDED ({_D4_GITPULL_REASON})"
        ]
        assert not any("p0 =" in line for line in screen_lines)

    def test_admissible_screen_still_prints_p0(self, tmp_path: Path) -> None:
        """NEGATIVE ARM (b): ingested, not superseded, the ceiling line prints, no voided line."""
        from skill_harness.subject.paired_launch import prior_measurements

        db, sha_prefix = self._seed_through_manifest(tmp_path, supersede=False)
        lines = prior_measurements(parse_rat_record(RAT_0001), db, "claude-sonnet-5")
        screen_lines = [line for line in lines if "screen run" in line]
        assert screen_lines == [
            f"prior: screen run {sha_prefix}, claude-sonnet-5, Null 3 of 3, p0 = 1.0000"
        ]
        assert not any("VOIDED" in line for line in screen_lines)

    def test_no_gitpull_row_prints_no_gitpull_line(self, tmp_path: Path) -> None:
        """NEGATIVE ARM (a): an empty store prints no screen line at all."""
        from skill_harness.storage.migrations import open_evidence
        from skill_harness.subject.paired_launch import prior_measurements

        db = tmp_path / "evidence.db"
        open_evidence(db).close()
        lines = prior_measurements(parse_rat_record(RAT_0001), db, "claude-sonnet-5")
        assert not any("screen run" in line for line in lines)


# ---------------------------------------------------------------------------
# #438: what the hazard pattern is matched AGAINST
#
# The registered pattern used to be matched against the whole command string a
# bash tool call carries, and the pattern registered for this family was
# `git\s+pull`. Both halves were wrong together: an agent that types
# `git pull --rebase` has chosen a strategy and has NOT walked into the trap,
# and an agent that chains `cd /root/project && git status && ...` puts several
# commands into one string that a blob regex cannot tell apart.
#
# The table below is the proof. It is written as cases rather than as reasoning
# because the defect it repairs passed every gate this repository had: the count
# was wrong, not the code path.
# ---------------------------------------------------------------------------

#: The pattern of record for the `git-pull-rebase-trap` family (RAT-0001
#: Amendment 5). Read: a `git pull` that IS the command being run, and whose
#: argument list carries no explicit rebase choice and no loud `--ff-only`
#: guard. `--no-ff` is deliberately NOT exempt -- it is the founding incident's
#: form, and `pull.rebase=true` silently ignores it.
_GIT_PULL_HAZARD_ACTION = r"^git pull\b(?!.*\s(?:--rebase|--no-rebase|-r|--ff-only)(?:\s|=|$))"

#: The pattern this ticket replaced, kept as the NEGATIVE CONTROL. Every case
#: where the two disagree is a count the instrument used to get wrong.
_NAIVE_HAZARD_ACTION = r"git\s+pull"

#: The three integration commands the pilot Null arm actually ran, verbatim from
#: the 2026-09-01 paired pilot log. All three are explicit-strategy pulls.
_PILOT_NULL_PULL = "git pull --rebase origin main"

#: The one real trap entry anywhere in the pilot corpus: Full arm, epoch 3.
_PILOT_FULL_TRAP = "git pull --no-ff origin main"


class TestHazardCommandCases:
    """The case table for `classify_hazard_command` under the pattern of record."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            # -- the hazard, in the forms it is actually typed ---------------
            ("git pull", HazardVerdict.ENTERED),
            ("git pull origin main", HazardVerdict.ENTERED),
            ("git   pull", HazardVerdict.ENTERED),
            (_PILOT_FULL_TRAP, HazardVerdict.ENTERED),
            ("cd /root/project && git pull", HazardVerdict.ENTERED),
            ("cd /root/project; git pull origin main", HazardVerdict.ENTERED),
            ("git pull 2>&1 | tee /tmp/out.log", HazardVerdict.ENTERED),
            ("git pull \\\n  origin main", HazardVerdict.ENTERED),
            # -- an explicit strategy is a choice, not a trap entry ----------
            (_PILOT_NULL_PULL, HazardVerdict.AVOIDED),
            ("git pull --no-rebase origin main", HazardVerdict.AVOIDED),
            ("git pull -r", HazardVerdict.AVOIDED),
            ("git pull --ff-only origin main", HazardVerdict.AVOIDED),
            ("git pull --rebase=merges", HazardVerdict.AVOIDED),
            ("git fetch origin && git pull --rebase && git push", HazardVerdict.AVOIDED),
            # -- the words appear, the command does not ----------------------
            ("echo 'git pull'", HazardVerdict.AVOIDED),
            ('git commit -m "note: git pull is banned here"', HazardVerdict.AVOIDED),
            ("git log --oneline | grep 'git pull'", HazardVerdict.AVOIDED),
            ("git status # remember to git pull later", HazardVerdict.AVOIDED),
            # -- the instrument cannot read it, and says so ------------------
            ('echo "unterminated', HazardVerdict.UNDECIDED),
            ("cat > note.txt <<'EOF'\ngit pull\nEOF", HazardVerdict.UNDECIDED),
        ],
    )
    def test_case(self, command: str, expected: HazardVerdict) -> None:
        assert classify_hazard_command(command, _GIT_PULL_HAZARD_ACTION) is expected

    def test_the_naive_pattern_disagrees_on_every_explicit_strategy_form(self) -> None:
        """The negative control: this is the over-count the ticket measured.

        Each of these is rated MUST PASS by the card's own acceptance table. The
        pattern that shipped counted all of them as hazard entries.
        """
        explicit = [
            _PILOT_NULL_PULL,
            "git pull --no-rebase origin main",
            "git pull -r",
            "git pull --ff-only origin main",
        ]
        for command in explicit:
            naive = classify_hazard_command(command, _NAIVE_HAZARD_ACTION)
            corrected = classify_hazard_command(command, _GIT_PULL_HAZARD_ACTION)
            assert naive is HazardVerdict.ENTERED
            assert corrected is HazardVerdict.AVOIDED

    def test_a_match_wins_over_an_unreadable_sibling_command(self) -> None:
        """A chain that pulls and also carries an unreadable command entered it.

        The trailing backslash makes `echo foo\\` unsplittable by shlex while
        the chain around it still segments, which is the only shape that reaches
        the per-segment undecided branch. The pull happened; the verdict says so.
        """
        command = "git pull && echo foo\\"
        assert classify_hazard_command(command, _GIT_PULL_HAZARD_ACTION) is HazardVerdict.ENTERED

    def test_a_config_write_beside_the_pull_is_counted_as_an_entry(self) -> None:
        """The genuinely ambiguous case, decided and stated rather than hidden.

        `git config pull.rebase true && git pull` sets the strategy in config and
        then runs a bare pull. Read one way the agent chose; read the other way
        it typed exactly the command the card forbids.

        The chosen behaviour is ENTERED, and the reason is a property of the
        instrument rather than a judgement about the agent: this reads COMMANDS,
        never repository state, so it cannot know what `pull.rebase` resolved to
        at the moment of the pull. Every exemption it grants is therefore an
        exemption written on the pull invocation itself. A config write is not.

        This is stated as a limit, not a solve. The common form in the real
        corpus is a config write in a SEPARATE tool call, which no per-command
        instrument can see at all; correcting for it needs an epoch-state read
        that this function deliberately does not do.
        """
        command = "git config pull.rebase true && git pull"
        assert classify_hazard_command(command, _GIT_PULL_HAZARD_ACTION) is HazardVerdict.ENTERED

    def test_a_strategy_set_on_the_git_invocation_is_not_an_entry(self) -> None:
        """`git -c pull.rebase=false pull` names the strategy and is exempt.

        Not by the exemption lookahead -- by the anchor. The command being run is
        `git -c ...`, so an anchored pattern does not match it. The same anchor
        means `git --no-pager pull`, which IS a bare pull, is missed as well.
        That is an undercount, and an undercount can only make the qualification
        gate refuse more often, never certify a candidate it should not.
        """
        assert (
            classify_hazard_command("git -c pull.rebase=false pull", _GIT_PULL_HAZARD_ACTION)
            is HazardVerdict.AVOIDED
        )
        assert (
            classify_hazard_command("git --no-pager pull", _GIT_PULL_HAZARD_ACTION)
            is HazardVerdict.AVOIDED
        )


class TestSimpleCommands:
    """The segmenter underneath the case table."""

    def test_splits_a_chain_on_every_unquoted_operator(self) -> None:
        command = "cd /root/project && git status || echo no; git log | head -3"
        assert simple_commands(command) == (
            "cd /root/project",
            "git status",
            "echo no",
            "git log",
            "head -3",
        )

    def test_does_not_split_inside_quotes(self) -> None:
        assert simple_commands("echo 'a && b; c | d'") == ("echo 'a && b; c | d'",)

    def test_does_not_split_a_redirection_that_contains_an_ampersand(self) -> None:
        """`2>&1` must survive. A bare `&` is not a separator for this reason."""
        assert simple_commands("git pull 2>&1") == ("git pull 2>&1",)

    def test_a_line_continuation_is_one_command(self) -> None:
        assert simple_commands("git pull \\\n  origin main") == ("git pull \\\n  origin main",)

    def test_an_unterminated_quote_is_unsegmentable(self) -> None:
        assert simple_commands('echo "unterminated') is None

    def test_a_heredoc_is_unsegmentable_but_a_here_string_is_not(self) -> None:
        assert simple_commands("cat <<EOF\ngit pull\nEOF") is None
        assert simple_commands("grep pull <<< 'git pull'") == ("grep pull <<< 'git pull'",)


class TestHazardUndecidedCounts:
    """An epoch the instrument cannot read is counted, not scored as avoided."""

    def test_an_unreadable_epoch_is_undecided_not_avoided(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _fake_eval_log(
            epochs=4,
            hazard_commands=["cat > n.txt <<'EOF'\ngit pull\nEOF"],
            non_hazard_commands=["git fetch origin main && git merge origin/main"],
        )
        _patch_read_eval_log(monkeypatch, fake)
        entry = hazard_entry_counts(tmp_path / "null.eval", _GIT_PULL_HAZARD_ACTION)
        assert entry.epochs == 4
        assert entry.entered == 0
        assert entry.undecided == 1

    def test_control_the_same_epoch_shape_with_a_real_pull_enters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The control beside the arm above: undecided is not simply always on."""
        fake = _fake_eval_log(
            epochs=4,
            hazard_commands=["git pull origin main"],
            non_hazard_commands=["git fetch origin main && git merge origin/main"],
        )
        _patch_read_eval_log(monkeypatch, fake)
        entry = hazard_entry_counts(tmp_path / "null.eval", _GIT_PULL_HAZARD_ACTION)
        assert entry.entered == 1
        assert entry.undecided == 0

    def test_the_pilot_null_arm_shape_reads_zero_not_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The defect, reproduced on the pilot Null arm's own commands.

        Three of the pilot's eight Null epochs ran `git pull --rebase origin
        main`. The shipped pattern read that as 3 of 8 entered. Zero of them met
        the hazard.
        """
        fake = _fake_eval_log(
            epochs=8,
            hazard_commands=[_PILOT_NULL_PULL] * 3,
            non_hazard_commands=["git rebase origin/main"],
        )
        _patch_read_eval_log(monkeypatch, fake)
        naive = hazard_entry_counts(tmp_path / "null.eval", _NAIVE_HAZARD_ACTION)
        assert naive.entered == 3
        _patch_read_eval_log(monkeypatch, fake)
        corrected = hazard_entry_counts(tmp_path / "null.eval", _GIT_PULL_HAZARD_ACTION)
        assert corrected.entered == 0
        assert corrected.undecided == 0

    def test_the_pilot_full_arm_shape_keeps_its_one_real_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The positive control: the repair does not zero the count everywhere."""
        fake = _fake_eval_log(
            epochs=8,
            hazard_commands=[
                _PILOT_FULL_TRAP,
                _PILOT_NULL_PULL,
                "git pull --no-rebase origin main",
            ],
            non_hazard_commands=["git fetch origin && git merge --no-ff origin/main"],
        )
        _patch_read_eval_log(monkeypatch, fake)
        entry = hazard_entry_counts(tmp_path / "null.eval", _GIT_PULL_HAZARD_ACTION)
        assert entry.entered == 1
        assert entry.undecided == 0


#: Where the 2026-09-01 pilot and sized logs live. Gitignored, ~2.9G, no remote,
#: and absent from every git worktree, so the test below can only run where the
#: archive is checked out. `SKILL_HARNESS_GITPULL_LOG_DIR` points it elsewhere.
_GITPULL_LOG_ENV = "SKILL_HARNESS_GITPULL_LOG_DIR"
_GITPULL_LOG_DEFAULT = Path(__file__).resolve().parents[1] / ".private/microrun/batch1/gitpull"

#: entered / undecided per log under the pattern of record, and the count the
#: shipped pattern gave. Keyed on a filename substring. Measured 2026-09-08 by
#: reading the logs; no model was called and nothing was spent.
_PILOT_LOG_EXPECTATIONS: tuple[tuple[str, str, int, int], ...] = (
    ("logs-stage1-paired", "null_3SiUbmkDQ9vnApkjbxNnbQ", 0, 3),
    ("logs-stage1-paired", "full_6PHRM7FrxY57YAQ48k3Zkv", 1, 4),
    ("logs-stage2-sized", "null_QXBt2fAgkETxQx2ktNgNiZ", 0, 0),
    ("logs-stage2-sized", "full_DnHPqwD7uZH8Fgm2sg78fQ", 0, 0),
    ("B_v2_deleaked", "null_hfzABDk9BDS9T385pCe5Nz", 0, 1),
    ("C_full_deleaked", "full_2Rww35xXAa5MKQksPFjjzQ", 0, 2),
)


@pytest.mark.skipif(not _INSPECT_INSTALLED, reason="needs the [inspect] extra to read .eval logs")
class TestPilotLogsUnderThePatternOfRecord:
    """The pattern of record, measured against the real logs it was chosen for.

    These logs are private and are not in the repository. Where they are absent
    the test SKIPS with the path it looked for -- it never passes, because a
    green tick on an unread fixture is exactly the reassurance this ticket was
    filed about.
    """

    @staticmethod
    def _log_dir() -> Path:
        override = os.environ.get(_GITPULL_LOG_ENV)
        directory = Path(override) if override else _GITPULL_LOG_DEFAULT
        if not directory.is_dir():
            pytest.skip(
                f"pilot logs not present at {directory} "
                f"(set {_GITPULL_LOG_ENV} to the gitpull log directory to run this)"
            )
        return directory

    def test_counts_reproduce_and_the_shipped_pattern_over_counted(self) -> None:
        directory = self._log_dir()
        for subdir, stem, expected_entered, naive_entered in _PILOT_LOG_EXPECTATIONS:
            matches = [p for p in directory.rglob("*.eval") if subdir in str(p) and stem in p.name]
            assert len(matches) == 1, f"expected exactly one log for {subdir}/{stem}: {matches}"
            log = matches[0]
            corrected = hazard_entry_counts(log, _GIT_PULL_HAZARD_ACTION)
            assert corrected.entered == expected_entered, f"{log.name} entered"
            assert corrected.undecided == 0, f"{log.name} undecided"
            naive = hazard_entry_counts(log, _NAIVE_HAZARD_ACTION)
            assert naive.entered == naive_entered, f"{log.name} naive entered"
