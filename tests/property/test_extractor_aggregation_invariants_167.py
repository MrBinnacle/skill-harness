"""Assurance Phase 3 (#167) -- Hypothesis property tests for pure functions.

Invariants, not examples. Each test's docstring states the invariant as a
sentence; the assertions are that sentence made executable.

Scope is the pure surface named in #167: the SKILL.md parser, the extractor
models, the corpus census/coverage counting helpers, and the clause-status
state machine. Nothing here touches the network, a database, or the clock.

Example counts are held low deliberately. These run in the default lane, which
has a 25-minute ceiling per CI matrix cell, so no property here is allowed to
approach the ~60s mark that would require `@pytest.mark.assurance`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from skill_harness.aggregation.status import (
    ClauseStatus,
    ClauseStatusInput,
    UnmeasuredSubReason,
    derive_clause_status,
)
from skill_harness.extractor.corpus_census import (
    _COMPARATORS_SPECIFIED,
    _percent,
    falsifying_case_complete,
    run_census,
)
from skill_harness.extractor.corpus_coverage import _parse_clause_index
from skill_harness.extractor.corpus_coverage import _percent as _coverage_percent
from skill_harness.extractor.errors import MalformedSkillError
from skill_harness.extractor.models import (
    ExtractorInstrument,
    compare_extractor_generations,
    instrument_from_mapping,
)
from skill_harness.extractor.parser import parse_skill_file
from skill_harness.oracles.tier1.axis_registry import TIER1_AXIS_NAMES

_PROFILE = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)

# Arbitrary text, including the delimiters and control bytes the parser must
# survive. Explicitly seeded with frontmatter-shaped strings so the generator
# does not have to rediscover the interesting branch by chance.
_ARBITRARY_TEXT = st.one_of(
    st.text(),
    st.text(alphabet=st.sampled_from(["-", "\n", ":", " ", "\t", ".", "\r", "a"])),
    st.sampled_from(
        [
            "",
            "---\n",
            "---\nname: x\n---\n",
            "---\nname: x\n---\nbody\n",
            "---\nname: x\n...\nbody\n",
            "---\nno close delimiter\nbody\n",
            "---\r\nname: x\r\n---\r\nbody\r\n",
            "---\nname:\n---\nbody\n",
            "body with no frontmatter",
        ]
    ),
)

_HEX64 = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)

_JSON_SCALAR = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1000, max_value=1000),
    st.text(max_size=12),
)


# ---------------------------------------------------------------------------
# parser.py
# ---------------------------------------------------------------------------


@_PROFILE
@given(text=_ARBITRARY_TEXT)
def test_parser_only_documented_failure_mode(tmp_path: Path, text: str) -> None:
    """Parsing arbitrary text either succeeds or raises MalformedSkillError.

    No other exception type may escape parse_skill_file for input that is
    readable UTF-8. An unexpected exception class here is a crash, not a
    refusal, and the caller has no typed way to handle it.
    """
    path = tmp_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    try:
        parsed = parse_skill_file(path)
    except MalformedSkillError:
        return
    assert isinstance(parsed.body, str)
    assert parsed.body.strip(), "a successful parse must carry a non-empty body"


@_PROFILE
@given(raw=st.binary(max_size=256))
def test_parser_rejects_non_utf8_as_malformed(tmp_path: Path, raw: bytes) -> None:
    """Arbitrary bytes never escape as UnicodeDecodeError.

    Decode failure is converted to MalformedSkillError so that a corrupt file
    is a typed refusal rather than a stack trace from the stdlib.
    """
    path = tmp_path / "SKILL.md"
    path.write_bytes(raw)
    try:
        parse_skill_file(path)
    except MalformedSkillError:
        return
    except UnicodeDecodeError as exc:  # pragma: no cover - the property failing
        raise AssertionError(f"raw decode error escaped the parser: {exc}") from exc


@_PROFILE
@given(text=_ARBITRARY_TEXT)
def test_parser_sha256_is_over_raw_bytes_and_stable(tmp_path: Path, text: str) -> None:
    """The recorded SHA-256 equals the digest of the file's raw bytes, always.

    Provenance depends on this: the digest must be taken before decoding, so
    that two parses of identical bytes agree and the audit hash cannot drift
    from what is actually on disk.
    """
    path = tmp_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        first = parse_skill_file(path)
        second = parse_skill_file(path)
    except MalformedSkillError:
        return
    assert first.source_sha256 == expected
    assert second.source_sha256 == first.source_sha256


@_PROFILE
@given(
    stem=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=12
    ),
    body=st.text(min_size=1, max_size=40),
)
def test_parser_name_falls_back_to_filename_stem(tmp_path: Path, stem: str, body: str) -> None:
    """With no frontmatter name field, the parsed name is the filename stem.

    The fallback is what keeps an unnamed skill addressable, so it must hold
    for every stem, not just the well-formed ones.
    """
    assume(body.strip())
    path = tmp_path / f"{stem}.md"
    path.write_text(body, encoding="utf-8")
    parsed = parse_skill_file(path)
    assert parsed.name == stem


# ---------------------------------------------------------------------------
# models.py
# ---------------------------------------------------------------------------


@_PROFILE
@given(
    row=st.dictionaries(
        keys=st.sampled_from(
            [
                "extractor_model",
                "system_prompt_sha256",
                "tool_schema_sha256",
                "slug",
                "ok",
            ]
        ),
        values=st.one_of(_JSON_SCALAR, _HEX64),
        max_size=5,
    )
)
def test_instrument_from_mapping_is_total(row: dict[str, Any]) -> None:
    """Parsing an instrument triple from an arbitrary mapping never raises.

    A legacy or malformed corpus row must degrade to None (generation-unknown),
    because an exception here would abort a census over a corpus that is
    otherwise readable.
    """
    result = instrument_from_mapping(row)
    assert result is None or isinstance(result, ExtractorInstrument)


@_PROFILE
@given(
    model=st.text(min_size=1, max_size=20),
    prompt_sha=_HEX64,
    schema_sha=_HEX64,
)
def test_incomplete_triple_never_compares_as_same(
    model: str, prompt_sha: str, schema_sha: str
) -> None:
    """A missing triple compares as 'unknown', never as 'same'.

    This is the guard against a legacy row being silently folded into the
    current generation's figures.
    """
    instrument = ExtractorInstrument(
        model_id=model,
        system_prompt_sha256=prompt_sha,
        tool_schema_sha256=schema_sha,
    )
    assert compare_extractor_generations(None, instrument) == "unknown"
    assert compare_extractor_generations(instrument, None) == "unknown"
    assert compare_extractor_generations(None, None) == "unknown"
    assert compare_extractor_generations(instrument, instrument) == "same"


# ---------------------------------------------------------------------------
# aggregation/status.py
# ---------------------------------------------------------------------------


_STATUS_INPUT = st.builds(
    ClauseStatusInput,
    axis=st.one_of(st.sampled_from(sorted(TIER1_AXIS_NAMES)), st.text(max_size=12)),
    admissible_verdict_count=st.integers(min_value=0, max_value=40),
    total_verdict_count=st.integers(min_value=0, max_value=40),
    confounded_verdict_count=st.integers(min_value=0, max_value=40),
    n_verdicts=st.integers(min_value=0, max_value=40),
    p_win_gt_threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    current_frozen_case_count=st.integers(min_value=0, max_value=5),
    any_stale_frozen_case=st.booleans(),
    run_state=st.one_of(st.none(), st.sampled_from(["aborted_budget", "complete", "running"])),
    bh_fdr_pass=st.one_of(st.none(), st.booleans()),
)


@_PROFILE
@given(inp=_STATUS_INPUT)
def test_status_mapping_is_total_and_typed(inp: ClauseStatusInput) -> None:
    """Every input reaches exactly one status, with a sub-reason from the enum.

    Totality is the point: there is no input for which the state machine falls
    off the end, and no free-typed reason string can appear where the fixed
    vocabulary is expected.
    """
    status, sub_reason = derive_clause_status(inp)
    assert isinstance(status, ClauseStatus)
    assert sub_reason is None or isinstance(sub_reason, UnmeasuredSubReason)


@_PROFILE
@given(inp=_STATUS_INPUT)
def test_sub_reason_present_exactly_when_unmeasured(inp: ClauseStatusInput) -> None:
    """A sub-reason accompanies UNMEASURED and never accompanies any other status.

    A decided verdict carrying a not-knowing reason, or an UNMEASURED carrying
    none, would both make the refusal vocabulary unreadable downstream.
    """
    status, sub_reason = derive_clause_status(inp)
    if status is ClauseStatus.UNMEASURED:
        assert sub_reason is not None
    else:
        assert sub_reason is None


@_PROFILE
@given(inp=_STATUS_INPUT)
def test_status_derivation_is_deterministic(inp: ClauseStatusInput) -> None:
    """The same evidence yields the same status on every call.

    The function is declared pure; this is that declaration made falsifiable.
    """
    assert derive_clause_status(inp) == derive_clause_status(inp)


@_PROFILE
@given(inp=_STATUS_INPUT, unscoreable_axis=st.text(max_size=12))
def test_unscoreable_axis_dominates_every_other_signal(
    inp: ClauseStatusInput, unscoreable_axis: str
) -> None:
    """An axis no Tier-1 scorer can see is always UNMEASURED(mechanical_vacuous).

    Rule 0 must outrank every other input. If any amount of evidence could
    produce NO_DATA on an unscoreable axis, the report would imply that more
    sampling can resolve a clause that no scorer can ever measure.
    """
    assume(unscoreable_axis not in TIER1_AXIS_NAMES)
    inp.axis = unscoreable_axis
    status, sub_reason = derive_clause_status(inp)
    assert status is ClauseStatus.UNMEASURED
    assert sub_reason is UnmeasuredSubReason.MECHANICAL_VACUOUS


# ---------------------------------------------------------------------------
# corpus_census.py / corpus_coverage.py
# ---------------------------------------------------------------------------


@_PROFILE
@given(
    count=st.integers(min_value=0, max_value=10_000),
    total=st.integers(min_value=0, max_value=10_000),
)
def test_percent_refuses_an_empty_denominator(count: int, total: int) -> None:
    """A zero denominator returns None rather than a number.

    This is the smallest instance of the repo's own rule: a figure that is not
    there is refused, never filled in with a placeholder zero.
    """
    result = _percent(count, total)
    if total == 0:
        assert result is None
        return
    assert result is not None
    if count <= total:
        assert 0.0 <= result <= 100.0
    assert result == _percent(count, total)


@_PROFILE
@given(
    clause=st.dictionaries(
        keys=st.sampled_from(["falsifying_case", "axis", "comparator"]),
        values=st.one_of(
            _JSON_SCALAR,
            st.dictionaries(
                keys=st.sampled_from(
                    [
                        "input_population_spec",
                        "expected_directional_pair",
                        "min_reproducibility",
                        "other",
                    ]
                ),
                values=_JSON_SCALAR,
                max_size=4,
            ),
        ),
        max_size=3,
    )
)
def test_falsifying_case_completeness_is_total(clause: dict[str, Any]) -> None:
    """Structural completeness is decidable for any clause mapping, without raising.

    A bare boolean, a missing key, or a null value is incomplete rather than an
    error, so that one malformed clause cannot abort a whole-corpus census.
    """
    assert isinstance(falsifying_case_complete(clause), bool)


_CLAUSE = st.fixed_dictionaries(
    {
        "axis": st.one_of(st.sampled_from(sorted(TIER1_AXIS_NAMES)), st.text(max_size=8)),
        "comparator": st.one_of(
            st.sampled_from(sorted(_COMPARATORS_SPECIFIED)),
            st.text(max_size=8),
            st.none(),
        ),
        "falsifying_case": st.one_of(
            st.none(),
            st.booleans(),
            st.fixed_dictionaries(
                {
                    "input_population_spec": st.text(max_size=8),
                    "expected_directional_pair": st.text(max_size=8),
                    "min_reproducibility": st.text(max_size=8),
                }
            ),
        ),
    }
)


def _unique_by_slug(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first row per slug.

    The slug is the census key, so a duplicate is a different scenario than the
    one these properties are about.
    """
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        slug = str(row["slug"])
        if slug in seen:
            continue
        seen.add(slug)
        unique.append(row)
    return unique


def _write_corpus(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write rows as JSONL and return the path, the shape run_census expects."""
    path = tmp_path / "corpus.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


_SKILL_ROW = st.fixed_dictionaries(
    {
        "slug": st.text(
            alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=8
        ),
        "ok": st.booleans(),
        "clauses": st.lists(_CLAUSE, max_size=4),
    }
)


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(rows=st.lists(_SKILL_ROW, min_size=1, max_size=6))
def test_census_buckets_partition_their_population(
    tmp_path: Path, rows: list[dict[str, Any]]
) -> None:
    """Census buckets partition the clause population: nothing double-counted, nothing dropped.

    Every clause in a successfully-extracted row lands in exactly one axis
    bucket and exactly one comparator bucket, so each pair of counts sums to
    the clause subtotal. A bucket pair that fails to sum means some clause was
    either counted twice or silently discarded, and every percentage computed
    from it is wrong.
    """
    unique_rows = _unique_by_slug(rows)
    result = run_census(_write_corpus(tmp_path, unique_rows))

    assert result.known_clause_subtotal >= 0
    assert result.scoreable_axis_count >= 0
    assert result.unscoreable_axis_count >= 0
    assert result.comparator_specified_count >= 0
    assert result.comparator_unspecified_count >= 0

    assert (
        result.scoreable_axis_count + result.unscoreable_axis_count == result.known_clause_subtotal
    ), "axis buckets must partition the clause subtotal"
    assert (
        result.comparator_specified_count + result.comparator_unspecified_count
        == result.known_clause_subtotal
    ), "comparator buckets must partition the clause subtotal"


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(rows=st.lists(_SKILL_ROW, min_size=1, max_size=6))
def test_failed_extractions_never_enter_a_denominator(
    tmp_path: Path, rows: list[dict[str, Any]]
) -> None:
    """A failed extraction contributes zero clauses to the subtotal it is excluded from.

    A row that failed extracted an unknown number of clauses, so counting its
    zero into a denominator would report a partial population under a complete
    name and deflate every percentage taken against it.
    """
    unique_rows = _unique_by_slug(rows)
    result = run_census(_write_corpus(tmp_path, unique_rows))

    expected_failed = {row["slug"] for row in unique_rows if not row["ok"]}
    assert set(result.failed_extraction_slugs) == expected_failed

    expected_subtotal = sum(len(row["clauses"]) for row in unique_rows if row["ok"])
    assert result.known_clause_subtotal == expected_subtotal


@_PROFILE
@given(
    count=st.integers(min_value=0, max_value=10_000),
    total=st.integers(min_value=0, max_value=10_000),
)
def test_coverage_percent_refuses_an_empty_denominator(count: int, total: int) -> None:
    """The coverage module's own percent helper refuses a zero denominator too.

    corpus_coverage carries a second _percent with the same contract as the
    census one. It is tested separately and deliberately: a shared rule that
    lives in two copies is exactly the shape that drifts, and a defence applied
    to one module is not a defence for the class.
    """
    result = _coverage_percent(count, total)
    if total == 0:
        assert result is None
        return
    assert result is not None
    if count <= total:
        assert 0.0 <= result <= 100.0
    assert result == _percent(count, total), "the two _percent copies must agree"


@_PROFILE
@given(
    clause=st.dictionaries(
        keys=st.sampled_from(["clause_index", "index", "id"]),
        values=st.one_of(_JSON_SCALAR, st.floats(allow_nan=True, allow_infinity=True)),
        max_size=3,
    )
)
def test_clause_index_parsing_is_total(clause: dict[str, Any]) -> None:
    """A clause index is either an int or None, and parsing never raises.

    The index joins coverage rows back to clauses. A raised exception here
    would abort the join for a whole skill because one row was malformed.
    """
    result = _parse_clause_index(clause)
    assert result is None or isinstance(result, int)
