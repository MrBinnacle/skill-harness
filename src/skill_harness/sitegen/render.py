"""HTML rendering for the published receipts site (#186).

Pure functions: data in, markup out. No filesystem writes, no network, no
template engine -- ``string.Template`` over the ``.html`` files in
``templates/``, so the site's prose lives in files the public-surface copy guard
already scans (``tests/test_structural_bans.py`` reads
``src/skill_harness/sitegen/**`` for template suffixes).

Two invariants this module exists to hold:

1. Every figure on a page is either copied from the receipt or produced by the
   clause-evidence loader. There is no code path here that can emit a number of
   its own: a leg carrying neither a measured value nor a typed refusal raises
   ``SiteBuildError`` instead of rendering something plausible.
2. A refusal is primary content. Refusal lines from the clause-evidence loader
   are rendered verbatim, in document order, never dimmed or footnoted.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from string import Template
from typing import Any, Final

from skill_harness.extractor.clause_evidence import (
    SECTION_TITLE,
    ClauseEvidenceOutcome,
    format_instrument_line,
    format_refusal_line,
    format_summary_lines,
    format_unparseable_warning,
)

_PACKAGE: Final[str] = "skill_harness.sitegen"

STYLESHEET_NAME: Final[str] = "style.css"
SCHEMA_FILE_NAME: Final[str] = "sers.schema.json"
INDEX_FILE_NAME: Final[str] = "index.html"
SCHEMA_PAGE_NAME: Final[str] = "schema.html"

#: Rendered in place of an optional key the receipt does not carry. Never a
#: number, never a zero: an absent figure is stated as absent.
ABSENT_TEXT: Final[str] = "absent from this receipt"
NO_QUALIFIER_TEXT: Final[str] = "none stated"

_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


class SiteBuildError(Exception):
    """Raised when a page cannot be written without inventing a figure."""


@dataclass(frozen=True)
class Figure:
    """One rendered figure: a measured value or a typed refusal, plus detail."""

    text: str
    detail: str
    refused: bool


def safe(text: str) -> str:
    """Escape ``text`` for HTML after refusing control characters.

    Same output-side discipline as the CLI's Rich escaper, for a different
    channel: untrusted extractor output (axis names, refusal reasons, clause
    text) reaches this markup, so it is escaped, and a control character is a
    refusal rather than something to smuggle into a published page.
    """
    for ch in text:
        cp = ord(ch)
        if cp == 0 or (cp < 0x20 and cp not in (0x09, 0x0A, 0x0D)):
            raise SiteBuildError(
                f"text contains control character U+{cp:04X} -- "
                "refusing to publish untrusted content"
            )
    return html.escape(text, quote=True)


def skill_page_name(skill_name: str) -> str:
    """File name for one skill's page. Refuses a name with no slug."""
    slug = _SLUG_RE.sub("-", skill_name.lower()).strip("-")
    if not slug:
        raise SiteBuildError(f"skill name {skill_name!r} has no renderable page name")
    return f"skill-{slug}.html"


def read_stylesheet() -> str:
    """The one hand-written stylesheet, copied verbatim into the output."""
    return _package_text(STYLESHEET_NAME)


# ---------------------------------------------------------------------------
# Figures: measured value or typed refusal, never anything else
# ---------------------------------------------------------------------------


def token_figure(leg: str, figure: Mapping[str, Any]) -> Figure:
    """Render one SERS ``token_figure`` leg of the cost triple."""
    tokens = figure.get("tokens")
    if isinstance(tokens, bool):
        raise SiteBuildError(f"cost leg {leg!r} carries a boolean where a token count belongs")
    if isinstance(tokens, int):
        return Figure(text=f"{tokens} tokens", detail=_detail(figure), refused=False)
    refusal = figure.get("refusal")
    if isinstance(refusal, str):
        return Figure(text=f"REFUSED ({refusal})", detail=_detail(figure), refused=True)
    raise SiteBuildError(
        f"cost leg {leg!r} carries neither a token count nor a typed refusal; "
        "refusing to render a figure for it"
    )


def rate_figure(key: str, figure: Mapping[str, Any]) -> Figure:
    """Render one SERS ``rate_or_refusal`` measurement."""
    value = figure.get("value")
    if isinstance(value, bool):
        raise SiteBuildError(f"measurement {key!r} carries a boolean where a rate belongs")
    if isinstance(value, int | float):
        return Figure(text=_rate_text(value, figure), detail=_detail(figure), refused=False)
    refusal = figure.get("refusal")
    if isinstance(refusal, str):
        return Figure(text=f"REFUSED ({refusal})", detail=_detail(figure), refused=True)
    raise SiteBuildError(
        f"measurement {key!r} carries neither a value nor a typed refusal; "
        "refusing to render a figure for it"
    )


def _rate_text(value: float, figure: Mapping[str, Any]) -> str:
    text = str(value)
    passes = figure.get("passes")
    epochs = figure.get("epochs")
    if (
        isinstance(passes, int)
        and not isinstance(passes, bool)
        and isinstance(epochs, int)
        and not isinstance(epochs, bool)
    ):
        return f"{text} ({passes}/{epochs} epochs)"
    return text


def _detail(figure: Mapping[str, Any]) -> str:
    detail = figure.get("detail")
    return detail if isinstance(detail, str) else ""


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def render_page(*, title: str, heading: str, body: str, marker: str) -> str:
    """Wrap a rendered body fragment in the site shell."""
    return _template("page.html").substitute(
        title=safe(title),
        heading=safe(heading),
        body=body,
        marker=safe(marker),
    )


def render_index_page(
    *,
    receipts: Sequence[Mapping[str, Any]],
    unreceipted_skills: Sequence[str],
    marker: str,
) -> str:
    """The receipts index: one row per validated receipt."""
    rows = [_index_row(receipt) for receipt in receipts]
    unreceipted = ""
    if unreceipted_skills:
        items = [
            f'<li><a href="{safe(skill_page_name(name))}">{safe(name)}</a></li>'
            for name in unreceipted_skills
        ]
        unreceipted = _template("index_unreceipted.html").substitute(rows=_indent(items, 10))
    body = _template("index.html").substitute(
        receipt_count=len(receipts),
        receipt_rows=_indent(rows, 10),
        unreceipted=unreceipted,
    )
    return render_page(
        title="Published receipts",
        heading="Published receipts",
        body=body,
        marker=marker,
    )


def render_schema_page(*, schema: Mapping[str, Any], marker: str) -> str:
    """The reporting-standard page, derived from the schema itself."""
    required = _string_list(schema.get("required"))
    required_rows = [f"<li><code>{safe(name)}</code></li>" for name in required]
    vocabulary_tables = [
        _vocabulary_section(name, subschema) for name, subschema in _vocabularies(schema)
    ]
    title = _string_field(schema, "title", "Reporting standard")
    body = _template("schema.html").substitute(
        description=safe(_string_field(schema, "description", "")),
        required_rows=_indent(required_rows, 8),
        vocabulary_tables="".join(vocabulary_tables),
    )
    return render_page(title=title, heading=title, body=body, marker=marker)


def render_skill_page(
    *,
    skill_name: str,
    receipt: Mapping[str, Any] | None,
    evidence: ClauseEvidenceOutcome,
    schema: Mapping[str, Any],
    marker: str,
) -> str:
    """One skill page: cost triple beside the clause-level evidence grade."""
    clause_evidence = render_clause_evidence(evidence)
    if receipt is None:
        body = _template("skill_no_receipt.html").substitute(clause_evidence=clause_evidence)
    else:
        body = _template("skill.html").substitute(
            verdict=safe(_string_field(receipt, "verdict", "")),
            cut_sub_reason=safe(_nullable_text(receipt.get("cut_sub_reason"))),
            unmeasured_sub_reason=safe(_nullable_text(receipt.get("unmeasured_sub_reason"))),
            value_class=safe(_nullable_text(receipt.get("value_class"))),
            wrong_instrument=safe(_nullable_text(receipt.get("wrong_instrument"))),
            declared_synthetic_control=safe(
                _nullable_text(receipt.get("declared_synthetic_control"))
            ),
            summary=safe(_string_field(receipt, "summary", "")),
            cost_rows=_indent(_cost_rows(receipt), 14),
            clause_evidence=clause_evidence,
            measurement_rows=_indent(_measurement_rows(receipt, schema), 12),
            gate_status=safe(_gate_status(receipt)),
            gate_detail=safe(_gate_detail(receipt)),
            instrument_rows=_indent(_identity_rows(receipt), 10),
            source_rows=_indent(_source_rows(receipt), 10),
        )
    return render_page(
        title=f"{skill_name}: receipt",
        heading=skill_name,
        body=body,
        marker=marker,
    )


def render_clause_evidence(outcome: ClauseEvidenceOutcome) -> str:
    """Clause-level evidence, or the loader's refusal line verbatim."""
    parts: list[str] = []
    if outcome.kind != "measured" or outcome.measured is None:
        parts.append(f'<p class="refusal">{safe(format_refusal_line(outcome))}</p>')
        if outcome.unparseable_line_count and outcome.kind != "unreadable_extraction_file":
            parts.append(
                f'<p class="refusal">'
                f"{safe(format_unparseable_warning(outcome.unparseable_line_count))}</p>"
            )
        return _indent(parts, 12)

    measured = outcome.measured
    parts.append(f"<p>{safe(SECTION_TITLE)}</p>")
    parts.append(f'<p class="instrument">{safe(format_instrument_line(measured.instrument))}</p>')
    clause_rows = [
        _clause_row(
            (
                str(row.clause_index),
                row.axis,
                "yes" if row.scoreable else "no",
                row.vacuity_flag,
                row.flag_evidence_status,
                row.kind_evidence_status,
                _nullable_text(row.adjudicated_vacuity_kind),
                "yes" if row.constructible_fc else "no",
            )
        )
        for row in measured.rows
    ]
    parts.append(
        '<table class="clauses"><caption>Clauses</caption><thead><tr>'
        '<th scope="col">#</th><th scope="col">Axis</th><th scope="col">Scoreable</th>'
        '<th scope="col">Vacuity flag</th><th scope="col">Flag evidence</th>'
        '<th scope="col">Kind evidence</th><th scope="col">Adjudicated kind</th>'
        '<th scope="col">Falsifying case</th>'
        f"</tr></thead><tbody>{''.join(clause_rows)}</tbody></table>"
    )
    summary_items = [f"<li>{safe(line)}</li>" for line in format_summary_lines(measured.summary)]
    parts.append(f'<ul class="summary-lines">{"".join(summary_items)}</ul>')
    if outcome.unparseable_line_count:
        parts.append(
            f'<p class="refusal">'
            f"{safe(format_unparseable_warning(outcome.unparseable_line_count))}</p>"
        )
    return _indent(parts, 12)


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def _index_row(receipt: Mapping[str, Any]) -> str:
    name = _string_field(receipt, "skill_name", "")
    href = safe(skill_page_name(name))
    source = receipt.get("source")
    prose = ""
    if isinstance(source, Mapping):
        prose = _string_field(source, "prose_path", "")
    return (
        f'<tr><th scope="row"><a href="{href}">{safe(name)}</a></th>'
        f'<td><span class="verdict-token">{safe(_string_field(receipt, "verdict", ""))}</span></td>'
        f"<td>{safe(_qualifier_text(receipt))}</td>"
        f"<td>{safe(_gate_status(receipt))}</td>"
        f"<td><code>{safe(prose)}</code></td></tr>"
    )


def _qualifier_text(receipt: Mapping[str, Any]) -> str:
    parts: list[str] = []
    cut = receipt.get("cut_sub_reason")
    if isinstance(cut, str):
        parts.append(f"cut: {cut}")
    unmeasured = receipt.get("unmeasured_sub_reason")
    if isinstance(unmeasured, str):
        parts.append(f"unmeasured: {unmeasured}")
    return ", ".join(parts) if parts else NO_QUALIFIER_TEXT


def _cost_rows(receipt: Mapping[str, Any]) -> list[str]:
    cost = receipt.get("cost")
    if not isinstance(cost, Mapping):
        raise SiteBuildError("receipt carries no cost triple")
    rows: list[str] = []
    for leg in ("standing_tokens", "fired_tokens", "aux_tokens"):
        raw = cost.get(leg)
        if not isinstance(raw, Mapping):
            raise SiteBuildError(f"cost triple is missing leg {leg!r}")
        rows.append(_figure_row(leg, token_figure(leg, raw)))
    return rows


def _measurement_rows(receipt: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    present = receipt.get("measurements")
    measurements: Mapping[str, Any] = present if isinstance(present, Mapping) else {}
    rows: list[str] = []
    for key in _measurement_keys(schema):
        raw = measurements.get(key)
        if raw is None:
            rows.append(
                f'<tr><th scope="row">{safe(key)}</th>'
                f'<td class="absent">{safe(ABSENT_TEXT)}</td><td></td></tr>'
            )
        elif isinstance(raw, Mapping):
            rows.append(_figure_row(key, rate_figure(key, raw)))
        elif isinstance(raw, str):
            rows.append(_figure_row(key, Figure(text=raw, detail="", refused=False)))
        else:
            raise SiteBuildError(f"measurement {key!r} is neither a figure nor a stated gate")
    return rows


def _figure_row(label: str, figure: Figure) -> str:
    css = "figure refused" if figure.refused else "figure"
    return (
        f'<tr><th scope="row">{safe(label)}</th>'
        f'<td class="{css}">{safe(figure.text)}</td>'
        f"<td>{safe(figure.detail)}</td></tr>"
    )


def _clause_row(cells: Sequence[str]) -> str:
    return "<tr>" + "".join(f"<td>{safe(cell)}</td>" for cell in cells) + "</tr>"


def _identity_rows(receipt: Mapping[str, Any]) -> list[str]:
    identity = receipt.get("instrument_identity")
    if not isinstance(identity, Mapping):
        raise SiteBuildError("receipt carries no instrument identity")
    rows: list[str] = []
    for key in ("extractor_model", "prompt_fingerprint", "schema_fingerprint"):
        value = identity.get(key)
        text = value if isinstance(value, str) else ABSENT_TEXT
        rows.append(f"<dt>{safe(key)}</dt><dd><code>{safe(text)}</code></dd>")
    return rows


def _source_rows(receipt: Mapping[str, Any]) -> list[str]:
    source = receipt.get("source")
    if not isinstance(source, Mapping):
        raise SiteBuildError("receipt carries no source of record")
    rows: list[str] = []
    for key in ("prose_path", "date", "notes"):
        value = source.get(key)
        if isinstance(value, str):
            rows.append(f"<dt>{safe(key)}</dt><dd>{safe(value)}</dd>")
        else:
            rows.append(f'<dt>{safe(key)}</dt><dd class="absent">{safe(ABSENT_TEXT)}</dd>')
    return rows


def _gate_status(receipt: Mapping[str, Any]) -> str:
    gate = receipt.get("evidence_admissibility")
    if not isinstance(gate, Mapping):
        raise SiteBuildError("receipt carries no evidence admissibility ruling")
    status = gate.get("status")
    if not isinstance(status, str):
        raise SiteBuildError("evidence admissibility ruling carries no status")
    return status


def _gate_detail(receipt: Mapping[str, Any]) -> str:
    gate = receipt.get("evidence_admissibility")
    if not isinstance(gate, Mapping):
        raise SiteBuildError("receipt carries no evidence admissibility ruling")
    detail = gate.get("detail")
    return detail if isinstance(detail, str) else ABSENT_TEXT


# ---------------------------------------------------------------------------
# Schema-derived vocabulary
# ---------------------------------------------------------------------------


def _measurement_keys(schema: Mapping[str, Any]) -> tuple[str, ...]:
    properties = _sub(schema, "properties")
    measurements = _sub(properties, "measurements")
    keys = _sub(measurements, "properties")
    return tuple(str(key) for key in keys)


def _vocabularies(schema: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    found: list[tuple[str, Mapping[str, Any]]] = []
    for name, subschema in _sub(schema, "properties").items():
        if isinstance(subschema, Mapping) and isinstance(subschema.get("enum"), list):
            found.append((str(name), subschema))
        if isinstance(subschema, Mapping) and isinstance(subschema.get("properties"), Mapping):
            for nested_name, nested in subschema["properties"].items():
                if isinstance(nested, Mapping) and isinstance(nested.get("enum"), list):
                    found.append((f"{name}.{nested_name}", nested))
    for def_name, definition in _sub(schema, "$defs").items():
        if not isinstance(definition, Mapping):
            continue
        for branch in definition.get("oneOf", []):
            if not isinstance(branch, Mapping):
                continue
            properties = branch.get("properties")
            if not isinstance(properties, Mapping):
                continue
            refusal = properties.get("refusal")
            if isinstance(refusal, Mapping) and isinstance(refusal.get("enum"), list):
                found.append((f"{def_name}.refusal", refusal))
    return found


def _vocabulary_section(name: str, subschema: Mapping[str, Any]) -> str:
    values = [
        f"<li><code>{safe('null' if value is None else str(value))}</code></li>"
        for value in _enum_values(subschema)
    ]
    return _template("schema_vocabulary.html").substitute(
        name=safe(name),
        description=safe(_string_field(subschema, "description", "")),
        values=_indent(values, 10),
    )


def _enum_values(subschema: Mapping[str, Any]) -> list[Any]:
    enum = subschema.get("enum")
    return list(enum) if isinstance(enum, list) else []


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _sub(node: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = node.get(key)
    if not isinstance(value, Mapping):
        raise SiteBuildError(f"schema is missing the {key!r} object")
    return value


def _string_field(node: Mapping[str, Any], key: str, default: str) -> str:
    value = node.get(key)
    return value if isinstance(value, str) else default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _nullable_text(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _indent(fragments: Iterable[str], columns: int) -> str:
    pad = " " * columns
    return "\n".join(f"{pad}{fragment}" for fragment in fragments)


def _template(name: str) -> Template:
    return Template(_package_text(f"templates/{name}"))


def _package_text(relative: str) -> str:
    resource = resources.files(_PACKAGE)
    for part in relative.split("/"):
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")
