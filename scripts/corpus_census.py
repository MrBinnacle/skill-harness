#!/usr/bin/env python3
"""CLI: deterministic census of an extracted-clause JSONL corpus (#118).

Usage:
    python scripts/corpus_census.py PATH/to/clauses.jsonl [--receipt OUT.json]

Zero network calls. Same input always produces the same output.
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
            "Deterministic census of how much of an extracted-clause JSONL "
            "corpus is mechanically measurable today. Pure computation - no "
            "API calls, no model judgment."
        )
    )
    parser.add_argument(
        "jsonl",
        type=Path,
        help="Path to the extracted-clause JSONL file",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="Write the JSON receipt to this path (re-derivable / diffable)",
    )
    args = parser.parse_args(argv)

    # Import after argv parse so --help works without the package on broken envs.
    from skill_harness.extractor.corpus_census import emit_report, run_census

    if not args.jsonl.is_file():
        print(f"error: not a file: {args.jsonl}", file=sys.stderr)
        return 2

    result = run_census(args.jsonl)
    emit_report(result, stdout=sys.stdout, receipt_path=args.receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
