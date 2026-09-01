"""Budget / cost reconciliation tests — falsification-plan item 7.

Property: every model that appears in the evidence store's samples table
must have a corresponding row in PRICE_PER_MTOK.  A missing row means the
reconciler and frontier projections cannot price that model's spend, and
the budget gate is blind to its cost.

Detection of pricing-table drift vs vendor: if a model is used in
production evidence but lacks a price row, project_pair_usd /
project_trial_usd raise KeyError, and cost projections return REFUSED.
This test catches that gap at test time, before merge.
"""

from __future__ import annotations

import os
import sqlite3

import pytest


def test_pythonhashseed_set() -> None:
    assert os.environ.get("PYTHONHASHSEED") == "0", (
        "PYTHONHASHSEED must be set to 0 for deterministic tests. Run with: PYTHONHASHSEED=0 pytest"
    )


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from skill_harness.ablation.subject import (  # noqa: E402
    PRICE_PER_MTOK,
    resolve_price_key,
)
from skill_harness.oracles.calibration.cost_projection import (  # noqa: E402
    project_pair_usd,
    project_trial_usd,
)
from skill_harness.storage.models import RunWrite, SkillWrite  # noqa: E402
from skill_harness.storage.repositories.evidence import (  # noqa: E402
    runs as runs_repo,
)
from skill_harness.storage.repositories.evidence import (  # noqa: E402
    skills as skills_repo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHA = "a" * 64
_TS = "2026-07-10T12:00:00.000Z"


def _seed_evidence_prereqs(conn: sqlite3.Connection) -> None:
    """Insert the FK chain required for samples rows: skills -> runs."""
    skills_repo.insert_skill(
        conn,
        SkillWrite(
            skill_id="skill-1",
            name="Test",
            source_path="/x",
            source_sha256=_SHA,
            imported_at=_TS,
        ),
    )
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "clause-1",
            "skill-1",
            0,
            0,
            "Test clause",
            "citation_support",
            "increase",
            1,
            "none",
            _TS,
        ),
    )
    runs_repo.insert_run(
        conn,
        RunWrite(
            run_id="run-1",
            skill_id="skill-1",
            run_kind="ablation",
            config_json="{}",
            started_at=_TS,
            completed_at=None,
        ),
    )


def _insert_sample(
    conn: sqlite3.Connection,
    *,
    run_id: str = "run-1",
    clause_id: str = "clause-1",
    subject_model: str = "claude-sonnet-5",
    sample_id: str = "s1",
    sample_index: int = 0,
) -> None:
    """Insert a minimal evidence sample row (prereqs must already exist)."""
    conn.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (sample_id, run_id, clause_id, "full", subject_model, "text", _SHA, _TS, sample_index),
    )


# ---------------------------------------------------------------------------
# Drift-guard: every evidence-store model must have a price row
# ---------------------------------------------------------------------------


class TestPricingTableCoversEvidenceModels:
    """Falsification-plan item 7 (supply-chain: pricing-table drift vs vendor).

    If a model appears in evidence.samples but has no PRICE_PER_MTOK entry,
    project_pair_usd / project_trial_usd raise KeyError and cost projections
    return REFUSED.  This class catches that gap: insert a sample, then
    assert the projection functions succeed for that model.
    """

    def test_sonnet_5_has_price_row(self, evidence_db: sqlite3.Connection) -> None:
        """claude-sonnet-5 evidence must be priceable (the 2026-07-10 paired run)."""
        _seed_evidence_prereqs(evidence_db)
        _insert_sample(evidence_db, subject_model="claude-sonnet-5")

        models = {
            row[0]
            for row in evidence_db.execute("SELECT DISTINCT subject_model FROM samples").fetchall()
        }
        assert "claude-sonnet-5" in models

        # This is the drift guard: if the price row is missing, KeyError.
        usd_pair = project_pair_usd(
            "claude-sonnet-5",
            input_tokens_per_pair=486212.75,
            output_tokens_per_pair=54777.625,
        )
        assert usd_pair > 0

        usd_trial = project_trial_usd(
            "claude-sonnet-5",
            input_tokens_per_trial=249623.25,
            output_tokens_per_trial=29456,
        )
        assert usd_trial > 0

    def test_provider_prefixed_sonnet_5_is_priceable(self, evidence_db: sqlite3.Connection) -> None:
        """The routed form the production store records must price (#302).

        Both runs that anchor the collection's cost projections were made
        through the OpenRouter fallback, so ``samples.subject_model`` holds
        ``anthropic/claude-sonnet-5``, not ``claude-sonnet-5``. Seeding the
        bare name (the #299 guard) never exercises that string.
        """
        prefixed = "anthropic/claude-sonnet-5"

        _seed_evidence_prereqs(evidence_db)
        _insert_sample(evidence_db, subject_model=prefixed)

        models = {
            row[0]
            for row in evidence_db.execute("SELECT DISTINCT subject_model FROM samples").fetchall()
        }
        assert prefixed in models
        assert prefixed not in PRICE_PER_MTOK, (
            "The canonical pricing key is the bare vendor name; a provider-prefixed "
            "row would defeat the normalisation this test guards."
        )

        usd_pair = project_pair_usd(
            prefixed,
            input_tokens_per_pair=486212.75,
            output_tokens_per_pair=54777.625,
        )
        assert usd_pair > 0

        usd_trial = project_trial_usd(
            prefixed,
            input_tokens_per_trial=249623.25,
            output_tokens_per_trial=29456,
        )
        assert usd_trial > 0

        # Canonical form (a): the route does not change the price, so the
        # prefixed identifier must project the same USD as the bare one.
        assert usd_pair == project_pair_usd(
            "claude-sonnet-5",
            input_tokens_per_pair=486212.75,
            output_tokens_per_pair=54777.625,
        )
        assert usd_trial == project_trial_usd(
            "claude-sonnet-5",
            input_tokens_per_trial=249623.25,
            output_tokens_per_trial=29456,
        )

    def test_unknown_model_behind_provider_prefix_raises_keyerror(self) -> None:
        """Stripping the route must not widen the lookup: the model still has to exist."""
        with pytest.raises(KeyError):
            project_pair_usd(
                "anthropic/claude-nonexistent-model",
                input_tokens_per_pair=1000,
                output_tokens_per_pair=100,
            )

    def test_all_evidence_models_are_priceable(self, evidence_db: sqlite3.Connection) -> None:
        """Every model in the evidence store must have a PRICE_PER_MTOK row."""
        _seed_evidence_prereqs(evidence_db)

        # Seed evidence with the models used across the test suite, in both
        # forms the production store actually carries: the bare vendor name,
        # and the routed 'provider/model' form the OpenRouter fallback writes.
        known_models = [
            "claude-sonnet-4-6",
            "claude-opus-4-7",
            "claude-sonnet-5",
            "gpt-5.5",
            "anthropic/claude-sonnet-5",
        ]
        for i, model in enumerate(known_models):
            _insert_sample(evidence_db, subject_model=model, sample_id=f"s{i}", sample_index=i)

        evidence_models = {
            row[0]
            for row in evidence_db.execute("SELECT DISTINCT subject_model FROM samples").fetchall()
        }

        missing = {
            model for model in evidence_models if resolve_price_key(model) not in PRICE_PER_MTOK
        }
        assert not missing, (
            f"Models in evidence store without a PRICE_PER_MTOK row: {missing}. "
            f"Add rows to skill_harness.ablation.subject.PRICE_PER_MTOK before merging."
        )

    def test_unknown_model_raises_keyerror(self) -> None:
        """Inverse guard: a model NOT in PRICE_PER_MTOK must raise, not default-price."""
        with pytest.raises(KeyError):
            project_pair_usd(
                "claude-nonexistent-model",
                input_tokens_per_pair=1000,
                output_tokens_per_pair=100,
            )


# ===========================================================================
# Falsification plan item 7 (#349): the three registered assertions this file
# lacked. Verified absent by reading all 254 pre-change lines; the ratchet in
# #342 counted this row as satisfied on file existence alone, which is why a
# present-but-partial detector is worse than an absent one.
#
# 1. RECONCILIATION: every recorded call reconciles tokens <-> usd <-> model
#    price within EPSILON_USD, and the three ledgers agree with each other.
# 2. ORPHAN INJECTION: a runtime budget-commit failure after the evidence
#    commit leaves orphan evidence; resume must reconcile the budget to the
#    evidence sum BEFORE any new spend, and the hard cap must fire on the
#    reconciled figure.
# 3. HARD CAP: the pre-call refusal semantics, asserted under the invariant
#    the code actually claims. REL-7 in runner.py states plainly that the
#    check and the spend update are two separate BEGIN IMMEDIATE transactions
#    and correctness rests on single-threaded serialisation, NOT on a held
#    reservation. Per #349's revisit clause, this file asserts that invariant
#    directly (strict check -> call -> spend bracketing on one thread, refusal
#    before the call, no overspend) rather than simulating a concurrency the
#    code does not claim to survive. If multi-process sampling (D11) lands,
#    the bracketing assertion below is the one that must be replaced by a true
#    reservation test.
#
# EPSILON_USD = 1e-6, registered before the first run of these tests: from
# below, float rounding on an 8-decimal-rounded price of order 1e-2 USD is
# below 1e-9, three orders quieter; from above, the cheapest single priced
# token is of order 1e-6..1e-5 USD, so any real field-mangling (a swapped
# token column, a dropped cache component) moves a call's price by at least
# one token's worth and cannot hide under the epsilon.
# ===========================================================================

import uuid  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from skill_harness.ablation.runner import (  # noqa: E402
    AblationRunner,
    BudgetAbortedError,
    ClauseSpec,
)
from skill_harness.ablation.subject import SubjectClient, _estimate_usd  # noqa: E402
from skill_harness.storage.migrations import open_evidence, open_runtime  # noqa: E402
from skill_harness.storage.repositories.runtime.run_budget import get_run_budget_by_id  # noqa: E402

EPSILON_USD = 1e-6
_MODEL = "claude-sonnet-4-6"
_USER_MSG = "Write a paragraph about testing."


def _usage_mock(
    text: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.model = _MODEL
    resp.stop_reason = "end_turn"
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_input_tokens = cache_read
    usage.cache_creation_input_tokens = cache_write
    resp.usage = usage
    return resp


def _varied_factory(idx: int) -> MagicMock:
    """Deterministic token counts that vary per call and exercise cache pricing."""
    input_tokens = 100 + 13 * idx
    output_tokens = 20 + 7 * idx
    cache_read = 50 if idx % 3 == 1 else 0
    cache_write = 30 if idx % 3 == 2 else 0
    return _usage_mock(
        "word " * (10 + idx % 5), input_tokens, output_tokens, cache_read, cache_write
    )


def _budget_runner(
    tmp_path: Any,
    response_factory: Any,
) -> tuple[AblationRunner, MagicMock, sqlite3.Connection, sqlite3.Connection]:
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")
    _seed_evidence_prereqs(ev)
    ev.commit()
    mock_client = MagicMock()
    call_count = [0]

    def _side_effect(**kwargs: Any) -> MagicMock:
        resp: MagicMock = response_factory(call_count[0])
        call_count[0] += 1
        return resp

    mock_client.messages.create.side_effect = _side_effect
    subject = SubjectClient(client=mock_client, model=_MODEL)
    scorers = {
        "verbosity": lambda t: float(len(t.split())),
        "char_count": lambda t: float(len(t)),
    }
    runner = AblationRunner(
        evidence_conn=ev,
        runtime_conn=rt,
        subject_client=subject,
        scorers=scorers,
        max_retries=0,
        retry_delay_s=0.0,
        null_floor=2,
    )
    return runner, mock_client, ev, rt


def _clause_spec() -> ClauseSpec:
    return ClauseSpec(
        clause_id="clause-1",
        clause_index=0,
        clause_text="Test clause",
        axis="verbosity",
        metric_id="verbosity",
        oracle_tier=1,
    )


class TestEveryCallReconciles:
    """Item 7 assertion 1: tokens <-> usd <-> model price, per recorded call."""

    def test_every_ledger_row_reconciles_and_ledgers_agree(self, tmp_path: Any) -> None:
        runner, _client, ev, rt = _budget_runner(tmp_path, _varied_factory)
        try:
            run_id = f"recon-{uuid.uuid4().hex[:8]}"
            runner.run_ablation(
                skill_id="skill-1",
                clauses=[_clause_spec()],
                user_message=_USER_MSG,
                max_usd=100.0,
                run_id=run_id,
            )
            ledger_rows = rt.execute(
                "SELECT ledger_id, model_id, input_tok, cache_write_tok, cache_read_tok,"
                " output_tok, usd FROM cost_ledger WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            assert ledger_rows, "run produced no cost_ledger rows; harness fault"
            for lid, model_id, in_tok, cw, cr, out_tok, usd in ledger_rows:
                expected = _estimate_usd(model_id, in_tok, cr, cw, out_tok)
                assert abs(usd - expected) <= EPSILON_USD, (
                    f"BUDGET_LEDGER_PRICE_MISMATCH: cost_ledger row {lid} records"
                    f" usd={usd!r} but the pricing table prices its own token"
                    f" counts (in={in_tok}, cache_write={cw}, cache_read={cr},"
                    f" out={out_tok}, model={model_id}) at {expected!r};"
                    f" difference exceeds epsilon {EPSILON_USD}. The ledger and"
                    f" the price table have drifted apart."
                )
            sample_rows = ev.execute(
                "SELECT input_tokens, cache_read_input_tokens, cache_creation_input_tokens,"
                " output_tokens, usd, subject_model FROM samples WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            assert sample_rows, "run produced no evidence samples; harness fault"
            for in_tok, cr, cw, out_tok, usd, model_id in sample_rows:
                expected = _estimate_usd(model_id, in_tok, cr, cw, out_tok)
                assert abs(usd - expected) <= EPSILON_USD, (
                    f"BUDGET_EVIDENCE_PRICE_MISMATCH: evidence sample records"
                    f" usd={usd!r} against recomputed {expected!r} for its own"
                    f" token counts; difference exceeds epsilon {EPSILON_USD}."
                )
            ledger_sum = sum(r[6] for r in ledger_rows)
            evidence_sum = sum(r[4] for r in sample_rows)
            assert abs(ledger_sum - evidence_sum) <= EPSILON_USD, (
                f"BUDGET_LEDGERS_DISAGREE: runtime cost_ledger sums to"
                f" {ledger_sum!r} while evidence samples sum to {evidence_sum!r}."
                f" The two ledgers record the same calls and must agree; a gap is"
                f" an orphan write on one side."
            )
            budget = get_run_budget_by_id(rt, run_id)
            assert budget is not None
            # Warmup spend is budget-only by design (A3 scope note in
            # _warmup_or_serialize): budget >= ledger sum, and the excess is
            # exactly the warmup call (call index 0 of the factory).
            warmup_usd = _estimate_usd(_MODEL, 100, 0, 0, 20)
            assert abs(budget["usd_spent"] - (ledger_sum + warmup_usd)) <= EPSILON_USD, (
                f"BUDGET_SPEND_DIVERGES_FROM_LEDGER: run_budget.usd_spent="
                f"{budget['usd_spent']!r} but cost_ledger sum plus the warmup"
                f" call prices to {ledger_sum + warmup_usd!r}; the budget row"
                f" and the ledger have diverged beyond epsilon {EPSILON_USD}."
            )
        finally:
            ev.close()
            rt.close()


class TestOrphanEvidenceReconciledBeforeSpend:
    """Item 7 assertion 2: injected runtime commit failure -> resume repairs first."""

    def test_injected_budget_commit_failure_is_reconciled_on_resume(self, tmp_path: Any) -> None:
        def factory(idx: int) -> MagicMock:
            if idx == 0:
                return _usage_mock("warm " * 5, 100, 20)
            # Expensive calls so orphan evidence clearly exceeds warmup spend.
            return _usage_mock("word " * (10 + idx % 5), 2000, 4000)

        runner, client, ev, rt = _budget_runner(tmp_path, factory)
        try:
            run_id = f"orphan-{uuid.uuid4().hex[:8]}"
            real_update = runner._update_budget_spend
            update_calls = [0]

            def crashing_update(rid: str, resp: Any) -> None:
                update_calls[0] += 1
                if update_calls[0] == 2:
                    # Call 1 is the warmup. Call 2 is the first sampled call,
                    # whose evidence row is already committed (A25
                    # evidence-first) -- this is the exact crash window REL-7
                    # documents.
                    raise RuntimeError("injected: runtime budget commit failed")
                real_update(rid, resp)

            runner._update_budget_spend = crashing_update  # type: ignore[method-assign, assignment]
            with pytest.raises(RuntimeError, match="injected"):
                runner.run_ablation(
                    skill_id="skill-1",
                    clauses=[_clause_spec()],
                    user_message=_USER_MSG,
                    max_usd=100.0,
                    run_id=run_id,
                )
            runner._update_budget_spend = real_update  # type: ignore[method-assign]

            evidence_sum = ev.execute(
                "SELECT COALESCE(SUM(usd), 0) FROM samples WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            budget = get_run_budget_by_id(rt, run_id)
            assert budget is not None
            assert evidence_sum > budget["usd_spent"], (
                "harness fault: the injection did not create orphan evidence"
                " (evidence sum must exceed the budget row after the crash)"
            )

            calls_before_resume = client.messages.create.call_count
            # Cap below the orphan evidence sum: a correct resume reconciles
            # the budget row from evidence FIRST, so its very first pre-call
            # check must refuse. Any new subject call means the cap consulted
            # the stale, understated ledger.
            with pytest.raises(BudgetAbortedError):
                runner.resume_ablation(
                    run_id=run_id,
                    clauses=[_clause_spec()],
                    user_message=_USER_MSG,
                    max_usd=evidence_sum * 0.5,
                )
            budget_after = get_run_budget_by_id(rt, run_id)
            assert budget_after is not None
            assert budget_after["usd_spent"] >= evidence_sum, (
                f"BUDGET_RECONCILIATION_MISSED: after resume the budget row"
                f" records usd_spent={budget_after['usd_spent']!r}, still below"
                f" the evidence sum {evidence_sum!r}. Orphan evidence from the"
                f" injected commit failure was not reconciled, so the hard cap"
                f" is checking an understated ledger."
            )
            assert client.messages.create.call_count == calls_before_resume, (
                f"CAP_SPENT_ON_UNRECONCILED_LEDGER: resume made"
                f" {client.messages.create.call_count - calls_before_resume}"
                f" subject call(s) despite the reconciled spend already"
                f" exceeding the cap; the pre-call check ran against the stale"
                f" budget row instead of the evidence-reconciled one."
            )
            progress = rt.execute(
                "SELECT state FROM run_progress WHERE run_id = ?", (run_id,)
            ).fetchone()
            assert progress is not None and progress[0] == "aborted_budget", (
                f"BUDGET_ABORT_STATE_NOT_RECORDED: run_progress.state is"
                f" {progress[0] if progress else None!r} after a budget abort on"
                f" resume; a killed-then-resumed run must be distinguishable"
                f" from a crash (A4)."
            )
        finally:
            ev.close()
            rt.close()


class TestHardCapRefusalSemantics:
    """Item 7 assertion 3, under the invariant the code claims (REL-7).

    The registered wording is 'the hard cap cannot be bypassed by interleaved
    spend'. runner.py's own REL-7 note states there is no reservation held
    across the call and that correctness rests on single-threaded
    serialisation. Per #349's revisit clause this test asserts that invariant
    directly: strict check/call/spend bracketing on one thread, refusal BEFORE
    the subject call, and no overspend of the cap. It does not simulate
    multi-process interleaving the code explicitly does not claim to survive;
    when D11 (multi-process sampling) lands, this test is the one that must be
    replaced by a true reservation test.
    """

    def test_refusal_is_pre_call_and_serialised_and_never_overspends(self, tmp_path: Any) -> None:
        runner, client, ev, rt = _budget_runner(tmp_path, _varied_factory)
        try:
            run_id = f"cap-{uuid.uuid4().hex[:8]}"
            events: list[str] = []
            real_check = runner._check_budget
            real_update = runner._update_budget_spend
            real_side_effect = client.messages.create.side_effect

            def logged_check(rid: str, max_usd: float, projected: float) -> None:
                events.append("check")
                real_check(rid, max_usd, projected)

            def logged_call(**kwargs: Any) -> MagicMock:
                events.append("call")
                resp: MagicMock = real_side_effect(**kwargs)
                return resp

            def logged_update(rid: str, resp: Any) -> None:
                events.append("spend")
                real_update(rid, resp)

            runner._check_budget = logged_check  # type: ignore[method-assign, assignment]
            runner._update_budget_spend = logged_update  # type: ignore[method-assign, assignment]
            client.messages.create.side_effect = logged_call

            max_usd = 0.005
            with pytest.raises(BudgetAbortedError):
                runner.run_ablation(
                    skill_id="skill-1",
                    clauses=[_clause_spec()],
                    user_message=_USER_MSG,
                    max_usd=max_usd,
                    run_id=run_id,
                )

            assert events, "harness fault: no budget events recorded"
            assert events[-1] == "check", (
                f"CAP_REFUSAL_NOT_PRE_CALL: the run aborted but the last"
                f" recorded event is {events[-1]!r}, not the pre-call check;"
                f" the refusal must fire before a subject call is attempted,"
                f" never after spend."
            )
            for i, ev_name in enumerate(events):
                if ev_name != "call":
                    continue
                rest = events[i + 1 :]
                next_call = rest.index("call") if "call" in rest else len(rest)
                assert "spend" in rest[:next_call], (
                    f"CAP_SPEND_NOT_SERIALISED: subject call at event index {i}"
                    f" was followed by another call before its spend was"
                    f" recorded (events {events[i : i + next_call + 2]!r})."
                    f" The check/call/spend bracketing REL-7's correctness"
                    f" argument rests on does not hold."
                )
            budget = get_run_budget_by_id(rt, run_id)
            assert budget is not None
            assert budget["usd_spent"] <= max_usd + EPSILON_USD, (
                f"CAP_OVERSPENT: run_budget.usd_spent={budget['usd_spent']!r}"
                f" exceeds the hard cap {max_usd!r}; the pre-call gate admitted"
                f" spend past the cap it exists to refuse."
            )
        finally:
            ev.close()
            rt.close()
