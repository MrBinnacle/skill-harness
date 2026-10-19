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

from skill_harness.sitegen import (
    DEFAULT_BASE_URL,
    DEFAULT_LANDING_COPY,
    SiteBuildError,
    SitegenNotInstalledError,
    build_site,
)

_DEFAULT_SCHEMA = Path("docs") / "sers" / "sers.schema.json"
_DEFAULT_RECEIPTS = Path("docs") / "sers" / "receipts"
_DEFAULT_OUTPUT = Path("site")
_DEFAULT_SOCIAL_IMAGE = Path("assets") / "social-preview.png"
#: No icon is on the tree at this path today, so no page links one. See the
#: S455 make log's halt on audit finding A4.
_DEFAULT_FAVICON = Path("assets") / "favicon.svg"


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
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "the published address every absolute URL on the site is composed from "
            f"(default: {DEFAULT_BASE_URL})"
        ),
    )
    parser.add_argument(
        "--landing",
        action="store_true",
        help=(
            "write the landing page as index.html and move the receipts index to "
            "receipts.html (default: off, so index.html stays the receipts index)"
        ),
    )
    parser.add_argument(
        "--landing-copy",
        type=Path,
        default=DEFAULT_LANDING_COPY,
        help="Markdown file the landing copy is read from",
    )
    parser.add_argument(
        "--social-preview",
        type=Path,
        default=_DEFAULT_SOCIAL_IMAGE,
        help="image copied into the build and referenced as og:image (skipped when absent)",
    )
    parser.add_argument(
        "--favicon",
        type=Path,
        default=_DEFAULT_FAVICON,
        help="icon copied into the build and linked from every page (skipped when absent)",
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
            base_url=args.base_url,
            landing=args.landing,
            landing_copy_path=args.landing_copy,
            social_image_path=args.social_preview,
            favicon_path=args.favicon,
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
