"""Batch-1 Stage-0 screen backfill manifest + apply logic.

The program's historical Stage-0 screen verdicts are pre-registry observations
recorded per task family in the OBS ledger (``docs/observations/`` — canonical
for the per-record counts and their decomposition; estimand n/a, π_c
not-instrumented). This backfill makes the subset that HAS raw Inspect ``.eval``
logs on disk store-auditable: it ingests those logs into the screen store
(migration 0501) so p0 — and therefore the keep/cut verdict — is DERIVED from
append-only evidence rather than hand-transcribed.

SCOPE (honest): only batch-1's 4 skills have local ``.eval`` logs
(``.private/microrun/`` — gitignored, not shipped). This manifest backfills 3
of them; ``llm-judge-calibration`` is DEFERRED (see below). The other program
screens (the S62-S63 probe families) have no local logs and remain prose-backed.
Every backfilled screen ceilings (p0 = 1) → CUT(subsumed); the store-backed
result matches the pre-reg, and the pipeline is the durable asset — it is the
path by which a FUTURE real-workload screen with p0 < 1 becomes auditable.

EVIDENCE ADMISSIBILITY is the one human judgment, localized here and cited. The outcome
oracle scores INCORRECT for ANY non-zero exit and stores no field distinguishing
"subject failed" from "oracle-harness crashed", so the void decisions the
operator made in the pre-reg cannot be re-derived mechanically — they are
transcribed as manifest entries, each with its evidence:

  - ``sqlite-tie-break-red-test-trap`` has TWO stage-0 logs with IDENTICAL task
    input (sha256/7 bcfb990) and harness pin (2f76c933…): 11-10-33 scored 3/3
    "I" with ``exit=1`` and a mangled oracle-runner path (no structured
    ORACLE-PASS) — the grading harness crashed, not the subject; 11-21-00,
    11 minutes later, scored 3/3 "C" with ``exit=0: ORACLE-PASS``. The pre-reg's
    "3/3 PASS — CEILING" is the 11-21-00 run. 11-10-33 is ingested and marked
    INADMISSIBLE (apparatus void) — append-only keeps the evidence; p0 excludes
    it. A naive ingest-both would derive p0 = 3/6 = 0.5, a false KEEP-candidate.

DEFERRED — ``llm-judge-calibration``: its canonical 3/3 is assembled ACROSS
FOUR partial logs over the pre-reg's credit-exhaustion incident (2 admissible
epochs in one log, a third in a later log, ``None``-scored voided epochs in
between). That requires per-trial cross-log assembly, a harder capability than
this log-level manifest supports; the result is a known ceiling (CUT). Tracked
for a follow-up; do NOT hand-assemble it into a single evidence-admissible screen here.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from skill_harness.storage.models import D4CheckState
from skill_harness.storage.repositories.evidence.screens import (
    derive_p0_by_skill,
    get_screen_run_by_id,
    supersede_screen_run,
)
from skill_harness.subject.ingest import ParsedEvalLog, parse_eval_log
from skill_harness.subject.screen_ingest import (
    AdmissibilityState,
    ScreenIngestResult,
    derived_screen_run_id,
    ingest_screen_eval_log,
    write_screen_evidence,
)

# ---------------------------------------------------------------------------
# D4 leak check — prompt text or fixture files leaking the skill's rule
# ---------------------------------------------------------------------------

_D4_LEAK_REASON = "apparatus_void: D4 prompt leak"

# #395 criterion 2 — d4_check_state (migration 1000).
#
# A screen_runs row that never ran D4 must be distinguishable from one that ran
# and came back clean. The marker is the coded column ``d4_check_state``:
#
#   unknown_legacy  pre-migration rows only (SQLite DEFAULT; never written)
#   not_applicable  entry carried neither operative_rule nor prompt_text
#   ran_clean       check ran; no normalised verbatim match
#   ran_flagged     check ran; leak found
#
# Same-field placement (``inadmissibility_reason = "d4: not_checked"``) is
# blocked by the write_screen_evidence guard that refuses an admissible row
# carrying a reason — that column means WHY THIS IS INADMISSIBLE. The four-
# state vocabulary and the decision against a companion table are recorded on
# issue 395 (owner comment, 2026-09-02).


class ScreenManifestError(ValueError):
    """A manifest entry is internally inconsistent and cannot be applied.

    Raised for a HALF-SPECIFIED D4 entry: ``operative_rule`` without
    ``prompt_text`` or the reverse. Such an entry was previously admitted with
    the check silently skipped, which is indistinguishable in the store from an
    entry that was checked and found clean (#395 criterion 2).
    """


@dataclass(frozen=True)
class D4LeakResult:
    """Result of a D4 prompt-leak check.

    ``leaked`` is True when the skill's operative rule was found in the prompt
    text or in any fixture file the prompt references.  ``locations`` names
    where the rule appeared (e.g. ``"prompt"`` or ``"RELEASING.md"``).
    ``searched`` names every source actually compared, in order, so a reader
    can tell a prompt-only check from one that also read fixture files, and can
    tell either from a check that compared nothing.
    """

    leaked: bool
    locations: tuple[str, ...] = ()
    searched: tuple[str, ...] = ()


def check_d4_prompt_leak(
    operative_rule: str,
    prompt_text: str,
    prompt_fixture_files: dict[str, str] | None = None,
) -> D4LeakResult:
    """Check whether a screen prompt leaks the skill's operative rule (D4).

    The check searches:

    1. The **prompt text** itself (direct leak — e.g. ``appendonly``, ``bayes``,
       ``judgegate``).
    2. Every **fixture file** the prompt names or references (indirect /
       one-hop leak — e.g. ``gitpull`` pointing at ``RELEASING.md``).

    Both the rule and the searched text are normalised (lowercased, whitespace
    collapsed) before comparison, so phrasing variation does not produce false
    negatives.

    BOUND, and it is the reason a clean result is weaker than it looks (#395
    criterion 3): this is a SUBSTRING match after normalisation. A prompt that
    PARAPHRASES the operative rule is reported clean, because no normalised
    verbatim match exists. The D4 finding
    (``docs/findings/d4-prompt-leak-into-null-arm.md``) classified
    ``appendonly``, ``bayes`` and ``judgegate`` as leaks by READING the prompts
    against the cards, not by string match, so this check and that finding can
    disagree on the same inputs. Read a clean result as "no normalised verbatim
    match", never as "no leak".

    Returns a :class:`D4LeakResult` stating whether a leak was found, where it
    hit, and which sources were compared.
    """
    rule_norm = _normalise(operative_rule)
    if not rule_norm:
        # Nothing to match, so nothing was compared: `searched` stays empty
        # rather than claiming sources this call never read.
        return D4LeakResult(leaked=False)

    locations: list[str] = []
    searched: list[str] = ["prompt"]

    # 1. Direct check: rule in prompt text.
    if rule_norm in _normalise(prompt_text):
        locations.append("prompt")

    # 2. Indirect check: rule in fixture files the prompt references.
    if prompt_fixture_files:
        for filename, content in prompt_fixture_files.items():
            searched.append(filename)
            if rule_norm in _normalise(content):
                locations.append(filename)

    return D4LeakResult(
        leaked=bool(locations),
        locations=tuple(locations),
        searched=tuple(searched),
    )


def format_d4_leak_reason(result: D4LeakResult) -> str:
    """Render a leak result as the store's ``inadmissibility_reason`` (#395 criterion 1).

    Shape::

        apparatus_void: D4 prompt leak; hit=prompt,RELEASING.md; searched=prompt,RELEASING.md

    The leading ``apparatus_void: D4 prompt leak`` is preserved verbatim so
    existing prefix matches keep working, including the re-disposition step on
    issue 381's criterion 3. Everything after the first ``;`` is
    ``key=comma,separated,values``, so a reader can parse which sources hit and
    which were compared at all.

    BOUND: the grammar has no escaping. A fixture filename containing ``,`` or
    ``;`` would render ambiguously. Every fixture name in the manifest today is
    a plain basename, so this is a stated limit rather than a live defect; give
    the field a real encoding before admitting arbitrary filenames.
    """
    return (
        f"{_D4_LEAK_REASON}; hit={','.join(result.locations)}; searched={','.join(result.searched)}"
    )


def _normalise(text: str) -> str:
    """Lower-case and collapse whitespace for comparison."""
    return re.sub(r"\s+", " ", text.lower()).strip()


@dataclass(frozen=True)
class ScreenManifestEntry:
    """One curated backfill decision: a source log + its evidence-admissibility ruling.

    ``rel_path`` is relative to the screens root (the local, gitignored
    ``.private/microrun`` tree). ``expected_skill`` / ``expected_pass`` are
    self-checks: the apply step surfaces any disagreement with the stored
    evidence rather than trusting the manifest blindly.

    When ``operative_rule`` and ``prompt_text`` are set, ``apply_manifest``
    runs the D4 prompt-leak check and overrides ``admissibility_state`` to
    ``inadmissible`` (with reason ``apparatus_void: D4 prompt leak``) if the
    rule is found in the prompt text or any of the ``prompt_fixture_files``.
    """

    rel_path: str
    admissibility_state: AdmissibilityState
    inadmissibility_reason: str | None
    expected_skill: str
    expected_pass: int  # expected passing epochs in THIS log (audit self-check)
    operative_rule: str | None = None
    prompt_text: str | None = None
    prompt_fixture_files: dict[str, str] = field(default_factory=dict)


# Curated batch-1 manifest. Paths are under the gitignored .private/microrun
# tree; the manifest (decisions + citations) is the committed, auditable
# artifact — the raw logs stay local.
BATCH1_MANIFEST: tuple[ScreenManifestEntry, ...] = (
    ScreenManifestEntry(
        rel_path="batch1/appendonly/logs-stage0/"
        "2026-07-10T13-00-15-00-00_append-only-evidence-design-null_4mjvXbwSeu3p7Y9A4iGxXJ.eval",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        expected_skill="append-only-evidence-design",
        expected_pass=3,
    ),
    ScreenManifestEntry(
        rel_path="batch1/bayes/logs-stage0/"
        "2026-07-10T12-12-20-00-00_bayesian-eval-discipline-null_RhDuM6AK6nJFcB2887ca7R.eval",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        expected_skill="bayesian-eval-discipline",
        expected_pass=3,
    ),
    ScreenManifestEntry(
        rel_path="batch1/tiebreak/logs-stage0/"
        "2026-07-10T11-21-00-00-00_sqlite-tie-break-red-test-trap-null_VQ4ja8CmFMXKfDsyviqN9S.eval",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        expected_skill="sqlite-tie-break-red-test-trap",
        expected_pass=3,
    ),
    ScreenManifestEntry(
        rel_path="batch1/tiebreak/logs-stage0/"
        "2026-07-10T11-10-33-00-00_sqlite-tie-break-red-test-trap-null_jUvUz9CyAFAfFf96nJ9Tx8.eval",
        admissibility_state="inadmissible",
        inadmissibility_reason=(
            "apparatus_void: oracle exit=1 with mangled runner path and no structured "
            "ORACLE-PASS (grading harness crashed, not the subject); identical task+pin "
            "to the 11-21-00 run that ceilinged 3/3 eleven minutes later"
        ),
        expected_skill="sqlite-tie-break-red-test-trap",
        expected_pass=0,
    ),
    # #430: the OBS-0007 Null screen of 2026-07-21, 3/3 on the priced subject.
    # Admissible AT CAPTURE; docs/findings/d4-prompt-leak-into-null-arm.md
    # later ruled its prompt leaked one hop via RELEASING.md, and
    # supersede_d4_screen_runs (run on the same --execute) appends the
    # apparatus_void supersession. The manifest records the capture and the
    # supersession records the void, in that order, which is what the store's
    # append-only shape is for. Marking it inadmissible here would erase the
    # order and leave the D4 disposition table's gitpull row store-less.
    ScreenManifestEntry(
        rel_path="batch1/gitpull/logs-stage0/"
        "2026-07-21T03-05-28-00-00_git-pull-rebase-trap-null_E9uYtKBETxuAQtRHExMsTW.eval",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        expected_skill="git-pull-rebase-trap",
        expected_pass=3,
    ),
)


def _validate_d4_fields(manifest: tuple[ScreenManifestEntry, ...]) -> None:
    """Refuse a manifest carrying a half-specified D4 entry (#395 criterion 2).

    The check needs both the rule and the prompt. An entry supplying one of
    them states an intent to check that cannot be honoured, and admitting it
    unchecked writes a row indistinguishable from a checked-and-clean one.

    An entry supplying NEITHER is legitimate and passes here. Its row stores
    ``d4_check_state='not_applicable'`` so a reader can tell it from
    ``ran_clean``.
    """
    for entry in manifest:
        has_rule = entry.operative_rule is not None
        has_prompt = entry.prompt_text is not None
        if has_rule == has_prompt:
            continue
        missing = "prompt_text" if has_rule else "operative_rule"
        present = "operative_rule" if has_rule else "prompt_text"
        raise ScreenManifestError(
            f"{entry.rel_path}: manifest entry carries {present} but not "
            f"{missing}; the D4 leak check needs both. Supply {missing}, or "
            f"drop {present} to record the row as d4_check_state=not_applicable."
        )


@dataclass(frozen=True)
class BackfillReport:
    """Outcome of a manifest apply: what was ingested + any audit mismatches."""

    ingested: tuple[ScreenIngestResult, ...]
    mismatches: tuple[str, ...]  # human-readable audit disagreements (empty == clean)
    # Entries whose screen task was already in the store (#430): a re-run
    # against a live store is the normal case once the manifest has grown,
    # and it must reach the new entries instead of refusing at the first old one.
    skipped: tuple[str, ...] = ()


def apply_manifest(
    screens_root: Path,
    conn: sqlite3.Connection,
    *,
    manifest: tuple[ScreenManifestEntry, ...] = BATCH1_MANIFEST,
    parse: Callable[[Path], ParsedEvalLog] = parse_eval_log,
) -> BackfillReport:
    """Ingest every manifest entry into the screen store, auditing against expectations.

    ``parse`` is injectable so callers/tests can supply already-parsed logs
    without the optional ``[inspect]`` extra or the private log tree. Each
    ingest's skill_name and pass count are checked against the manifest's
    ``expected_*``; disagreements are collected (not silently swallowed) so a
    stale manifest or a surprising log surfaces rather than corrupting p0.

    Every entry's D4 fields are validated BEFORE anything is written, so a
    half-specified entry anywhere in the manifest refuses the whole apply rather
    than leaving earlier entries persisted behind a later failure.

    :raises ScreenManifestError: an entry carries exactly one of
        ``operative_rule`` / ``prompt_text`` (#395 criterion 2).
    :raises FileNotFoundError: a manifest path is absent under ``screens_root``.
    """
    _validate_d4_fields(manifest)

    ingested: list[ScreenIngestResult] = []
    mismatches: list[str] = []
    skipped: list[str] = []
    for entry in manifest:
        path = screens_root / entry.rel_path
        if not path.is_file():
            raise FileNotFoundError(f"manifest log not found: {path}")
        parsed = parse(path)

        # #430: an entry already in the store is skipped, not refused. The
        # writer's own guard decides (same derivation of screen_run_id), so a
        # re-run cannot double-ingest; it reports what it left alone.
        existing_id = derived_screen_run_id(parsed.task_id)
        if get_screen_run_by_id(conn, existing_id) is not None:
            skipped.append(f"{entry.rel_path}: already ingested as {existing_id}")
            continue

        # --- D4 prompt-leak check (when manifest supplies the inputs) ---------
        # D4 hit -> inadmissible ruling. Not an audit mismatch (mismatches =
        # manifest-vs-log only); CLI treats mismatches as backfill failure.
        admissibility = entry.admissibility_state
        reason = entry.inadmissibility_reason
        # #395 criterion 2: coded marker so "never checked" != "checked clean".
        d4_state: D4CheckState = "not_applicable"
        if entry.operative_rule is not None and entry.prompt_text is not None:
            leak = check_d4_prompt_leak(
                entry.operative_rule,
                entry.prompt_text,
                entry.prompt_fixture_files or None,
            )
            if leak.leaked:
                admissibility = "inadmissible"
                reason = format_d4_leak_reason(leak)
                d4_state = "ran_flagged"
            else:
                d4_state = "ran_clean"

        result = write_screen_evidence(
            parsed=parsed,
            source_eval_sha256=_sha256_file(path),
            admissibility_state=admissibility,
            inadmissibility_reason=reason,
            d4_check_state=d4_state,
            conn=conn,
        )
        ingested.append(result)
        if result.skill_name != entry.expected_skill:
            mismatches.append(
                f"{entry.rel_path}: skill {result.skill_name!r} != expected "
                f"{entry.expected_skill!r}"
            )
        if result.n_pass != entry.expected_pass:
            mismatches.append(
                f"{entry.rel_path}: {result.n_pass} passing epochs != expected "
                f"{entry.expected_pass}"
            )
    return BackfillReport(
        ingested=tuple(ingested), mismatches=tuple(mismatches), skipped=tuple(skipped)
    )


# convenience re-export so callers backfill + read p0 from one module
__all__ = [
    "BATCH1_MANIFEST",
    "BackfillReport",
    "D4LeakResult",
    "ScreenManifestEntry",
    "ScreenManifestError",
    "apply_manifest",
    "check_d4_prompt_leak",
    "derive_p0_by_skill",
    "format_d4_leak_reason",
    "ingest_screen_eval_log",
    "supersede_d4_screen_runs",
]


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# D4 / stale-pin re-disposition — supersede the four disposition-table rows (#402)
# ---------------------------------------------------------------------------
#
# docs/findings/d4-prompt-leak-into-null-arm.md disposition table:
#   git-pull-rebase-trap          → apparatus_void D4 (leak site: RELEASING.md)
#   append-only-evidence-design   → apparatus_void D4 (leak site: prompt text)
#   bayesian-eval-discipline      → apparatus_void D4 (leak site: prompt text)
#   sqlite-tie-break-red-test-trap → stands on D4; voided on the stale-pin ground
#
# Reasons use the #401 format for D4 voids (hit=...; searched=...).

_D4_REDISPOSITION: dict[str, str] = {
    "git-pull-rebase-trap": (
        "apparatus_void: D4 prompt leak; hit=RELEASING.md; searched=prompt,RELEASING.md"
    ),
    "append-only-evidence-design": ("apparatus_void: D4 prompt leak; hit=prompt; searched=prompt"),
    "bayesian-eval-discipline": ("apparatus_void: D4 prompt leak; hit=prompt; searched=prompt"),
}

_STALE_PIN_REDISPOSITION_SKILL = "sqlite-tie-break-red-test-trap"
_STALE_PIN_REDISPOSITION_REASON = (
    "apparatus_void: stale harness pin; stored fingerprint does not match the running instrument"
)


def supersede_d4_screen_runs(conn: sqlite3.Connection) -> list[str]:
    """Supersede the four disposition-table screen runs (#402).

    Three skills are voided on D4 ground with the #401 reason format naming
    the leak site. ``sqlite-tie-break-red-test-trap`` stands on D4 (prompt is
    clean) and is voided on the independent stale-pin ground instead.

    For each target skill, finds admissible rows that are not already
    superseded and appends an inadmissible correction. Returns the list of
    superseded screen_run_ids.
    """
    superseded_ids: list[str] = []
    targets: list[tuple[str, str]] = [
        *[(name, reason) for name, reason in _D4_REDISPOSITION.items()],
        (_STALE_PIN_REDISPOSITION_SKILL, _STALE_PIN_REDISPOSITION_REASON),
    ]
    for skill_name, reason in targets:
        rows = conn.execute(
            "SELECT screen_run_id FROM screen_runs "
            "WHERE skill_name = ? AND admissibility_state = 'admissible'",
            (skill_name,),
        ).fetchall()
        for (screen_run_id,) in rows:
            existing = get_screen_run_by_id(conn, screen_run_id)
            if existing is None:
                continue
            already = conn.execute(
                "SELECT 1 FROM screen_run_supersessions WHERE superseded_screen_run_id = ?",
                (screen_run_id,),
            ).fetchone()
            if already is not None:
                continue
            supersede_screen_run(
                conn,
                superseded_screen_run_id=screen_run_id,
                reason=reason,
                admissibility_state="inadmissible",
                inadmissibility_reason=reason,
                d4_check_state=(
                    "ran_flagged" if skill_name in _D4_REDISPOSITION else "not_applicable"
                ),
                skill_name=existing["skill_name"],
                subject_model=existing["subject_model"],
                harness_pin_fingerprint=existing["harness_pin_fingerprint"],
                source_eval_task_id=existing["source_eval_task_id"],
                source_eval_sha256=existing["source_eval_sha256"],
                created_at=existing["created_at"],
            )
            superseded_ids.append(screen_run_id)
    return superseded_ids
