"""Read-only CLI surface for the paired-lane Gate-2 decision (#389).

Takes a paired run id, a ratification-record reference, and a value class,
and prints the decision, signed delta with its interval, pi_c line, and
verdict — or a typed refusal.  Performs no writes and no API calls.

The design used is the one in the referenced RATIFIED record; a DRAFT record,
a missing record, or a field mismatch is a typed refusal naming the field.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from rich.console import Console

from skill_harness.aggregation.matched_bridge import MatchedRefusalReason
from skill_harness.aggregation.profile import effect_from_matched_gate2
from skill_harness.aggregation.verdict import ValueClass, matched_gate2_verdict
from skill_harness.oc import Gate2Design, MMESpec
from skill_harness.ratification import RatificationError, RatRecord, parse_rat_record
from skill_harness.storage.migrations import open_evidence_readonly

_console = Console()


class PairedGate2Refusal(Exception):
    """A typed refusal from the paired Gate-2 read path."""

    def __init__(self, reason: str, exit_code: int = 1) -> None:
        super().__init__(reason)
        self.exit_code = exit_code


# The four fields section 2 of a Gate-2 record requires the runner to declare
# and the ingest to record. Compared as strings against the parsed record.
_RUNNER_DECLARED_FIELDS: tuple[str, ...] = ("rat_id", "skill_id", "task_family", "estimand")


def _arm_entered_msg(hazard_block: dict[str, Any], arm: str) -> str:
    """Render ``entered/epochs`` for one arm of the hazard block (#421)."""
    arm_block = hazard_block.get(arm)
    if isinstance(arm_block, dict):
        return f"{arm_block.get('entered', '?')}/{arm_block.get('epochs', '?')}"
    return "?"


def _check_runner_declaration(record: RatRecord, run_id: str, runner: object) -> None:
    """Refuse unless the run's recorded runner block declares this record's identity.

    :param record: The parsed RATIFIED record.
    :param run_id: The paired run id, for the refusal text.
    :param runner: ``config_json["runner"]`` as ingested, or ``None`` when the run
        carries no block.
    :raises PairedGate2Refusal: No runner block, or a declared field differs from
        the record. The refusal names every differing field.
    """
    if not isinstance(runner, dict):
        raise PairedGate2Refusal(
            f"paired run {run_id!r} records no runner block in config_json; "
            f"section 2 of {record.rat_id} requires the runner to declare "
            f"{', '.join(_RUNNER_DECLARED_FIELDS)} and the ingest to record them "
            f"(a run launched outside the record cannot be decided under it)",
            exit_code=1,
        )
    mismatches: list[str] = []
    for field in _RUNNER_DECLARED_FIELDS:
        declared = runner.get(field)
        expected = getattr(record, field)
        if declared != expected:
            mismatches.append(f"{field} record {expected!r} != run {declared!r}")
    if mismatches:
        raise PairedGate2Refusal(
            f"ratification record {record.rat_id} field mismatch: " + "; ".join(mismatches),
            exit_code=1,
        )


def paired_gate2_read(
    run_id: str,
    ratification_path: Path,
    value_class: ValueClass,
    *,
    evidence_db: Path = Path("./evidence.db"),
) -> None:
    """Read-only paired-lane Gate-2 decision.

    :param run_id: The paired run id.
    :param ratification_path: Path to the RAT record.
    :param value_class: The value class (required, no default).
    :param evidence_db: Path to the evidence DB.
    """
    # 1. Validate the ratification record
    try:
        record = parse_rat_record(ratification_path)
    except RatificationError as exc:
        raise PairedGate2Refusal(
            f"ratification record {ratification_path.name}: {exc}",
            exit_code=1,
        ) from exc

    if record.status != "RATIFIED":
        raise PairedGate2Refusal(
            f"ratification record {record.rat_id} has status {record.status!r}; "
            f"only RATIFIED records authorize a Gate-2 decision "
            f"(operator signs last, pre-spend)",
            exit_code=1,
        )

    if record.gate != "gate2":
        raise PairedGate2Refusal(
            f"ratification record {record.rat_id} field 'gate' is {record.gate!r}; "
            f"paired Gate-2 read requires gate2",
            exit_code=1,
        )

    # Design knobs are registered on the record, never defaulted here.
    missing_design: list[str] = []
    if record.gamma is None:
        missing_design.append("gamma")
    if record.delta_min is None:
        missing_design.append("delta_min")
    if record.q_min is None:
        missing_design.append("q_min")
    if missing_design:
        named = ", ".join(repr(f) for f in missing_design)
        raise PairedGate2Refusal(
            f"ratification record {record.rat_id} field mismatch: missing design field(s) {named}",
            exit_code=1,
        )

    # 2. Open evidence DB read-only and load the run
    conn: sqlite3.Connection | None = None
    try:
        conn = open_evidence_readonly(evidence_db)
    except Exception as exc:
        raise PairedGate2Refusal(
            f"cannot open evidence DB {evidence_db}: {exc}",
            exit_code=1,
        ) from exc

    try:
        row = conn.execute(
            "SELECT skill_id, config_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise PairedGate2Refusal(
            f"paired run {run_id!r} not found in evidence DB",
            exit_code=1,
        )

    config_raw = row[1]
    config = json.loads(config_raw)

    # 3. Read paired cell counts from config_json (written by #387)
    paired_cells = config.get("paired_cells")
    if paired_cells is None:
        raise PairedGate2Refusal(
            f"paired run {run_id!r} has no paired_cells in config_json "
            f"(was this run ingested by #387?)",
            exit_code=1,
        )

    # 4. The run must be the one the record authorises. Section 2 of a Gate-2
    # record puts that equality on the RUNNER-DECLARED config, recorded at
    # ingest under config_json["runner"] (#409, #411): rat_id, skill_id,
    # task_family and estimand must equal the record's values exactly. The
    # runs.skill_id column is the card's content digest, not its name, so it
    # was never the field the record names; comparing it refused every real
    # ingest (#391, 2026-09-03) while the seeded tests passed on a name.
    _check_runner_declaration(record, run_id, config.get("runner"))

    # 4a. #424: a trap-discipline read refuses when the record carries no
    # outcome_type. The outcome_type declares which oracle scored this run:
    # ``pass_fail`` (legacy conjunction) or ``invariant`` (split invariant +
    # completion). Without it the decision rule cannot select the right lattice.
    if value_class is ValueClass.TRAP_DISCIPLINE and record.outcome_type is None:
        raise PairedGate2Refusal(
            f"OUTCOME_TYPE_REQUIRED: paired run {run_id!r} under {record.rat_id} "
            f"carries value_class trap-discipline but the ratification record has "
            f"no outcome_type field. A trap-discipline read requires outcome_type "
            f"(pass_fail or invariant) to select the scoring lattice (#424).",
            exit_code=1,
        )

    # 4b. #421: a trap-discipline read refuses when the Null arm met the hazard
    # too rarely to measure. The oracle checks the outcome (ancestry preserved),
    # not whether the hazard was entered; a model that never runs the
    # trap-entering command passes, and the lattice is indistinguishable from
    # "trap avoided". The hazard block is under config_json["runner"]["hazard"]
    # (pattern, floor, null/full epochs+entered). A run whose runner block
    # predates the field is refused as HAZARD_NOT_RECORDED. The threshold is the
    # registered hazard_floor (on the record; mirrored into the block at launch),
    # not zero: entered = 0 is the degenerate case of the same refusal.
    # The Full arm is printed and never gated (#403): hazard entry there is
    # post-treatment.
    runner_block = config.get("runner")
    hazard_block = runner_block.get("hazard") if isinstance(runner_block, dict) else None
    if value_class is ValueClass.TRAP_DISCIPLINE:
        if not isinstance(hazard_block, dict):
            raise PairedGate2Refusal(
                f"HAZARD_NOT_RECORDED: paired run {run_id!r} records no hazard block "
                f"in config_json['runner']['hazard'] under {record.rat_id}; "
                f"a trap-discipline read refuses when the runner never recorded "
                f"whether the Null arm entered the hazard (#421). The run predates "
                f"the hazard_entry_counts field and is not evidence the trap was "
                f"avoided.",
                exit_code=1,
            )
        null_hazard = hazard_block.get("null")
        if not isinstance(null_hazard, dict):
            raise PairedGate2Refusal(
                f"HAZARD_NOT_RECORDED: paired run {run_id!r} hazard block under "
                f"{record.rat_id} carries no null arm counts "
                f"(config_json['runner']['hazard']['null']); "
                f"a trap-discipline read refuses when Null-arm entry was never "
                f"recorded (#421).",
                exit_code=1,
            )
        null_entered = int(null_hazard.get("entered", 0) or 0)
        null_epochs = int(null_hazard.get("epochs", 0) or 0)
        # Floor: record first (registered), then the block mirror written at launch.
        floor_raw = record.hazard_floor
        if floor_raw is None:
            block_floor = hazard_block.get("floor")
            floor_raw = float(block_floor) if isinstance(block_floor, (int, float)) else None
        if floor_raw is None:
            raise PairedGate2Refusal(
                f"HAZARD_NOT_RECORDED: paired run {run_id!r} under {record.rat_id} "
                f"has a hazard block but neither the record nor the block carries "
                f"hazard_floor; the Null-arm rate cannot be checked against a "
                f"registered floor (#421).",
                exit_code=1,
            )
        floor = float(floor_raw)
        null_rate = (null_entered / null_epochs) if null_epochs > 0 else 0.0
        if null_rate < floor:
            raise PairedGate2Refusal(
                f"HAZARD_NOT_MET: paired run {run_id!r} under {record.rat_id} "
                f"records null.entered = {null_entered} of {null_epochs} epochs "
                f"(rate {null_rate:.4f}) below hazard_floor {floor}; "
                f"pattern {hazard_block.get('pattern', '?')!r}. A trap-discipline "
                f"read refuses when the Null arm met the hazard too rarely to "
                f"measure (#421): the oracle checks the outcome, not whether the "
                f"trap was entered, so a model that rarely or never pulls cannot "
                f"be distinguished from one that avoids the pull trap.",
                exit_code=2,
            )
        _console.print(
            f"Full arm entered the hazard in {_arm_entered_msg(hazard_block, 'full')} "
            f"(pattern {hazard_block.get('pattern', '?')!r}; not gated)"
        )
    elif isinstance(hazard_block, dict):
        _console.print(
            f"[dim]hazard: pattern={hazard_block.get('pattern', '?')!r} "
            f"null.entered={_arm_entered_msg(hazard_block, 'null')} "
            f"full.entered={_arm_entered_msg(hazard_block, 'full')}[/]"
        )

    both_pass = int(paired_cells["both_pass"])
    full_only = int(paired_cells["full_only"])
    null_only = int(paired_cells["null_only"])
    both_fail = int(paired_cells["both_fail"])
    total_pairs = both_pass + full_only + null_only + both_fail

    # 4. Build the design from the ratification record (knobs already checked)
    assert record.gamma is not None
    assert record.delta_min is not None
    assert record.q_min is not None
    design = Gate2Design(
        n_pairs=record.n,
        gamma=record.gamma,
        mme=MMESpec(delta_min=record.delta_min, q_min=record.q_min),
    )

    # 5. Count-mismatch check (k=8 pilot vs n=32 design)
    if total_pairs != design.n_pairs:
        raise PairedGate2Refusal(
            f"{MatchedRefusalReason.COUNT_MISMATCH.name}: paired run {run_id!r} "
            f"has {total_pairs} pairs but the ratified design {record.rat_id} "
            f"specifies n_pairs={design.n_pairs}",
            exit_code=2,
        )

    # 6. Compute the effect and verdict
    effect = effect_from_matched_gate2(
        design,
        both_pass=both_pass,
        full_only=full_only,
        null_only=null_only,
        both_fail=both_fail,
    )

    verdict = matched_gate2_verdict(effect, value_class=value_class)

    # 7. Format pi_c line from config_json
    pi_c_data = config.get("pi_c")
    pi_c_line = ""
    if pi_c_data is not None:
        pi_c_hat = pi_c_data.get("pi_c_hat", 0.0)
        pi_c_n = pi_c_data.get("trials", 0)
        ci_low = pi_c_data.get("ci_low", 0.0)
        ci_high = pi_c_data.get("ci_high", 1.0)
        confidence = pi_c_data.get("confidence", 0.95)
        k = round(pi_c_hat * pi_c_n)
        pi_c_line = (
            f"pi_c_hat = {k}/{pi_c_n} = {pi_c_hat:.4f} "
            f"[{confidence:.0%} CI {ci_low:.4f}, {ci_high:.4f}]"
        )
        if pi_c_hat == 0.0:
            pi_c_line += " CACE secondary is not identified (zero invocations with full exposure)."

    # 8. Print the decision
    assert effect.decision is not None  # effect_from_matched_gate2 always sets decision
    _console.print(f"Decision: {effect.decision.value}")
    _console.print(
        f"Signed delta: {effect.mean:.3f}, 95% CI [{effect.ci_lo:.3f}, {effect.ci_hi:.3f}]"
    )
    if pi_c_line:
        _console.print(pi_c_line)
    if verdict.cut_sub_reason is not None:
        sub = f"({verdict.cut_sub_reason.value})"
    elif verdict.wrong_instrument:
        sub = "(wrong_instrument)"
    else:
        sub = ""
    _console.print(f"Verdict: {verdict.verdict.value} {sub}".rstrip())
    _console.print(f"Rationale: {verdict.rationale}")
