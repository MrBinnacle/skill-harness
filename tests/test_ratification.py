"""Ratification record schema + preflight gate decision (#57).

The RAT front-matter schema, the OBS front-matter schema, and the pure gate
decision are tested here at the module seam; the CLI refusal matrix lives in
tests/ablation/test_cli_ratification_gate.py. Front-matter parse fixtures
double as the RAT/OBS schema contract tests (ticket #57 acceptance criteria).

Fixture literals are hand-written against the ratified field lists:
- RAT load-bearing fields: #47 resolution (eleven-field checklist, mechanical
  run binding) + the #56 review carry-in (cost provenance must be the live
  cost_projection function for the record's gate).
- OBS fields: #41 resolution (task_family / arm / counts / model / date /
  evidence / pi_c / estimand / classification / disposition_of_record).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_harness.ratification import (
    DISCLOSURE_LINE,
    GateDecision,
    RatificationError,
    RefusalReason,
    check_execute_ratification,
    parse_frontmatter,
    parse_obs_frontmatter,
    parse_rat_record,
)

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

_VALID_FIELDS: dict[str, str] = {
    "rat": "RAT-0001",
    "status": "RATIFIED",
    "skill_id": "skill-abc",
    "task_family": "append-only-evidence-design",
    "estimand": "treatment-policy",
    "gate": "gate2",
    "n": "20",
    "worst_case_cost_usd": "15.55",
    "hard_cap_usd": "15.55",
    "cost_provenance": "project_pair_usd",
    "sme_status": "deliberated",
    "ratified_date": '"2026-08-02"',
}


def _rat_text(
    overrides: dict[str, str | None] | None = None,
    body: str = "# RAT-0001\n\nRecord body.\n",
) -> str:
    fields = dict(_VALID_FIELDS)
    for key, value in (overrides or {}).items():
        if value is None:
            fields.pop(key, None)
        else:
            fields[key] = value
    lines = "\n".join(f"{k}: {v}" for k, v in fields.items())
    return f"---\n{lines}\n---\n\n{body}"


def _write_rat(tmp_path: Path, text: str, name: str = "RAT-0001-skill-abc.md") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _decision(
    record: Path | None,
    *,
    skill_id: str = "skill-abc",
    task_family: str = "append-only-evidence-design",
    estimand: str = "treatment-policy",
    max_usd: float = 15.55,
) -> GateDecision:
    return check_execute_ratification(
        record,
        skill_id=skill_id,
        task_family=task_family,
        estimand=estimand,
        max_usd=max_usd,
    )


# ---------------------------------------------------------------------------
# Generic front-matter parser (one-level nesting, no external YAML dependency)
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_flat_scalars_parse_with_numeric_coercion(self) -> None:
        fm = parse_frontmatter('---\na: 1\nb: 2.5\nc: text\nd: "quoted"\n---\nbody\n')
        assert fm == {"a": 1, "b": 2.5, "c": "text", "d": "quoted"}

    def test_one_level_nesting_parses_as_dict(self) -> None:
        fm = parse_frontmatter("---\ncounts:\n  epochs: 3\n  passes: 3\ntop: x\n---\n")
        assert fm["counts"] == {"epochs": 3, "passes": 3}
        assert fm["top"] == "x"

    def test_missing_frontmatter_raises(self) -> None:
        with pytest.raises(RatificationError, match="front-matter"):
            parse_frontmatter("# no front matter\n")

    def test_unterminated_frontmatter_raises(self) -> None:
        with pytest.raises(RatificationError, match="front-matter"):
            parse_frontmatter("---\na: 1\nbody without closing fence\n")

    def test_malformed_line_raises(self) -> None:
        with pytest.raises(RatificationError, match="malformed"):
            parse_frontmatter("---\njust-a-token-no-colon\n---\n")


# ---------------------------------------------------------------------------
# RAT record schema
# ---------------------------------------------------------------------------


class TestParseRatRecord:
    def test_valid_record_parses(self, tmp_path: Path) -> None:
        record = parse_rat_record(_write_rat(tmp_path, _rat_text()))
        assert record.rat_id == "RAT-0001"
        assert record.status == "RATIFIED"
        assert record.skill_id == "skill-abc"
        assert record.task_family == "append-only-evidence-design"
        assert record.estimand == "treatment-policy"
        assert record.gate == "gate2"
        assert record.n == 20
        assert record.worst_case_cost_usd == 15.55
        assert record.hard_cap_usd == 15.55
        assert record.sme_status == "deliberated"

    def test_integral_cap_parses(self, tmp_path: Path) -> None:
        # "15" (int-looking) must coerce into the float cap fields.
        text = _rat_text({"worst_case_cost_usd": "15", "hard_cap_usd": "15"})
        record = parse_rat_record(_write_rat(tmp_path, text))
        assert record.hard_cap_usd == 15.0

    @pytest.mark.parametrize("missing", sorted(_VALID_FIELDS))
    def test_each_missing_field_is_an_error(self, tmp_path: Path, missing: str) -> None:
        path = _write_rat(tmp_path, _rat_text({missing: None}))
        with pytest.raises(RatificationError, match=missing):
            parse_rat_record(path)

    def test_unknown_extra_field_is_tolerated(self, tmp_path: Path) -> None:
        # Records grow by dated amendment; an extra front-matter field is not
        # an error (only the load-bearing mirror is schema-checked).
        text = _rat_text().replace("---\n\n#", "amendment_note: added-later\n---\n\n#")
        record = parse_rat_record(_write_rat(tmp_path, text))
        assert record.rat_id == "RAT-0001"

    def test_bad_rat_id_pattern_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(RatificationError, match="rat"):
            parse_rat_record(_write_rat(tmp_path, _rat_text({"rat": "RAT-1"})))

    def test_unknown_status_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(RatificationError, match="status"):
            parse_rat_record(_write_rat(tmp_path, _rat_text({"status": "APPROVED"})))

    def test_unregistered_estimand_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(RatificationError, match="estimand"):
            parse_rat_record(_write_rat(tmp_path, _rat_text({"estimand": "intention-to-treat"})))

    def test_na_estimand_rejected_for_rat(self, tmp_path: Path) -> None:
        # 'n/a' is the honest OBS marker for pre-registry observations; a
        # forward-looking ratification must use a registered estimand.
        with pytest.raises(RatificationError, match="estimand"):
            parse_rat_record(_write_rat(tmp_path, _rat_text({"estimand": "n/a"})))

    def test_unknown_gate_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(RatificationError, match="gate"):
            parse_rat_record(_write_rat(tmp_path, _rat_text({"gate": "gate3"})))

    def test_cap_above_evaluation_ceiling_rejected(self, tmp_path: Path) -> None:
        # $35 ceiling from cost_projection.EVALUATION_HARD_CAP_USD (#40).
        text = _rat_text({"worst_case_cost_usd": "35.01", "hard_cap_usd": "35.01"})
        with pytest.raises(RatificationError, match="35"):
            parse_rat_record(_write_rat(tmp_path, text))

    def test_cap_exactly_at_ceiling_allowed(self, tmp_path: Path) -> None:
        text = _rat_text({"worst_case_cost_usd": "35.00", "hard_cap_usd": "35.00"})
        record = parse_rat_record(_write_rat(tmp_path, text))
        assert record.hard_cap_usd == 35.0

    def test_cap_below_worst_case_rejected(self, tmp_path: Path) -> None:
        text = _rat_text({"worst_case_cost_usd": "15.56", "hard_cap_usd": "15.55"})
        with pytest.raises(RatificationError, match="worst"):
            parse_rat_record(_write_rat(tmp_path, text))

    def test_sub_cent_cap_rejected(self, tmp_path: Path) -> None:
        # #47: the cap to pass is the worst-case cost rounded UP to the cent —
        # a sub-cent cap cannot come from that rule.
        text = _rat_text({"worst_case_cost_usd": "15.551", "hard_cap_usd": "15.551"})
        with pytest.raises(RatificationError, match="cent"):
            parse_rat_record(_write_rat(tmp_path, text))

    def test_gate2_requires_pair_provenance(self, tmp_path: Path) -> None:
        text = _rat_text({"cost_provenance": "project_trial_usd"})
        with pytest.raises(RatificationError, match="cost_provenance"):
            parse_rat_record(_write_rat(tmp_path, text))

    def test_gate1_requires_trial_provenance(self, tmp_path: Path) -> None:
        good = _rat_text({"gate": "gate1", "cost_provenance": "project_trial_usd"})
        assert parse_rat_record(_write_rat(tmp_path, good)).gate == "gate1"
        bad = _rat_text({"gate": "gate1", "cost_provenance": "project_pair_usd"})
        with pytest.raises(RatificationError, match="cost_provenance"):
            parse_rat_record(_write_rat(tmp_path, bad, name="RAT-0002-x.md"))

    def test_self_certified_without_disclosure_line_rejected(self, tmp_path: Path) -> None:
        text = _rat_text({"sme_status": "self-certified"})
        with pytest.raises(RatificationError, match="disclosure"):
            parse_rat_record(_write_rat(tmp_path, text))

    def test_self_certified_with_disclosure_line_parses(self, tmp_path: Path) -> None:
        body = f"# RAT-0001\n\nThis record is {DISCLOSURE_LINE}.\n"
        text = _rat_text({"sme_status": "self-certified"}, body=body)
        record = parse_rat_record(_write_rat(tmp_path, text))
        assert record.sme_status == "self-certified"

    def test_nonpositive_n_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(RatificationError, match="n must"):
            parse_rat_record(_write_rat(tmp_path, _rat_text({"n": "0"})))


# ---------------------------------------------------------------------------
# OBS front-matter schema (#41 ratified field list; consumed by DC-13 later)
# ---------------------------------------------------------------------------

_OBS_TEXT = """---
obs: OBS-9999
task_family: example-family
arm: null-only-stage0
counts:
  epochs: 3
  passes: 3
model: anthropic/claude-sonnet-5
date: "2026-07-10"
evidence: store-ref
pi_c: not-instrumented
estimand: n/a
classification: DEFERRED
disposition_of_record: "Screened out 2026-07-10; standing"
---

# OBS-9999
"""


class TestParseObsFrontmatter:
    def test_valid_obs_parses(self, tmp_path: Path) -> None:
        path = tmp_path / "OBS-9999-example-family.md"
        path.write_text(_OBS_TEXT, encoding="utf-8")
        obs = parse_obs_frontmatter(path)
        assert obs.task_family == "example-family"
        assert obs.counts.epochs == 3
        assert obs.counts.passes == 3
        assert obs.classification == "DEFERRED"
        assert obs.estimand == "n/a"

    def test_missing_ratified_field_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "OBS-9998-broken.md"
        path.write_text(_OBS_TEXT.replace("pi_c: not-instrumented\n", ""), encoding="utf-8")
        with pytest.raises(RatificationError, match="pi_c"):
            parse_obs_frontmatter(path)

    def test_live_tree_obs_records_conform(self) -> None:
        # Read-only conformance sweep over the committed ledger: every OBS
        # record must parse against the #41 ratified field list. This test
        # deliberately does NOT touch docs/observations/ — DC-13 activation
        # stays owed to the first PR that modifies that surface.
        obs_dir = Path(__file__).resolve().parent.parent / "docs" / "observations"
        records = sorted(obs_dir.glob("OBS-*.md"))
        assert len(records) >= 6
        for path in records:
            obs = parse_obs_frontmatter(path)
            assert obs.classification == "DEFERRED"


# ---------------------------------------------------------------------------
# Pure gate decision (refusal reasons; CLI seam tested separately)
# ---------------------------------------------------------------------------


class TestCheckExecuteRatification:
    def test_happy_path_allows(self, tmp_path: Path) -> None:
        decision = _decision(_write_rat(tmp_path, _rat_text()))
        assert decision.allowed
        assert decision.reason is None

    def test_no_record_referenced_refuses(self) -> None:
        decision = _decision(None)
        assert not decision.allowed
        assert decision.reason == RefusalReason.RECORD_MISSING

    def test_nonexistent_path_refuses(self, tmp_path: Path) -> None:
        decision = _decision(tmp_path / "RAT-0404-absent.md")
        assert not decision.allowed
        assert decision.reason == RefusalReason.RECORD_MISSING

    def test_invalid_record_refuses(self, tmp_path: Path) -> None:
        path = _write_rat(tmp_path, _rat_text({"status": "APPROVED"}))
        decision = _decision(path)
        assert not decision.allowed
        assert decision.reason == RefusalReason.RECORD_INVALID

    def test_draft_status_refuses(self, tmp_path: Path) -> None:
        path = _write_rat(tmp_path, _rat_text({"status": "DRAFT"}))
        decision = _decision(path)
        assert not decision.allowed
        assert decision.reason == RefusalReason.STATUS_NOT_RATIFIED

    def test_cap_mismatch_refuses(self, tmp_path: Path) -> None:
        decision = _decision(_write_rat(tmp_path, _rat_text()), max_usd=15.54)
        assert not decision.allowed
        assert decision.reason == RefusalReason.CAP_MISMATCH

    def test_cap_equality_is_cent_precise(self, tmp_path: Path) -> None:
        # 15.55 parsed from text and 15.55 parsed by click must compare equal
        # regardless of binary float representation (compared as integer cents).
        decision = _decision(_write_rat(tmp_path, _rat_text()), max_usd=15.549999999999999)
        assert decision.allowed

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("skill_id", "other-skill"),
            ("task_family", "other-family"),
            ("estimand", "hypothetical"),
        ],
    )
    def test_scope_mismatch_refuses(self, tmp_path: Path, field: str, value: str) -> None:
        scope = {
            "skill_id": "skill-abc",
            "task_family": "append-only-evidence-design",
            "estimand": "treatment-policy",
        }
        scope[field] = value
        decision = _decision(
            _write_rat(tmp_path, _rat_text()),
            skill_id=scope["skill_id"],
            task_family=scope["task_family"],
            estimand=scope["estimand"],
        )
        assert not decision.allowed
        assert decision.reason == RefusalReason.SCOPE_MISMATCH
        assert field in decision.detail

    def test_status_checked_before_cap_and_scope(self, tmp_path: Path) -> None:
        # #47 orders the checks (a) status, (b) cap, (c) scope.
        path = _write_rat(tmp_path, _rat_text({"status": "DRAFT"}))
        decision = _decision(path, skill_id="other", max_usd=1.0)
        assert decision.reason == RefusalReason.STATUS_NOT_RATIFIED

    def test_undeclared_scope_refuses_with_named_gap(self, tmp_path: Path) -> None:
        # The CLI passes "" when --task-family / --estimand were not given:
        # the refusal must name the undeclared axis, not just "mismatch".
        decision = _decision(_write_rat(tmp_path, _rat_text()), task_family="", estimand="")
        assert not decision.allowed
        assert decision.reason == RefusalReason.SCOPE_MISMATCH
        assert "not declared" in decision.detail


# ---------------------------------------------------------------------------
# #421: hazard_action — a regex registered on the record, validated at parse
# ---------------------------------------------------------------------------


class TestHazardAction:
    """The hazard_action field is optional, but when present it must compile."""

    def test_hazard_action_absent_parses(self, tmp_path: Path) -> None:
        record = parse_rat_record(_write_rat(tmp_path, _rat_text()))
        assert record.hazard_action is None

    def test_hazard_action_present_parses(self, tmp_path: Path) -> None:
        text = _rat_text({"hazard_action": r"git\s+pull"})
        record = parse_rat_record(_write_rat(tmp_path, text))
        assert record.hazard_action == r"git\s+pull"

    def test_hazard_action_non_compiling_regex_refused_by_name(self, tmp_path: Path) -> None:
        """Negative control: a regex that does not compile is refused, naming the field."""
        text = _rat_text({"hazard_action": r"git(s+pull"})
        with pytest.raises(RatificationError, match="hazard_action"):
            parse_rat_record(_write_rat(tmp_path, text))

    def test_hazard_action_empty_string_refused(self, tmp_path: Path) -> None:
        text = _rat_text({"hazard_action": ""})
        with pytest.raises(RatificationError, match="hazard_action"):
            parse_rat_record(_write_rat(tmp_path, text))


# ---------------------------------------------------------------------------
# #421: pilot_subject_model + subject_change_waiver
# ---------------------------------------------------------------------------


class TestPilotSubjectModel:
    """pilot_subject_model is optional at parse time; subject_change_waiver is a nested block."""

    def test_pilot_subject_model_absent_parses(self, tmp_path: Path) -> None:
        record = parse_rat_record(_write_rat(tmp_path, _rat_text()))
        assert record.pilot_subject_model is None
        assert record.subject_change_waiver is None

    def test_pilot_subject_model_present_parses(self, tmp_path: Path) -> None:
        text = _rat_text({"pilot_subject_model": "claude-sonnet-5"})
        record = parse_rat_record(_write_rat(tmp_path, text))
        assert record.pilot_subject_model == "claude-sonnet-5"

    def test_subject_change_waiver_parses_as_nested_block(self, tmp_path: Path) -> None:
        text = _rat_text()
        text = text.replace(
            "---\n\n# RAT-0001",
            "subject_change_waiver:\n"
            "  reason: host had no Anthropic key\n"
            "  measurement: OBS-0007 measured sonnet-5 at the ceiling\n"
            '  date: "2026-09-03"\n'
            "---\n\n# RAT-0001",
        )
        record = parse_rat_record(_write_rat(tmp_path, text))
        assert record.subject_change_waiver is not None
        assert record.subject_change_waiver["reason"] == "host had no Anthropic key"
        assert "sonnet-5" in record.subject_change_waiver["measurement"]
        assert record.subject_change_waiver["date"] == "2026-09-03"
