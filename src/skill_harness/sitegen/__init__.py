"""Static site generator for the published SERS receipts (#186).

Two inputs, one gate:

- ``docs/sers/receipts/*.json``, validated against ``docs/sers/sers.schema.json``
  before a single byte of output is written. A receipt that does not validate
  raises out of ``build_site`` and no site exists afterwards, so "published" and
  "validated" are the same event rather than two hopefully-consistent ones.
- the extraction join, read through the same
  :mod:`skill_harness.extractor.clause_evidence` loader the
  ``skill audit --extraction`` path uses. There is no second loader here, so the
  clause-evidence grade on a page and the one in the terminal cannot drift.

Every page is rendered in memory first and only then written, so a refusal
partway through cannot leave a half-published site behind.

Build locally::

    python -m skill_harness.sitegen --output site --marker "$(git rev-parse HEAD)"
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skill_harness.extractor.clause_evidence import (
    ClauseEvidenceOutcome,
    load_clause_evidence,
    no_extraction_outcome,
)
from skill_harness.sitegen.landing import parse_landing, render_landing_page
from skill_harness.sitegen.render import (
    DEFAULT_BASE_URL,
    FAVICON_NAME,
    INDEX_FILE_NAME,
    NOT_FOUND_PAGE_NAME,
    RECEIPTS_PAGE_NAME,
    SCHEMA_FILE_NAME,
    SCHEMA_PAGE_NAME,
    SOCIAL_IMAGE_NAME,
    STYLESHEET_NAME,
    SiteBuildError,
    SiteShell,
    read_stylesheet,
    render_index_page,
    render_not_found_page,
    render_schema_page,
    render_skill_page,
    skill_page_name,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_LANDING_COPY",
    "SiteBuildError",
    "SitegenNotInstalledError",
    "build_site",
    "load_receipts",
    "load_schema",
]

#: Where the landing copy lives. Under ``docs/`` on purpose: the required
#: ``vale`` job already lints that tree at error level, so the prose a stranger
#: reads is gated with no workflow edit.
DEFAULT_LANDING_COPY = Path("docs") / "site" / "landing.md"


# The [sitegen] extra's install hint. ``jsonschema`` reaches this environment
# only through that extra (and through [dev], which re-declares it for the test
# stack; and transitively through inspect-ai, jsonschema>3.1.1) -- never
# through [project.dependencies]. A core install therefore imports this module
# fine; the validator import sits behind this hint so a build fails at use
# time with an actionable message rather than at import time with a bare
# ImportError. Mirrors subject/inspect_adapter._yaml for the same reason.
_INSTALL_HINT = (
    'building the receipts site requires the optional extra: pip install "skill-harness[sitegen]"'
)


class SitegenNotInstalledError(RuntimeError):
    """Raised when ``jsonschema`` is missing (the optional ``[sitegen]`` extra)."""


def _validator() -> Any:
    """Import ``jsonschema.Draft202012Validator`` lazily, with this module's
    own install hint on failure.

    Module scope would be wrong here. ``jsonschema`` is an optional extra, not
    a core dependency: a top-level ``from jsonschema import ...`` makes a core
    install fail at import time with a bare ImportError naming a package the
    user never asked for, instead of the typed hint below. ``build_site`` and
    the schema self-check both go through this seam so the failure is at use
    time, naming the extra to install.
    """
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - core install without the extra
        raise SitegenNotInstalledError(_INSTALL_HINT) from exc
    return Draft202012Validator


@dataclass(frozen=True)
class _JoinRow:
    """One extraction-join row, reduced to what page planning needs."""

    skill_name: str
    source_sha256: str


def load_schema(schema_path: Path) -> dict[str, Any]:
    """Parse and self-check the SERS schema."""
    return _parse_schema(schema_path.read_text(encoding="utf-8"))


def load_receipts(schema_path: Path, receipts_dir: Path) -> list[dict[str, Any]]:
    """Load all receipts through the SERS validation gate."""
    return validate_receipts(load_schema(schema_path), receipts_dir)


def validate_receipts(
    schema: Mapping[str, Any],
    receipts_dir: Path,
) -> list[dict[str, Any]]:
    """Validate every receipt in ``receipts_dir``, hard-failing on the first bad one."""
    validator = _validator()(dict(schema))
    loaded: list[dict[str, Any]] = []
    for path in sorted(receipts_dir.glob("*.json")):
        receipt_obj: object = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(receipt_obj)
        if not isinstance(receipt_obj, dict):
            raise SiteBuildError(f"{path}: SERS receipt must be a JSON object")
        loaded.append(receipt_obj)
    _check_carried_forward_immutability(loaded, receipts_dir)
    return loaded


def _check_carried_forward_immutability(
    receipts: list[dict[str, Any]],
    receipts_dir: Path,
) -> None:
    """A CARRIED_FORWARD receipt's verdict_scope must match the original.

    The schema enforces that ``tested_at`` is present, but a schema cannot
    compare two separate files.  This step loads the superseded receipt for
    the same skill and refuses any change to ``verdict_scope`` fields.
    """
    superseded_dir = receipts_dir / "superseded"
    for receipt in receipts:
        currentness = receipt.get("currentness")
        if not isinstance(currentness, Mapping):
            continue
        if currentness.get("state") != "CARRIED_FORWARD":
            continue
        skill_name = receipt.get("skill_name")
        if not isinstance(skill_name, str):
            continue
        scope = receipt.get("verdict_scope")
        if not isinstance(scope, Mapping):
            continue
        # Find the superseded receipt for the same skill.
        if not superseded_dir.is_dir():
            raise SiteBuildError(
                f"CARRIED_FORWARD receipt for {skill_name!r} but no superseded/ "
                "directory exists to carry forward from"
            )
        original: dict[str, Any] | None = None
        for super_path in sorted(superseded_dir.glob("*.json")):
            super_obj = json.loads(super_path.read_text(encoding="utf-8"))
            if isinstance(super_obj, dict) and super_obj.get("skill_name") == skill_name:
                original = super_obj
                break
        if original is None:
            raise SiteBuildError(
                f"CARRIED_FORWARD receipt for {skill_name!r} but no superseded "
                f"receipt found for that skill in {superseded_dir}"
            )
        orig_scope = original.get("verdict_scope")
        if not isinstance(orig_scope, Mapping):
            continue
        # Compare every key present in either scope.
        all_keys = set(scope.keys()) | set(orig_scope.keys())
        for key in sorted(all_keys):
            new_val = scope.get(key)
            old_val = orig_scope.get(key)
            if new_val != old_val:
                raise SiteBuildError(
                    f"CARRIED_FORWARD receipt for {skill_name!r}: "
                    f"verdict_scope.{key} changed from {old_val!r} to "
                    f"{new_val!r}; verdict_scope must not change when "
                    "carrying forward"
                )


def build_site(
    *,
    schema_path: Path,
    receipts_dir: Path,
    extraction_path: Path | None,
    output_dir: Path,
    marker: str,
    base_url: str = DEFAULT_BASE_URL,
    landing: bool = False,
    landing_copy_path: Path | None = None,
    social_image_path: Path | None = None,
    favicon_path: Path | None = None,
) -> tuple[Path, ...]:
    """Render the site, after validating every receipt. Returns the files written.

    ``marker`` is a content marker unique to one build: it is written into every
    page so a deploy can be checked by fetching the published URL, rather than
    inferred from a green workflow.

    ``landing`` defaults to OFF, and that default is the point. A landing page
    amplifies whatever is true, including the parts that are not, so the
    project's own definition of done orders it after claim integrity. The page
    is built, tested and reviewable here; flipping the default is a separate
    one-line change at a moment the owner picks. ``tests/sitegen`` pins the
    default so the ordering rule is held by a machine rather than by memory.

    With ``landing`` off the output is exactly the previous page set plus the
    404 page: ``index.html`` is the receipts index, and both published inbound
    links keep resolving.
    """
    if not marker.strip():
        raise SiteBuildError(
            "a build marker is required: without one a deploy cannot be verified "
            "from the published URL"
        )
    schema_text = schema_path.read_text(encoding="utf-8")
    schema = _parse_schema(schema_text)
    receipts = validate_receipts(schema, receipts_dir)

    landing_copy = None
    if landing:
        path = landing_copy_path if landing_copy_path is not None else DEFAULT_LANDING_COPY
        if not path.is_file():
            raise SiteBuildError(f"landing copy not found at {path}")
        landing_copy = parse_landing(path.read_text(encoding="utf-8"))

    social_bytes: bytes | None = None
    if social_image_path is not None and social_image_path.is_file():
        social_bytes = social_image_path.read_bytes()

    # No icon ships in the tree today. The link is emitted only when the bytes
    # are in the build, because a <link rel="icon"> pointing at a 404 is worse
    # than no icon link: it makes the absence a broken reference instead of an
    # absence. Dropping an SVG at the default path closes it with no code edit.
    favicon_bytes: bytes | None = None
    if favicon_path is not None and favicon_path.is_file():
        favicon_bytes = favicon_path.read_bytes()

    receipts_page = RECEIPTS_PAGE_NAME if landing else INDEX_FILE_NAME
    nav: list[tuple[str, str]] = []
    if landing:
        nav.append((INDEX_FILE_NAME, "Home"))
    nav.append((receipts_page, "Receipts"))
    nav.append((SCHEMA_PAGE_NAME, "How results are reported"))
    shell = SiteShell(
        marker=marker,
        base_url=base_url,
        nav=tuple(nav),
        receipts_href=receipts_page,
        has_social_image=social_bytes is not None,
        has_favicon=favicon_bytes is not None,
    )

    by_skill = _receipts_by_skill(receipts)
    join_rows = _read_join_rows(extraction_path)
    join_skills = sorted({row.skill_name for row in join_rows})
    skill_names = sorted(set(by_skill) | set(join_skills))
    _check_page_names(skill_names)

    pages: dict[str, str] = {
        receipts_page: render_index_page(
            shell=shell,
            page_name=receipts_page,
            receipts=[by_skill[name] for name in sorted(by_skill)],
            unreceipted_skills=[name for name in join_skills if name not in by_skill],
        ),
        SCHEMA_PAGE_NAME: render_schema_page(shell=shell, schema=schema),
        NOT_FOUND_PAGE_NAME: render_not_found_page(shell),
    }
    if landing_copy is not None:
        pages[INDEX_FILE_NAME] = render_landing_page(shell=shell, copy=landing_copy)
    for name in skill_names:
        pages[skill_page_name(name)] = render_skill_page(
            shell=shell,
            skill_name=name,
            receipt=by_skill.get(name),
            evidence=_clause_evidence_for(name, extraction_path, join_rows),
            schema=schema,
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    written = [
        _write(output_dir / STYLESHEET_NAME, read_stylesheet()),
        _write(output_dir / SCHEMA_FILE_NAME, schema_text),
    ]
    if social_bytes is not None:
        social_target = output_dir / SOCIAL_IMAGE_NAME
        social_target.write_bytes(social_bytes)
        written.append(social_target)
    if favicon_bytes is not None:
        favicon_target = output_dir / FAVICON_NAME
        favicon_target.write_bytes(favicon_bytes)
        written.append(favicon_target)
    written.extend(_write(output_dir / name, text) for name, text in sorted(pages.items()))
    return tuple(sorted(written))


def _clause_evidence_for(
    skill_name: str,
    extraction_path: Path | None,
    join_rows: Sequence[_JoinRow],
) -> ClauseEvidenceOutcome:
    """Clause-evidence outcome for one skill, via the audit path's own loader.

    A skill name carrying two different source shas is refused rather than
    resolved: extraction output is not stable across runs, so picking one row
    would publish a grade for an arbitrary version of the skill.
    """
    if extraction_path is None:
        return no_extraction_outcome()
    shas = sorted({row.source_sha256 for row in join_rows if row.skill_name == skill_name})
    if not shas:
        return no_extraction_outcome()
    if len(shas) > 1:
        raise SiteBuildError(
            f"skill {skill_name!r} appears in the join input under {len(shas)} different "
            "source shas; refusing to choose which version to publish"
        )
    return load_clause_evidence(extraction_path, shas[0])


def _parse_schema(schema_text: str) -> dict[str, Any]:
    schema_obj: object = json.loads(schema_text)
    if not isinstance(schema_obj, dict):
        raise SiteBuildError("SERS schema must be a JSON object")
    schema: dict[str, Any] = schema_obj
    _validator().check_schema(schema)
    return schema


def _receipts_by_skill(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_skill: dict[str, Mapping[str, Any]] = {}
    for receipt in receipts:
        name = receipt.get("skill_name")
        if not isinstance(name, str) or not name:
            raise SiteBuildError("receipt carries no skill name")
        if name in by_skill:
            raise SiteBuildError(
                f"two receipts name skill {name!r}; refusing to choose which one to publish"
            )
        by_skill[name] = receipt
    return by_skill


def _read_join_rows(extraction_path: Path | None) -> tuple[_JoinRow, ...]:
    """Skill name and source sha per parseable join row; nothing else is read here.

    Unparseable lines are skipped without comment on purpose: the clause-evidence
    loader counts them and states the count on the page it renders. A row that
    parses but carries no skill name or no sha cannot be attributed to a page and
    is skipped too -- the extraction model requires both fields, so such a row is
    malformed rather than merely old.
    """
    if extraction_path is None or not extraction_path.exists():
        return ()
    rows: list[_JoinRow] = []
    for raw_line in extraction_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row_obj: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row_obj, dict):
            continue
        name = row_obj.get("name")
        sha = row_obj.get("source_sha256")
        if isinstance(name, str) and name and isinstance(sha, str) and sha:
            rows.append(_JoinRow(skill_name=name, source_sha256=sha))
    return tuple(rows)


def _check_page_names(skill_names: Sequence[str]) -> None:
    seen: dict[str, str] = {}
    for name in skill_names:
        page = skill_page_name(name)
        if page in seen:
            raise SiteBuildError(
                f"skills {seen[page]!r} and {name!r} both render to {page}; "
                "refusing to overwrite one skill's page with another's"
            )
        seen[page] = name


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
