"""Static ban on the unpinned verdict insert + the currency gate that feeds PASSED (item 10, #352).

Registered condition (docs/assurance/falsification-plan.md item 10, corrected
by this change): ``mint_oracle_verdict`` requires an ``ArticleFingerprint`` and
pins before inserting; ``insert_oracle_verdict`` remains directly callable. An
unpinned insert lets threshold-clearing evidence enter the store without the
fingerprint that establishes what it was measured against. Separately, the
gate that actually decides PASSED is the frozen-case currency mechanism:
``frozen_cases_with_currency`` labels each case ``current`` only when its
``metric_version`` AND ``implementation_hash`` match the current audited
metric version, and ``derive_clause_status`` requires
``current_frozen_case_count >= 1`` for PASSED (A15/A57).

The plan's original item 10 text pointed at ``is_stale_vs_fleet``, which has
no production caller (verified: its only call sites are four lines in
``tests/test_article_fingerprint.py``); the plan text is corrected in the same
change so the registered mechanism matches the tree.

Static half (the ``tests/test_structural_bans.py`` convention, including the
pre-commit mirror ``ban-unpinned-verdict-insert`` and the F-8 drift
cross-check):

- Production modules must not call ``insert_oracle_verdict`` outside the
  allowlist: the defining repository module (the mint path calls it after
  pinning) and ``storage/dual_write.py`` (documented historical/reconciler
  helper).
- Allowlist entries must still contain the call, so a retired caller cannot
  leave a dead allowlist row behind.
- ``write_verdict_with_cost_entry``'s docstring claims zero live callers;
  this module VERIFIES that claim instead of inheriting it, per the ticket.
  If it fires, record the finding on #341 (the allowlist question changes
  shape).

Behavioural half:

- A frozen case whose currency state is not ``current`` cannot satisfy the
  PASSED frozen-case gate: ``derive_clause_status`` at a decisive posterior
  with zero current cases returns UNMEASURED with FALSIFYING_CASE_STALE (or
  _MISSING), never PASSED; the positive control with one current case returns
  PASSED.
- The view itself: a hash-mismatched case labels ``stale``, a version-and-hash
  match labels ``current``, and a metric with no audited current version
  labels ``no_current_metric_version`` -- none of the non-current states may
  read as ``current``.

Test and fixture call sites of the raw insert are out of scope by design
(twenty-two across eight files at authoring time; they are legitimate).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from skill_harness.aggregation.status import (
    ClauseStatus,
    ClauseStatusInput,
    UnmeasuredSubReason,
    derive_clause_status,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
PRECOMMIT = REPO_ROOT / ".pre-commit-config.yaml"

_INSERT_CALL_RE = re.compile(r"\binsert_oracle_verdict\s*\(")

# The two production modules allowed to call the raw insert. Everything else
# routes through mint_oracle_verdict, which pins first.
_ALLOWLIST = {
    SRC_ROOT / "skill_harness" / "storage" / "repositories" / "evidence" / "oracle_verdicts.py",
    SRC_ROOT / "skill_harness" / "storage" / "dual_write.py",
}


def _production_py_files() -> list[Path]:
    return [p for p in SRC_ROOT.rglob("*.py") if ".sandcastle" not in p.parts]


class TestUnpinnedInsertBan:
    def test_no_unpinned_insert_outside_allowlist(self) -> None:
        offenders = [
            p
            for p in _production_py_files()
            if p not in _ALLOWLIST and _INSERT_CALL_RE.search(p.read_text(encoding="utf-8"))
        ]
        assert not offenders, (
            f"MINT_PATH_BYPASS: production module(s) call insert_oracle_verdict"
            f" outside the allowlist: {[str(p.relative_to(REPO_ROOT)) for p in offenders]}."
            f" An unpinned insert admits threshold-clearing evidence without the"
            f" ArticleFingerprint that establishes what it was measured against;"
            f" route through mint_oracle_verdict or extend the allowlist here,"
            f" in the pre-commit mirror, and in the plan's item 10 with"
            f" justification."
        )

    def test_allowlist_entries_still_call_the_insert(self) -> None:
        stale = [
            p
            for p in sorted(_ALLOWLIST)
            if not (p.is_file() and _INSERT_CALL_RE.search(p.read_text(encoding="utf-8")))
        ]
        assert not stale, (
            f"MINT_ALLOWLIST_STALE: allowlist entr(y/ies)"
            f" {[str(p.relative_to(REPO_ROOT)) for p in stale]} no longer call"
            f" insert_oracle_verdict (or no longer exist); remove them here and"
            f" in the pre-commit mirror so the allowlist cannot grow dead rows."
        )

    def test_exclude_matches_pre_commit_config(self) -> None:
        """F-8 cross-check: the pre-commit mirror excludes the SAME file set."""
        config = PRECOMMIT.read_text(encoding="utf-8")
        m = re.search(r"- id: ban-unpinned-verdict-insert\n(?:.*\n)*?\s+exclude: '([^']+)'", config)
        assert m, (
            "MINT_BAN_MIRROR_MISSING: .pre-commit-config.yaml has no"
            " ban-unpinned-verdict-insert hook with an exclude regex; the static"
            " ban must exist in both layers (test_structural_bans.py convention)."
        )
        exclude_re = re.compile(m.group(1))
        for p in _production_py_files():
            rel = p.relative_to(REPO_ROOT).as_posix()
            assert bool(exclude_re.search(rel)) == (p in _ALLOWLIST), (
                f"MINT_BAN_ALLOWLIST_DRIFT: {rel} is"
                f" {'excluded' if exclude_re.search(rel) else 'not excluded'} by"
                f" the pre-commit mirror but"
                f" {'in' if p in _ALLOWLIST else 'not in'} this module's"
                f" allowlist; the two layers have drifted (F-8)."
            )

    def test_dormant_dual_write_helper_has_no_live_caller(self) -> None:
        """Verify, not inherit, dual_write's zero-live-callers self-report."""
        callers = [
            p
            for p in _production_py_files()
            if p.name != "dual_write.py"
            and p.name != "__init__.py"
            and re.search(r"\bwrite_verdict_with_cost_entry\s*\(", p.read_text(encoding="utf-8"))
        ]
        assert not callers, (
            f"DORMANT_HELPER_AWOKE: write_verdict_with_cost_entry has live"
            f" production caller(s) {[str(p.relative_to(REPO_ROOT)) for p in callers]}"
            f" despite its docstring's zero-live-callers claim. Per #352's"
            f" revisit clause the allowlist question changes shape; record the"
            f" finding on #341."
        )


_DECISIVE = dict(
    axis="verbosity",
    admissible_verdict_count=40,
    total_verdict_count=40,
    confounded_verdict_count=0,
    n_verdicts=40,
    p_win_gt_threshold=0.99,
)


class TestCurrencyGateFeedsPassed:
    def test_stale_only_frozen_case_cannot_satisfy_passed_gate(self) -> None:
        status, reason = derive_clause_status(
            ClauseStatusInput(
                **_DECISIVE,  # type: ignore[arg-type]
                current_frozen_case_count=0,
                any_stale_frozen_case=True,
            )
        )
        assert (status, reason) == (
            ClauseStatus.UNMEASURED,
            UnmeasuredSubReason.FALSIFYING_CASE_STALE,
        ), (
            f"STALE_CASE_SATISFIED_PASSED_GATE: a decisive posterior with only"
            f" a STALE frozen case derived ({status}, {reason}) instead of"
            f" UNMEASURED/FALSIFYING_CASE_STALE; evidence frozen against an"
            f" outdated metric is feeding PASSED (violates A15)."
        )

    def test_missing_frozen_case_cannot_satisfy_passed_gate(self) -> None:
        status, reason = derive_clause_status(
            ClauseStatusInput(
                **_DECISIVE,  # type: ignore[arg-type]
                current_frozen_case_count=0,
                any_stale_frozen_case=False,
            )
        )
        assert (status, reason) == (
            ClauseStatus.UNMEASURED,
            UnmeasuredSubReason.FALSIFYING_CASE_MISSING,
        ), (
            f"MISSING_CASE_SATISFIED_PASSED_GATE: a decisive posterior with NO"
            f" frozen case derived ({status}, {reason}) instead of"
            f" UNMEASURED/FALSIFYING_CASE_MISSING (violates A15)."
        )

    def test_current_frozen_case_passes_positive_control(self) -> None:
        status, reason = derive_clause_status(
            ClauseStatusInput(
                **_DECISIVE,  # type: ignore[arg-type]
                current_frozen_case_count=1,
                any_stale_frozen_case=False,
            )
        )
        assert (status, reason) == (ClauseStatus.PASSED, None), (
            f"PASSED_GATE_POSITIVE_CONTROL_BROKEN: a decisive posterior WITH a"
            f" current frozen case derived ({status}, {reason}); the gate or"
            f" this harness is wrong and the stale/missing tests above cannot"
            f" be trusted either way."
        )


_TS = "2026-08-31T00:00:00Z"
_SHA = "a" * 64


def _seed_currency_world(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES ('sk1', 'S', '/p', ?, ?)",
        (_SHA, _TS),
    )
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag) VALUES"
        " ('cl1', 'sk1', 0, 0, 'text', 'verbosity', 'increase', 1, 'none')"
    )
    # Metric m1: an old audited version then a newer audited current version.
    conn.execute(
        "INSERT INTO metric_versions (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES ('m1', '1.0.0', 'hash-old', 1, 1, 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO metric_versions (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES ('m1', '2.0.0', 'hash-new', 1, 1, 1, '2026-06-01T00:00:00Z')"
    )
    # Metric m2: registered but never audited -> no current version exists.
    conn.execute(
        "INSERT INTO metric_versions (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES ('m2', '1.0.0', 'hash-m2', 1, 0, 0, '2026-01-01T00:00:00Z')"
    )
    rows = [
        ("fc-current", "m1", "2.0.0", "hash-new"),
        ("fc-old-version", "m1", "1.0.0", "hash-old"),
        ("fc-hash-mismatch", "m1", "2.0.0", "hash-TAMPERED"),
        ("fc-no-current", "m2", "1.0.0", "hash-m2"),
    ]
    for fc_id, metric_id, version, impl_hash in rows:
        conn.execute(
            "INSERT INTO frozen_cases (frozen_case_id, clause_id, failing_input_text,"
            " failing_input_sha256, oracle_source, metric_id, metric_version,"
            " implementation_hash, frozen_at) VALUES (?, 'cl1', 'x', ?, 'mechanical',"
            " ?, ?, ?, ?)",
            (fc_id, _SHA, metric_id, version, impl_hash, _TS),
        )


def test_currency_view_never_promotes_non_current(evidence_db: sqlite3.Connection) -> None:
    """The view labels exactly one seeded case current, and mislabels none."""
    _seed_currency_world(evidence_db)
    evidence_db.commit()
    states = dict(
        evidence_db.execute(
            "SELECT frozen_case_id, currency_state FROM frozen_cases_with_currency"
        ).fetchall()
    )
    expected = {
        "fc-current": "current",
        "fc-old-version": "stale",
        "fc-hash-mismatch": "stale",
        "fc-no-current": "no_current_metric_version",
    }
    assert states == expected, (
        f"CURRENCY_VIEW_MISCLASSIFIES: frozen_cases_with_currency labelled"
        f" {states}, expected {expected}. Any non-current case read as"
        f" 'current' feeds the PASSED gate evidence frozen against a metric"
        f" other than the one currently audited (A14/A57 tamper-evidence)."
    )
