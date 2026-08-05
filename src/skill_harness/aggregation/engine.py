"""Aggregation engine — `aggregate_skill()` (A54).

Pure read-side aggregation library. NO API calls. NO sampling. NO writes.

Callers (Track E.3 CLI) supply already-opened DB connections; this module
never opens a raw sqlite3 connection itself. All reads go through the
received connections to maintain pragma/FK discipline (open_db() invariant).

Design:
- Discovers completed ablation runs for skill_id.
- Validates preconditions (incomplete runs → PreconditionError).
- Reads admissible verdicts via the admissible_verdicts VIEW (A29).
- Reads frozen_cases_with_currency VIEW (A57 / 0401 migration) for PASSED gate.
- Fits EB-MoM / BH-FDR / UNPOOLED per A53.
- Derives per-clause status via the A57 state machine.
- Returns a SkillReport dataclass (E.3 renders it; this module is format-agnostic).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from collections import defaultdict
from sqlite3 import Connection
from typing import Any

from skill_harness.aggregation.errors import MalformedRunConfig, PreconditionError
from skill_harness.aggregation.fit import ClauseObservations, ClausePosterior, FitResult, fit_skill
from skill_harness.aggregation.report import (
    REPORT_SCHEMA_VERSION,
    ClauseReport,
    ContributionSummary,
    SkillReport,
    VectorSummary,
)
from skill_harness.aggregation.status import (
    ClauseStatus,
    ClauseStatusInput,
    derive_clause_status,
)
from skill_harness.storage.recovery import find_incomplete_runs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def aggregate_skill(
    skill_id: str,
    *,
    evidence_conn_ro: Connection,
    runtime_conn: Connection,
    harness_version: str,
    generated_at_utc: str,  # caller-supplied — never datetime.now() here
) -> SkillReport:
    """Pure read-side aggregation. NO API calls. NO sampling. NO writes.

    Discovers runs with skill_id matching + run_kind='ablation' + completed_at IS NOT NULL.
    Reads admissible+non-confounded verdicts via the admissible_verdicts VIEW (A29).
    Reads frozen_cases_with_currency VIEW (A57) to gate PASSED.
    Returns the SkillReport dataclass (serialised by E.3 layer).

    Preconditions checked (raises if violated):
    - any incomplete runs for skill_id → PreconditionError('incomplete_runs', [run_ids])
    - no completed runs for skill_id → PreconditionError('no_completed_runs')
    - no clauses authored for skill_id → PreconditionError('no_clauses')
    - clauses exist but none has an instantiated frozen_cases row →
      PreconditionError('no_instantiated_frozen_cases')
    """
    # ------------------------------------------------------------------
    # Precondition 1: No incomplete runs (would bias aggregation)
    # ------------------------------------------------------------------
    incomplete = find_incomplete_runs(
        skill_id,
        evidence_conn_ro=evidence_conn_ro,
        runtime_conn=runtime_conn,
    )
    if incomplete:
        run_ids = [r.run_id for r in incomplete]
        raise PreconditionError("incomplete_runs", run_ids)

    # ------------------------------------------------------------------
    # Discover completed ablation runs
    # ------------------------------------------------------------------
    completed_runs = _fetch_completed_ablation_runs(evidence_conn_ro, skill_id)
    if not completed_runs:
        raise PreconditionError("no_completed_runs")

    # ------------------------------------------------------------------
    # Load clauses for skill
    # ------------------------------------------------------------------
    all_clauses = _fetch_clauses(evidence_conn_ro, skill_id)
    total_clause_count = len(all_clauses)

    # ------------------------------------------------------------------
    # Read family_size from config_json (A59) — use first completed run
    # (all completed runs for a skill should share the same config shape)
    # ------------------------------------------------------------------
    family_size = _read_family_size(completed_runs)

    # ------------------------------------------------------------------
    # Collect all admissible verdicts across completed runs
    # Keyed by (clause_id, axis) -> list of observation values
    # ------------------------------------------------------------------
    clause_axis_observations: dict[tuple[str, str], list[float]] = defaultdict(list)
    clause_axis_run_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    # B6: collect ALL metric_id / metric_version values per key — detect divergence
    # at resolution time (mirrors op_hash/subject_model MIXED pattern), instead of
    # last-write-wins which silently drops earlier-scored metric provenance.
    clause_axis_metric_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    clause_axis_metric_versions: dict[tuple[str, str], set[str]] = defaultdict(set)
    # I2: collect ALL op_hashes per (clause_id, axis) — detect divergence at resolution time
    clause_axis_op_hashes: dict[tuple[str, str], set[str]] = defaultdict(set)

    # A55 comparability axes: track per-run subject_model + user_message_sha256
    run_id_to_subject_model: dict[str, str | None] = {}
    run_id_to_user_msg_sha: dict[str, str | None] = {}

    # Track full_vs_null observations for ContributionSummary (A50)
    full_vs_null_observations: list[float] = []

    # Track total + inadmissible verdict counts per clause
    clause_total_verdicts: dict[tuple[str, str], int] = defaultdict(int)
    clause_inadmissible_verdicts: dict[tuple[str, str], int] = defaultdict(int)
    # Track confounded verdicts (verdicts that were filtered by the VIEW — confound-flagged)
    clause_confounded_verdicts: dict[tuple[str, str], int] = defaultdict(int)

    run_ids_seen: set[str] = set()
    run_id_to_state: dict[str, str | None] = {}

    # Fetch run_progress states for budget_exhausted detection
    for run in completed_runs:
        run_id = run["run_id"]
        run_ids_seen.add(run_id)
        run_id_to_state[run_id] = _fetch_run_state(runtime_conn, run_id)

    for run in completed_runs:
        run_id = run["run_id"]

        # Admissible+non-confounded verdicts (VIEW)
        admissible_rows = evidence_conn_ro.execute(
            "SELECT clause_id, axis, observation, comparison, "
            "metric_id, metric_version "
            "FROM admissible_verdicts WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        for row in admissible_rows:
            clause_id, axis, obs, comparison, metric_id, metric_version = row
            key = (clause_id, axis)
            clause_axis_observations[key].append(float(obs))
            clause_axis_run_ids[key].add(run_id)
            # B6: record ALL distinct metric provenance values seen; resolved
            # (single value vs MIXED) below once all rows have been scanned.
            if metric_id is not None:
                clause_axis_metric_ids[key].add(metric_id)
            if metric_version is not None:
                clause_axis_metric_versions[key].add(metric_version)

            if comparison == "full_vs_null":
                full_vs_null_observations.append(float(obs))

        # Total verdicts (raw table — for inadmissible / confounded detection)
        total_rows = evidence_conn_ro.execute(
            "SELECT clause_id, axis, admissibility_state FROM oracle_verdicts WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        for row in total_rows:
            clause_id, axis, adm = row
            key = (clause_id, axis)
            clause_total_verdicts[key] += 1
            if adm == "inadmissible":
                clause_inadmissible_verdicts[key] += 1

        # Confounded verdicts: those that were in oracle_verdicts but excluded by VIEW
        # = admissible raw rows that have confound_events with delta_kind='confound_flagged'
        confounded_rows = evidence_conn_ro.execute(
            """
            SELECT DISTINCT v.clause_id, v.axis
            FROM oracle_verdicts v
            JOIN confound_events ce
              ON ce.run_id = v.run_id
             AND ce.primary_clause_id = v.clause_id
             AND ce.delta_kind = 'confound_flagged'
            WHERE v.run_id = ? AND v.admissibility_state = 'admissible'
            """,
            (run_id,),
        ).fetchall()
        for row in confounded_rows:
            clause_id, axis = row
            key = (clause_id, axis)
            # Count the admissible-but-confounded verdicts for this run
            cnt = evidence_conn_ro.execute(
                """
                SELECT COUNT(*) FROM oracle_verdicts v
                WHERE v.run_id = ? AND v.clause_id = ? AND v.axis = ?
                  AND v.admissibility_state = 'admissible'
                  AND EXISTS (
                    SELECT 1 FROM confound_events ce
                    WHERE ce.run_id = v.run_id
                      AND ce.primary_clause_id = v.clause_id
                      AND ce.delta_kind = 'confound_flagged'
                  )
                """,
                (run_id, clause_id, axis),
            ).fetchone()
            clause_confounded_verdicts[key] += cnt[0] if cnt else 0

        # Ablation operator hash + A55 comparability fields — read from runs.config_json
        config_json = run.get("config_json", "{}")
        try:
            config = json.loads(config_json)
        except (json.JSONDecodeError, TypeError):
            config = {}
        op_hash = config.get("ablation_operator_hash") or "unknown"
        for key in clause_axis_run_ids:
            if run_id in clause_axis_run_ids[key]:
                clause_axis_op_hashes[key].add(op_hash)

        # A55: capture subject_model + user_message_sha256 per run
        run_id_to_subject_model[run_id] = config.get("subject_model")
        user_msg = config.get("user_message")
        if user_msg is not None:
            run_id_to_user_msg_sha[run_id] = hashlib.sha256(
                str(user_msg).encode("utf-8")
            ).hexdigest()
        else:
            run_id_to_user_msg_sha[run_id] = None

    # ------------------------------------------------------------------
    # Frozen case currency counts per (clause_id, axis) from VIEW
    # ------------------------------------------------------------------
    frozen_current_counts: dict[tuple[str, str], int] = defaultdict(int)
    frozen_stale_any: dict[tuple[str, str], bool] = defaultdict(bool)

    # Fetch all frozen_cases_with_currency rows for the skill's clauses
    if all_clauses:
        clause_ids = [c["clause_id"] for c in all_clauses]
        placeholders = ",".join("?" * len(clause_ids))
        fwc_rows = evidence_conn_ro.execute(
            f"SELECT clause_id, axis, currency_state FROM frozen_cases_with_currency "  # noqa: S608
            f"WHERE clause_id IN ({placeholders})",
            clause_ids,
        ).fetchall()
        for row in fwc_rows:
            fclause_id, faxis, fcurrency = row
            key = (fclause_id, faxis)
            if fcurrency == "current":
                frozen_current_counts[key] += 1
            elif fcurrency == "stale":
                frozen_stale_any[key] = True

    # ------------------------------------------------------------------
    # Build per-clause ClauseObservations for fit
    # ------------------------------------------------------------------
    # We aggregate over all (clause_id, axis) pairs that have any admissible data.
    # Clauses with NO admissible data are still included in the report as UNMEASURED.

    # All known (clause_id, axis) keys — union of observed + all clauses
    all_keys: set[tuple[str, str]] = set()
    for c in all_clauses:
        cid = c["clause_id"]
        # Each clause has exactly one axis in the schema
        all_keys.add((cid, c["axis"]))
    # Also add any keys seen in observations (should be a subset, but be defensive)
    all_keys.update(clause_axis_observations.keys())

    # ------------------------------------------------------------------
    # Fit: only on keys that have >= 1 admissible observation
    # ------------------------------------------------------------------
    keys_with_data = [k for k in all_keys if clause_axis_observations.get(k)]
    obs_inputs = [
        ClauseObservations(
            clause_id=k[0],
            w=sum(clause_axis_observations[k]),
            n=len(clause_axis_observations[k]),
        )
        for k in keys_with_data
    ]

    fit_result: FitResult | None = None
    posteriors_by_key: dict[tuple[str, str], ClausePosterior] = {}

    if obs_inputs:
        fit_result = fit_skill(obs_inputs)
        for i, key in enumerate(keys_with_data):
            posteriors_by_key[key] = fit_result.posteriors[i]

    # ------------------------------------------------------------------
    # Derive per-clause status + build ClauseReport objects
    # ------------------------------------------------------------------
    clause_reports: list[ClauseReport] = []
    status_counts: dict[str, int] = {
        "PASSED": 0,
        "FAILED": 0,
        "CONFOUNDED": 0,
        "UNMEASURED": 0,
    }
    unmeasured_breakdown: dict[str, int] = defaultdict(int)

    for key in sorted(all_keys):  # deterministic ordering
        clause_id, axis = key
        obs_list = clause_axis_observations.get(key, [])
        n = len(obs_list)
        w = sum(obs_list)

        # Get posterior if available
        posterior = posteriors_by_key.get(key)
        if posterior is not None:
            assert isinstance(posterior, ClausePosterior)
            p_win = posterior.p_win_gt_threshold
            post_mean = posterior.posterior_mean
            ci_lo = posterior.credible_interval_lo
            ci_hi = posterior.credible_interval_hi
            is_prior_only = False
        else:
            # B5: no admissible data — this is an uninformative Beta(1,1) PRIOR, not a
            # measurement. Values are shape-identical to a genuine near-0.5 measured
            # result (posterior_mean=0.5, p_win=0.4, CI=[0.025,0.975]); is_prior_only
            # marks them so a numeric-field consumer (dashboard/diff/reviewer) does not
            # mistake "UNMEASURED" for "measured at 0.5" (report.py ClauseReport).
            from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

            p_win = float(beta_dist.sf(0.60, 1.0, 1.0))
            post_mean = 0.5
            ci_lo = float(beta_dist.ppf(0.025, 1.0, 1.0))
            ci_hi = float(beta_dist.ppf(0.975, 1.0, 1.0))
            is_prior_only = True

        # Determine run state for this clause's runs
        # Use aborted_budget if any run for this clause was aborted
        clause_run_ids = clause_axis_run_ids.get(key, set())
        run_state: str | None = None
        for rid in clause_run_ids:
            st = run_id_to_state.get(rid)
            if st == "aborted_budget":
                run_state = "aborted_budget"
                break

        # Count distinct verdict kinds
        total = clause_total_verdicts.get(key, 0)
        confounded = clause_confounded_verdicts.get(key, 0)
        inadmissible = clause_inadmissible_verdicts.get(key, 0)
        admissible_count = n  # admissible + non-confounded

        # For CONFOUNDED rule: admissible_count == 0 AND confounded > 0
        # But the VIEW already excludes confounded, so admissible_count > 0 means
        # there are non-confounded verdicts. If admissible_count == 0 but there
        # are confounded verdicts, the clause is CONFOUNDED.
        # Let's compute whether ALL verdicts are confounded:
        # total = all verdicts; inadmissible = inadmissible ones
        # admissible_raw = total - inadmissible; confounded = admissible-but-confounded
        # non_confounded_admissible = admissible_raw - confounded (= n above)
        all_confounded_flag = (
            total > 0
            and (total - inadmissible) > 0  # some admissible existed
            and admissible_count == 0  # none survived confound filter
            and confounded > 0
        )

        # B1: resolve BH-FDR gate for this clause when the skill fit fell back to
        # BH-FDR. None (not that method) leaves the raw threshold ungated.
        bh_fdr_pass: bool | None = None
        if (
            fit_result is not None
            and fit_result.aggregation_method == "bh_fdr_fallback"
            and fit_result.bh_fdr_passes is not None
        ):
            bh_fdr_pass = clause_id in fit_result.bh_fdr_passes

        # Build state machine input
        inp = ClauseStatusInput(
            axis=axis,
            admissible_verdict_count=admissible_count,
            total_verdict_count=total,
            confounded_verdict_count=confounded,
            n_verdicts=n,
            p_win_gt_threshold=p_win,
            current_frozen_case_count=frozen_current_counts.get(key, 0),
            any_stale_frozen_case=frozen_stale_any.get(key, False),
            run_state=run_state,
            bh_fdr_pass=bh_fdr_pass,
        )

        # Override for pure CONFOUNDED case
        if all_confounded_flag:
            status = ClauseStatus.CONFOUNDED
            sub_reason = None
        else:
            status, sub_reason = derive_clause_status(inp)

        status_counts[status.value] += 1
        if status == ClauseStatus.UNMEASURED and sub_reason is not None:
            unmeasured_breakdown[sub_reason.value] += 1

        # Metric provenance for this (clause_id, axis) — B6: resolve divergence to
        # a MIXED sentinel (mirrors _resolve_op_hash / _derive_a55_fields) instead
        # of the prior last-write-wins behaviour.
        metric_id_val = _resolve_metric_field(
            clause_axis_metric_ids.get(key, set()), skill_id, key, "metric_id"
        )
        metric_ver_val = _resolve_metric_field(
            clause_axis_metric_versions.get(key, set()), skill_id, key, "metric_version"
        )

        # A55 comparability: derive subject_model + user_message_sha256 for this clause
        clause_run_ids_for_key = clause_axis_run_ids.get(key, set())
        subject_model_val, user_msg_sha256_val = _derive_a55_fields(
            clause_run_ids_for_key,
            run_ids_seen,
            run_id_to_subject_model,
            run_id_to_user_msg_sha,
            skill_id=skill_id,
        )

        clause_reports.append(
            ClauseReport(
                clause_id=clause_id,
                status=status.value,
                sub_reason=sub_reason.value if sub_reason is not None else None,
                posterior_mean=post_mean,
                credible_interval_95=(ci_lo, ci_hi),
                p_win_gt_threshold=p_win,
                frozen_case_count_at_current_metric_version=frozen_current_counts.get(key, 0),
                metric_id_per_axis={axis: metric_id_val} if metric_id_val else {},
                metric_version_per_axis={axis: metric_ver_val} if metric_ver_val else {},
                ablation_operator_hash=_resolve_op_hash(
                    clause_axis_op_hashes.get(key, set()), skill_id, key
                ),
                run_ids_aggregated=tuple(sorted(clause_axis_run_ids.get(key, set()))),
                n_verdicts=n,
                w_observation_sum=w,
                subject_model=subject_model_val,
                user_message_sha256=user_msg_sha256_val,
                is_prior_only=is_prior_only,
            )
        )

    # ------------------------------------------------------------------
    # Coverage = tested_clauses / total_clauses (A15)
    # tested = has ≥1 row in frozen_cases: an instantiated failing input with an
    # oracle binding (human-labeled or mechanically scored) — not merely that a
    # falsifying case is constructible in principle from an extractor recipe.
    # ------------------------------------------------------------------
    tested_clause_ids = (
        {
            row[0]
            for row in evidence_conn_ro.execute(
                "SELECT DISTINCT clause_id FROM frozen_cases WHERE clause_id IN ("  # noqa: S608
                + ",".join("?" * len(all_clauses))
                + ")",
                [c["clause_id"] for c in all_clauses],
            ).fetchall()
        }
        if all_clauses
        else set()
    )

    # OBS-G2: zero clauses is a precondition failure — Coverage: 0% on zero clauses is a falsehood.
    if total_clause_count == 0:
        raise PreconditionError("no_clauses")
    # Corpus-wide zero frozen_cases is the same falsehood wearing a different hat:
    # the freeze stage has not produced any instantiated, oracle-bound cases yet
    # (instrument gap). It is not a finding that clauses were checked and none is
    # testable.
    if not tested_clause_ids:
        raise PreconditionError("no_instantiated_frozen_cases")
    coverage = len(tested_clause_ids) / total_clause_count

    # ------------------------------------------------------------------
    # ContributionSummary (A50): mean full_vs_null delta
    # ------------------------------------------------------------------
    if full_vs_null_observations:
        delta: float | None = sum(full_vs_null_observations) / len(full_vs_null_observations)
    else:
        delta = None

    contribution = ContributionSummary(
        full_vs_null_delta=delta,
        label="single-clause LOO; lower-bound under redundancy",
    )

    # ------------------------------------------------------------------
    # VectorSummary (§16) with coverage_warnings (M3)
    # ------------------------------------------------------------------
    coverage_warnings: list[str] = []
    n_no_scorer = unmeasured_breakdown.get("no_data", 0)
    n_no_fc = unmeasured_breakdown.get("falsifying_case_missing", 0)
    n_stale = unmeasured_breakdown.get("falsifying_case_stale", 0)
    if n_no_scorer:
        coverage_warnings.append(
            f"{n_no_scorer} clause(s) UNMEASURED: no registered Tier-1 scorer"
            " or no admissible verdicts"
        )
    if n_no_fc:
        coverage_warnings.append(
            f"{n_no_fc} clause(s) UNMEASURED: no falsifying case at current metric version"
        )
    if n_stale:
        coverage_warnings.append(
            f"{n_stale} clause(s) UNMEASURED: falsifying case stale (metric version changed)"
        )
    vector = VectorSummary(
        passed=status_counts["PASSED"],
        failed=status_counts["FAILED"],
        confounded=status_counts["CONFOUNDED"],
        unmeasured=status_counts["UNMEASURED"],
        unmeasured_breakdown=dict(unmeasured_breakdown),
        coverage=coverage,
        coverage_warnings=coverage_warnings,
    )

    # ------------------------------------------------------------------
    # Aggregation provenance — include family_size_used (A59)
    # ------------------------------------------------------------------
    prov: dict[str, object] = {}
    if fit_result is not None:
        prov = dict(fit_result.aggregation_provenance)

    prov["family_size_used"] = family_size
    prov["pythonhashseed"] = int(os.environ.get("PYTHONHASHSEED", -1))
    agg_method = fit_result.aggregation_method if fit_result is not None else "unpooled"

    return SkillReport(
        report_schema_version=REPORT_SCHEMA_VERSION,
        skill_id=skill_id,
        generated_at_utc=generated_at_utc,
        harness_version=harness_version,
        aggregation_method=agg_method,
        aggregation_provenance=prov,
        clauses=tuple(clause_reports),
        vector=vector,
        coverage=coverage,
        contribution=contribution,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_completed_ablation_runs(conn: Connection, skill_id: str) -> list[dict[str, Any]]:
    """Fetch completed ablation runs for skill_id (single-shot query)."""
    cur = conn.execute(
        """
        SELECT run_id, skill_id, run_kind, config_json, started_at, completed_at
        FROM runs
        WHERE skill_id = ?
          AND run_kind = 'ablation'
          AND completed_at IS NOT NULL
        ORDER BY started_at, run_id
        """,
        (skill_id,),
    )
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if not rows:
        return []
    return [dict(zip(cols, row, strict=True)) for row in rows]


def _fetch_clauses(conn: Connection, skill_id: str) -> list[dict[str, Any]]:
    """Fetch all clause rows for a skill."""
    cur = conn.execute(
        """
        SELECT clause_id, skill_id, clause_index, rendering_index, clause_text,
               axis, comparator, oracle_tier, vacuity_flag,
               falsifying_case_schema_sha256, created_at
        FROM clauses WHERE skill_id = ? ORDER BY clause_index
        """,
        (skill_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def _read_family_size(completed_runs: list[dict[str, object]]) -> int:
    """Read family_size from runs.config_json (A59).

    Uses the first completed run; warns on mismatch between runs.
    Raises MalformedRunConfig if family_size is missing or <= 0.
    """
    first_run = completed_runs[0]
    run_id = str(first_run["run_id"])
    config_json = str(first_run.get("config_json") or "{}")

    try:
        config = json.loads(config_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MalformedRunConfig(f"config_json is not valid JSON: {exc}", run_id) from exc

    family_size = config.get("family_size", 0)
    if not isinstance(family_size, int) or family_size <= 0:
        raise MalformedRunConfig("family_size missing or zero in config_json", run_id)

    # A59: log warning if family_size mismatches across runs
    if len(completed_runs) > 1:
        for run in completed_runs[1:]:
            try:
                other_config = json.loads(str(run.get("config_json") or "{}"))
                other_fs = other_config.get("family_size", 0)
                if other_fs != family_size:
                    logger.warning(
                        "family_size mismatch: run %s has %d, run %s has %d. "
                        "Using first run's value (%d). "
                        "Investigate per A41 reconciler pattern.",
                        run_id,
                        family_size,
                        run["run_id"],
                        other_fs,
                        family_size,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

    return int(family_size)


def _resolve_divergent_field(
    values: set[str],
    *,
    empty_default: str | None,
    warn_message: str | None,
    warn_args: tuple[object, ...] = (),
) -> str | None:
    """Generic diverge -> warn + 'MIXED' resolution (F-10, S55 hostile review).

    Shared control flow behind ``_resolve_op_hash``, ``_resolve_metric_field``,
    and ``_derive_a55_fields``'s two inline resolutions -- three copies of the
    same three-way branch (diverges -> log + 'MIXED' / single value -> that
    value / no data -> caller-supplied default) that differed only in their log
    message text and empty-set default. Each site's exact warning wording, log
    fields, and empty-set default are preserved by passing them in rather than
    hardcoding one generic message here.

    :param values: The distinct values observed for this field across the pool.
    :param empty_default: Returned when ``values`` is empty (site-specific:
        ``"unknown"`` for op_hash, ``None`` for the metric/A55 fields).
    :param warn_message: ``logger.warning``-style %-format string to log when
        ``len(values) > 1``. ``None`` skips logging entirely (preserves
        ``user_message_sha256``'s pre-F-10 silent-MIXED behavior — that site
        never warned on divergence, unlike the other three).
    :param warn_args: %-format args for ``warn_message``.
    """
    if len(values) > 1:
        if warn_message is not None:
            logger.warning(warn_message, *warn_args)
        return "MIXED"
    if len(values) == 1:
        return next(iter(values))
    return empty_default


def _resolve_op_hash(
    op_hashes: set[str],
    skill_id: str,
    key: tuple[str, str],
) -> str:
    """Resolve the ablation_operator_hash for a (clause_id, axis) key.

    Mirrors the subject_model MIXED pattern from _derive_a55_fields (Phase 3.2 C1).
    If multiple distinct hashes are present, emits a data-integrity warning and
    returns "MIXED". Single hash returns that hash. Empty set returns "unknown".
    """
    clause_id, axis = key
    result = _resolve_divergent_field(
        op_hashes,
        empty_default="unknown",
        warn_message=(
            "[data-integrity] skill %r clause %r axis %r: ablation_operator_hash diverges "
            "across aggregated runs: %r. Setting ablation_operator_hash='MIXED'. "
            "Metric drift may be present per A55."
        ),
        warn_args=(skill_id, clause_id, axis, sorted(op_hashes)),
    )
    assert result is not None  # empty_default="unknown" guarantees a str
    return result


def _resolve_metric_field(
    values: set[str],
    skill_id: str,
    key: tuple[str, str],
    field_label: str,
) -> str | None:
    """Resolve metric_id/metric_version for a (clause_id, axis) key (B6).

    Mirrors the ablation_operator_hash MIXED pattern (_resolve_op_hash / I2):
    when the pooled admissible verdicts for this key were scored under more than
    one distinct value (e.g. metric re-registered mid-skill with changed
    normalization), report 'MIXED' + emit a data-integrity warning instead of the
    prior last-write-wins behaviour, which silently reported only the most
    recently processed run's value while pooling ALL runs' observations into one
    posterior regardless.

    NOTE (B6 scope): this fixes reporting/provenance-integrity parity with the
    op_hash/subject_model doctrine (surface divergence, do not silently hide it).
    It does NOT exclude cross-metric-version observations from the pooled w/n fed
    to the Beta posterior — doing so would require threading metric_version
    through ClauseObservations/fit_skill (fit.py), a materially larger change
    outside this finding's blast radius. Flagged for follow-up.
    """
    clause_id, axis = key
    return _resolve_divergent_field(
        values,
        empty_default=None,
        warn_message=(
            "[data-integrity] skill %r clause %r axis %r: %s diverges across "
            "aggregated verdicts: %r. Setting %s='MIXED'. Observations scored under "
            "different metric versions are pooled into one posterior with no "
            "scale-compatibility guarantee (B6)."
        ),
        warn_args=(skill_id, clause_id, axis, field_label, sorted(values), field_label),
    )


def _derive_a55_fields(
    clause_run_ids: set[str],
    all_run_ids_in_skill: set[str],
    run_id_to_subject_model: dict[str, str | None],
    run_id_to_user_msg_sha: dict[str, str | None],
    *,
    skill_id: str,
) -> tuple[str | None, str | None]:
    """Derive subject_model and user_message_sha256 for a clause's aggregated runs.

    For clauses with no run data, falls back to all completed runs for the skill.
    Returns ("MIXED", ...) when subject_model diverges across the pool — this is
    a data-integrity anomaly per A41 / A55; a warning is logged. user_message_sha256
    diverging also resolves to "MIXED" but has never logged a warning (pre-F-10
    behavior, preserved as-is — not part of this finding's scope).
    """
    # Use clause-specific runs if available; else all skill runs
    run_ids = clause_run_ids if clause_run_ids else all_run_ids_in_skill

    subject_models: set[str] = {
        v for rid in run_ids if (v := run_id_to_subject_model.get(rid)) is not None
    }
    user_msg_shas: set[str] = {
        v for rid in run_ids if (v := run_id_to_user_msg_sha.get(rid)) is not None
    }

    subject_model = _resolve_divergent_field(
        subject_models,
        empty_default=None,
        warn_message=(
            "[data-integrity] skill %r: subject_model diverges across aggregated runs: %r. "
            "Setting subject_model='MIXED'. Cross-pool comparison is invalid per A55."
        ),
        warn_args=(skill_id, sorted(subject_models)),
    )
    user_message_sha256 = _resolve_divergent_field(
        user_msg_shas,
        empty_default=None,
        warn_message=None,
    )

    return subject_model, user_message_sha256


def _fetch_run_state(runtime_conn: Connection, run_id: str) -> str | None:
    """Fetch the run_progress.state for a run_id, or None if not found."""
    try:
        row = runtime_conn.execute(
            "SELECT state FROM run_progress WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error as exc:
        logger.warning("_fetch_run_state failed for run_id=%r: %s", run_id, exc)
        return None
