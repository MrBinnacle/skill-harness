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
from skill_harness.sitegen.render import (
    INDEX_FILE_NAME,
    SCHEMA_FILE_NAME,
    SCHEMA_PAGE_NAME,
    STYLESHEET_NAME,
    SiteBuildError,
    read_stylesheet,
    render_index_page,
    render_schema_page,
    render_skill_page,
    skill_page_name,
)

__all__ = [
    "SiteBuildError",
    "SitegenNotInstalledError",
    "build_site",
    "load_receipts",
    "load_schema",
]


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
    return loaded


def build_site(
    *,
    schema_path: Path,
    receipts_dir: Path,
    extraction_path: Path | None,
    output_dir: Path,
    marker: str,
) -> tuple[Path, ...]:
    """Render the site, after validating every receipt. Returns the files written.

    ``marker`` is a content marker unique to one build: it is written into every
    page so a deploy can be checked by fetching the published URL, rather than
    inferred from a green workflow.
    """
    if not marker.strip():
        raise SiteBuildError(
            "a build marker is required: without one a deploy cannot be verified "
            "from the published URL"
        )
    schema_text = schema_path.read_text(encoding="utf-8")
    schema = _parse_schema(schema_text)
    receipts = validate_receipts(schema, receipts_dir)

    by_skill = _receipts_by_skill(receipts)
    join_rows = _read_join_rows(extraction_path)
    join_skills = sorted({row.skill_name for row in join_rows})
    skill_names = sorted(set(by_skill) | set(join_skills))
    _check_page_names(skill_names)

    pages: dict[str, str] = {
        INDEX_FILE_NAME: render_index_page(
            receipts=[by_skill[name] for name in sorted(by_skill)],
            unreceipted_skills=[name for name in join_skills if name not in by_skill],
            marker=marker,
        ),
        SCHEMA_PAGE_NAME: render_schema_page(schema=schema, marker=marker),
    }
    for name in skill_names:
        pages[skill_page_name(name)] = render_skill_page(
            skill_name=name,
            receipt=by_skill.get(name),
            evidence=_clause_evidence_for(name, extraction_path, join_rows),
            schema=schema,
            marker=marker,
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    written = [
        _write(output_dir / STYLESHEET_NAME, read_stylesheet()),
        _write(output_dir / SCHEMA_FILE_NAME, schema_text),
    ]
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
