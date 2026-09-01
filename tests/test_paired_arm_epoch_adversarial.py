"""Adversarial pair tables: arm swaps, epoch mis-keys, absent scores (item 8, #350).

Registered condition (docs/assurance/falsification-plan.md item 8): paired
evidence is joined by epoch (``full_by_epoch`` / ``null_by_epoch`` in
``subject/ingest.py``) and scored by ``_observation(full.score, null.score)``.
A swapped Full and Null log, a renumbered epoch, or a missing score inverts or
dilutes every Gate-2 table built from the pair, flipping KEEP and CUT(harmful)
while each piece stays green in isolation.

PRE-REGISTRATION -- the properties and their predicted outcomes, written
before the first run.

Every property drives the REAL ``write_paired_evidence`` (the pure write path;
no ``[inspect]`` extra needed) against adversarial ``ParsedEvalLog`` pairs and
requires refusal at write time or fail-closed behaviour (zero verdict rows).

1. Arm swap, labels not relabelled: the true logs are exchanged but each
   sample keeps its original ``condition``. PREDICTED: refused (the role/
   condition check in ``_validate_pair``).
2. Arm swap, labels relabelled to be internally consistent, where the true
   Full arm invoked the skill: the invoked samples now sit in the Null role.
   PREDICTED: refused (control-arm contamination check, #46), and zero
   verdict rows written. This is the ticket's "a swapped beneficial table
   never emits an inverted KEEP" assertion: the only beneficial table that
   could invert is one whose Full arm actually used the skill, and that arm
   swap is exactly the contamination the gate refuses.
3. Epoch mis-key that changes the epoch SET (a dropped or renumbered-out-of-
   set epoch in one arm): PREDICTED: refused (unpaired-epochs check).
4. Duplicate epoch within an arm: PREDICTED: refused.
5. Absent score, arriving as NaN in ``score_value``: PREDICTED RED on current
   production code. ``_score_to_float`` passes a float NaN through, and
   ``_observation(nan, x)`` returns 0.5 because both comparisons are False --
   a missing measurement silently becomes a TIE, which dilutes the paired
   effect exactly as the plan registers. The pre-registered requirement is
   refuse-or-fail-closed; silent 0.5 is neither.

The honest boundary (per the ticket's revisit clause)
-----------------------------------------------------
The registration above predicted the zero-invocation label-consistent swap
would be structurally invisible. THE FIRST RUN REFUTED THAT PREDICTION: under
the old invocation-only model, production refused it via ``ZeroInvocationError``
(dead treated arm, pi_c_hat = 0). Under #384 (treatment = exposure),
``ZeroInvocationError`` is retired from the write path; the arm-swap surface
is closed by the contamination refusal (invoked samples in Null role) and the
unexposed-Full refusal (no description in Full transcript). A label-consistent
swap either places invoked samples in the Null role (contamination refusal) or
presents a Full role with no exposure (unexposed-Full refusal). An adversary
would need fabricated exposure traces to pass both, which is outside
"mis-keying".

One adversary remains structurally invisible from inside a pair, and this
module says so rather than asserting vacuously:

- A permutation of epoch labels WITHIN the same epoch set in one arm: the
  join key itself is the corrupted quantity, sets stay equal, and every
  structural check passes while pairs decouple. Residual risk documented in
  docs/findings/paired-ingest-boundary-undetectables.md.

``test_epoch_permutation_within_set_is_structurally_invisible`` pins that
boundary as a characterisation test: it asserts the CURRENT acceptance, so a
future defence flips it red and forces this registration to be revisited.

Isolation: the ``evidence_db_for_property_tests`` fixture with the documented
SAVEPOINT-per-example pattern (A28). Determinism: PYTHONHASHSEED=0 asserted at
collection; Hypothesis derandomised by the project profile, seeded examples.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from skill_harness.subject.ingest import (
    EvalLogIngestError,
    ParsedEvalLog,
    ParsedSample,
    write_paired_evidence,
)

_TS = "2026-08-31T00:00:00+00:00"
_PIN_FP = "f" * 64


def _sample(
    condition: str,
    epoch: int,
    score: float,
    *,
    invoked: bool,
    exposed: bool | None = None,
) -> ParsedSample:
    # Default: Full-arm samples are exposed, Null-arm samples are not (#384).
    if exposed is None:
        exposed = condition == "full"
    return ParsedSample(
        condition=condition,  # type: ignore[arg-type]
        skill_name="adversarial-skill",
        epoch=epoch,
        scorer_name="file_contains",
        score_value=score,
        invoked_skill=invoked,
        exposed_skill=exposed,
        output_text=f"output-{condition}-{epoch}",
        subject_model="openrouter/anthropic/claude-haiku-4.5",
        harness_pin_json=None,
        harness_pin_fingerprint=_PIN_FP,
        input_tokens=100,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        output_tokens=10,
        usd=None,
    )


def _log(condition: str, samples: tuple[ParsedSample, ...]) -> ParsedEvalLog:
    return ParsedEvalLog(
        task_name=f"task-{condition}",
        task_id=f"tid-{condition}",
        status="success",
        created=_TS,
        samples=samples,
    )


def _beneficial_pair(
    epochs: list[int], *, full_invokes: bool
) -> tuple[ParsedEvalLog, ParsedEvalLog]:
    """A pair where Full wins every epoch (the table a KEEP is minted from)."""
    full = _log("full", tuple(_sample("full", e, 1.0, invoked=full_invokes) for e in epochs))
    null = _log("null", tuple(_sample("null", e, 0.0, invoked=False) for e in epochs))
    return full, null


def _verdict_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM oracle_verdicts").fetchone()[0])


def _assert_refused(
    conn: sqlite3.Connection,
    accepted_name: str,
    wrote_name: str,
    *,
    full: ParsedEvalLog,
    null: ParsedEvalLog,
    skill_dir: Path,
    match: str | None = None,
) -> None:
    """Require write_paired_evidence to refuse the pair AND fail closed.

    Both failure directions carry named assertions so a mutation receipt can
    attribute a red to this detector rather than to a bare DID-NOT-RAISE.
    """
    refused = False
    message = ""
    try:
        write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    except EvalLogIngestError as exc:
        refused = True
        message = str(exc)
    except sqlite3.OperationalError as exc:
        # Inside the per-example SAVEPOINT, production's BEGIN IMMEDIATE cannot
        # start; reaching it at all means every refusal gate ACCEPTED the pair
        # and the write began. Attribute that as acceptance, not as noise.
        if "within a transaction" not in str(exc):
            raise
    assert refused, (
        f"{accepted_name}: write_paired_evidence ACCEPTED an adversarial pair"
        f" it must refuse; the corrupted table is now mintable evidence."
    )
    if match is not None:
        assert match in message, (
            f"{accepted_name}: refused, but by {message!r} rather than the"
            f" registered {match!r} gate."
        )
    assert _verdict_count(conn) == 0, (
        f"{wrote_name}: the pair was refused but verdict rows exist; refusal must fail closed."
    )


@pytest.fixture()
def skill_dir(tmp_path: Path) -> Path:
    d = tmp_path / "adversarial-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("# adversarial-skill\n", encoding="utf-8")
    return d


_EPOCH_SETS = st.lists(st.integers(min_value=1, max_value=50), min_size=2, max_size=6, unique=True)


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(epochs=_EPOCH_SETS)
def test_arm_swap_without_relabel_refused(
    epochs: list[int],
    evidence_db_for_property_tests: sqlite3.Connection,
    skill_dir: Path,
) -> None:
    """Property 1: exchanged logs whose samples keep their true condition are refused."""
    conn = evidence_db_for_property_tests
    full, null = _beneficial_pair(epochs, full_invokes=True)
    conn.execute("SAVEPOINT hyp_example")
    try:
        # The swap: the null-role argument receives the log whose samples
        # say condition="full", and vice versa.
        _assert_refused(
            conn,
            "ARM_SWAP_ACCEPTED",
            "ARM_SWAP_WROTE_VERDICTS",
            full=null,
            null=full,
            skill_dir=skill_dir,
        )
    finally:
        conn.execute("ROLLBACK TO hyp_example")
        conn.execute("RELEASE hyp_example")


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(epochs=_EPOCH_SETS)
def test_label_consistent_arm_swap_with_invocation_refused(
    epochs: list[int],
    evidence_db_for_property_tests: sqlite3.Connection,
    skill_dir: Path,
) -> None:
    """Property 2: the swapped beneficial table never mints an inverted KEEP.

    The adversary relabels conditions so each log is internally consistent,
    but the true Full arm (which invoked the skill, as a beneficial arm that
    was actually exercised does) now sits in the Null role. The control-arm
    contamination gate must refuse, and nothing may be written.
    """
    conn = evidence_db_for_property_tests
    # True world: full invoked and won. Adversary swaps and relabels.
    swapped_null = _log("null", tuple(_sample("null", e, 1.0, invoked=True) for e in epochs))
    swapped_full = _log("full", tuple(_sample("full", e, 0.0, invoked=False) for e in epochs))
    conn.execute("SAVEPOINT hyp_example")
    try:
        _assert_refused(
            conn,
            "INVERTED_KEEP_TABLE_ACCEPTED",
            "INVERTED_KEEP_TABLE_WRITTEN",
            full=swapped_full,
            null=swapped_null,
            skill_dir=skill_dir,
            match="contamination",
        )
    finally:
        conn.execute("ROLLBACK TO hyp_example")
        conn.execute("RELEASE hyp_example")


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(epochs=_EPOCH_SETS, data=st.data())
def test_epoch_set_mismatch_refused(
    epochs: list[int],
    data: st.DataObject,
    evidence_db_for_property_tests: sqlite3.Connection,
    skill_dir: Path,
) -> None:
    """Property 3: an epoch dropped or renumbered out of the shared set is refused."""
    conn = evidence_db_for_property_tests
    full, null = _beneficial_pair(epochs, full_invokes=True)
    victim = data.draw(st.sampled_from(epochs), label="victim_epoch")
    renumber = data.draw(st.booleans(), label="renumber_not_drop")
    if renumber:
        replacement = data.draw(st.integers(min_value=51, max_value=99), label="replacement_epoch")
        mutated = tuple(
            _sample(
                "null", replacement if s.epoch == victim else s.epoch, s.score_value, invoked=False
            )
            for s in null.samples
        )
    else:
        mutated = tuple(s for s in null.samples if s.epoch != victim)
        if not mutated:
            return  # empty-samples refusal is its own check; not this property
    conn.execute("SAVEPOINT hyp_example")
    try:
        _assert_refused(
            conn,
            "EPOCH_MISKEY_ACCEPTED",
            "EPOCH_MISKEY_WROTE_VERDICTS",
            full=full,
            null=_log("null", mutated),
            skill_dir=skill_dir,
        )
    finally:
        conn.execute("ROLLBACK TO hyp_example")
        conn.execute("RELEASE hyp_example")


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(epochs=_EPOCH_SETS)
def test_duplicate_epoch_refused(
    epochs: list[int],
    evidence_db_for_property_tests: sqlite3.Connection,
    skill_dir: Path,
) -> None:
    """Property 4: a duplicated epoch within one arm is refused."""
    conn = evidence_db_for_property_tests
    full, null = _beneficial_pair(epochs, full_invokes=True)
    dup = (*null.samples, null.samples[0])
    conn.execute("SAVEPOINT hyp_example")
    try:
        _assert_refused(
            conn,
            "DUPLICATE_EPOCH_ACCEPTED",
            "DUPLICATE_EPOCH_WROTE_VERDICTS",
            full=full,
            null=_log("null", dup),
            skill_dir=skill_dir,
        )
    finally:
        conn.execute("ROLLBACK TO hyp_example")
        conn.execute("RELEASE hyp_example")


def test_nan_score_is_refused_or_fails_closed(
    evidence_db: sqlite3.Connection, skill_dir: Path
) -> None:
    """Property 5: an absent measurement arriving as NaN must not become a tie.

    Registered prediction: RED on current code, confirmed on first run
    (observations=[0.5, 1.0, 1.0]). NaN passed ``_score_to_float``, and
    ``_observation(nan, x)`` returned 0.5 because both orderings are False, so
    a missing score silently diluted the paired effect toward no-effect.

    Repaired by #363 at the MODEL layer: ``ParsedSample.score_value`` carries
    ``allow_inf_nan=False``, so the refusal fires when the sample is
    constructed. PR #364's M4 survivor is the evidence for that placement --
    this detector builds ``ParsedSample`` directly, so the write path never
    calls ``_score_to_float`` and a guard there alone leaves the property red.

    The refusal now precedes the write instead of happening during it, which is
    earlier than the registered requirement rather than weaker than it: nothing
    is written either way. Only the NaN-carrying construction is guarded, and
    the guard requires the error to name ``score_value``. A blanket
    ``except ValidationError`` around the whole pair would green this detector
    on any future field constraint firing on any unrelated field, which would
    keep the registered BOUND while losing the registered MECHANISM -- the test
    would no longer prove that the NaN was what got refused.

    The registered bound is unchanged: no observation may be 0.5.
    """
    conn = evidence_db
    epochs = [1, 2, 3]
    null = _log("null", tuple(_sample("null", e, 0.0, invoked=False) for e in epochs))
    try:
        full = _log(
            "full",
            tuple(_sample("full", e, math.nan if e == 2 else 1.0, invoked=True) for e in epochs),
        )
    except ValidationError as exc:
        assert "score_value" in str(exc), (
            f"NAN_REFUSED_BY_THE_WRONG_FIELD: construction was refused, but not for"
            f" score_value ({exc}); this detector must not go green on an unrelated"
            f" constraint."
        )
        return  # refused at construction: nothing reaches the write path
    try:
        result = write_paired_evidence(full=full, null=null, skill_dir=skill_dir, conn=conn)
    except EvalLogIngestError:
        return  # refused at write time: the other acceptable outcome
    observations = [
        row[0]
        for row in conn.execute(
            "SELECT observation FROM oracle_verdicts WHERE verdict_id IN ({})".format(
                ",".join("?" * len(result.verdict_ids))
            ),
            list(result.verdict_ids),
        ).fetchall()
    ]
    assert 0.5 not in observations, (
        f"NAN_SCORE_BECOMES_TIE: a NaN score_value produced observation 0.5"
        f" (observations={observations}); a missing measurement is being"
        f" recorded as evidence of no effect, diluting every Gate-2 table"
        f" built from this pair. Refuse it or fail closed."
    )


def test_zero_invocation_arm_swap_with_null_contamination_refused(
    evidence_db: sqlite3.Connection, skill_dir: Path
) -> None:
    """The other half of the swap surface: the true Full arm (which invoked)
    is relabelled as Null.

    Under the #384 treatment=exposure model, the label-consistent swap with
    invoked samples in the Null role is refused as control-arm contamination
    (NullArmContaminationError), not as a dead treated arm. ZeroInvocationError
    is retired from the write path; exposure, not invocation, is the treatment.
    """
    conn = evidence_db
    epochs = [1, 2]
    swapped_null = _log("null", tuple(_sample("null", e, 1.0, invoked=True) for e in epochs))
    swapped_full = _log("full", tuple(_sample("full", e, 0.0, invoked=False) for e in epochs))
    _assert_refused(
        conn,
        "DEAD_ARM_SWAP_ACCEPTED",
        "DEAD_ARM_SWAP_WROTE_VERDICTS",
        full=swapped_full,
        null=swapped_null,
        skill_dir=skill_dir,
        match="contamination",
    )


def test_epoch_permutation_within_set_is_structurally_invisible(
    evidence_db: sqlite3.Connection, skill_dir: Path
) -> None:
    """Honest-boundary characterisation: a within-set epoch relabel is ACCEPTED.

    The join key itself is the corrupted quantity; the epoch sets stay equal
    and every structural check passes while the pairs decouple. Residual risk:
    docs/findings/paired-ingest-boundary-undetectables.md.
    """
    conn = evidence_db
    # Full wins epoch 1, loses epoch 2; permuting Null's epochs decouples pairs.
    full = _log(
        "full",
        (_sample("full", 1, 1.0, invoked=True), _sample("full", 2, 0.0, invoked=True)),
    )
    null_permuted = _log(
        "null",
        (_sample("null", 2, 0.0, invoked=False), _sample("null", 1, 1.0, invoked=False)),
    )
    result = write_paired_evidence(full=full, null=null_permuted, skill_dir=skill_dir, conn=conn)
    assert result.verdict_ids, "characterisation drift: the permutation is now refused"
