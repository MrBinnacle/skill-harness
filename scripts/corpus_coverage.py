#!/usr/bin/env python3
"""CLI: dual corpus coverage — constructible vs instantiated (#121, #136).

Usage:
    python scripts/corpus_coverage.py PATH/to/clauses.jsonl \\
        [--evidence PATH/to/evidence.db] [--receipt OUT.json]

Zero network calls. Same input always produces the same output.

Reports two distinct figures side by side (never blended):
  - constructible coverage (offline from clause JSONL)
  - instantiated coverage (from evidence.frozen_cases; named refusal when
    the freeze stage has produced no cases, or no evidence DB is supplied)

Also reports (#136):
  - cross-tab of case-presence against vacuity_flag==none
  - whether constructible coverage is independent of vacuity_flag on this
    input, or equal to the vacuity_none fraction by construction
    (off-diagonal empty)
  - detector false positives: flagged clauses that still carry a complete case
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, so any non-ASCII byte in this report
    # raises UnicodeEncodeError on write and UnicodeDecodeError in a UTF-8
    # reader. Report text is kept ASCII-only; this is the belt-and-braces half
    # so a future non-ASCII string degrades instead of aborting the run.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description=(
            "Dual corpus coverage: constructible (structurally complete "
            "falsifying_case) vs instantiated (>=1 frozen_cases row). "
            "Also states whether constructible coverage is independent of "
            "vacuity_flag on the input or equal by construction, and surfaces "
            "detector false positives (flagged + complete case). "
            "Pure computation - no API calls, no model judgment."
        )
    )
    parser.add_argument(
        "jsonl",
        type=Path,
        help="Path to the extracted-clause JSONL file",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=None,
        help=(
            "Path to the evidence SQLite database (for instantiated coverage). "
            "If omitted, instantiated coverage is refused with reason "
            "no_evidence_database."
        ),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="Write the JSON receipt to this path (re-derivable / diffable)",
    )
    args = parser.parse_args(argv)

    from skill_harness.extractor.corpus_coverage import emit_report, run_coverage

    if not args.jsonl.is_file():
        print(f"error: not a file: {args.jsonl}", file=sys.stderr)
        return 2
    if args.evidence is not None and not args.evidence.is_file():
        print(f"error: not a file: {args.evidence}", file=sys.stderr)
        return 2

    result = run_coverage(args.jsonl, evidence_path=args.evidence)
    emit_report(result, stdout=sys.stdout, receipt_path=args.receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
