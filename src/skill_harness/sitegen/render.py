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
#: Where the receipts index is written when the landing page takes ``index.html``.
RECEIPTS_PAGE_NAME: Final[str] = "receipts.html"
NOT_FOUND_PAGE_NAME: Final[str] = "404.html"
SOCIAL_IMAGE_NAME: Final[str] = "social-preview.png"

#: The address a stranger is sent to. Every absolute URL on the site is composed
#: from this, never written as a literal, so moving to a custom domain later is
#: one build argument rather than a code change.
DEFAULT_BASE_URL: Final[str] = "https://mrbinnacle.github.io/skill-harness/"

#: The nav in the flag-off state, which is what the site publishes today. With
#: the landing page on, ``build_site`` passes a nav with a home item ahead of
#: these two and the receipts item pointing at ``receipts.html``.
DEFAULT_NAV: Final[tuple[tuple[str, str], ...]] = (
    (INDEX_FILE_NAME, "Receipts"),
    (SCHEMA_PAGE_NAME, "How results are reported"),
)

#: Written into ``<link rel="icon">`` when an icon file is supplied to the
#: build. ``assets/favicon.svg`` ships in the tree since S456, so every page of
#: a default build links one. The link is still emitted only when the bytes
#: exist, because a 404ing icon link is worse than no icon link.
FAVICON_NAME: Final[str] = "favicon.svg"

#: Rendered in place of an optional key the receipt does not carry. Never a
#: number, never a zero: an absent figure is stated as absent.
ABSENT_TEXT: Final[str] = "absent from this receipt"
NO_QUALIFIER_TEXT: Final[str] = "none stated"

_DELIVERY_CHANNEL_TEXT: Final[dict[str, str]] = {
    "description_only": (
        "The standing description carried the value; the skill body was never read."
    ),
    "body_and_description": ("The skill body was read in addition to the standing description."),
    "not_instrumented": ("No delivery detector was present; channel is not instrumented."),
}

_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")

_ISO_DATE_RE: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}")

#: The one construction a SERS field description uses to name a word for its
#: null case, as in ``value_class``'s "null = unclassified." Anything looser
#: would start turning sentences into labels (#583).
_NULL_LANGUAGE_RE: Final[re.Pattern[str]] = re.compile(r"\bnull\s*=\s*(?P<word>[^.;\n]+)")


class SiteBuildError(Exception):
    """Raised when a page cannot be written without inventing a figure."""


@dataclass(frozen=True)
class Figure:
    """One rendered figure: a measured value or a typed refusal, plus detail.

    ``machine_value`` carries the bare number a measured figure displays, so the
    markup can state it as ``<data value="...">``. This page's whole product is
    machine-checkable claims, so the machine value and the displayed value both
    belong in the DOM. A refusal has no machine value and carries the empty
    string, which is what keeps a refusal out of ``<data>`` entirely.
    """

    text: str
    detail: str
    refused: bool
    machine_value: str = ""


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
        return Figure(
            text=f"{tokens} tokens",
            detail=_detail(figure),
            refused=False,
            machine_value=str(tokens),
        )
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
        return Figure(
            text=_rate_text(value, figure),
            detail=_detail(figure),
            refused=False,
            machine_value=str(value),
        )
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


@dataclass(frozen=True)
class SiteShell:
    """What every page's head, nav and footer need, fixed once per build.

    ``nav`` is a sequence of (href, label). It differs between the two flag
    states, which is why the nav is data rather than markup in the template, and
    it is what supplies the page identity ``aria-current`` needs. One change,
    two fixes: the current-page marker has been open as DESIGN.md Known
    Divergence 7 since #308.

    Every field except ``marker`` carries the flag-off default, so a caller that
    only has a marker (the page-level unit tests, and any future one-page render)
    builds a valid shell without restating the whole site. ``build_site`` passes
    all of them.
    """

    marker: str
    base_url: str = DEFAULT_BASE_URL
    nav: tuple[tuple[str, str], ...] = DEFAULT_NAV
    receipts_href: str = INDEX_FILE_NAME
    has_social_image: bool = False
    has_favicon: bool = False

    def url_for(self, page_name: str) -> str:
        """The absolute URL of one page, composed from ``base_url``.

        ``index.html`` resolves to the bare directory URL, which is the address
        the two published inbound links already point at.
        """
        base = self.base_url if self.base_url.endswith("/") else f"{self.base_url}/"
        return base if page_name == INDEX_FILE_NAME else f"{base}{page_name}"


def _shell_for(shell: SiteShell | None, marker: str | None) -> SiteShell:
    """One shell from whichever of the two the caller supplied.

    Exactly one is required. Accepting both would let a caller pass a marker
    that the shell contradicts, and the marker is the string a deploy is
    verified against, so two sources for it is the one ambiguity worth refusing.
    """
    if shell is not None and marker is not None:
        raise SiteBuildError("pass either a shell or a marker, not both")
    if shell is not None:
        return shell
    if marker is None:
        raise SiteBuildError("rendering a page needs a shell or a build marker")
    return SiteShell(marker=marker)


def render_page(
    *,
    shell: SiteShell,
    page_name: str,
    title: str,
    heading: str,
    description: str,
    body: str,
    body_class: str = "",
    footer: bool = True,
) -> str:
    """Wrap a rendered body fragment in the site shell.

    ``footer`` carries the visible build-marker line. It stays on the evidence
    pages, where the string is a real identifier a reader can check a deploy
    against, and comes off the landing page, where a version footer is marketing
    furniture. The ``<meta name="skill-harness-build">`` marker is on every page
    either way, and that meta tag is what the deploy verification greps.
    """
    nav_items = [
        (
            f'<li><a href="{safe(href)}"'
            f"{' aria-current="page"' if href == page_name else ''}"
            f">{safe(label)}</a></li>"
        )
        for href, label in shell.nav
    ]
    social_image = ""
    if shell.has_social_image:
        url = safe(shell.url_for(SOCIAL_IMAGE_NAME))
        social_image = f'    <meta property="og:image" content="{url}" />'
    # Emitted only when the icon bytes are in the build. No icon ships in the
    # tree today, so today every page renders this as the empty string.
    favicon_link = ""
    if shell.has_favicon:
        favicon_link = f'    <link rel="icon" href="{safe(FAVICON_NAME)}" />'
    return _template("page.html").substitute(
        title=safe(title),
        heading=safe(heading),
        description=safe(description),
        canonical_url=safe(shell.url_for(page_name)),
        favicon_link=favicon_link,
        social_image=social_image,
        nav_items=_indent(nav_items, 10),
        body_class=f' class="{safe(body_class)}"' if body_class else "",
        body=body,
        footer=_template("footer.html").substitute(marker=safe(shell.marker)) if footer else "",
        marker=safe(shell.marker),
    )


def render_not_found_page(shell: SiteShell) -> str:
    """The page GitHub Pages serves for an address that is not on the site."""
    body = _template("not_found.html").substitute(receipts_href=safe(shell.receipts_href))
    return render_page(
        shell=shell,
        page_name=NOT_FOUND_PAGE_NAME,
        title="Page not found",
        heading="Page not found",
        description="This page is not on the skill-harness receipts site.",
        body=body,
    )


def render_index_page(
    *,
    shell: SiteShell,
    page_name: str,
    receipts: Sequence[Mapping[str, Any]],
    unreceipted_skills: Sequence[str],
) -> str:
    """The receipts index: one row per validated receipt.

    A build with no receipt renders a refusal block instead of an empty table.
    A table with no rows and a measured zero look alike on a screen and mean
    different things, so the page says which one this is.
    """
    if receipts:
        receipts_section = _template("index_table.html").substitute(
            receipt_count=len(receipts),
            receipt_rows=_indent([_index_row(receipt) for receipt in receipts], 10),
        )
    else:
        receipts_section = _package_text("templates/index_no_receipts.html")
    unreceipted = ""
    if unreceipted_skills:
        items = [
            f'<li><a href="{safe(skill_page_name(name))}">{safe(name)}</a></li>'
            for name in unreceipted_skills
        ]
        unreceipted = _template("index_unreceipted.html").substitute(rows=_indent(items, 10))
    body = _template("index.html").substitute(
        receipts_section=receipts_section,
        unreceipted=unreceipted,
    )
    return render_page(
        shell=shell,
        page_name=page_name,
        title="Published receipts",
        heading="Published receipts",
        description=(
            "Published SERS receipts: one page per screened skill, the cost triple beside "
            "the clause-level evidence grade, every figure copied from the receipt."
        ),
        body=body,
    )


def render_schema_page(*, shell: SiteShell, schema: Mapping[str, Any]) -> str:
    """The reporting-standard page, derived from the schema itself."""
    required = _string_list(schema.get("required"))
    required_rows = [f"<li><code>{safe(name)}</code></li>" for name in required]
    vocabulary_tables = [
        _vocabulary_section(name, subschema) for name, subschema in _vocabularies(schema)
    ]
    title = _string_field(schema, "title", "How results are reported")
    body = _template("schema.html").substitute(
        description=safe(_string_field(schema, "description", "")),
        required_rows=_indent(required_rows, 8),
        vocabulary_tables="".join(vocabulary_tables),
    )
    return render_page(
        shell=shell,
        page_name=SCHEMA_PAGE_NAME,
        title=title,
        heading=title,
        description=(
            "The reporting standard the published receipts validate against, with every "
            "closed vocabulary the schema fixes."
        ),
        body=body,
    )


def render_skill_page(
    *,
    skill_name: str,
    receipt: Mapping[str, Any] | None,
    evidence: ClauseEvidenceOutcome,
    schema: Mapping[str, Any],
    shell: SiteShell | None = None,
    marker: str | None = None,
) -> str:
    """One skill page: cost triple beside the clause-level evidence grade.

    Takes either a ``shell``, which is what ``build_site`` passes, or a bare
    ``marker``, which is what a caller rendering one page in isolation has. The
    marker form builds the flag-off shell, so a single page renders with the
    site's real nav and head rather than a stub.
    """
    shell = _shell_for(shell, marker)
    clause_evidence = render_clause_evidence(evidence)
    if receipt is None:
        body = _template("skill_no_receipt.html").substitute(clause_evidence=clause_evidence)
    else:
        body = _template("skill.html").substitute(
            verdict=safe(_string_field(receipt, "verdict", "")),
            qualifier_rows=_indent(_qualifier_rows(receipt, schema), 8),
            summary=safe(_string_field(receipt, "summary", "")),
            cost_rows=_indent(_cost_rows(receipt, schema), 14),
            clause_evidence=clause_evidence,
            measurement_rows=_indent(_measurement_rows(receipt, schema), 12),
            delivery_section=_delivery_section(receipt),
            gate_status=safe(_gate_status(receipt)),
            gate_detail=safe(_gate_detail(receipt)),
            instrument_rows=_indent(_identity_rows(receipt), 10),
            source_rows=_indent(_source_rows(receipt, schema), 10),
            subject_identity_section=_subject_identity_section(receipt),
            verdict_scope_section=_verdict_scope_section(receipt),
            currentness_section=_currentness_section(receipt),
        )
    return render_page(
        shell=shell,
        page_name=skill_page_name(skill_name),
        title=f"{skill_name}: receipt",
        heading=skill_name,
        description=(
            f"The published receipt for {skill_name}: verdict, cost triple, measured values "
            "and typed refusals, with the source of record."
        ),
        body=body,
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
                (str(row.clause_index), ""),
                (row.axis, ""),
                ("yes" if row.scoreable else "no", ""),
                (row.vacuity_flag, ""),
                (row.flag_evidence_status, ""),
                (row.kind_evidence_status, ""),
                # No adjudication on file is an absence, and it wears the same
                # marker every other absence on the site wears (#583).
                (
                    (row.adjudicated_vacuity_kind, "")
                    if row.adjudicated_vacuity_kind is not None
                    else (ABSENT_TEXT, "absent")
                ),
                ("yes" if row.constructible_fc else "no", ""),
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


def schema_properties(schema: Mapping[str, Any], group: str) -> Mapping[str, Any]:
    """The ``properties`` map for one receipt group, or an empty map."""
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return {}
    node = properties.get(group)
    if not isinstance(node, Mapping):
        return {}
    nested = node.get("properties")
    return nested if isinstance(nested, Mapping) else {}


def schema_label(properties: Mapping[str, Any], key: str) -> str:
    """One row label: the schema's own words for the key, then the key itself.

    This is #583's rule one layer out. A raw schema key is not a human label,
    and the page does not paraphrase one into a label either. It prints what the
    schema already says about the field, whole and unedited, and keeps the raw
    key beside it in ``<code>`` so the page stays greppable by key.

    A description is rendered entire, punctuation included. Trimming a sentence
    to label length is a rewrite, and a rewrite is the thing being refused.
    Where the schema states neither a ``title`` nor a ``description``, the raw
    key stands alone, which is the honest result: the language belongs in the
    schema, not in a word this page made up for it.
    """
    gloss = ""
    field = properties.get(key)
    if isinstance(field, Mapping):
        for source in ("title", "description"):
            value = field.get(source)
            if isinstance(value, str) and value.strip():
                gloss = value.strip()
                break
    code = f"<code>{safe(key)}</code>"
    if not gloss:
        return code
    return f'<span class="key-gloss">{safe(gloss)}</span>{code}'


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


#: The column label each body cell carries in ``data-label``.
#:
#: Below 40rem the receipts index and the measurements table stop being tables
#: and become one labelled block per row (S456 defect 3: with the word breaking
#: repaired, the five-column index needs 531px and a 360px viewport leaves 328).
#: The stylesheet prints the label from this attribute, so the label a narrow
#: reader sees is markup rather than copy invented in CSS. It prints the
#: attribute whole and adds no separator, because a separator written in CSS
#: would be the same copy-outside-the-gate this attribute exists to avoid.
#:
#: These strings repeat the ``<th scope="col">`` text in the templates, and the
#: duplication is deliberate rather than unnoticed: the header row is written in
#: HTML and the body rows are written here.
#: ``test_site_viewport_S456.py`` asserts the two sets are equal, so the copy
#: cannot drift in one place without a red suite.
INDEX_COLUMN_LABELS: Final[tuple[str, ...]] = (
    "Verdict",
    "Refusal qualifier",
    "Evidence admissibility",
    "Source of record",
)

#: The same, for the cost triple and the measurements table. Both carry a row
#: header and then these two columns.
FIGURE_COLUMN_LABELS: Final[tuple[str, ...]] = ("Figure", "Detail")


def _index_row(receipt: Mapping[str, Any]) -> str:
    name = _string_field(receipt, "skill_name", "")
    href = safe(skill_page_name(name))
    source = receipt.get("source")
    prose = ""
    if isinstance(source, Mapping):
        prose = _string_field(source, "prose_path", "")
    verdict, qualifier, gate, record = (safe(label) for label in INDEX_COLUMN_LABELS)
    return (
        f'<tr><th scope="row"><a href="{href}">{safe(name)}</a></th>'
        f'<td data-label="{verdict}"><span class="verdict-token">'
        f"{safe(_string_field(receipt, 'verdict', ''))}</span></td>"
        f'<td data-label="{qualifier}">{safe(_qualifier_text(receipt))}</td>'
        f'<td data-label="{gate}">{safe(_gate_status(receipt))}</td>'
        f'<td data-label="{record}"><code>{safe(prose)}</code></td></tr>'
    )


#: The five qualifiers a receipt page states under its verdict, as
#: (human label, receipt key). The labels are the page's own, not schema keys:
#: the schema declares no ``title`` for any of them.
_QUALIFIERS: Final[tuple[tuple[str, str], ...]] = (
    ("Cut sub-reason", "cut_sub_reason"),
    ("Unmeasured sub-reason", "unmeasured_sub_reason"),
    ("Value class", "value_class"),
    ("Wrong instrument", "wrong_instrument"),
    ("Declared synthetic control", "declared_synthetic_control"),
)


def nullable_cell(schema: Mapping[str, Any], key: str, value: object) -> tuple[str, str]:
    """Render one nullable receipt field as (text, css class).

    Three cases, and none of them invents a word (#583):

    - a boolean is an answer the receipt carries, so it renders ``yes`` or
      ``no``, which is that answer in plain language;
    - a ``None`` whose schema field names a word for its null case renders that
      word;
    - anything else absent renders ``ABSENT_TEXT`` in the ``absent`` class, the
      same treatment the measurements table has given a missing key since #186,
      so a reader meets one vocabulary for absence across the whole page.
    """
    if isinstance(value, bool):
        return ("yes" if value else "no", "")
    if value is None:
        declared = null_case_language(schema, key)
        if declared is not None:
            return (declared, "")
        return (ABSENT_TEXT, "absent")
    return (str(value), "")


def _qualifier_rows(receipt: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    rows: list[str] = []
    for label, key in _QUALIFIERS:
        text, css = nullable_cell(schema, key, receipt.get(key))
        attribute = f' class="{css}"' if css else ""
        rows.append(f"<dt>{safe(label)}</dt><dd{attribute}>{safe(text)}</dd>")
    return rows


def _qualifier_text(receipt: Mapping[str, Any]) -> str:
    parts: list[str] = []
    cut = receipt.get("cut_sub_reason")
    if isinstance(cut, str):
        parts.append(f"cut: {cut}")
    unmeasured = receipt.get("unmeasured_sub_reason")
    if isinstance(unmeasured, str):
        parts.append(f"unmeasured: {unmeasured}")
    return ", ".join(parts) if parts else NO_QUALIFIER_TEXT


def _cost_rows(receipt: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    """The cost triple, with each leg labelled in the schema's own words.

    The schema states neither a title nor a description for any of the three
    legs as of this pass, so all three render as the bare key. That is the
    result, not a gap the page papers over: inventing the language here would
    put a word on the site that no receipt can be checked against.
    """
    cost = receipt.get("cost")
    if not isinstance(cost, Mapping):
        raise SiteBuildError("receipt carries no cost triple")
    properties = schema_properties(schema, "cost")
    rows: list[str] = []
    for leg in ("standing_tokens", "fired_tokens", "aux_tokens"):
        raw = cost.get(leg)
        if not isinstance(raw, Mapping):
            raise SiteBuildError(f"cost triple is missing leg {leg!r}")
        rows.append(_figure_row(schema_label(properties, leg), token_figure(leg, raw)))
    return rows


def _measurement_rows(receipt: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    present = receipt.get("measurements")
    measurements: Mapping[str, Any] = present if isinstance(present, Mapping) else {}
    properties = schema_properties(schema, "measurements")
    rows: list[str] = []
    for key in _measurement_keys(schema):
        label = schema_label(properties, key)
        raw = measurements.get(key)
        if raw is None:
            figure, _ = (safe(column) for column in FIGURE_COLUMN_LABELS)
            rows.append(
                f'<tr><th scope="row">{label}</th>'
                f'<td class="absent" data-label="{figure}">'
                f"{safe(ABSENT_TEXT)}</td>{_detail_cell('')}</tr>"
            )
        elif isinstance(raw, Mapping):
            rows.append(_figure_row(label, rate_figure(key, raw)))
        elif isinstance(raw, str):
            rows.append(_figure_row(label, Figure(text=raw, detail="", refused=False)))
        else:
            raise SiteBuildError(f"measurement {key!r} is neither a figure nor a stated gate")
    return rows


def _detail_cell(detail: str) -> str:
    """The Detail cell of a figure row, stated rather than left blank.

    A figure's ``detail`` is optional in the schema, so an empty one means the
    receipt did not carry it. That is the same absence the qualifier fields and
    a missing measurement key already name, so it renders the same way, in the
    same words, at every width.

    The alternative shipped at cb25ea2 and was wrong: the cell was left empty
    and the narrow viewport hid empty cells, so a phone reader was shown less
    than a desktop reader and was not told. Concealing a field is the defect
    class this pass exists to remove, and a blank cell under a column header a
    narrow reader cannot see is a value with no name.
    """
    _, detail_label = (safe(column) for column in FIGURE_COLUMN_LABELS)
    if not detail:
        return f'<td class="absent" data-label="{detail_label}">{safe(ABSENT_TEXT)}</td>'
    return f'<td data-label="{detail_label}">{safe(detail)}</td>'


def _figure_row(label: str, figure: Figure) -> str:
    """One figure row. ``label`` is already-escaped markup from ``schema_label``."""
    css = "figure refused" if figure.refused else "figure"
    text = safe(figure.text)
    if figure.machine_value:
        text = f'<data value="{safe(figure.machine_value)}">{text}</data>'
    figure_label, _ = (safe(column) for column in FIGURE_COLUMN_LABELS)
    return (
        f'<tr><th scope="row">{label}</th>'
        f'<td class="{css}" data-label="{figure_label}">{text}</td>'
        f"{_detail_cell(figure.detail)}</tr>"
    )


def _clause_row(cells: Sequence[tuple[str, str]]) -> str:
    """One clause row. Each cell is (text, css class); an empty class draws none."""
    rendered: list[str] = []
    for text, css in cells:
        attribute = f' class="{css}"' if css else ""
        rendered.append(f"<td{attribute}>{safe(text)}</td>")
    return "<tr>" + "".join(rendered) + "</tr>"


def _identity_rows(receipt: Mapping[str, Any]) -> list[str]:
    """The instrument identity pins.

    These keys are deliberately NOT given the schema-sourced label the
    measurement and cost keys get. #490's brief fixed this block's markup, and
    ``tests/test_sitegen_subject_identity.py`` holds that pin by asserting the
    literal ``<dt>extractor_model</dt>`` row. Relabelling them is a decision
    that reopens #490 rather than one this pass makes on the way past.
    """
    identity = receipt.get("instrument_identity")
    if not isinstance(identity, Mapping):
        raise SiteBuildError("receipt carries no instrument identity")
    rows: list[str] = []
    for key in ("extractor_model", "prompt_fingerprint", "schema_fingerprint"):
        value = identity.get(key)
        if isinstance(value, str):
            text = value
        elif isinstance(value, Mapping) and isinstance(value.get("refusal"), str):
            # A declined pin is not a missing one (#479). extractor_model may be
            # refused when no model-based extraction stage ran, and rendering that
            # as ABSENT_TEXT would report a receipt that says something as one that
            # says nothing.
            text = f"refused: {value['refusal']}"
        else:
            text = ABSENT_TEXT
        rows.append(f"<dt>{safe(key)}</dt><dd><code>{safe(text)}</code></dd>")
    return rows


def _source_rows(receipt: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    source = receipt.get("source")
    if not isinstance(source, Mapping):
        raise SiteBuildError("receipt carries no source of record")
    properties = schema_properties(schema, "source")
    rows: list[str] = []
    for key in ("prose_path", "date", "notes"):
        label = schema_label(properties, key)
        value = source.get(key)
        if not isinstance(value, str):
            rows.append(f'<dt>{label}</dt><dd class="absent">{safe(ABSENT_TEXT)}</dd>')
            continue
        # A date is a machine value as much as a figure is, so it is marked up
        # as one rather than left as loose text.
        if key == "date" and _ISO_DATE_RE.fullmatch(value):
            cell = f'<time datetime="{safe(value)}">{safe(value)}</time>'
        else:
            cell = safe(value)
        rows.append(f"<dt>{label}</dt><dd>{cell}</dd>")
    return rows


def _delivery_section(receipt: Mapping[str, Any]) -> str:
    """Render the delivery block, or the empty string for receipts without one."""
    delivery = receipt.get("delivery")
    if not isinstance(delivery, Mapping):
        return ""
    channel = delivery.get("channel", "")
    channel_text = _DELIVERY_CHANNEL_TEXT.get(
        channel, f"Channel: {channel}" if isinstance(channel, str) else ABSENT_TEXT
    )
    parts: list[str] = [
        '<section aria-labelledby="value-delivery">',
        '<h2 id="value-delivery">Value delivery</h2>',
        f"<p>{safe(channel_text)}</p>",
    ]
    # Pi_c detail
    pi_c = delivery.get("pi_c")
    if isinstance(pi_c, Mapping):
        refusal = pi_c.get("refusal")
        if isinstance(refusal, str):
            parts.append(f'<p class="refusal">pi_c: REFUSED ({safe(refusal)})</p>')
        else:
            hat = pi_c.get("hat")
            invocations = pi_c.get("invocations")
            trials = pi_c.get("trials")
            hat_ok = isinstance(hat, (int, float))
            inv_ok = isinstance(invocations, int)
            tri_ok = isinstance(trials, int)
            if hat_ok and inv_ok and tri_ok:
                parts.append(f"<p>pi_c: {hat} ({invocations}/{trials} trials)</p>")
    # Exposure detail
    exposure = delivery.get("exposure")
    if isinstance(exposure, Mapping):
        refusal = exposure.get("refusal")
        if isinstance(refusal, str):
            parts.append(f'<p class="refusal">exposure: REFUSED ({safe(refusal)})</p>')
        else:
            value = exposure.get("value")
            passes = exposure.get("passes")
            epochs = exposure.get("epochs")
            if isinstance(value, (int, float)):
                text = str(value)
                if isinstance(passes, int) and isinstance(epochs, int):
                    text = f"{value} ({passes}/{epochs} epochs)"
                parts.append(f"<p>exposure: {safe(text)}</p>")
    parts.append("</section>")
    return "\n".join(parts)


def _subject_identity_section(receipt: Mapping[str, Any]) -> str:
    """Render the subject identity section, or the compact pointer for pre-1.1.0 receipts.

    A receipt with no ``subject_identity`` block (1.0.0) renders a one-line
    pointer to the prose source. A receipt with the block but no
    ``subject_model`` (1.1.0-1.3.0) renders all present fields and shows
    ``subject_model`` as absent.
    """
    identity = receipt.get("subject_identity")
    if not isinstance(identity, Mapping):
        # Pre-1.1.0: no subject_identity block. Render a compact pointer.
        prose = ""
        source = receipt.get("source")
        if isinstance(source, Mapping):
            prose = _string_field(source, "prose_path", "")
        pointer = "subject not recorded in this receipt"
        if prose:
            pointer += f"; the prose source may name it ({prose})"
        return (
            '<section aria-labelledby="subject-identity">\n'
            '  <h2 id="subject-identity">Subject identity</h2>\n'
            f'  <p class="absent">{safe(pointer)}</p>\n'
            "</section>"
        )
    # 1.1.0+: render all subject_identity fields with absent/refusal discipline.
    keys = (
        "skill_id",
        "harness_version",
        "metric_version",
        "implementation_hash",
        "subject_model",
        "arms",
    )
    rows: list[str] = []
    for key in keys:
        value = identity.get(key)
        if isinstance(value, str):
            text = value
        elif isinstance(value, list):
            text = ", ".join(str(item) for item in value)
        elif isinstance(value, Mapping) and isinstance(value.get("refusal"), str):
            text = f"refused: {value['refusal']}"
        else:
            text = ABSENT_TEXT
        rows.append(f"<dt>{safe(key)}</dt><dd><code>{safe(text)}</code></dd>")
    return (
        '<section aria-labelledby="subject-identity">\n'
        '  <h2 id="subject-identity">Subject identity</h2>\n'
        '  <dl class="subject">\n'
        f"{_indent(rows, 4)}\n"
        "  </dl>\n"
        "</section>"
    )


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
# Verdict scope and currentness sections (#643)
# ---------------------------------------------------------------------------

CARRIED_FORWARD_DISCLAIMER: Final[str] = (
    "A carried-forward verdict means the historical experiment has not been repeated "
    "in full on the current model; it has only passed the preregistered freshness "
    "checks. It must not be read as a new full validation."
)


def _verdict_scope_section(receipt: Mapping[str, Any]) -> str:
    """Render the verdict scope section, or the empty string for receipts without one."""
    scope = receipt.get("verdict_scope")
    if not isinstance(scope, Mapping):
        return ""
    keys = (
        "model_id",
        "harness_version",
        "fixture_version",
        "task_id",
        "tested_at",
        "task_family",
        "estimand",
        "delivery_mechanism",
        "n_per_arm",
        "margin_pp",
        "cs_lower_bound",
        "control_world_result",
        "placebo_ref",
        "fixture_id",
    )
    rows: list[str] = []
    for key in keys:
        value = scope.get(key)
        if isinstance(value, str):
            text = value
        elif isinstance(value, (int, float)):
            text = str(value)
        elif isinstance(value, Mapping) and isinstance(value.get("refusal"), str):
            text = f"refused: {value['refusal']}"
        else:
            text = ABSENT_TEXT
        rows.append(f"<dt>{safe(key)}</dt><dd><code>{safe(text)}</code></dd>")
    parts = [
        '<section aria-labelledby="verdict-scope">',
        '  <h2 id="verdict-scope">Verdict scope</h2>',
        '  <dl class="verdict-scope">',
        f"{_indent(rows, 4)}",
        "  </dl>",
    ]
    scope_line = _scope_line(receipt)
    if scope_line:
        parts.append(f"  {scope_line}")
    parts.append("</section>")
    return "\n".join(parts)


def _currentness_section(receipt: Mapping[str, Any]) -> str:
    """Render the currentness section with the verbatim disclaimer.

    A missing currentness reads as STALE / NONE at render time, never as
    validated.
    """
    currentness = receipt.get("currentness")
    if not isinstance(currentness, Mapping):
        state = "STALE"
        basis = "NONE"
    else:
        state = _string_field(currentness, "state", "STALE")
        basis = _string_field(currentness, "basis", "NONE")
    last_checked = ""
    next_check = ""
    max_age = ""
    if isinstance(currentness, Mapping):
        last_checked = _string_field(currentness, "last_checked_at", "")
        next_check = _string_field(currentness, "next_check_due", "")
        age = currentness.get("max_age_days")
        if isinstance(age, int):
            max_age = str(age)
    rows: list[str] = [
        f"<dt>state</dt><dd><code>{safe(state)}</code></dd>",
        f"<dt>basis</dt><dd><code>{safe(basis)}</code></dd>",
    ]
    if last_checked:
        dt_str = safe(last_checked)
        rows.append(f'<dt>last_checked_at</dt><dd><time datetime="{dt_str}">{dt_str}</time></dd>')
    else:
        rows.append(f'<dt>last_checked_at</dt><dd class="absent">{safe(ABSENT_TEXT)}</dd>')
    if next_check:
        dt_str = safe(next_check)
        rows.append(f'<dt>next_check_due</dt><dd><time datetime="{dt_str}">{dt_str}</time></dd>')
    else:
        rows.append(f'<dt>next_check_due</dt><dd class="absent">{safe(ABSENT_TEXT)}</dd>')
    if max_age:
        rows.append(f"<dt>max_age_days</dt><dd>{safe(max_age)}</dd>")
    else:
        rows.append(f'<dt>max_age_days</dt><dd class="absent">{safe(ABSENT_TEXT)}</dd>')
    parts = [
        '<section aria-labelledby="currentness">',
        '  <h2 id="currentness">Currentness</h2>',
        '  <dl class="currentness">',
        f"{_indent(rows, 4)}",
        "  </dl>",
    ]
    if state == "CARRIED_FORWARD":
        parts.append(f'  <p class="disclaimer">{safe(CARRIED_FORWARD_DISCLAIMER)}</p>')
    parts.append("</section>")
    return "\n".join(parts)


def _scope_line(receipt: Mapping[str, Any]) -> str:
    """Render the S476 scope line for a KEEP verdict.

    A KEEP licenses that scoped sentence only. The line is filled from
    verdict_scope fields.
    """
    if receipt.get("verdict") != "KEEP":
        return ""
    scope = receipt.get("verdict_scope")
    if not isinstance(scope, Mapping):
        return ""
    model = _string_field(scope, "model_id", "unknown model")
    task_family = _string_field(scope, "task_family", "unknown task family")
    delivery = _string_field(scope, "delivery_mechanism", "unknown delivery")
    tested_at = _string_field(scope, "tested_at", "unknown date")
    return (
        f'<p class="scope-line">'
        f"Shown here: effect on {safe(task_family)}, {safe(model)}, "
        f"{safe(delivery)}, measured {safe(tested_at)}. "
        f"Not shown: other task families, models, environments, or real-world incidence."
        f"</p>"
    )


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


def null_case_language(schema: Mapping[str, Any], key: str) -> str | None:
    """The schema's own word for ``key``'s null case, or ``None`` if it declares none.

    The site does not invent vocabulary (#583). Where a nullable field's schema
    description names a word for the null case, it does so in one construction,
    ``null = <word>``, and that word is what the page prints. A description that
    discusses the null case without naming a word for it supplies semantics, not
    vocabulary, and the caller renders absence instead.

    Deliberately narrow. A looser reader would start paraphrasing sentences into
    labels, which is the defect this function exists to end, one layer down.
    """
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return None
    field = properties.get(key)
    if not isinstance(field, Mapping):
        return None
    description = field.get("description")
    if not isinstance(description, str):
        return None
    match = _NULL_LANGUAGE_RE.search(description)
    return match.group("word").strip() if match is not None else None


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
