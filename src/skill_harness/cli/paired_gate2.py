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

from rich.console import Console

from skill_harness.aggregation.profile import effect_from_matched_gate2
from skill_harness.aggregation.verdict import ValueClass, matched_gate2_verdict
from skill_harness.oc import Gate2Design, MMESpec
from skill_harness.ratification import RatificationError, parse_rat_record
from skill_harness.storage.migrations import open_evidence_readonly

_console = Console()


class PairedGate2Refusal(Exception):
    """A typed refusal from the paired Gate-2 read path."""

    def __init__(self, reason: str, exit_code: int = 1) -> None:
        super().__init__(reason)
        self.exit_code = exit_code


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
            "SELECT config_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise PairedGate2Refusal(
            f"paired run {run_id!r} not found in evidence DB",
            exit_code=1,
        )

    config = json.loads(row[0])

    # 3. Read paired cell counts from config_json (written by #387)
    paired_cells = config.get("paired_cells")
    if paired_cells is None:
        raise PairedGate2Refusal(
            f"paired run {run_id!r} has no paired_cells in config_json "
            f"(was this run ingested by #387?)",
            exit_code=1,
        )

    both_pass = int(paired_cells["both_pass"])
    full_only = int(paired_cells["full_only"])
    null_only = int(paired_cells["null_only"])
    both_fail = int(paired_cells["both_fail"])
    total_pairs = both_pass + full_only + null_only + both_fail

    # 4. Build the design from the ratification record
    design = Gate2Design(
        n_pairs=record.n,
        gamma=record.gamma,
        mme=MMESpec(delta_min=record.delta_min, q_min=record.q_min),
    )

    # 5. Count-mismatch check (k=8 pilot vs n=32 design)
    if total_pairs != design.n_pairs:
        raise PairedGate2Refusal(
            f"COUNT_MISMATCH: paired run {run_id!r} has {total_pairs} pairs "
            f"but the ratified design {record.rat_id} specifies "
            f"n_pairs={design.n_pairs}",
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
            pi_c_line += (
                " CACE secondary is not identified "
                "(zero invocations with full exposure)."
            )

    # 8. Print the decision
    assert effect.decision is not None  # effect_from_matched_gate2 always sets decision
    _console.print(f"Decision: {effect.decision.value}")
    _console.print(
        f"Signed delta: {effect.mean:.3f}, "
        f"95% CI [{effect.ci_lo:.3f}, {effect.ci_hi:.3f}]"
    )
    if pi_c_line:
        _console.print(pi_c_line)
    sub = (
        f"({verdict.cut_sub_reason.value})"
        if verdict.cut_sub_reason is not None
        else ""
    )
    _console.print(f"Verdict: {verdict.verdict.value} {sub}".rstrip())
    _console.print(f"Rationale: {verdict.rationale}")
