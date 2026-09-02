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

from skill_harness.storage.repositories.evidence.screens import derive_p0_by_skill
from skill_harness.subject.ingest import ParsedEvalLog, parse_eval_log
from skill_harness.subject.screen_ingest import (
    AdmissibilityState,
    ScreenIngestResult,
    ingest_screen_eval_log,
    write_screen_evidence,
)

# ---------------------------------------------------------------------------
# D4 leak check — prompt text or fixture files leaking the skill's rule
# ---------------------------------------------------------------------------

_D4_LEAK_REASON = "apparatus_void: D4 prompt leak"


@dataclass(frozen=True)
class D4LeakResult:
    """Result of a D4 prompt-leak check.

    ``leaked`` is True when the skill's operative rule was found in the prompt
    text or in any fixture file the prompt references.  ``locations`` names
    where the rule appeared (e.g. ``"prompt"`` or ``"RELEASING.md"``).
    """

    leaked: bool
    locations: tuple[str, ...] = ()


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

    Returns a :class:`D4LeakResult` stating whether a leak was found and where.
    """
    rule_norm = _normalise(operative_rule)
    if not rule_norm:
        return D4LeakResult(leaked=False)

    locations: list[str] = []

    # 1. Direct check: rule in prompt text.
    if rule_norm in _normalise(prompt_text):
        locations.append("prompt")

    # 2. Indirect check: rule in fixture files the prompt references.
    if prompt_fixture_files:
        for filename, content in prompt_fixture_files.items():
            if rule_norm in _normalise(content):
                locations.append(filename)

    if locations:
        return D4LeakResult(leaked=True, locations=tuple(locations))
    return D4LeakResult(leaked=False)


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
)


@dataclass(frozen=True)
class BackfillReport:
    """Outcome of a manifest apply: what was ingested + any audit mismatches."""

    ingested: tuple[ScreenIngestResult, ...]
    mismatches: tuple[str, ...]  # human-readable audit disagreements (empty == clean)


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

    :raises FileNotFoundError: a manifest path is absent under ``screens_root``.
    """
    ingested: list[ScreenIngestResult] = []
    mismatches: list[str] = []
    for entry in manifest:
        path = screens_root / entry.rel_path
        if not path.is_file():
            raise FileNotFoundError(f"manifest log not found: {path}")
        parsed = parse(path)

        # --- D4 prompt-leak check (when manifest supplies the inputs) ---------
        # D4 hit → inadmissible ruling. Not an audit mismatch (mismatches =
        # manifest-vs-log only); CLI treats mismatches as backfill failure.
        admissibility = entry.admissibility_state
        reason = entry.inadmissibility_reason
        if entry.operative_rule is not None and entry.prompt_text is not None:
            leak = check_d4_prompt_leak(
                entry.operative_rule,
                entry.prompt_text,
                entry.prompt_fixture_files or None,
            )
            if leak.leaked:
                admissibility = "inadmissible"
                reason = _D4_LEAK_REASON

        result = write_screen_evidence(
            parsed=parsed,
            source_eval_sha256=_sha256_file(path),
            admissibility_state=admissibility,
            inadmissibility_reason=reason,
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
    return BackfillReport(ingested=tuple(ingested), mismatches=tuple(mismatches))


# convenience re-export so callers backfill + read p0 from one module
__all__ = [
    "BATCH1_MANIFEST",
    "BackfillReport",
    "D4LeakResult",
    "ScreenManifestEntry",
    "apply_manifest",
    "check_d4_prompt_leak",
    "derive_p0_by_skill",
    "ingest_screen_eval_log",
]


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
