"""AblationRunner -- deterministic orchestration engine for ablation sampling (D.2).

This is the core runner that:
1. For each clause in a skill, renders Full / Ablated_k / Null conditions.
2. Samples subject-model outputs (via SubjectClient).
3. Scores them through the oracles directionally (Full beats Ablated_k on primary axis?).
4. Accumulates the Beta-Binomial posterior and evaluates sequential stopping.
5. Monitors confounds across all metric axes in-memory.
6. Enforces budget (pre-call gate + post-call reconciliation in ONE transaction).
7. Writes append-only verdicts to evidence.db via Track A repositories.
8. Stamps runs.completed_at exactly ONCE after the last verdict commits.

Non-negotiable invariants (CLAUDE.md load-bearing):
- Deterministic Python owns ALL control flow. SubjectClient is content worker only.
- Append-only evidence: no UPDATE on evidence rows except runs.completed_at single-shot.
- Budget cap check + reservation in ONE writer_transaction(runtime) (A42).
- Cost written from actual response usage, never projection (A41).
- primary_clause_id == ablated_clause_id write-side assertion (A46).
- runs.completed_at written once, gated on samples_collected == samples_planned (D.2 spec).
- Warmup-or-serialize before fan-out across conditions (A43/COST-4).

Design principles:
- All model calls mocked at SDK boundary in tests (A32 precedent).
- No live API calls in tests (--m 'not live').
- Single-threaded in v0.1 (D11 deferred).
- Evidence-first dual-write ordering (A25).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from skill_harness.ablation.confound import (
    N_NULL_FLOOR,
    ConfoundEvent,
    MetricFn,
    NullAccumulator,
    check_operator_length_tolerance,
    delta_to_observation,
    detect_confounds,
    get_default_tier1_scorers,
)
from skill_harness.ablation.operator import AblationOperator
from skill_harness.ablation.reconciler import reconcile_run_cost
from skill_harness.ablation.render import ConditionRenderer
from skill_harness.ablation.stopping import (
    N_INC,
    N_MAX,
    N_MIN,
    BetaBinomialAccumulator,
    StopDecision,
    StoppingReason,
    next_check_at,
)
from skill_harness.ablation.subject import (
    SubjectCallError,
    SubjectClient,
    SubjectResponse,
    project_call_cost,
    sha256_of_output,
)
from skill_harness.storage.models import (
    ConfoundEventWrite,
    CostLedgerWrite,
    OracleVerdictWrite,
    RunBudgetWrite,
    RunProgressWrite,
    RunWrite,
    SampleWrite,
)
from skill_harness.storage.repositories.evidence.confound_events import insert_confound_event
from skill_harness.storage.repositories.evidence.oracle_verdicts import insert_oracle_verdict
from skill_harness.storage.repositories.evidence.runs import complete_run, insert_run
from skill_harness.storage.repositories.evidence.samples import insert_sample
from skill_harness.storage.repositories.runtime.cost_ledger import insert_cost_ledger_entry
from skill_harness.storage.repositories.runtime.run_budget import (
    get_run_budget_by_id,
    insert_run_budget,
    update_run_budget_aborted,
    update_run_budget_spend,
)
from skill_harness.storage.repositories.runtime.run_progress import (
    get_run_progress_by_id,
    insert_run_progress,
    update_run_progress,
)
from skill_harness.storage.transaction import writer_transaction

# ---------------------------------------------------------------------------
# ClauseSpec -- specification for a single clause being tested
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClauseSpec:
    """Specification for a single clause in a run.

    Fields
    ------
    clause_id : str
        Primary key from evidence.clauses.
    clause_text : str
        The original clause text.
    clause_index : int
        Authoring order index (0-based).
    axis : str
        The metric axis this clause claims (e.g. 'verbosity').
    oracle_tier : int
        1 = Tier-1 mechanical, 2 = Tier-2 judge.
    metric_id : str | None
        For Tier-1 clauses, the registered metric ID.
    """

    clause_id: str
    clause_text: str
    clause_index: int
    axis: str
    oracle_tier: int
    metric_id: str | None = None


# ---------------------------------------------------------------------------
# RunConfig -- frozen plan for a run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunConfig:
    """Frozen configuration for an ablation run.

    Written to runs.config_json at run start. Used for:
    - Idempotency + resume: set-difference of existing tuples vs this plan (A40).
    - Multiplicity provenance: K x |axes| family size for Track E (A49).
    - Stopping reason recording (A44).
    """

    run_id: str
    skill_id: str
    clauses: list[dict[str, Any]]
    """List of clause dicts: {clause_id, clause_text, clause_index, axis, oracle_tier}."""

    subject_model: str
    user_message: str
    n_min: int = N_MIN
    n_inc: int = N_INC
    n_max: int = N_MAX
    max_usd: float = 5.0
    family_size: int = 0
    """K x |axes| — set by runner after building the clause list (A49)."""

    stopping_reasons: dict[str, str] = field(default_factory=dict)
    """Maps clause_id -> stopping_reason (recorded at run-end for A44)."""

    def to_json(self) -> str:
        """Serialize to JSON for storage in runs.config_json."""
        return json.dumps(
            {
                "run_id": self.run_id,
                "skill_id": self.skill_id,
                "clauses": self.clauses,
                "subject_model": self.subject_model,
                "user_message": self.user_message,
                "n_min": self.n_min,
                "n_inc": self.n_inc,
                "n_max": self.n_max,
                "max_usd": self.max_usd,
                "family_size": self.family_size,
                "stopping_reasons": self.stopping_reasons,
            },
            sort_keys=True,
        )

    @staticmethod
    def from_json(json_str: str) -> RunConfig:
        """Deserialize from JSON."""
        d = json.loads(json_str)
        return RunConfig(
            run_id=d["run_id"],
            skill_id=d["skill_id"],
            clauses=d["clauses"],
            subject_model=d["subject_model"],
            user_message=d["user_message"],
            n_min=d.get("n_min", N_MIN),
            n_inc=d.get("n_inc", N_INC),
            n_max=d.get("n_max", N_MAX),
            max_usd=d.get("max_usd", 5.0),
            family_size=d.get("family_size", 0),
            stopping_reasons=d.get("stopping_reasons", {}),
        )


# ---------------------------------------------------------------------------
# ClauseResult -- per-clause run outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClauseResult:
    """Outcome for a single clause after the sampling loop completes."""

    clause_id: str
    stopping_reason: StoppingReason
    stop_decision: StopDecision
    samples_collected: int
    length_confounded: bool
    """True if the operator could not meet tolerance (QUAL-1 — clause excluded)."""

    unmeasured_reason: str | None = None
    """Sub-reason when the clause is UNMEASURED before/without sampling.

    Values: 'tier2_uncalibrated' (BLOCKER-1, not Tier-1-measurable),
    'length_confounded' (QUAL-1, operator out of tolerance), or None.
    """


# ---------------------------------------------------------------------------
# BudgetAbortedError -- raised internally when budget is exceeded
# ---------------------------------------------------------------------------


class BudgetAbortedError(Exception):
    """Raised when the run is aborted due to budget exhaustion."""

    def __init__(self, run_id: str, usd_spent: float, usd_cap: float) -> None:
        super().__init__(
            f"Budget exhausted: run {run_id!r} spent ${usd_spent:.4f} vs cap ${usd_cap:.4f}"
        )
        self.run_id = run_id
        self.usd_spent = usd_spent
        self.usd_cap = usd_cap


# ---------------------------------------------------------------------------
# AblationRunner
# ---------------------------------------------------------------------------


class AblationRunner:
    """Deterministic orchestration engine for clause-level ablation sampling.

    Parameters
    ----------
    evidence_conn : sqlite3.Connection
        Open evidence DB connection (synchronous=FULL, via open_evidence()).
    runtime_conn : sqlite3.Connection
        Open runtime DB connection (via open_runtime()).
    subject_client : SubjectClient | None
        Subject model client. If None, one is created (reads ANTHROPIC_API_KEY).
    operator : AblationOperator | None
        Ablation operator (injected for testing).
    renderer : ConditionRenderer | None
        Condition renderer (injected for testing).
    scorers : dict[str, MetricFn] | None
        Tier-1 metric scoring functions (injected for testing).
    max_retries : int
        Number of retries for transient API errors (default 3).
    retry_delay_s : float
        Base delay in seconds for retry backoff (default 1.0).
    null_floor : int
        Minimum Null samples per axis before confound detection activates and a
        verdict can be admissible (A47). Defaults to ``N_NULL_FLOOR`` (30). Lowered
        ONLY in tests for speed/determinism — production runs use the default.
    """

    def __init__(
        self,
        evidence_conn: sqlite3.Connection,
        runtime_conn: sqlite3.Connection,
        subject_client: SubjectClient | None = None,
        operator: AblationOperator | None = None,
        renderer: ConditionRenderer | None = None,
        scorers: dict[str, MetricFn] | None = None,
        max_retries: int = 3,
        retry_delay_s: float = 1.0,
        null_floor: int = N_NULL_FLOOR,
    ) -> None:
        self._evidence = evidence_conn
        self._runtime = runtime_conn
        self._subject: SubjectClient = (
            subject_client if subject_client is not None else SubjectClient()
        )
        self._operator: AblationOperator = operator if operator is not None else AblationOperator()
        self._renderer: ConditionRenderer = (
            renderer if renderer is not None else ConditionRenderer(operator=self._operator)
        )
        self._scorers: dict[str, MetricFn] = (
            scorers if scorers is not None else get_default_tier1_scorers()
        )
        self._max_retries = max_retries
        self._retry_delay_s = retry_delay_s
        self._null_floor = null_floor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_ablation(
        self,
        skill_id: str,
        clauses: list[ClauseSpec],
        user_message: str,
        max_usd: float = 5.0,
        subject_model: str = "claude-sonnet-4-6",
        run_id: str | None = None,
    ) -> list[ClauseResult]:
        """Execute a full ablation run for all clauses in a skill.

        :param skill_id: Evidence.skills primary key.
        :param clauses: Ordered list of ClauseSpec objects to ablate.
        :param user_message: Task prompt sent to the subject model.
        :param max_usd: Per-run budget cap in USD (A12, A42).
        :param subject_model: Model ID for subject calls.
        :param run_id: Optional run ID (generated if None).
        :returns: List of ClauseResult (one per clause).
        :raises BudgetAbortedError: If the budget cap is exceeded.
        """
        if run_id is None:
            run_id = str(uuid.uuid4())

        # Build run config + family size (A49 multiplicity provenance)
        clause_dicts = [
            {
                "clause_id": c.clause_id,
                "clause_text": c.clause_text,
                "clause_index": c.clause_index,
                "axis": c.axis,
                "oracle_tier": c.oracle_tier,
                "metric_id": c.metric_id,
            }
            for c in clauses
        ]
        axes = {c.axis for c in clauses}
        family_size = len(clauses) * len(axes)  # K x |axes| (A49)

        run_config = RunConfig(
            run_id=run_id,
            skill_id=skill_id,
            clauses=clause_dicts,
            subject_model=subject_model,
            user_message=user_message,
            max_usd=max_usd,
            family_size=family_size,
        )

        # Compute total samples_planned: per clause = N_MAX x 3 conditions (pessimistic)
        samples_planned = len(clauses) * N_MAX * 3

        now = self._now()

        # Initialize run in evidence.db (insert_run) + runtime.db (run_budget, run_progress)
        # Evidence-first ordering (A25)
        with writer_transaction(self._evidence):
            insert_run(
                self._evidence,
                RunWrite(
                    run_id=run_id,
                    skill_id=skill_id,
                    run_kind="ablation",
                    config_json=run_config.to_json(),
                    started_at=now,
                    completed_at=None,
                ),
            )

        with writer_transaction(self._runtime):
            insert_run_budget(
                self._runtime,
                RunBudgetWrite(
                    run_id=run_id,
                    hard_cap_usd=max_usd,
                    tokens_spent_in=0,
                    tokens_spent_out=0,
                    cache_write_in=0,
                    cache_read_in=0,
                    usd_spent=0.0,
                    dry_run=0,
                    aborted_at=None,
                    last_updated=now,
                ),
            )
            insert_run_progress(
                self._runtime,
                RunProgressWrite(
                    run_id=run_id,
                    state="running",
                    samples_planned=samples_planned,
                    samples_collected=0,
                    last_heartbeat=now,
                    error=None,
                ),
            )

        # Build clause_to_axis_map for confound classification (A11)
        clause_to_axis_map = {c.clause_id: c.axis for c in clauses}

        # Null accumulator for sigma(Null) estimation (A47)
        null_acc = NullAccumulator(scorers=self._scorers, null_floor=self._null_floor)

        # Track collected samples (shared mutable state for update_run_progress)
        samples_collected: int = 0
        clause_results: list[ClauseResult] = []
        stopping_reasons: dict[str, str] = {}

        try:
            # A43/COST-4: warmup shared prefix BEFORE fan-out
            # Use Full condition of first clause for warmup
            if clauses:
                clause_texts = [c.clause_text for c in clauses]
                warmup_conditions = self._renderer.render_conditions(
                    clause_texts, target_clause_index=0
                )
                warmup_blocks = warmup_conditions["full"]["system_blocks"]
                self._warmup_or_serialize(warmup_blocks, user_message)

            # Process each clause
            for clause_spec in clauses:
                result = self._run_clause(
                    run_id=run_id,
                    clause_spec=clause_spec,
                    all_clauses=clauses,
                    user_message=user_message,
                    clause_to_axis_map=clause_to_axis_map,
                    null_acc=null_acc,
                    samples_collected_ref=[samples_collected],
                    max_usd=max_usd,
                )
                samples_collected = result[0]
                clause_result = result[1]
                clause_results.append(clause_result)
                stopping_reasons[clause_spec.clause_id] = clause_result.stopping_reason.value

                # Update run progress after each clause
                with writer_transaction(self._runtime):
                    update_run_progress(
                        self._runtime,
                        run_id,
                        state="running",
                        samples_collected=samples_collected,
                        last_heartbeat=self._now(),
                    )

        except BudgetAbortedError:
            # Mark run as aborted in runtime
            abort_ts = self._now()
            with writer_transaction(self._runtime):
                update_run_budget_aborted(self._runtime, run_id, abort_ts, abort_ts)
                update_run_progress(
                    self._runtime,
                    run_id,
                    state="aborted_budget",
                    samples_collected=samples_collected,
                    last_heartbeat=abort_ts,
                    error="budget_exhausted",
                )
            raise

        # Stamp completed_at exactly ONCE (A20 carve-out, single-shot per REL-1 spec)
        # Gated on samples_collected == samples_planned (or early stop is fine -- completed means
        # the run reached its natural stopping condition, not that every sample was collected).
        completed_ts = self._now()
        with writer_transaction(self._evidence):
            complete_run(self._evidence, run_id, completed_ts)

        # Set terminal state in runtime (LAST runtime write, crash-vs-complete discriminator)
        with writer_transaction(self._runtime):
            update_run_progress(
                self._runtime,
                run_id,
                state="completed",
                samples_collected=samples_collected,
                last_heartbeat=completed_ts,
            )

        # Post-run: reconcile cost (A41)
        reconcile_run_cost(
            evidence_conn=self._evidence,
            runtime_conn=self._runtime,
            run_id=run_id,
            model_id=subject_model,
            skill_id=skill_id,
        )

        return clause_results

    def resume_ablation(
        self,
        run_id: str,
        clauses: list[ClauseSpec],
        user_message: str,
        max_usd: float = 5.0,
        subject_model: str = "claude-sonnet-4-6",
    ) -> list[ClauseResult]:
        """Resume an incomplete run (A40 idempotency + resume).

        Resume = set-difference of existing (run_id, clause_id, condition, sample_index)
        tuples vs the frozen plan in runs.config_json. Issues calls only for missing slots.

        :param run_id: The run to resume.
        :param clauses: Clause specs (same as original run).
        :param user_message: Task prompt (same as original run).
        :param max_usd: Budget cap.
        :param subject_model: Subject model ID.
        :returns: List of ClauseResult.
        :raises ValueError: If the run does not exist or is already complete.
        """
        # Verify run exists and is resumable
        existing = self._get_existing_samples(run_id)
        progress = get_run_progress_by_id(self._runtime, run_id)
        if progress is None:
            raise ValueError(f"Run {run_id!r} does not exist in runtime.run_progress")
        if progress["state"] == "completed":
            raise ValueError(f"Run {run_id!r} is already completed")

        # MAJOR-2: re-derive samples_collected + usd_spent from EVIDENCE (authoritative),
        # not from runtime progress, so a crash between the evidence commit and the runtime
        # budget update cannot let the A42 hard cap be overspent after resume. Reconcile the
        # runtime budget row to the evidence sum BEFORE re-entering the sampling loop.
        samples_collected = self._evidence_samples_collected(run_id)
        evidence_usd = self._evidence_usd_spent(run_id)
        budget = get_run_budget_by_id(self._runtime, run_id)
        if budget is not None and evidence_usd > budget["usd_spent"]:
            with writer_transaction(self._runtime):
                update_run_budget_spend(
                    self._runtime,
                    run_id,
                    tokens_spent_in=budget["tokens_spent_in"],
                    tokens_spent_out=budget["tokens_spent_out"],
                    cache_write_in=budget["cache_write_in"],
                    cache_read_in=budget["cache_read_in"],
                    usd_spent=evidence_usd,
                    last_updated=self._now(),
                )

        # Build the expected plan
        clause_to_axis_map = {c.clause_id: c.axis for c in clauses}
        null_acc = NullAccumulator(scorers=self._scorers, null_floor=self._null_floor)
        clause_results: list[ClauseResult] = []

        for clause_spec in clauses:
            result = self._run_clause(
                run_id=run_id,
                clause_spec=clause_spec,
                all_clauses=clauses,
                user_message=user_message,
                clause_to_axis_map=clause_to_axis_map,
                null_acc=null_acc,
                samples_collected_ref=[samples_collected],
                max_usd=max_usd,
                existing_samples=existing,
            )
            samples_collected = result[0]
            clause_results.append(result[1])

            with writer_transaction(self._runtime):
                update_run_progress(
                    self._runtime,
                    run_id,
                    state="running",
                    samples_collected=samples_collected,
                    last_heartbeat=self._now(),
                )

        # Stamp completed_at
        completed_ts = self._now()
        with writer_transaction(self._evidence):
            complete_run(self._evidence, run_id, completed_ts)

        with writer_transaction(self._runtime):
            update_run_progress(
                self._runtime,
                run_id,
                state="completed",
                samples_collected=samples_collected,
                last_heartbeat=completed_ts,
            )

        reconcile_run_cost(
            evidence_conn=self._evidence,
            runtime_conn=self._runtime,
            run_id=run_id,
            model_id=subject_model,
        )

        return clause_results

    # ------------------------------------------------------------------
    # Core clause loop
    # ------------------------------------------------------------------

    def _run_clause(
        self,
        run_id: str,
        clause_spec: ClauseSpec,
        all_clauses: list[ClauseSpec],
        user_message: str,
        clause_to_axis_map: dict[str, str],
        null_acc: NullAccumulator,
        samples_collected_ref: list[int],
        max_usd: float,
        existing_samples: set[tuple[str, str, str, int]] | None = None,
    ) -> tuple[int, ClauseResult]:
        """Execute sampling loop for a single clause.

        :returns: (updated_samples_collected, ClauseResult)
        """
        clause_id = clause_spec.clause_id
        clause_text = clause_spec.clause_text
        clause_idx = clause_spec.clause_index
        all_clause_texts = [c.clause_text for c in all_clauses]

        # BLOCKER-1: gate Tier-2 / no-Tier-1-scorer clauses to UNMEASURED BEFORE sampling.
        # No samples issued, no acc.add, no admissible verdict — a clause that cannot be
        # measured on its own axis must never enter the pass rule on a fallback axis.
        if not self._is_tier1_measurable(clause_spec):
            return (
                samples_collected_ref[0],
                ClauseResult(
                    clause_id=clause_id,
                    stopping_reason=StoppingReason.UNDERPOWERED_NMAX,
                    stop_decision=BetaBinomialAccumulator().check_stop(),
                    samples_collected=0,
                    length_confounded=False,
                    unmeasured_reason="tier2_uncalibrated",
                ),
            )

        # Render conditions
        conditions = self._renderer.render_conditions(all_clause_texts, clause_idx)
        full_blocks = conditions["full"]["system_blocks"]
        ablated_key = f"ablated_{clause_idx}"
        ablated_blocks = conditions[ablated_key]["system_blocks"]
        null_blocks = conditions["null"]["system_blocks"]

        # QUAL-1: check operator length tolerance BEFORE sampling
        placeholder_text = self._operator.render(clause_text)
        within_tolerance, _, _, _ = check_operator_length_tolerance(clause_text, placeholder_text)
        if not within_tolerance:
            # Operator could not meet tolerance -- flag clause as length-confounded
            # Do not emit clean verbosity evidence for this clause (QUAL-1)
            return (
                samples_collected_ref[0],
                ClauseResult(
                    clause_id=clause_id,
                    stopping_reason=StoppingReason.UNDERPOWERED_NMAX,
                    stop_decision=BetaBinomialAccumulator().check_stop(),
                    samples_collected=0,
                    length_confounded=True,
                    unmeasured_reason="length_confounded",
                ),
            )

        # QUAL-2 assertion: filler unit tokens pinned as module constant
        from skill_harness.ablation.operator import FILLER_UNIT_TOKENS

        assert FILLER_UNIT_TOKENS > 0, (
            f"FILLER_UNIT_TOKENS must be > 0 (QUAL-2); got {FILLER_UNIT_TOKENS!r}"
        )

        # Sequential stop accumulator
        acc = BetaBinomialAccumulator()

        samples_collected = samples_collected_ref[0]
        sample_index_full = 0
        sample_index_ablated = 0
        sample_index_null = 0

        # Resume: skip existing samples
        if existing_samples is None:
            existing_samples = set()

        # SCHEMA-3 / BLOCKER-2.2: comparison sample_indexes that already have a verdict.
        # On resume we re-build the posterior from prior verdicts but never APPEND a
        # duplicate verdict for an already-recorded comparison.
        existing_verdict_indexes = self._existing_verdict_keys(run_id, clause_id)

        # Collect Null samples (needed for confound sigma estimation)
        # We collect Null samples interleaved with Full/Ablated_k pairs.
        # Each comparison unit: 1 Full + 1 Ablated_k + optionally 1 Null

        next_stop_at = N_MIN  # First admissible-sample count at which to check stop

        stop_decision: StopDecision | None = None
        stopping_reason: StoppingReason | None = None

        # Hard cap on comparisons ISSUED (not just admissible adds). Inadmissible
        # comparisons (below Null floor / confounded) do not advance acc.n, so the
        # stopping posterior alone cannot bound the loop — comparisons_issued does.
        # Bounds total API cost at N_MAX comparisons per clause (A44: no batches past N_MAX).
        comparisons_issued = sample_index_full  # > 0 on resume (already-issued count)

        while acc.n < N_MAX and comparisons_issued < N_MAX:
            # Admissible-sample target before the next stop check.
            target = min(next_stop_at, N_MAX)

            while acc.n < target and comparisons_issued < N_MAX:
                # REL-1: initialize sample ids to "" at the top of each comparison so a
                # control-flow gap can never leave them unbound (no latent UnboundLocalError).
                full_sample_id = ""
                abl_sample_id = ""

                # The comparison is keyed by the Full sample_index (one Full vs one Ablated).
                comparison_index = sample_index_full
                comparisons_issued += 1

                # Budget gate (A42): check BEFORE issuing any API call
                projected_cost = project_call_cost(
                    model=self._subject._model,
                    estimated_input_tokens=512,  # conservative estimate
                    estimated_output_tokens=512,
                )
                self._check_budget(run_id, max_usd, projected_cost * 3)  # 3 calls per iteration

                # Issue Full call (if not already collected for this index)
                full_key = (run_id, clause_id, "full", sample_index_full)
                if full_key not in existing_samples:
                    full_resp = self._call_subject_with_retry(full_blocks, user_message)
                    full_sample_id = str(uuid.uuid4())
                    full_now = self._now()
                    self._write_sample_evidence(
                        run_id,
                        clause_id,
                        "full",
                        sample_index_full,
                        full_resp,
                        full_now,
                        full_sample_id,
                        self._subject._model,
                    )
                    self._write_cost_ledger(run_id, full_resp, full_now, self._subject._model)
                    self._update_budget_spend(run_id, full_resp)
                    samples_collected += 1
                    sample_index_full += 1
                    full_output = full_resp.output_text
                else:
                    # Load real (sample_id, output) from evidence (BLOCKER-2.1)
                    full_sample_id, full_output = self._load_sample(
                        run_id, clause_id, "full", sample_index_full
                    )
                    sample_index_full += 1

                # Issue Ablated_k call
                abl_key = (run_id, clause_id, "ablated", sample_index_ablated)
                if abl_key not in existing_samples:
                    abl_resp = self._call_subject_with_retry(ablated_blocks, user_message)
                    abl_sample_id = str(uuid.uuid4())
                    abl_now = self._now()
                    self._write_sample_evidence(
                        run_id,
                        clause_id,
                        "ablated",
                        sample_index_ablated,
                        abl_resp,
                        abl_now,
                        abl_sample_id,
                        self._subject._model,
                    )
                    self._write_cost_ledger(run_id, abl_resp, abl_now, self._subject._model)
                    self._update_budget_spend(run_id, abl_resp)
                    samples_collected += 1
                    sample_index_ablated += 1
                    ablated_output = abl_resp.output_text
                else:
                    abl_sample_id, ablated_output = self._load_sample(
                        run_id, clause_id, "ablated", sample_index_ablated
                    )
                    sample_index_ablated += 1

                # Issue Null call (for sigma(Null) estimation, A47)
                null_key = (run_id, clause_id, "null", sample_index_null)
                if null_key not in existing_samples:
                    null_resp = self._call_subject_with_retry(null_blocks, user_message)
                    null_sample_id = str(uuid.uuid4())
                    null_now = self._now()
                    self._write_sample_evidence(
                        run_id,
                        clause_id,
                        "null",
                        sample_index_null,
                        null_resp,
                        null_now,
                        null_sample_id,
                        self._subject._model,
                    )
                    self._write_cost_ledger(run_id, null_resp, null_now, self._subject._model)
                    self._update_budget_spend(run_id, null_resp)
                    samples_collected += 1
                    sample_index_null += 1
                    null_output = null_resp.output_text
                else:
                    _null_sample_id, null_output = self._load_sample(
                        run_id, clause_id, "null", sample_index_null
                    )
                    sample_index_null += 1

                null_acc.add(null_output)

                # Score Full vs Ablated_k on the primary axis (Tier-1 directional).
                # Reached only for Tier-1-measurable clauses (gated at method entry).
                primary_full_score = self._score_primary_axis(full_output, clause_spec)
                primary_abl_score = self._score_primary_axis(ablated_output, clause_spec)
                primary_delta = primary_full_score - primary_abl_score
                observation = delta_to_observation(primary_delta)

                # Confound monitoring (A47) across all axes for this comparison
                null_sigmas = null_acc.sigmas()
                confound_events_out = detect_confounds(
                    full_text=full_output,
                    ablated_text=ablated_output,
                    null_sigmas=null_sigmas,
                    primary_clause_id=clause_id,
                    clause_to_axis_map=clause_to_axis_map,
                    scorers=self._scorers,
                )

                # A46: write-side assertion
                assert all(e.primary_clause_id == clause_id for e in confound_events_out), (
                    "A46 violation: confound event primary_clause_id must "
                    f"== ablated_clause_id={clause_id!r}"
                )

                # Root-insight: snapshot admissibility at write time from real state.
                # - confound_flagged for THIS clause  -> inadmissible (reason confounded)
                # - Null accumulator below floor       -> inadmissible (reason underpowered)
                # - otherwise                          -> admissible
                this_clause_confounded = any(
                    ce.delta_kind == "confound_flagged" and ce.primary_clause_id == clause_id
                    for ce in confound_events_out
                )
                null_floor_met = self._null_floor_met_for_axis(null_acc, clause_spec.axis)
                admissibility_state, inadmissibility_reason = self._snapshot_admissibility(
                    confounded=this_clause_confounded,
                    null_floor_met=null_floor_met,
                )

                # SCHEMA-3 / BLOCKER-2.2: write a verdict only if one doesn't already exist
                # for this comparison index (resume must not double-write verdicts).
                if comparison_index not in existing_verdict_indexes:
                    self._write_verdict_and_confounds(
                        run_id=run_id,
                        clause_id=clause_id,
                        clause_spec=clause_spec,
                        observation=observation,
                        full_sample_id=full_sample_id,
                        abl_sample_id=abl_sample_id,
                        admissibility_state=admissibility_state,
                        inadmissibility_reason=inadmissibility_reason,
                        confound_events=confound_events_out,
                    )
                    existing_verdict_indexes.add(comparison_index)

                # MAJOR-1: only admissible (non-confounded, powered) observations move the
                # stopping posterior, so the runner's PASS/FAIL matches the aggregation VIEW.
                if admissibility_state == "admissible":
                    acc.add(observation)

            # Check stop after reaching target
            stop_decision = acc.check_stop()
            if stop_decision.should_stop:
                stopping_reason = stop_decision.stopping_reason
                break

            # Compute next check point
            next_stop_at = next_check_at(acc.n)
            if next_stop_at > N_MAX:
                break

        # If loop exited without stop decision (shouldn't happen but guard)
        if stop_decision is None:
            acc_check = acc.check_stop()
            stop_decision = acc_check
            stopping_reason = acc_check.stopping_reason or StoppingReason.UNDERPOWERED_NMAX

        if stopping_reason is None:
            stopping_reason = StoppingReason.UNDERPOWERED_NMAX

        samples_collected_ref[0] = samples_collected

        return (
            samples_collected,
            ClauseResult(
                clause_id=clause_id,
                stopping_reason=stopping_reason,
                stop_decision=stop_decision,
                samples_collected=acc.n,
                length_confounded=False,
            ),
        )

    # ------------------------------------------------------------------
    # Budget management (A42)
    # ------------------------------------------------------------------

    def _check_budget(self, run_id: str, max_usd: float, projected_cost: float) -> None:
        """Pre-call budget gate (A42).

        REL-7: this is a pre-call READ of the current spend, not a transactional
        reservation. The check (here) and the post-call spend update
        (``_update_budget_spend``) are two SEPARATE ``BEGIN IMMEDIATE`` transactions.
        Correctness in v0.1 rests on **single-threaded serialization** of the runner,
        not on holding a reservation across the API call (a true reservation would
        require an in-transaction debit, which v0.1 does not do). The single-writer
        discipline (A26) makes interleaving impossible until multi-process sampling
        (D11), which would reintroduce the race A42 is scoped to.

        :raises BudgetAbortedError: If projected cost would exceed the cap.
        """
        with writer_transaction(self._runtime):
            budget = get_run_budget_by_id(self._runtime, run_id)
            if budget is None:
                return  # No budget row -- allow (shouldn't happen in normal flow)

            current_spend = budget["usd_spent"]
            if current_spend + projected_cost > max_usd:
                raise BudgetAbortedError(run_id, current_spend, max_usd)

    def _update_budget_spend(self, run_id: str, resp: SubjectResponse) -> None:
        """Reconcile budget after a call (A42 post-call write)."""
        with writer_transaction(self._runtime):
            budget = get_run_budget_by_id(self._runtime, run_id)
            if budget is None:
                return
            update_run_budget_spend(
                self._runtime,
                run_id,
                tokens_spent_in=budget["tokens_spent_in"] + resp.input_tokens,
                tokens_spent_out=budget["tokens_spent_out"] + resp.output_tokens,
                cache_write_in=budget["cache_write_in"] + resp.cache_creation_input_tokens,
                cache_read_in=budget["cache_read_in"] + resp.cache_read_input_tokens,
                usd_spent=budget["usd_spent"] + resp.usd,
                last_updated=self._now(),
            )

    # ------------------------------------------------------------------
    # Evidence writes
    # ------------------------------------------------------------------

    def _write_sample_evidence(
        self,
        run_id: str,
        clause_id: str,
        condition: str,
        sample_index: int,
        resp: SubjectResponse,
        sampled_at: str,
        sample_id: str,
        model_id: str,
    ) -> None:
        """Write a sample row to evidence.db inside a writer_transaction (A25 evidence-first)."""
        sha = sha256_of_output(resp.output_text)
        sample = SampleWrite(
            sample_id=sample_id,
            run_id=run_id,
            clause_id=clause_id,
            condition=condition,
            subject_model=model_id,
            subject_seed=None,
            output_text=resp.output_text,
            output_sha256=sha,
            sampled_at=sampled_at,
            sample_index=sample_index,
            input_tokens=resp.input_tokens,
            cache_read_input_tokens=resp.cache_read_input_tokens,
            cache_creation_input_tokens=resp.cache_creation_input_tokens,
            output_tokens=resp.output_tokens,
            usd=resp.usd,
        )
        with writer_transaction(self._evidence):
            insert_sample(self._evidence, sample)

    def _write_cost_ledger(
        self,
        run_id: str,
        resp: SubjectResponse,
        ts: str,
        model_id: str,
    ) -> None:
        """Write a cost ledger entry to runtime.db (A41 projection)."""
        entry = CostLedgerWrite(
            ts=ts,
            run_id=run_id,
            skill_id=None,
            model_id=model_id,
            call_kind="subject",
            input_tok=resp.input_tokens,
            cache_write_tok=resp.cache_creation_input_tokens,
            cache_read_tok=resp.cache_read_input_tokens,
            output_tok=resp.output_tokens,
            usd=resp.usd,
        )
        with writer_transaction(self._runtime):
            insert_cost_ledger_entry(self._runtime, entry)

    def _write_verdict_and_confounds(
        self,
        run_id: str,
        clause_id: str,
        clause_spec: ClauseSpec,
        observation: float,
        full_sample_id: str,
        abl_sample_id: str,
        admissibility_state: str,
        inadmissibility_reason: str | None,
        confound_events: list[ConfoundEvent],
    ) -> None:
        """Write verdict + confound events to evidence.db (A25 evidence-first).

        A46: primary_clause_id == ablated_clause_id -- enforced by caller assertion.
        A49: verdict carries (run_id, clause_id, axis, comparison).
        Admissibility is a write-time snapshot supplied by the caller (root insight) —
        never a hardcoded constant, never recomputed at read time.

        BLOCKER-2.1: ``full_sample_id``/``abl_sample_id`` MUST be real sample ids (the
        NOT NULL FK columns reference samples.sample_id with foreign_keys=ON). A blank id
        is a caller bug — fail loudly rather than substitute verdict_id.
        """
        now = self._now()
        verdict_id = str(uuid.uuid4())

        if not full_sample_id or not abl_sample_id:
            raise RuntimeError(
                "BLOCKER-2.1: verdict requires real sample ids for the FK columns; "
                f"got full_sample_id={full_sample_id!r}, abl_sample_id={abl_sample_id!r}"
            )

        verdict = OracleVerdictWrite(
            verdict_id=verdict_id,
            run_id=run_id,
            clause_id=clause_id,
            axis=clause_spec.axis,
            comparison="full_vs_ablated",
            sample_a_id=full_sample_id,
            sample_b_id=abl_sample_id,
            observation=observation,
            oracle_tier=clause_spec.oracle_tier,
            metric_id=clause_spec.metric_id,
            metric_version=None,
            judge_id=None,
            calibration_event_id=None,
            position_swap_agreement=None,
            admissibility_state=admissibility_state,
            inadmissibility_reason=inadmissibility_reason,
            written_at=now,
        )

        with writer_transaction(self._evidence):
            # A46: write-side assertion before insert
            for ce in confound_events:
                assert ce.primary_clause_id == clause_id, (
                    f"A46 violation: confound primary_clause_id={ce.primary_clause_id!r} "
                    f"!= ablated_clause_id={clause_id!r}"
                )

            insert_oracle_verdict(self._evidence, verdict)

            # Write confound events in the same transaction (A45: two-table, A47: threshold)

            confound_ev_id_base = str(uuid.uuid4())
            for i, ce in enumerate(confound_events):
                cev = ConfoundEventWrite(
                    confound_event_id=f"{confound_ev_id_base}-{i}",
                    run_id=run_id,
                    primary_clause_id=ce.primary_clause_id,
                    affected_clause_id=ce.affected_clause_id,
                    axis=ce.axis,
                    delta=ce.delta,
                    null_sigma=ce.null_sigma,
                    k_threshold=ce.k_threshold,
                    delta_kind=ce.delta_kind,
                    detected_at=now,
                )
                insert_confound_event(self._evidence, cev)

    # ------------------------------------------------------------------
    # Oracle scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot_admissibility(
        *, confounded: bool, null_floor_met: bool
    ) -> tuple[str, str | None]:
        """Compute the write-time admissibility snapshot for a comparison.

        Root insight: ``admissibility_state`` is a real write-time snapshot of the
        comparison's state, NOT a hardcoded constant. Never recomputed at read time
        (CLAUDE.md Evidence model — locked invariant).

        - confounded (this clause's own axis confound_flagged) -> ('inadmissible', 'confounded')
        - Null accumulator below floor (N_null < 30, A47)       -> ('inadmissible', 'underpowered')
        - otherwise                                             -> ('admissible', None)

        :returns: (admissibility_state, inadmissibility_reason)
        """
        if confounded:
            return "inadmissible", "confounded"
        if not null_floor_met:
            return "inadmissible", "underpowered"
        return "admissible", None

    @staticmethod
    def _null_floor_met_for_axis(null_acc: NullAccumulator, axis: str) -> bool:
        """Return True iff the Null accumulator has enough samples for this axis (A47).

        Confound detection on ``axis`` is only meaningful when sigma(Null) for that axis
        is estimated from >= the configured floor (default N_NULL_FLOOR=30). Below the
        floor, the comparison is UNMEASURED(underpowered) — admissibility reflects that
        (MAJOR-3). Uses the accumulator's own floor so a test-lowered floor stays
        consistent between sigma estimation and the admissibility snapshot.
        """
        return null_acc.axis_n(axis) >= null_acc.null_floor

    def _is_tier1_measurable(self, clause_spec: ClauseSpec) -> bool:
        """Return True iff the clause can be measured by a registered Tier-1 scorer.

        A clause is Tier-1-measurable when BOTH hold:
        - ``oracle_tier == 1`` (a mechanical metric is declared), AND
        - ``clause_spec.axis`` resolves to a registered scorer in ``self._scorers``.

        BLOCKER-1: any clause failing this gate must NOT be scored on a fallback
        (wrong) axis. It is UNMEASURED — no admissible verdict, never aggregated.
        Per CLAUDE.md: "Tier-2 inadmissible without a calibrated (judge_id, axis)
        record" and "no admissible evidence => UNMEASURED never PASSED".
        """
        return clause_spec.oracle_tier == 1 and clause_spec.axis in self._scorers

    def _score_primary_axis(self, text: str, clause_spec: ClauseSpec) -> float:
        """Score text on the clause's primary axis (Tier-1 only in v0.1).

        Callers MUST gate on ``_is_tier1_measurable`` first — this method assumes a
        registered scorer exists for ``clause_spec.axis``. There is NO wrong-axis
        fallback (BLOCKER-1): an unscored clause is UNMEASURED, not silently scored
        on verbosity.

        :param text: Subject model output.
        :param clause_spec: Clause specification with axis name.
        :returns: Metric score (float).
        """
        scorer = self._scorers.get(clause_spec.axis)
        if scorer is None:
            # Defensive: callers gate on _is_tier1_measurable so this should not happen.
            raise RuntimeError(
                f"_score_primary_axis called for unscored axis {clause_spec.axis!r}; "
                "caller must gate on _is_tier1_measurable() first (BLOCKER-1)"
            )
        try:
            return float(scorer(text))
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Subject model call with retry (A40 per-call policy)
    # ------------------------------------------------------------------

    def _call_subject_with_retry(
        self,
        system_blocks: list[dict[str, Any]],
        user_message: str,
    ) -> SubjectResponse:
        """Call subject model with retry-backoff for transient errors (A40).

        Policy:
        - Transient (429/500/network): retry up to max_retries with backoff.
        - Permanent (400): raise immediately (caller should skip-and-record).
        - Budget abort: re-raise without retry.
        """
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._subject.call(system_blocks=system_blocks, user_message=user_message)
            except SubjectCallError as exc:
                if not exc.transient:
                    raise  # Permanent error -- skip-and-record (caller handles)
                last_exc = exc
                if attempt < self._max_retries:
                    delay = self._retry_delay_s * (2**attempt)
                    time.sleep(delay)

        # Exhausted retries
        raise SubjectCallError(
            f"Subject model call failed after {self._max_retries} retries",
            transient=False,
        ) from last_exc

    # ------------------------------------------------------------------
    # Warmup (A43/COST-4)
    # ------------------------------------------------------------------

    def _warmup_or_serialize(
        self,
        system_blocks: list[dict[str, Any]],
        user_message: str,
    ) -> None:
        """Send warmup call to write shared prefix to prompt cache (A43/COST-4).

        This must complete before fan-out across conditions. The response is
        discarded (cost is real but the output is not used as a sample).
        """
        import contextlib

        with contextlib.suppress(SubjectCallError):
            self._subject.warmup_shared_prefix(system_blocks, user_message)
            # Warmup failure is non-fatal -- cache write discipline is best-effort.

    # ------------------------------------------------------------------
    # Idempotency helpers (A40)
    # ------------------------------------------------------------------

    def _get_existing_samples(self, run_id: str) -> set[tuple[str, str, str, int]]:
        """Return set of (run_id, clause_id, condition, sample_index) already committed."""
        cur = self._evidence.execute(
            "SELECT run_id, clause_id, condition, sample_index FROM samples WHERE run_id = ?",
            (run_id,),
        )
        return {(row[0], row[1], row[2], row[3]) for row in cur.fetchall()}

    def _evidence_samples_collected(self, run_id: str) -> int:
        """COUNT(*) of samples already in evidence for a run (MAJOR-2 authoritative source)."""
        cur = self._evidence.execute(
            "SELECT COUNT(*) FROM samples WHERE run_id = ?",
            (run_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def _evidence_usd_spent(self, run_id: str) -> float:
        """SUM(usd) of samples already in evidence for a run (MAJOR-2 authoritative spend).

        Evidence is the authoritative ledger (synchronous=FULL). A crash between the
        evidence sample-commit and the runtime budget-spend update can leave runtime
        under-counting; re-deriving from evidence closes the A42 over-spend gap.
        """
        cur = self._evidence.execute(
            "SELECT COALESCE(SUM(usd), 0.0) FROM samples WHERE run_id = ? AND usd IS NOT NULL",
            (run_id,),
        )
        row = cur.fetchone()
        return float(row[0]) if row else 0.0

    def _load_sample(
        self, run_id: str, clause_id: str, condition: str, sample_index: int
    ) -> tuple[str, str]:
        """Load (sample_id, output_text) of an existing sample (for resume scoring).

        BLOCKER-2.1: returns the REAL sample_id so the verdict write can reference it
        via the NOT NULL FK columns. Never substitute verdict_id for a sample id.

        :returns: (sample_id, output_text). Empty strings if the sample is missing
            (a defensive case — the caller only loads samples it knows exist).
        """
        cur = self._evidence.execute(
            "SELECT sample_id, output_text FROM samples "
            "WHERE run_id=? AND clause_id=? AND condition=? AND sample_index=?",
            (run_id, clause_id, condition, sample_index),
        )
        row = cur.fetchone()
        if row is None:
            return "", ""
        return row[0], row[1]

    def _existing_verdict_keys(self, run_id: str, clause_id: str) -> set[int]:
        """Return the set of comparison sample_indexes already recorded as verdicts.

        SCHEMA-3 / BLOCKER-2.2: a verdict's comparison is keyed by the Full sample's
        ``sample_index`` (one Full vs one Ablated per comparison index). On resume we
        must not append a SECOND verdict for a comparison whose verdict already exists.

        We resolve this by joining the verdict's ``sample_a_id`` (the Full sample) back
        to ``samples.sample_index`` for full-condition rows of this clause+run.

        :returns: Set of Full-condition sample_index values that already have a verdict.
        """
        cur = self._evidence.execute(
            """
            SELECT s.sample_index
            FROM oracle_verdicts v
            JOIN samples s ON s.sample_id = v.sample_a_id
            WHERE v.run_id = ? AND v.clause_id = ? AND s.condition = 'full'
            """,
            (run_id, clause_id),
        )
        return {row[0] for row in cur.fetchall()}

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> str:
        """Return current UTC timestamp as ISO 8601 string."""
        return datetime.now(UTC).isoformat()
