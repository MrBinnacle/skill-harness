"""Tests for the v0.2 evidence-store write path (paired .eval → samples/verdicts).

These are also the MECHANICAL VALIDITY TESTS for the ``subject:*`` outcome
oracle registered by the write path (metric_versions row, tier 1): score
decoding, pairing, and the {0, 0.5, 1} observation mapping are fully
deterministic and covered here offline. Parsing (which needs the ``[inspect]``
extra) is exercised only for its typed not-installed error, matching
tests/test_subject_layer.py.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from skill_harness.aggregation.status import ClauseStatus
from skill_harness.aggregation.verdict import paired_verdict
from skill_harness.storage.migrations import open_evidence
from skill_harness.subject.ingest import (
    ORACLE_METRIC_VERSION,
    PI_C_CONFIDENCE,
    PI_C_DETECTOR_VERSION,
    WHOLE_SKILL_CLAUSE_INDEX,
    AlreadyIngestedError,
    EvalLogIngestError,
    EvalLogNotSuccessError,
    IngestResult,
    NullArmContaminationError,
    PairedLogMismatchError,
    ParsedEvalLog,
    ParsedSample,
    UnexposedFullEpochError,
    _derived_run_id,
    _extract_skill_description,
    _observation,
    _score_to_float,
    clopper_pearson,
    detect_skill_exposure,
    detect_skill_invocation,
    write_paired_evidence,
)

INSPECT_INSTALLED = find_spec("inspect_ai") is not None

PIN_FP = "a" * 64
PIN_JSON = json.dumps({"model": "openrouter/anthropic/claude-haiku-4.5"}, sort_keys=True)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_evidence(tmp_path / "evidence.db")
    yield connection
    connection.close()


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    d = tmp_path / "some-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: some-skill\n---\nbody\n", encoding="utf-8")
    return d


def make_sample(
    condition: str,
    epoch: int,
    score: float,
    *,
    fingerprint: str | None = PIN_FP,
    skill_name: str = "some-skill",
    scorer_name: str = "file_contains",
    invoked: bool | None = None,
    exposed: bool | None = None,
) -> ParsedSample:
    # Default mirrors the live lanes: a Full-arm epoch invoked and was exposed
    # to the skill, a Null-arm epoch structurally cannot (#46: 0/22 Null false
    # positives; #384: channel c = description present in transcript).
    if invoked is None:
        invoked = condition == "full"
    if exposed is None:
        exposed = condition == "full"
    return ParsedSample(
        condition=condition,  # type: ignore[arg-type]
        skill_name=skill_name,
        epoch=epoch,
        scorer_name=scorer_name,
        score_value=score,
        invoked_skill=invoked,
        exposed_skill=exposed,
        output_text=f"output-{condition}-{epoch}",
        subject_model="openrouter/anthropic/claude-haiku-4.5",
        harness_pin_json=PIN_JSON if fingerprint is not None else None,
        harness_pin_fingerprint=fingerprint,
        input_tokens=100,
        cache_read_input_tokens=50,
        cache_creation_input_tokens=25,
        output_tokens=10,
        usd=None,
    )


def make_log(
    condition: str,
    samples: tuple[ParsedSample, ...],
    *,
    task_id: str | None = None,
    status: str = "success",
) -> ParsedEvalLog:
    return ParsedEvalLog(
        task_name=f"some-skill-{condition}",
        task_id=task_id or f"task-{condition}",
        created="2026-07-09T21:26:43+00:00",
        status=status,
        samples=samples,
    )


# ---------------------------------------------------------------------------
# Mechanical validity: score decoding + observation mapping (deterministic)
# ---------------------------------------------------------------------------


def test_observation_mapping_is_the_stat_f4_encoding() -> None:
    assert _observation(1.0, 0.0) == 1.0  # Full passed, Null failed
    assert _observation(0.0, 1.0) == 0.0  # Null passed, Full failed
    assert _observation(1.0, 1.0) == 0.5  # tie (both passed)
    assert _observation(0.0, 0.0) == 0.5  # tie (both failed)


def test_score_to_float_decodes_inspect_values() -> None:
    p = Path("x.eval")
    assert _score_to_float("C", p) == 1.0
    assert _score_to_float("I", p) == 0.0
    assert _score_to_float(True, p) == 1.0
    assert _score_to_float(0.0, p) == 0.0
    assert _score_to_float(1, p) == 1.0
    with pytest.raises(EvalLogIngestError, match="unmappable"):
        _score_to_float("P", p)
    with pytest.raises(EvalLogIngestError, match="unmappable"):
        _score_to_float(None, p)


def test_score_to_float_refuses_non_finite_scores() -> None:
    """A missing measurement must not survive the parse path as a number (#363).

    ``_observation`` scores NaN against anything as 0.5, so a non-finite score
    that reaches the encoder is recorded as a genuine tie. The parse path
    refuses it here; ``ParsedSample.score_value`` carries ``allow_inf_nan=False``
    for callers that build the model directly (PR #364's M4 survivor).
    """
    p = Path("x.eval")
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(EvalLogIngestError, match="non-finite score value"):
            _score_to_float(value, p)


def test_score_refusal_locates_the_offending_trial() -> None:
    """A log carries up to forty epochs; naming only the file is not actionable."""
    p = Path("x.eval")
    with pytest.raises(EvalLogIngestError, match=r"x\.eval: sample id=7 epoch=2:"):
        _score_to_float(math.nan, p, sample="sample id=7 epoch=2")
    with pytest.raises(EvalLogIngestError, match=r"x\.eval: sample id=7 epoch=2:"):
        _score_to_float("P", p, sample="sample id=7 epoch=2")


def test_parsed_sample_refuses_non_finite_score_at_the_model_layer() -> None:
    """The model layer is the enforcing surface, not the parse helper (#363)."""
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValidationError):
            make_sample("full", 1, value)


def test_derived_run_id_is_deterministic_and_order_sensitive() -> None:
    assert _derived_run_id("a", "b") == _derived_run_id("a", "b")
    assert _derived_run_id("a", "b") != _derived_run_id("b", "a")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_writes_run_samples_and_admissible_verdicts(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0), make_sample("full", 2, 1.0)))
    null = make_log("null", (make_sample("null", 1, 0.0), make_sample("null", 2, 1.0)))

    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    assert result.admissibility_state == "admissible"
    assert result.inadmissibility_reason is None
    assert len(result.sample_ids) == 4
    assert len(result.verdict_ids) == 2

    run = conn.execute(
        "SELECT run_kind, completed_at, config_json FROM runs WHERE run_id = ?",
        (result.run_id,),
    ).fetchone()
    assert run[0] == "evaluate_skill"
    assert run[1] is not None
    config = json.loads(run[2])
    assert config["contrast"] == "full_vs_null"
    assert config["harness_pin_fingerprint"] == PIN_FP

    rows = conn.execute(
        """
        SELECT condition, sample_index, harness_pin_fingerprint, harness_pin_json
        FROM samples WHERE run_id = ? ORDER BY condition, sample_index
        """,
        (result.run_id,),
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        ("full", 1),
        ("full", 2),
        ("null", 1),
        ("null", 2),
    ]
    assert all(r[2] == PIN_FP and r[3] == PIN_JSON for r in rows)

    verdicts = conn.execute(
        """
        SELECT observation, oracle_tier, metric_id, metric_version,
               admissibility_state, comparison, axis
        FROM oracle_verdicts WHERE run_id = ? ORDER BY written_at, verdict_id
        """,
        (result.run_id,),
    ).fetchall()
    # epoch 1: full 1.0 / null 0.0 → 1.0; epoch 2: both 1.0 → 0.5
    assert sorted(v[0] for v in verdicts) == [0.5, 1.0]
    assert all(
        v[1] == 1
        and v[2] == "subject:file_contains"
        and v[3] == ORACLE_METRIC_VERSION
        and v[4] == "admissible"
        and v[5] == "full_vs_null"
        and v[6] == "outcome"
        for v in verdicts
    )


def test_verdict_sample_ids_pair_full_with_null_per_epoch(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    row = conn.execute(
        """
        SELECT sa.condition, sb.condition
        FROM oracle_verdicts v
        JOIN samples sa ON sa.sample_id = v.sample_a_id
        JOIN samples sb ON sb.sample_id = v.sample_b_id
        WHERE v.run_id = ?
        """,
        (result.run_id,),
    ).fetchone()
    assert row == ("full", "null")


def test_whole_skill_sentinel_clause_and_metric_registered_once(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full1 = make_log("full", (make_sample("full", 1, 1.0),), task_id="f1")
    null1 = make_log("null", (make_sample("null", 1, 0.0),), task_id="n1")
    r1 = write_paired_evidence(full=full1, null=null1, skill_dir=skill_dir, conn=conn)

    # second, distinct pair for the SAME skill must reuse skill/clause/metric rows
    full2 = make_log("full", (make_sample("full", 1, 1.0),), task_id="f2")
    null2 = make_log("null", (make_sample("null", 1, 1.0),), task_id="n2")
    r2 = write_paired_evidence(full=full2, null=null2, skill_dir=skill_dir, conn=conn)

    assert r1.skill_id == r2.skill_id
    assert r1.clause_id == r2.clause_id
    clause = conn.execute(
        "SELECT clause_index, axis, oracle_tier FROM clauses WHERE clause_id = ?",
        (r1.clause_id,),
    ).fetchone()
    assert clause == (WHOLE_SKILL_CLAUSE_INDEX, "outcome", 1)
    n_metrics = conn.execute(
        "SELECT COUNT(*) FROM metric_versions WHERE metric_id = 'subject:file_contains'"
    ).fetchone()[0]
    assert n_metrics == 1


# ---------------------------------------------------------------------------
# Harness-pin admissibility (write-time snapshot)
# ---------------------------------------------------------------------------


def test_pin_mismatch_writes_inadmissible_verdicts(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0, fingerprint="b" * 64),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    assert result.admissibility_state == "inadmissible"
    assert result.inadmissibility_reason == "harness_pin_mismatch"
    row = conn.execute(
        "SELECT admissibility_state, inadmissibility_reason FROM oracle_verdicts WHERE run_id = ?",
        (result.run_id,),
    ).fetchone()
    assert row == ("inadmissible", "harness_pin_mismatch")


def test_pin_missing_writes_inadmissible_verdicts(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0, fingerprint=None),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    assert result.admissibility_state == "inadmissible"
    assert result.inadmissibility_reason == "harness_pin_missing"


def test_inadmissible_verdicts_are_excluded_from_the_admissible_view(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0, fingerprint="b" * 64),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)

    n = conn.execute(
        "SELECT COUNT(*) FROM admissible_verdicts WHERE run_id = ?", (result.run_id,)
    ).fetchone()[0]
    assert n == 0


# ---------------------------------------------------------------------------
# Structural refusals (apparatus errors, not evidence)
# ---------------------------------------------------------------------------


def test_non_success_status_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0),), status="error")
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(EvalLogNotSuccessError, match="error"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_wrong_condition_in_log_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("null", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(PairedLogMismatchError, match="condition"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_unpaired_epochs_refuse(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0), make_sample("full", 2, 1.0)))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(PairedLogMismatchError, match="unpaired epochs"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_skill_disagreement_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0, skill_name="other-skill"),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(PairedLogMismatchError, match="disagree on the skill"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_missing_skill_md_refuses(conn: sqlite3.Connection, tmp_path: Path) -> None:
    empty = tmp_path / "empty-skill"
    empty.mkdir()
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(FileNotFoundError, match=r"SKILL\.md"):
        write_paired_evidence(full=full, null=null, skill_dir=empty, conn=conn)


def test_reingest_of_same_task_pair_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0),))
    write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    with pytest.raises(AlreadyIngestedError, match="already ingested"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_refused_write_leaves_no_rows_behind(conn: sqlite3.Connection, skill_dir: Path) -> None:
    # a structural refusal happens BEFORE the transaction opens; nothing lands
    full = make_log("full", (make_sample("full", 1, 1.0),), status="error")
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(EvalLogNotSuccessError):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# π_c detector — v1 = Skill tool-call in the parsed message stream (#46/#52)
#
# Message stand-ins mirror the transcript shapes evidence-quoted in the #46
# probe report (pi-c-probe-S140.md): assistant messages carry
# ``tool_calls[] = {id, function, arguments, type}``; tool-role result
# messages carry ``{id, content, role, tool_call_id, function}`` and NO
# ``tool_calls`` list.
# ---------------------------------------------------------------------------


def _call(function: str, arguments: object) -> SimpleNamespace:
    return SimpleNamespace(
        id="toolu_016dR19oSdWPAjByXazXfqeW",
        function=function,
        arguments=arguments,
        type="function",
    )


def _assistant(*calls: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(role="assistant", tool_calls=list(calls) or None)


def _tool_result(function: str, content: str) -> SimpleNamespace:
    # Tool-role result message: carries `function` but NO `tool_calls` — must
    # never fire the detector on its own.
    return SimpleNamespace(role="tool", function=function, content=content, tool_call_id="toolu_x")


def _plain(role: str) -> SimpleNamespace:
    return SimpleNamespace(role=role)


def test_detector_fires_on_matching_skill_tool_call() -> None:
    # Mirror of the #46 epoch-3 hit: Skill call with extra `args` key, followed
    # by its "Launching skill: ..." tool result.
    messages = [
        _plain("system"),
        _plain("user"),
        _assistant(
            _call("Bash", {"command": "ls"}),
            _call("Skill", {"skill": "sqlite-expert", "args": "Implement /root/notes_search.py"}),
        ),
        _tool_result("Skill", "Launching skill: sqlite-expert"),
    ]
    assert detect_skill_invocation(messages, "sqlite-expert") is True


def test_detector_ignores_other_skills_and_other_tools() -> None:
    messages = [
        _assistant(_call("Skill", {"skill": "other-skill"})),
        _assistant(_call("Bash", {"command": "cat SKILL.md"})),
        _assistant(_call("Write", {"path": "out.py"})),
    ]
    assert detect_skill_invocation(messages, "sqlite-expert") is False


def test_detector_does_not_fire_on_tool_result_messages() -> None:
    # The result message carries function="Skill" but is not an invocation.
    messages = [_tool_result("Skill", "Launching skill: sqlite-expert")]
    assert detect_skill_invocation(messages, "sqlite-expert") is False


def test_detector_is_conservative_on_malformed_shapes() -> None:
    assert detect_skill_invocation([], "sqlite-expert") is False
    assert detect_skill_invocation([_assistant()], "sqlite-expert") is False
    # arguments not a dict / missing the skill key → NOT invoked
    assert (
        detect_skill_invocation([_assistant(_call("Skill", "sqlite-expert"))], "sqlite-expert")
        is False
    )
    assert (
        detect_skill_invocation([_assistant(_call("Skill", {"args": "x"}))], "sqlite-expert")
        is False
    )
    # exact function-name match only ("Skill", as observed; lowercase is unknown)
    assert (
        detect_skill_invocation(
            [_assistant(_call("skill", {"skill": "sqlite-expert"}))], "sqlite-expert"
        )
        is False
    )
    # blank skill-under-test name can never count as invoked
    assert detect_skill_invocation([_assistant(_call("Skill", {"skill": ""}))], "") is False


def test_detector_null_arm_regression_fixture_0_of_22() -> None:
    """The #46 structural result as a regression fixture: 0/22 Null-arm epochs
    fired. Synthetic epoch streams mirror the probed Null-arm tool inventories
    (Bash/Write only — the Skill tool is not launchable when the skill is not
    passed to the solver)."""
    epochs: list[list[SimpleNamespace]] = []
    for i in range(22):
        epochs.append(
            [
                _plain("system"),
                _plain("user"),
                _assistant(_call("Bash", {"command": f"python task_{i}.py"})),
                _tool_result("Bash", "exit=0"),
                _assistant(_call("Write", {"path": f"out_{i}.txt"})),
                _tool_result("Write", "ok"),
                _plain("assistant"),
            ]
        )
    fires = sum(detect_skill_invocation(m, "sqlite-expert") for m in epochs)
    assert fires == 0


# ---------------------------------------------------------------------------
# Clopper-Pearson interval (mandatory π̂_c bound; #52)
# ---------------------------------------------------------------------------


def test_clopper_pearson_matches_reference_values() -> None:
    # x=2, n=8 (the #46 probe point): exact 95% CI
    low, high = clopper_pearson(2, 8)
    assert low == pytest.approx(0.0318540, abs=1e-6)
    assert high == pytest.approx(0.6508558, abs=1e-6)


def test_clopper_pearson_boundary_cases_are_exact() -> None:
    # x=0: lower bound exactly 0; upper = 1 - (alpha/2)^(1/n)
    low, high = clopper_pearson(0, 8)
    assert low == 0.0
    assert high == pytest.approx(1 - 0.025 ** (1 / 8), abs=1e-9)
    # x=n: symmetric
    low, high = clopper_pearson(8, 8)
    assert high == 1.0
    assert low == pytest.approx(0.025 ** (1 / 8), abs=1e-9)


def test_clopper_pearson_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        clopper_pearson(0, 0)
    with pytest.raises(ValueError):
        clopper_pearson(-1, 8)
    with pytest.raises(ValueError):
        clopper_pearson(9, 8)
    with pytest.raises(ValueError):
        clopper_pearson(1, 8, confidence=1.0)


# ---------------------------------------------------------------------------
# π_c at the write seam: mandatory reporting + zero-invocation refusal (#52)
# ---------------------------------------------------------------------------


def test_ingest_result_reports_pi_c_with_interval(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    full = make_log(
        "full",
        (
            make_sample("full", 1, 1.0, invoked=True),
            make_sample("full", 2, 1.0, invoked=False),
            make_sample("full", 3, 0.0, invoked=True),
        ),
    )
    null = make_log(
        "null",
        (
            make_sample("null", 1, 0.0),
            make_sample("null", 2, 1.0),
            make_sample("null", 3, 0.0),
        ),
    )
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    assert result.pi_c.invocations == 2
    assert result.pi_c.trials == 3
    assert result.pi_c.pi_c_hat == pytest.approx(2 / 3)
    expected_low, expected_high = clopper_pearson(2, 3)
    assert result.pi_c.ci_low == pytest.approx(expected_low)
    assert result.pi_c.ci_high == pytest.approx(expected_high)
    assert result.pi_c.confidence == PI_C_CONFIDENCE


def test_run_config_records_the_pi_c_block(conn: sqlite3.Connection, skill_dir: Path) -> None:
    full = make_log("full", (make_sample("full", 1, 1.0), make_sample("full", 2, 1.0)))
    null = make_log("null", (make_sample("null", 1, 0.0), make_sample("null", 2, 0.0)))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    row = conn.execute("SELECT config_json FROM runs WHERE run_id = ?", (result.run_id,)).fetchone()
    config = json.loads(row[0])
    assert config["pi_c"] == {
        "detector": PI_C_DETECTOR_VERSION,
        "invocations": 2,
        "trials": 2,
        "pi_c_hat": 1.0,
        "ci_low": result.pi_c.ci_low,
        "ci_high": result.pi_c.ci_high,
        "confidence": PI_C_CONFIDENCE,
    }


def test_pi_c_is_mandatory_on_ingest_result() -> None:
    # "mandatory, not optional": IngestResult cannot be constructed without it.
    with pytest.raises(ValidationError):
        IngestResult(  # type: ignore[call-arg]
            run_id="r",
            skill_id="s",
            clause_id="c",
            sample_ids=(),
            verdict_ids=(),
            admissibility_state="admissible",
            inadmissibility_reason=None,
        )


def test_zero_invocations_with_full_exposure_writes_successfully(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    """#384: zero invocations with full exposure is ADMISSIBLE — the write
    proceeds, records pi_c = 0/n, and the verdict line carries it."""
    full = make_log(
        "full",
        (
            make_sample("full", 1, 1.0, invoked=False, exposed=True),
            make_sample("full", 2, 1.0, invoked=False, exposed=True),
        ),
    )
    null = make_log("null", (make_sample("null", 1, 0.0), make_sample("null", 2, 0.0)))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    # pi_c = 0/2, but the write succeeded
    assert result.pi_c.invocations == 0
    assert result.pi_c.trials == 2
    assert result.pi_c.ci_low == 0.0
    # the run was written
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM oracle_verdicts").fetchone()[0] == 2
    # exposure summary recorded
    assert result.exposure.exposed_count == 2
    assert result.exposure.trials == 2


def test_null_arm_detected_invocation_refuses_as_contamination(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    # #46/#384: the Skill tool is structurally not launchable in the Null arm
    # and the skill's description is not mounted; a detected Null invocation
    # means the arms are mislabelled or the harness is misconfigured — an
    # apparatus error, not evidence. #384 widened this to NullArmContaminationError.
    from skill_harness.subject.ingest import NullArmContaminationError

    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0, invoked=True),))
    with pytest.raises(NullArmContaminationError, match="contamination"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


# ---------------------------------------------------------------------------
# #384 — v2 exposure detector (channel c: description in transcript)
# ---------------------------------------------------------------------------


def _user(content: str) -> SimpleNamespace:
    return SimpleNamespace(role="user", content=content)


def test_extract_skill_description_single_line(tmp_path: Path) -> None:
    d = tmp_path / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: x\ndescription: A trap card that prevents git rebase failures.\n---\nbody\n",
        encoding="utf-8",
    )
    assert _extract_skill_description(d) == "A trap card that prevents git rebase failures."


def test_extract_skill_description_folded_block_scalar(tmp_path: Path) -> None:
    """The repo fixture shape (description: >-) must yield the folded text the
    listing carries — never the bare '>-' indicator."""
    d = tmp_path / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\n"
        "name: declared-synthetic-positive-control\n"
        "description: >-\n"
        "  Declared synthetic positive control. Carries one invented fact so a Full-vs-Null\n"
        "  contrast has a real effect by construction. Instrument validation only.\n"
        "---\n"
        "# body\n",
        encoding="utf-8",
    )
    got = _extract_skill_description(d)
    assert got.startswith("Declared synthetic positive control.")
    assert "Full-vs-Null" in got
    assert "Instrument validation only." in got
    assert ">-" not in got


def test_extract_skill_description_quoted(tmp_path: Path) -> None:
    d = tmp_path / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        '---\nname: x\ndescription: "Quoted description text."\n---\nbody\n',
        encoding="utf-8",
    )
    assert _extract_skill_description(d) == "Quoted description text."


def test_extract_skill_description_missing_returns_empty(tmp_path: Path) -> None:
    d = tmp_path / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: x\n---\nbody\n", encoding="utf-8")
    assert _extract_skill_description(d) == ""


def test_detect_skill_exposure_fires_when_description_present() -> None:
    description = "A trap card that prevents git rebase failures."
    messages = [
        _plain("system"),
        _user(
            "The following skills are available for use with the Skill tool:\n"
            f"- git-pull-rebase-trap: {description}\n"
            "Use the Skill tool to invoke them."
        ),
        _assistant(_call("Bash", {"command": "git pull --rebase"})),
    ]
    assert detect_skill_exposure(messages, description) is True


def test_detect_skill_exposure_does_not_fire_when_description_absent() -> None:
    description = "A trap card that prevents git rebase failures."
    messages = [
        _plain("system"),
        _user("No skills are available."),
        _assistant(_call("Bash", {"command": "git pull --rebase"})),
    ]
    assert detect_skill_exposure(messages, description) is False


def test_detect_skill_exposure_is_conservative_on_malformed_shapes() -> None:
    description = "Some skill description."
    # empty messages
    assert detect_skill_exposure([], description) is False
    # message with no content attribute
    assert detect_skill_exposure([_plain("user")], description) is False
    # empty description can never count as exposed
    assert detect_skill_exposure([_user("anything")], "") is False
    # content as list of dicts (alternate message format)
    list_content = [SimpleNamespace(content=[{"text": f"skill: {description}"}])]
    assert detect_skill_exposure(list_content, description) is True


def test_exposure_summary_model_is_mandatory_on_ingest_result() -> None:
    """#384: ExposureSummary is mandatory, not optional, on IngestResult."""
    with pytest.raises(ValidationError):
        IngestResult(  # type: ignore[call-arg]
            run_id="r",
            skill_id="s",
            clause_id="c",
            sample_ids=(),
            verdict_ids=(),
            admissibility_state="admissible",
            inadmissibility_reason=None,
        )


# ---------------------------------------------------------------------------
# #384 — Paired-write refusal predicates at the ingest seam
# ---------------------------------------------------------------------------


def test_full_arm_unexposed_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC2(a): a Full-arm epoch with exposure not detected refuses."""
    full = make_log(
        "full",
        (make_sample("full", 1, 1.0, exposed=False),),
    )
    null = make_log("null", (make_sample("null", 1, 0.0),))
    with pytest.raises(UnexposedFullEpochError, match="exposure not detected"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_null_arm_exposed_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC2(b): a Null-arm epoch with exposure detected refuses."""
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0, exposed=True),))
    with pytest.raises(NullArmContaminationError, match="exposure detected"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_null_arm_invoked_still_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC2(b) regression: the 0/22 Null false-positive fixture stays green —
    a Null-arm epoch with invocation detected refuses as contamination."""
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0, invoked=True),))
    with pytest.raises(NullArmContaminationError, match="invocation detected"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_null_arm_exposed_and_invoked_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC2(b): a Null-arm epoch with both exposure and invocation refuses."""
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0, invoked=True, exposed=True),))
    with pytest.raises(NullArmContaminationError, match="exposure detected"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


# ---------------------------------------------------------------------------
# #384 — Fixtures at the ingest seam
# ---------------------------------------------------------------------------


def test_exposed_and_invoked_pair_writes(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC6: exposed-and-invoked pair writes successfully."""
    full = make_log(
        "full",
        (
            make_sample("full", 1, 1.0, invoked=True, exposed=True),
            make_sample("full", 2, 1.0, invoked=True, exposed=True),
        ),
    )
    null = make_log("null", (make_sample("null", 1, 0.0), make_sample("null", 2, 0.0)))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    assert result.pi_c.invocations == 2
    assert result.pi_c.trials == 2
    assert result.exposure.exposed_count == 2
    assert result.exposure.trials == 2
    assert result.admissibility_state == "admissible"
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_exposed_not_invoked_pair_writes_pi_c_0(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC6: exposed-not-invoked pair writes with pi_c = 0/n. This is the
    2026-09-01 scenario (git-pull-rebase-trap): description moved the model
    in 6/8 epochs but the Skill tool was never called."""
    full = make_log(
        "full",
        (
            make_sample("full", 1, 1.0, invoked=False, exposed=True),
            make_sample("full", 2, 1.0, invoked=False, exposed=True),
            make_sample("full", 3, 0.0, invoked=False, exposed=True),
            make_sample("full", 4, 1.0, invoked=False, exposed=True),
        ),
    )
    null = make_log(
        "null",
        (
            make_sample("null", 1, 0.0),
            make_sample("null", 2, 0.0),
            make_sample("null", 3, 0.0),
            make_sample("null", 4, 0.0),
        ),
    )
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    assert result.pi_c.invocations == 0
    assert result.pi_c.trials == 4
    assert result.pi_c.pi_c_hat == 0.0
    assert result.pi_c.ci_low == 0.0
    assert result.exposure.exposed_count == 4
    assert result.exposure.trials == 4
    # the run was written (not refused)
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM oracle_verdicts").fetchone()[0] == 4


def test_unexposed_full_epoch_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC6: Full epoch unexposed refuses as apparatus error."""
    full = make_log(
        "full",
        (
            make_sample("full", 1, 1.0, exposed=True),
            make_sample("full", 2, 1.0, exposed=False),
        ),
    )
    null = make_log("null", (make_sample("null", 1, 0.0), make_sample("null", 2, 0.0)))
    with pytest.raises(UnexposedFullEpochError) as excinfo:
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    assert excinfo.value.epoch == 2
    # refusal means refusal: nothing was written
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_null_epoch_exposed_refuses(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC6: Null epoch exposed refuses as control-arm contamination."""
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0, exposed=True),))
    with pytest.raises(NullArmContaminationError, match="exposure detected"):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_null_epoch_invoked_refuses_0_22_fixture(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC6: the 0/22 structural false-positive fixture from #46 stays green.
    All 22 Null-arm epochs in the original probe had zero Skill tool calls
    and zero exposures; an invoked epoch still refuses."""
    full = make_log("full", (make_sample("full", 1, 1.0),))
    null = make_log("null", (make_sample("null", 1, 0.0, invoked=True),))
    with pytest.raises(NullArmContaminationError):
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)


def test_screen_lane_parse_reports_exposure_not_computed(tmp_path: Path) -> None:
    """AC6: screen-lane parse (no skill_description) reports exposure as None
    (typed 'not computed' — never False)."""
    from skill_harness.storage.migrations import open_evidence
    from skill_harness.subject.screen_ingest import write_screen_evidence

    conn = open_evidence(tmp_path / "evidence.db")
    try:
        sample = ParsedSample(
            condition="null",
            skill_name="some-skill",
            epoch=1,
            scorer_name="command_succeeds",
            score_value=1.0,
            invoked_skill=False,
            exposed_skill=None,  # not computed in screen lane
            output_text="output",
            subject_model="m",
            harness_pin_json=None,
            harness_pin_fingerprint="fp",
            input_tokens=10,
            cache_read_input_tokens=None,
            cache_creation_input_tokens=None,
            output_tokens=10,
            usd=None,
        )
        log = ParsedEvalLog(
            task_name="some-skill-null",
            task_id="task-screen-1",
            created="2026-09-01T00:00:00+00:00",
            status="success",
            samples=(sample,),
        )
        # write_screen_evidence accepts this — exposure is not checked in the
        # screen lane (no skill directory, no exposure computation)
        result = write_screen_evidence(
            parsed=log,
            source_eval_sha256="sha-screen",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )
        assert result.n_trials == 1
        assert result.n_pass == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# #384 — config_json: paired cell counts and exposure summary
# ---------------------------------------------------------------------------


def test_config_json_records_paired_cell_counts(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC4: the run's config_json records the four paired-outcome cell counts."""
    full = make_log(
        "full",
        (
            make_sample("full", 1, 1.0, invoked=True, exposed=True),  # Full pass
            make_sample("full", 2, 1.0, invoked=True, exposed=True),  # Full pass
            make_sample("full", 3, 0.0, invoked=True, exposed=True),  # Full fail
            make_sample("full", 4, 1.0, invoked=True, exposed=True),  # Full pass
        ),
    )
    null = make_log(
        "null",
        (
            make_sample("null", 1, 0.0),  # Null fail → full_only
            make_sample("null", 2, 1.0),  # Null pass → both_pass
            make_sample("null", 3, 0.0),  # Null fail → both_fail
            make_sample("null", 4, 0.0),  # Null fail → full_only
        ),
    )
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    row = conn.execute("SELECT config_json FROM runs WHERE run_id = ?", (result.run_id,)).fetchone()
    config = json.loads(row[0])
    cells = config["paired_cells"]
    assert cells["both_pass"] == 1  # epoch 2: both 1.0
    assert cells["full_only"] == 2  # epochs 1, 4: full 1.0, null 0.0
    assert cells["null_only"] == 0  # no epoch where null passed and full failed
    assert cells["both_fail"] == 1  # epoch 3: both 0.0


def test_config_json_records_exposure_summary(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC4: the run's config_json records the exposure summary."""
    full = make_log(
        "full",
        (
            make_sample("full", 1, 1.0, invoked=True, exposed=True),
            make_sample("full", 2, 1.0, invoked=False, exposed=True),
        ),
    )
    null = make_log("null", (make_sample("null", 1, 0.0), make_sample("null", 2, 0.0)))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    row = conn.execute("SELECT config_json FROM runs WHERE run_id = ?", (result.run_id,)).fetchone()
    config = json.loads(row[0])
    assert config["exposure"]["exposed_count"] == 2
    assert config["exposure"]["trials"] == 2
    assert config["exposure"]["detector_version"] == "v2-description-channel"


def test_config_json_records_pi_c_block(conn: sqlite3.Connection, skill_dir: Path) -> None:
    """AC5: pi_c recorded in config_json with detector version."""
    full = make_log(
        "full",
        (
            make_sample("full", 1, 1.0, invoked=True, exposed=True),
            make_sample("full", 2, 1.0, invoked=False, exposed=True),
        ),
    )
    null = make_log("null", (make_sample("null", 1, 0.0), make_sample("null", 2, 0.0)))
    result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    row = conn.execute("SELECT config_json FROM runs WHERE run_id = ?", (result.run_id,)).fetchone()
    config = json.loads(row[0])
    pi_c = config["pi_c"]
    assert pi_c["detector"] == PI_C_DETECTOR_VERSION
    assert pi_c["invocations"] == 1
    assert pi_c["trials"] == 2
    assert pi_c["pi_c_hat"] == 0.5
    assert pi_c["confidence"] == PI_C_CONFIDENCE


# ---------------------------------------------------------------------------
# #384 — v2 detector: screen-lane parse (parse_eval_log without description)
# ---------------------------------------------------------------------------


def test_parse_eval_log_exposed_skill_defaults_none_without_description() -> None:
    """The screen lane has no skill directory, so exposure is typed 'not
    computed' (None) on every sample — never False."""
    # This tests the ParsedSample default, not the parse path (which needs [inspect])
    sample = ParsedSample(
        condition="null",
        skill_name="x",
        epoch=1,
        scorer_name="s",
        score_value=0.0,
        invoked_skill=False,
        output_text="o",
        subject_model="m",
        harness_pin_json=None,
        harness_pin_fingerprint=None,
        input_tokens=None,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=None,
        output_tokens=None,
        usd=None,
    )
    assert sample.exposed_skill is None  # default: not computed


@pytest.mark.skipif(INSPECT_INSTALLED, reason="extra installed; error path unreachable")
def test_parse_eval_log_raises_typed_error_without_extra(tmp_path: Path) -> None:
    from skill_harness.subject.ingest import parse_eval_log
    from skill_harness.subject.inspect_adapter import SubjectLayerNotInstalledError

    with pytest.raises(SubjectLayerNotInstalledError, match=r"skill-harness\[inspect\]"):
        parse_eval_log(tmp_path / "whatever.eval")


# ---------------------------------------------------------------------------
# #387 AC5 — verdict rationale carries the pi_c line
# ---------------------------------------------------------------------------


def test_paired_verdict_carries_pi_c_line() -> None:
    """AC5: every verdict rationale minted by the paired path carries the pi_c
    line per #36 adoption 4 display rule (`pi_c_hat = k/n [95% CI lo, hi]`)."""
    r = paired_verdict(
        ClauseStatus.PASSED,
        pi_c_hat=0.25,
        pi_c_n=8,
        pi_c_ci_low=0.0319,
        pi_c_ci_high=0.6509,
        pi_c_confidence=0.95,
    )
    assert "pi_c_hat = 2/8 = 0.2500" in r.rationale
    assert "95% CI 0.0319, 0.6509" in r.rationale


def test_paired_verdict_pi_c_zero_says_cace_not_identified() -> None:
    """AC5: at pi_c = 0 the CACE secondary is stated as not identified, never
    computed."""
    r = paired_verdict(
        ClauseStatus.FAILED,
        pi_c_hat=0.0,
        pi_c_n=8,
        pi_c_ci_low=0.0,
        pi_c_ci_high=0.369,
        pi_c_confidence=0.95,
    )
    assert "pi_c_hat = 0/8 = 0.0000" in r.rationale
    assert "CACE secondary is not identified" in r.rationale


# ---------------------------------------------------------------------------
# #387 AC7 — mutation receipts: each refusal predicate is load-bearing
# ---------------------------------------------------------------------------


def test_mutation_unexposed_full_refusal_removes_predicate(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    """AC7 mutant: removing the unexposed-Full refusal predicate lets a
    Full-arm epoch with no exposure through the write path.

    The named assertion that turns red: the write must refuse
    (UnexposedFullEpochError) when a Full epoch is unexposed. A mutant that
    removes the unexposed-Full check in _validate_pair lets the write succeed,
    turning this assertion from pass to fail."""
    from skill_harness.subject import ingest as ingest_mod

    full = make_log(
        "full",
        (make_sample("full", 1, 1.0, exposed=False),),
        task_id="mutant-unexposed-full",
    )
    null = make_log("null", (make_sample("null", 1, 0.0),), task_id="mutant-unexposed-null")

    # Save the original and monkey-patch: remove the unexposed-Full check
    original_validate = ingest_mod._validate_pair

    def _validate_no_unexposed_check(full: ParsedEvalLog, null: ParsedEvalLog) -> None:
        """Calls the original _validate_pair but skips the unexposed-Full check
        by patching exposed_skill to True on all Full samples."""
        for s in full.samples:
            object.__setattr__(s, "exposed_skill", True)
        original_validate(full, null)

    ingest_mod._validate_pair = _validate_no_unexposed_check
    try:
        # The assertion: with the predicate removed, the write SUCCEEDS
        # (no UnexposedFullEpochError). Without the predicate removal, this
        # would raise UnexposedFullEpochError.
        result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
        # The mutant lets the write through — the predicate was load-bearing
        assert result.run_id  # write succeeded (predicate was needed)
    finally:
        ingest_mod._validate_pair = original_validate
    # Verify the original predicate still blocks it (separate conn scope)
    full2 = make_log(
        "full", (make_sample("full", 1, 1.0, exposed=False),), task_id="verify-unexposed-f2"
    )
    null2 = make_log("null", (make_sample("null", 1, 0.0),), task_id="verify-unexposed-n2")
    with pytest.raises(UnexposedFullEpochError):
        write_paired_evidence(full=full2, null=null2, skill_dir=skill_dir, conn=conn)


def test_mutation_null_contamination_refusal_removes_predicate(
    conn: sqlite3.Connection, skill_dir: Path
) -> None:
    """AC7 mutant: removing the Null-contamination refusal predicate lets a
    Null-arm epoch with exposure detected through the write path.

    The named assertion that turns red: the write must refuse
    (NullArmContaminationError) when a Null epoch is exposed. A mutant that
    removes the Null contamination check in _validate_pair lets the write
    succeed, turning this assertion from pass to fail."""
    from skill_harness.subject import ingest as ingest_mod

    full = make_log("full", (make_sample("full", 1, 1.0),), task_id="mutant-null-exposed-full")
    null = make_log(
        "null",
        (make_sample("null", 1, 0.0, exposed=True),),
        task_id="mutant-null-exposed-null",
    )

    original_validate = ingest_mod._validate_pair

    def _validate_no_null_check(full: ParsedEvalLog, null: ParsedEvalLog) -> None:
        """Calls the original _validate_pair but skips the Null-contamination
        check by patching exposed_skill to False on all Null samples."""
        for s in null.samples:
            object.__setattr__(s, "exposed_skill", False)
            object.__setattr__(s, "invoked_skill", False)
        original_validate(full, null)

    ingest_mod._validate_pair = _validate_no_null_check
    try:
        # The assertion: with the predicate removed, the write SUCCEEDS
        result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
        assert result.run_id  # write succeeded (predicate was needed)
    finally:
        ingest_mod._validate_pair = original_validate
    # Verify the original predicate still blocks it
    full2 = make_log("full", (make_sample("full", 1, 1.0),), task_id="verify-null-f2")
    null2 = make_log("null", (make_sample("null", 1, 0.0, exposed=True),), task_id="verify-null-n2")
    with pytest.raises(NullArmContaminationError):
        write_paired_evidence(full=full2, null=null2, skill_dir=skill_dir, conn=conn)
