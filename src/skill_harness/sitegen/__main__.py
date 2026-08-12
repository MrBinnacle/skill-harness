"""Command-line entry point for the receipts site generator (#186).

Deliberately not a ``skill-harness`` subcommand: building the published site is
a repository task, not an operator-facing measurement command, and the shipped
CLI surface stays as it was.

Usage::

    python -m skill_harness.sitegen --output site --marker "$(git rev-parse HEAD)"
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from jsonschema.exceptions import ValidationError  # type: ignore[import-untyped]

from skill_harness.sitegen import SiteBuildError, build_site

_DEFAULT_SCHEMA = Path("docs") / "sers" / "sers.schema.json"
_DEFAULT_RECEIPTS = Path("docs") / "sers" / "receipts"
_DEFAULT_OUTPUT = Path("site")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m skill_harness.sitegen",
        description=(
            "Render the static receipts site. Every receipt is validated against "
            "the SERS schema first; an invalid receipt stops the build with nothing "
            "written."
        ),
    )
    parser.add_argument("--schema", type=Path, default=_DEFAULT_SCHEMA, help="SERS schema path")
    parser.add_argument(
        "--receipts", type=Path, default=_DEFAULT_RECEIPTS, help="directory of SERS receipts"
    )
    parser.add_argument(
        "--extraction",
        type=Path,
        default=None,
        help="extraction JSONL for the clause-evidence join (omitted: the page states the refusal)",
    )
    parser.add_argument(
        "--output", type=Path, default=_DEFAULT_OUTPUT, help="output directory (must not exist)"
    )
    parser.add_argument(
        "--marker",
        required=True,
        help="content marker unique to this build, written into every page",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        written = build_site(
            schema_path=args.schema,
            receipts_dir=args.receipts,
            extraction_path=args.extraction,
            output_dir=args.output,
            marker=args.marker,
        )
    except (SiteBuildError, ValidationError) as exc:
        print(f"SITE BUILD: REFUSED -- {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(path)
    print(f"SITE BUILD: {len(written)} file(s) written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
