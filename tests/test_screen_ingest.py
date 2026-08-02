"""Tests for the Stage-0 Null-only screen store (migration 0501): ingest, p0
derivation, the batch-1 backfill manifest, and the screen-verdict CLI.

All tests construct ``ParsedEvalLog`` directly (mirroring test_subject_ingest),
so nothing here needs the optional ``[inspect]`` extra or the gitignored
``.private`` log tree.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from skill_harness.aggregation.verdict import CutSubReason, KeepCutVerdict, screen_verdict
from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.repositories.evidence.screens import derive_p0_by_skill
from skill_harness.subject.ingest import ParsedEvalLog, ParsedSample
from skill_harness.subject.screen_backfill import (
    BATCH1_MANIFEST,
    ScreenManifestEntry,
    apply_manifest,
)
from skill_harness.subject.screen_ingest import (
    AlreadyIngestedScreenError,
    NotANullScreenError,
    ScreenIngestError,
    write_screen_evidence,
)

PIN_FP = "fp-deadbeef"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_evidence(tmp_path / "evidence.db")
    yield connection
    connection.close()


def make_null_sample(
    epoch: int, score: float, *, skill_name: str = "some-skill", fingerprint: str | None = PIN_FP
) -> ParsedSample:
    return ParsedSample(
        condition="null",
        skill_name=skill_name,
        epoch=epoch,
        scorer_name="command_succeeds",
        score_value=score,
        invoked_skill=False,  # structurally impossible in a Null screen (#46)
        output_text=f"null-output-{epoch}",
        subject_model="anthropic/claude-sonnet-5",
        harness_pin_json=None,
        harness_pin_fingerprint=fingerprint,
        input_tokens=100,
        cache_read_input_tokens=50,
        cache_creation_input_tokens=25,
        output_tokens=10,
        usd=None,
    )


def make_screen_log(
    *scores: float, skill_name: str = "some-skill", task_id: str = "task-null-1"
) -> ParsedEvalLog:
    samples = tuple(
        make_null_sample(i, s, skill_name=skill_name) for i, s in enumerate(scores, start=1)
    )
    return ParsedEvalLog(
        task_name=f"{skill_name}-null",
        task_id=task_id,
        created="2026-07-10T12:00:00+00:00",
        status="success",
        samples=samples,
    )


# ---------------------------------------------------------------------------
# write_screen_evidence
# ---------------------------------------------------------------------------


def test_admissible_screen_writes_run_and_trials(conn: sqlite3.Connection) -> None:
    result = write_screen_evidence(
        parsed=make_screen_log(1.0, 1.0, 1.0),
        source_eval_sha256="sha-a",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        conn=conn,
    )
    assert result.skill_name == "some-skill"
    assert result.n_trials == 3
    assert result.n_pass == 3
    trials = conn.execute(
        "SELECT passed FROM screen_trials WHERE screen_run_id = ?", (result.screen_run_id,)
    ).fetchall()
    assert sorted(t[0] for t in trials) == [1, 1, 1]


def test_passed_maps_binary_score(conn: sqlite3.Connection) -> None:
    result = write_screen_evidence(
        parsed=make_screen_log(1.0, 0.0, 1.0),
        source_eval_sha256="sha-b",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        conn=conn,
    )
    assert (result.n_pass, result.n_trials) == (2, 3)


def test_non_binary_score_refused(conn: sqlite3.Connection) -> None:
    with pytest.raises(ScreenIngestError, match="non-binary"):
        write_screen_evidence(
            parsed=make_screen_log(1.0, 0.5),
            source_eval_sha256="sha-c",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )


def test_non_null_condition_refused(conn: sqlite3.Connection) -> None:
    full_sample = ParsedSample(
        condition="full",
        skill_name="some-skill",
        epoch=1,
        scorer_name="command_succeeds",
        score_value=1.0,
        invoked_skill=True,
        output_text="x",
        subject_model="m",
        harness_pin_json=None,
        harness_pin_fingerprint=PIN_FP,
        input_tokens=None,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=None,
        output_tokens=None,
        usd=None,
    )
    log = ParsedEvalLog(
        task_name="x",
        task_id="t",
        created="2026-07-10T12:00:00+00:00",
        status="success",
        samples=(full_sample,),
    )
    with pytest.raises(NotANullScreenError, match="Null-only"):
        write_screen_evidence(
            parsed=log,
            source_eval_sha256="sha-d",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )


def test_inadmissible_requires_reason(conn: sqlite3.Connection) -> None:
    with pytest.raises(ScreenIngestError, match="requires an inadmissibility_reason"):
        write_screen_evidence(
            parsed=make_screen_log(0.0, 0.0, 0.0),
            source_eval_sha256="sha-e",
            admissibility_state="inadmissible",
            inadmissibility_reason=None,
            conn=conn,
        )


def test_admissible_rejects_reason(conn: sqlite3.Connection) -> None:
    with pytest.raises(ScreenIngestError, match="must not carry"):
        write_screen_evidence(
            parsed=make_screen_log(1.0),
            source_eval_sha256="sha-f",
            admissibility_state="admissible",
            inadmissibility_reason="oops",
            conn=conn,
        )


def test_reingest_is_idempotent(conn: sqlite3.Connection) -> None:
    log = make_screen_log(1.0, 1.0, 1.0, task_id="dup-task")
    write_screen_evidence(
        parsed=log,
        source_eval_sha256="s",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        conn=conn,
    )
    with pytest.raises(AlreadyIngestedScreenError):
        write_screen_evidence(
            parsed=log,
            source_eval_sha256="s",
            admissibility_state="admissible",
            inadmissibility_reason=None,
            conn=conn,
        )


# ---------------------------------------------------------------------------
# derive_p0_by_skill — the trust-critical exclusion of voided screens
# ---------------------------------------------------------------------------


def test_p0_excludes_inadmissible_screens(conn: sqlite3.Connection) -> None:
    """The whole point: a voided (inadmissible) screen is stored but MUST NOT
    enter p0 — else a false p0=0.5 (a spurious KEEP-candidate) results."""
    # admissible 3/3 pass
    write_screen_evidence(
        parsed=make_screen_log(1.0, 1.0, 1.0, task_id="good"),
        source_eval_sha256="g",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        conn=conn,
    )
    # inadmissible 0/3 (apparatus void) — same skill
    write_screen_evidence(
        parsed=make_screen_log(0.0, 0.0, 0.0, task_id="void"),
        source_eval_sha256="v",
        admissibility_state="inadmissible",
        inadmissibility_reason="apparatus_void: oracle crash",
        conn=conn,
    )
    rows = derive_p0_by_skill(conn)
    assert len(rows) == 1
    (row,) = rows
    assert row.skill_name == "some-skill"
    assert row.p0 == 1.0  # NOT 0.5 — the void is excluded
    assert row.n_trials == 3
    assert row.n_admissible_screens == 1
    # the void is still on disk (append-only)
    assert conn.execute("SELECT count(*) FROM screen_runs").fetchone()[0] == 2


def test_p0_multiple_skills_and_verdicts(conn: sqlite3.Connection) -> None:
    write_screen_evidence(
        parsed=make_screen_log(1.0, 1.0, 1.0, skill_name="ceiling-skill", task_id="c"),
        source_eval_sha256="c",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        conn=conn,
    )
    write_screen_evidence(
        parsed=make_screen_log(0.0, 0.0, 1.0, skill_name="hard-skill", task_id="h"),
        source_eval_sha256="h",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        conn=conn,
    )
    by_skill = {r.skill_name: r for r in derive_p0_by_skill(conn)}
    assert by_skill["ceiling-skill"].p0 == 1.0
    assert screen_verdict(by_skill["ceiling-skill"].p0).verdict is KeepCutVerdict.CUT
    assert screen_verdict(by_skill["ceiling-skill"].p0).cut_sub_reason is CutSubReason.SUBSUMED
    assert by_skill["hard-skill"].p0 == pytest.approx(1 / 3)
    # p0 = 0.33 > 0.3 bar -> still CUT(subsumed) with headroom
    assert screen_verdict(by_skill["hard-skill"].p0).verdict is KeepCutVerdict.CUT


def test_skill_with_only_inadmissible_screens_has_no_p0_row(conn: sqlite3.Connection) -> None:
    write_screen_evidence(
        parsed=make_screen_log(0.0, 0.0, 0.0, task_id="allvoid"),
        source_eval_sha256="x",
        admissibility_state="inadmissible",
        inadmissibility_reason="void",
        conn=conn,
    )
    assert derive_p0_by_skill(conn) == []


# ---------------------------------------------------------------------------
# backfill manifest apply (parse injected — no [inspect], no private logs)
# ---------------------------------------------------------------------------


def _fake_tree(tmp_path: Path) -> Path:
    """Create empty files at each manifest path so is_file() passes."""
    root = tmp_path / "screens"
    for entry in BATCH1_MANIFEST:
        p = root / entry.rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"stub")
    return root


def test_apply_manifest_clean(tmp_path: Path, conn: sqlite3.Connection) -> None:
    root = _fake_tree(tmp_path)

    def fake_parse(path: Path) -> ParsedEvalLog:
        # map each manifest entry to a synthetic log matching its expectation
        entry = next(e for e in BATCH1_MANIFEST if str(path).endswith(e.rel_path.split("/")[-1]))
        scores = tuple(1.0 for _ in range(3)) if entry.expected_pass == 3 else (0.0, 0.0, 0.0)
        return make_screen_log(*scores, skill_name=entry.expected_skill, task_id=str(path.name))

    report = apply_manifest(root, conn, parse=fake_parse)
    assert len(report.ingested) == len(BATCH1_MANIFEST)
    assert report.mismatches == ()
    # 3 admissible skills ceiling
    verdicts = {r.skill_name: screen_verdict(r.p0).verdict for r in derive_p0_by_skill(conn)}
    assert all(v is KeepCutVerdict.CUT for v in verdicts.values())
    assert "sqlite-tie-break-red-test-trap" in verdicts  # the void log did not sink it


def test_apply_manifest_surfaces_pass_mismatch(tmp_path: Path, conn: sqlite3.Connection) -> None:
    """A manifest whose expected_pass disagrees with the log must surface, not corrupt p0."""
    root = _fake_tree(tmp_path)

    def wrong_parse(path: Path) -> ParsedEvalLog:
        entry = next(e for e in BATCH1_MANIFEST if str(path).endswith(e.rel_path.split("/")[-1]))
        # force every log to 1/3 pass regardless of manifest expectation
        return make_screen_log(
            1.0, 0.0, 0.0, skill_name=entry.expected_skill, task_id=str(path.name)
        )

    report = apply_manifest(root, conn, parse=wrong_parse)
    assert report.mismatches  # non-empty — the disagreement was caught


def test_apply_manifest_missing_file_raises(tmp_path: Path, conn: sqlite3.Connection) -> None:
    with pytest.raises(FileNotFoundError):
        apply_manifest(tmp_path / "nonexistent", conn, parse=make_screen_log)  # type: ignore[arg-type]


def test_manifest_has_exactly_one_inadmissible_void() -> None:
    """Pin the curated tiebreak void decision — a regression guard on the manifest."""
    inadmissible = [e for e in BATCH1_MANIFEST if e.admissibility_state == "inadmissible"]
    assert len(inadmissible) == 1
    (void,) = inadmissible
    assert void.expected_skill == "sqlite-tie-break-red-test-trap"
    assert "apparatus_void" in (void.inadmissibility_reason or "")


# ---------------------------------------------------------------------------
# CLI: screen verdict
# ---------------------------------------------------------------------------


def test_cli_screen_verdict_empty_store(tmp_path: Path) -> None:
    open_evidence(tmp_path / "evidence.db").close()
    res = CliRunner().invoke(
        cli, ["screen", "verdict", "--evidence-db", str(tmp_path / "evidence.db")]
    )
    assert res.exit_code == 0
    assert "No admissible screens" in res.output


def test_cli_screen_verdict_renders_cut(tmp_path: Path) -> None:
    db = tmp_path / "evidence.db"
    c = open_evidence(db)
    write_screen_evidence(
        parsed=make_screen_log(1.0, 1.0, 1.0, skill_name="ceiling-skill"),
        source_eval_sha256="s",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        conn=c,
    )
    c.close()
    res = CliRunner().invoke(cli, ["screen", "verdict", "--evidence-db", str(db)])
    assert res.exit_code == 0
    assert "CUT" in res.output
    assert "ceiling-skill" in res.output


def test_cli_screen_verdict_missing_db(tmp_path: Path) -> None:
    res = CliRunner().invoke(
        cli, ["screen", "verdict", "--evidence-db", str(tmp_path / "absent.db")]
    )
    assert res.exit_code == 0
    assert "no screen store" in res.output


def test_cli_backfill_dry_run_lists_manifest(tmp_path: Path) -> None:
    # dry-run needs no screens-root writes; use tmp as an existing dir
    res = CliRunner().invoke(cli, ["screen", "backfill", "--screens-root", str(tmp_path)])
    assert res.exit_code == 0
    assert "DRY-RUN" in res.output
    assert "append-only-evidence-design" in res.output
    assert "inadmissible" in res.output


def test_manifest_entry_is_frozen() -> None:
    entry = BATCH1_MANIFEST[0]
    assert isinstance(entry, ScreenManifestEntry)
    with pytest.raises((AttributeError, TypeError)):
        entry.expected_pass = 99  # type: ignore[misc]
