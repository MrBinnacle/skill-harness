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

from skill_harness.sitegen import SiteBuildError, SitegenNotInstalledError, build_site

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


def _validation_errors() -> tuple[type[BaseException], ...]:
    """Exception types ``main`` treats as build refusals, beyond ``SiteBuildError``.

    ``jsonschema``'s ``ValidationError`` is included only when the
    ``[sitegen]`` extra is importable. Without the extra, ``build_site`` raises
    ``SitegenNotInstalledError`` before any receipt is validated, so the
    empty-tuple return matches nothing and this branch is never reached. The
    import is lazy for the same reason the validator import in
    ``skill_harness.sitegen`` is: a core install must be able to import this
    module (and answer ``--help``) without ``jsonschema`` present.
    """
    try:
        from jsonschema.exceptions import ValidationError
    except ImportError:
        return ()
    return (ValidationError,)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # ``ValidationError`` joins the refusal tuple only when the [sitegen] extra
    # is importable; without it ``build_site`` raises ``SitegenNotInstalledError``
    # first, so the empty-tuple case matches nothing. Built before the try so
    # the ``except`` clause stays a literal tuple of exception classes (mypy
    # checks ``except`` operands statically and does not follow ``*`` unpacking
    # of a function call there).
    refusal: tuple[type[BaseException], ...] = (SiteBuildError, *_validation_errors())
    try:
        written = build_site(
            schema_path=args.schema,
            receipts_dir=args.receipts,
            extraction_path=args.extraction,
            output_dir=args.output,
            marker=args.marker,
        )
    except SitegenNotInstalledError as exc:
        print(f"SITE BUILD: REFUSED -- {exc}", file=sys.stderr)
        return 1
    except refusal as exc:
        print(f"SITE BUILD: REFUSED -- {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(path)
    print(f"SITE BUILD: {len(written)} file(s) written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
