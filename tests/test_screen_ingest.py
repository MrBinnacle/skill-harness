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

from skill_harness.aggregation.verdict import (
    CutSubReason,
    KeepCutVerdict,
    ValueClass,
    screen_verdict,
)
from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.repositories.evidence.screens import derive_p0_by_skill
from skill_harness.subject.ingest import ParsedEvalLog, ParsedSample
from skill_harness.subject.screen_backfill import (
    BATCH1_MANIFEST,
    D4LeakResult,
    ScreenManifestEntry,
    apply_manifest,
    check_d4_prompt_leak,
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
    # Store rows are historical transformative-lift screens (#74/#76 guard: the
    # CUT-on-ceiling mapping is the transformative-lift class; pass it explicitly).
    tl = ValueClass.TRANSFORMATIVE_LIFT
    ceiling_p0 = by_skill["ceiling-skill"].p0
    assert ceiling_p0 == 1.0
    assert screen_verdict(ceiling_p0, value_class=tl).verdict is KeepCutVerdict.CUT
    assert screen_verdict(ceiling_p0, value_class=tl).cut_sub_reason is CutSubReason.SUBSUMED
    assert by_skill["hard-skill"].p0 == pytest.approx(1 / 3)
    # p0 = 0.33 > 0.3 bar -> still CUT(subsumed) with headroom
    assert screen_verdict(by_skill["hard-skill"].p0, value_class=tl).verdict is KeepCutVerdict.CUT


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
    # 3 admissible skills ceiling; store rows are historical transformative-lift
    # screens (#74/#76), so the CUT-on-ceiling mapping is exercised with that class.
    verdicts = {
        r.skill_name: screen_verdict(r.p0, value_class=ValueClass.TRANSFORMATIVE_LIFT).verdict
        for r in derive_p0_by_skill(conn)
    }
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


def test_cli_screen_verdict_renders_cant_tell_for_unclassified_ceiling(tmp_path: Path) -> None:
    """#74/#76/#77 guard, US-3: an UNREGISTERED skill_name ('ceiling-skill' is not in
    the classify-the-11 registry) → value_class_for → None → a screen ceiling (p0=1)
    renders CANT_TELL_YET (wrong instrument), NOT a false CUT(subsumed). This is the
    honest default render — the false CUT is gone here, not deferred to a board.
    (Registered non-transformative skills take the same CANT_TELL_YET path via their
    class; see test_value_class_registry for the OBS-0003..0006 flip.)"""
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
    # A ceiling (p0=1) rendering CANT_TELL_YET IS the guard firing: without it a
    # ceiling maps to CUT. (The wrong-instrument rationale wraps across the narrow
    # rationale cell, so it is asserted at the function level, not scraped here.)
    assert "CANT_TELL_YET" in res.output
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


# ---------------------------------------------------------------------------
# D4 prompt-leak check
# ---------------------------------------------------------------------------


def test_d4_direct_leak_in_prompt() -> None:
    """Rule text present in the prompt itself → leaked, location 'prompt'."""
    rule = "Do not rewrite, drop, or re-parent a commit that the ledger references."
    prompt = (
        "The repository's release process depends on ledger/releases.md staying "
        "valid — see RELEASING.md for the repository's history policy: "
        "Do not rewrite, drop, or re-parent a commit that the ledger references."
    )
    result = check_d4_prompt_leak(rule, prompt)
    assert result.leaked is True
    assert "prompt" in result.locations


def test_d4_indirect_leak_via_fixture_file() -> None:
    """Rule absent from prompt but present in a referenced fixture file → leaked."""
    rule = "Do not rewrite, drop, or re-parent a commit that the ledger references."
    prompt = (
        "The repository's release process depends on ledger/releases.md staying "
        "valid — see RELEASING.md for the repository's history policy."
    )
    fixture_files = {
        "RELEASING.md": (
            "# Releasing\n\nDo not rewrite, drop, or re-parent a commit that "
            "the ledger references.\n"
        ),
    }
    result = check_d4_prompt_leak(rule, prompt, fixture_files)
    assert result.leaked is True
    assert "RELEASING.md" in result.locations
    assert "prompt" not in result.locations


def test_d4_clean_prompt_no_leak() -> None:
    """Neither prompt nor fixture files contain the rule → clean."""
    rule = "Do not rewrite, drop, or re-parent a commit that the ledger references."
    prompt = "Please complete the git task using standard practices."
    fixture_files = {"README.md": "# Project\n\nA standard project.\n"}
    result = check_d4_prompt_leak(rule, prompt, fixture_files)
    assert result.leaked is False
    assert result.locations == ()


def test_d4_empty_rule_is_clean() -> None:
    """An empty operative rule is never a leak (nothing to match)."""
    result = check_d4_prompt_leak("", "any prompt at all")
    assert result.leaked is False


def test_d4_whitespace_normalisation() -> None:
    """Leading/trailing/extra whitespace does not prevent detection."""
    rule = "  Do   not   rewrite  "
    prompt = "The rule is: Do not rewrite history."
    result = check_d4_prompt_leak(rule, prompt)
    assert result.leaked is True


def test_d4_case_insensitive() -> None:
    """Case differences do not prevent detection."""
    rule = "DO NOT REWRITE HISTORY"
    prompt = "Remember: do not rewrite history."
    result = check_d4_prompt_leak(rule, prompt)
    assert result.leaked is True


def test_d4_multiple_fixture_files() -> None:
    """Rule found in one of several fixture files → leak with that file's name."""
    rule = "Append-only evidence design"
    prompt = "Complete the task."
    fixture_files = {
        "NOTES.md": "# Notes\n\nSome notes.\n",
        "RULES.md": "Append-only evidence design: all writes are permanent.\n",
    }
    result = check_d4_prompt_leak(rule, prompt, fixture_files)
    assert result.leaked is True
    assert "RULES.md" in result.locations
    assert "NOTES.md" not in result.locations


def test_d4_leak_result_is_frozen() -> None:
    """D4LeakResult is a frozen dataclass."""
    r = D4LeakResult(leaked=True, locations=("prompt",))
    with pytest.raises((AttributeError, TypeError)):
        r.leaked = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# D4 check integration: apply_manifest with D4 inputs
# ---------------------------------------------------------------------------


def _stored_admissibility(conn: sqlite3.Connection, screen_run_id: str) -> tuple[str, str | None]:
    row = conn.execute(
        "SELECT admissibility_state, inadmissibility_reason "
        "FROM screen_runs WHERE screen_run_id = ?",
        (screen_run_id,),
    ).fetchone()
    assert row is not None
    return str(row[0]), None if row[1] is None else str(row[1])


def test_apply_manifest_d4_poison_refused(tmp_path: Path, conn: sqlite3.Connection) -> None:
    """A manifest entry with operative_rule + prompt_text containing the rule
    is overridden to inadmissible with store reason apparatus_void: D4 prompt leak."""
    rule = "Do not rewrite, drop, or re-parent a commit."
    leaked_prompt = "Follow the rule: Do not rewrite, drop, or re-parent a commit."
    entry = ScreenManifestEntry(
        rel_path="d4/poison.eval",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        expected_skill="some-skill",
        expected_pass=3,
        operative_rule=rule,
        prompt_text=leaked_prompt,
    )
    root = tmp_path / "screens"
    p = root / entry.rel_path
    p.parent.mkdir(parents=True)
    p.write_bytes(b"stub")

    def fake_parse(path: Path) -> ParsedEvalLog:
        return make_screen_log(1.0, 1.0, 1.0, skill_name="some-skill", task_id=str(path.name))

    report = apply_manifest(root, conn, manifest=(entry,), parse=fake_parse)
    assert len(report.ingested) == 1
    result = report.ingested[0]
    assert result.admissibility_state == "inadmissible"
    # External behaviour: the store reason, not an audit-mismatch side channel.
    assert _stored_admissibility(conn, result.screen_run_id) == (
        "inadmissible",
        "apparatus_void: D4 prompt leak",
    )
    assert report.mismatches == ()
    # p0 must not include this inadmissible screen
    rows = derive_p0_by_skill(conn)
    assert rows == []


def test_apply_manifest_d4_clean_admitted(tmp_path: Path, conn: sqlite3.Connection) -> None:
    """A manifest entry with D4 inputs but no leak is admitted as-is."""
    rule = "Do not rewrite, drop, or re-parent a commit."
    clean_prompt = "Complete the git task using standard practices."
    entry = ScreenManifestEntry(
        rel_path="d4/clean.eval",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        expected_skill="some-skill",
        expected_pass=3,
        operative_rule=rule,
        prompt_text=clean_prompt,
    )
    root = tmp_path / "screens"
    p = root / entry.rel_path
    p.parent.mkdir(parents=True)
    p.write_bytes(b"stub")

    def fake_parse(path: Path) -> ParsedEvalLog:
        return make_screen_log(1.0, 1.0, 1.0, skill_name="some-skill", task_id=str(path.name))

    report = apply_manifest(root, conn, manifest=(entry,), parse=fake_parse)
    assert len(report.ingested) == 1
    result = report.ingested[0]
    assert result.admissibility_state == "admissible"
    assert _stored_admissibility(conn, result.screen_run_id) == ("admissible", None)
    assert report.mismatches == ()
    rows = derive_p0_by_skill(conn)
    assert len(rows) == 1
    assert rows[0].p0 == 1.0


def test_apply_manifest_d4_indirect_leak_via_fixture(
    tmp_path: Path, conn: sqlite3.Connection
) -> None:
    """Rule absent from prompt but present in a fixture file the prompt names → refused.

    Mirrors the gitpull shape: the prompt points at RELEASING.md; that file
    carries the operative rule. A prompt-text-only check would miss this.
    """
    rule = "Do not rewrite, drop, or re-parent a commit that the ledger references."
    prompt = (
        "The repository's release process depends on ledger/releases.md staying "
        "valid — see RELEASING.md for the repository's history policy."
    )
    fixture_files = {
        "RELEASING.md": (
            "# Releasing\n\nDo not rewrite, drop, or re-parent a commit that "
            "the ledger references.\n"
        ),
    }
    entry = ScreenManifestEntry(
        rel_path="d4/indirect.eval",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        expected_skill="some-skill",
        expected_pass=3,
        operative_rule=rule,
        prompt_text=prompt,
        prompt_fixture_files=fixture_files,
    )
    root = tmp_path / "screens"
    p = root / entry.rel_path
    p.parent.mkdir(parents=True)
    p.write_bytes(b"stub")

    def fake_parse(path: Path) -> ParsedEvalLog:
        return make_screen_log(1.0, 1.0, 1.0, skill_name="some-skill", task_id=str(path.name))

    report = apply_manifest(root, conn, manifest=(entry,), parse=fake_parse)
    result = report.ingested[0]
    assert result.admissibility_state == "inadmissible"
    assert _stored_admissibility(conn, result.screen_run_id) == (
        "inadmissible",
        "apparatus_void: D4 prompt leak",
    )
    assert report.mismatches == ()
    # Pure check still names the fixture file as the leak site.
    leak = check_d4_prompt_leak(rule, prompt, fixture_files)
    assert leak.leaked is True
    assert "RELEASING.md" in leak.locations
    assert "prompt" not in leak.locations


def test_apply_manifest_no_d4_fields_skips_check(tmp_path: Path, conn: sqlite3.Connection) -> None:
    """Entries without D4 fields (operative_rule=None) skip the check entirely."""
    entry = ScreenManifestEntry(
        rel_path="d4/skip.eval",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        expected_skill="some-skill",
        expected_pass=3,
    )
    root = tmp_path / "screens"
    p = root / entry.rel_path
    p.parent.mkdir(parents=True)
    p.write_bytes(b"stub")

    def fake_parse(path: Path) -> ParsedEvalLog:
        return make_screen_log(1.0, 1.0, 1.0, skill_name="some-skill", task_id=str(path.name))

    report = apply_manifest(root, conn, manifest=(entry,), parse=fake_parse)
    result = report.ingested[0]
    assert result.admissibility_state == "admissible"
    assert _stored_admissibility(conn, result.screen_run_id) == ("admissible", None)
    assert report.mismatches == ()
