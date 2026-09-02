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

from pathlib import Path

import pytest

from skill_harness.oc.gate2 import Gate2Design, MMESpec
from skill_harness.ratification import parse_rat_record
from skill_harness.subject.paired_launch import (
    ANTHROPIC_KEY_ENV,
    DIRECT_ROUTE,
    PairedLaunchRefusal,
    design_from_record,
    preflight_sized_run,
    resolve_direct_subject,
    runner_config_payload,
)

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


def test_preflight_passes_at_the_registered_figures(monkeypatch: pytest.MonkeyPatch) -> None:
    """CONTROL for the cap arm: the ratified row launches."""
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    record, design, config, worst_case = preflight_sized_run(
        ratification_path=RAT_0001,
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


def test_preflight_passes_exactly_at_the_breakeven(monkeypatch: pytest.MonkeyPatch) -> None:
    """At the measured breakeven the projection equals the cap, so it launches.

    This pins the boundary as an equality rather than a near-miss: if the
    comparison ever becomes strict-greater on a rounded figure, this case and
    the one below cannot both hold.
    """
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    _, _, _, worst_case = preflight_sized_run(
        ratification_path=RAT_0001,
        bare_model="claude-sonnet-5",
        input_tokens_per_pair=BREAKEVEN_INPUT_TOKENS,
        output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
    )
    assert worst_case == pytest.approx(23.36, abs=1e-9)


def test_one_token_over_the_breakeven_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """ARM: the knife-edge. 129 tokens of headroom, and this is token 130.

    A cent-rounded comparison passes this case, which is why the comparison is
    made in dollars: $23.360064 and $23.36 are the same 2336 cents, and the
    record's words are "above 353,850 input ... the row breaches the cap".
    """
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    with pytest.raises(PairedLaunchRefusal) as exc:
        preflight_sized_run(
            ratification_path=RAT_0001,
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


def test_runner_config_payload_is_json_shaped(monkeypatch: pytest.MonkeyPatch) -> None:
    """The payload the ingest records carries the route and the reference."""
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "sk-ant-test")
    _, _, config, _ = preflight_sized_run(
        ratification_path=RAT_0001,
        bare_model="claude-sonnet-5",
        input_tokens_per_pair=REGISTERED_INPUT_TOKENS,
        output_tokens_per_pair=REGISTERED_OUTPUT_TOKENS,
    )
    payload = runner_config_payload(config)
    assert payload["route"] == DIRECT_ROUTE
    assert payload["rat_id"] == "RAT-0001"
    assert payload["estimand"] == "treatment-policy"
    assert payload["n_pairs"] == 32
    assert payload["ratification_path"].endswith("RAT-0001-git-pull-rebase-trap.md")
    assert all(isinstance(value, (str, int)) for value in payload.values())
