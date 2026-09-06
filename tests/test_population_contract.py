"""The population-integrity contract, and the control that proves it can go red (#453).

``skill_harness.population`` exists because an enumeration-driven control can
execute perfectly over the wrong universe. These tests pin the contract itself.
Its first real consumer is ``tests/test_receipts_index.py``.

The load-bearing test in this module is
``test_the_omitted_member_fixture_fails_the_control_not_the_detector``. It
builds the exact fixture #453 specifies -- declared {A, B, C}, enumerated
{A, B}, a detector that passes correctly over what it received -- and requires
the CONTROL to fail anyway. A run where that fixture passes means the contract
is decorative, which is the state the contract exists to make impossible.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_harness.population import (
    DIGEST_VERSION,
    PopulationInvalidError,
    PopulationVerdict,
    UninterpretableSubReason,
    build_population_record,
    interpret,
    population_digest,
    posix_relative_ids,
    require_valid_population,
)

# --- the digest ------------------------------------------------------------


def test_the_digest_ignores_enumeration_order() -> None:
    """Filesystem and glob order must not change a population's identity."""
    assert population_digest(["c", "a", "b"]) == population_digest(["a", "b", "c"])


def test_the_digest_separates_populations_that_differ_by_one_member() -> None:
    assert population_digest(["a", "b"]) != population_digest(["a", "b", "c"])


def test_the_digest_is_injective_across_a_separator_in_an_identifier() -> None:
    """A separator-joined encoding would collide these two; JSON does not.

    ``{"a\\nb"}`` and ``{"a", "b"}`` are different populations of different
    cardinality. Under ``"\\n".join(sorted(ids))`` both encode to ``a\\nb`` and
    hash the same, so a control could swap one for the other undetected.
    """
    assert population_digest(["a\nb"]) != population_digest(["a", "b"])


def test_the_digest_is_version_prefixed() -> None:
    """A future canonicalisation change must not silently collide with this one."""
    import hashlib

    payload = DIGEST_VERSION + "\n" + json.dumps(["a", "b"], separators=(",", ":"))
    assert population_digest(["a", "b"]) == hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_a_duplicate_identifier_is_refused_rather_than_collapsed() -> None:
    """De-duplicating would repair the symptom and hide a double-counted case."""
    with pytest.raises(ValueError, match="duplicate population identifier"):
        population_digest(["a", "b", "a"])


def test_posix_ids_are_separator_stable(tmp_path: Path) -> None:
    """The same tree enumerated on Windows and on Linux must digest the same."""
    (tmp_path / "docs" / "assurance").mkdir(parents=True)
    first = tmp_path / "docs" / "assurance" / "one.md"
    first.write_text("x", encoding="utf-8")
    assert posix_relative_ids([first], tmp_path) == ("docs/assurance/one.md",)


# --- the record ------------------------------------------------------------


def test_an_agreeing_population_is_valid_and_records_both_sides() -> None:
    record = build_population_record(["a", "b"], declared=["b", "a"])
    assert record.population_valid
    assert record.population_count == 2
    assert record.population_ids == ("a", "b")
    assert record.declared_count == 2
    assert record.declared_digest == record.population_digest
    assert record.missing == ()
    assert record.unexpected == ()
    assert record.sub_reason is None


def test_a_declared_member_the_enumeration_missed_invalidates_the_population() -> None:
    """The #453 instance: a receipt existed and the enumeration never reached it."""
    record = build_population_record(["a", "b"], declared=["a", "b", "c"])
    assert not record.population_valid
    assert record.missing == ("c",)
    assert record.unexpected == ()
    assert record.sub_reason is UninterpretableSubReason.POPULATION_INVALID


def test_an_enumerated_member_no_declaration_named_invalidates_the_population() -> None:
    record = build_population_record(["a", "b", "z"], declared=["a", "b"])
    assert not record.population_valid
    assert record.unexpected == ("z",)


def test_an_undeclared_population_fails_closed() -> None:
    """Recording a population is not validating it.

    A control that never declared what it expected cannot demonstrate it got it,
    so the permissive reading -- no declaration means nothing to disagree with --
    is the wrong one and would let every unvalidated control report PASS.
    """
    record = build_population_record(["a", "b"])
    assert not record.population_valid
    assert record.declared_count is None
    assert record.declared_digest is None
    assert record.sub_reason is UninterpretableSubReason.POPULATION_INVALID


def test_the_record_serialises_the_field_names_453_specifies() -> None:
    """Two controls' records must be comparable without reading either control."""
    record = build_population_record(["a"], declared=["a"])
    assert set(record.as_dict()) == {
        "population_count",
        "population_ids",
        "population_digest",
        "declared_count",
        "declared_digest",
        "missing",
        "unexpected",
        "population_valid",
        "sub_reason",
    }


# --- the third verdict -----------------------------------------------------


def test_a_valid_population_with_no_detector_failures_passes() -> None:
    record = build_population_record(["a"], declared=["a"])
    assert interpret(record, []) is PopulationVerdict.PASS


def test_a_valid_population_with_detector_failures_fails() -> None:
    record = build_population_record(["a"], declared=["a"])
    assert interpret(record, ["a: missing claims line"]) is PopulationVerdict.FAIL


def test_an_invalid_population_is_uninterpretable_even_when_the_detector_passed() -> None:
    """The defect this contract exists to prevent, stated as an assertion.

    ``population_valid = false -> verdict = PASS`` is exactly the reading that
    turns "no defect found in the cases I received" into "no defect exists".
    """
    record = build_population_record(["a", "b"], declared=["a", "b", "c"])
    assert interpret(record, []) is PopulationVerdict.UNINTERPRETABLE


def test_an_invalid_population_is_uninterpretable_even_when_the_detector_failed() -> None:
    """A downstream result cannot repair an upstream validity failure.

    Reporting FAIL here would be a false finding about the subject, made from a
    universe that was never established. It is the same error as reporting PASS,
    with the sign flipped.
    """
    record = build_population_record(["a", "b"], declared=["a", "b", "c"])
    assert interpret(record, ["a: missing claims line"]) is PopulationVerdict.UNINTERPRETABLE


# --- fail closed -----------------------------------------------------------


def test_require_valid_population_is_silent_when_the_sets_agree() -> None:
    require_valid_population(build_population_record(["a"], declared=["a"]), "a control")


def test_require_valid_population_names_the_missing_member_and_the_verdict() -> None:
    """The message must carry the finding, not only the fact of a failure."""
    record = build_population_record(["a"], declared=["a", "b"])
    with pytest.raises(PopulationInvalidError) as caught:
        require_valid_population(record, "the receipts index control")
    message = str(caught.value)
    assert "UNINTERPRETABLE" in message
    assert str(UninterpretableSubReason.POPULATION_INVALID) in message
    assert "the receipts index control" in message
    assert "b" in message
    assert caught.value.record is record


def test_the_failure_is_an_assertion_error_so_pytest_reports_it_as_a_failure() -> None:
    """An ERROR reads as a broken test; a population failure is a real finding."""
    assert issubclass(PopulationInvalidError, AssertionError)


# --- the required negative control -----------------------------------------


def _detector(cases: tuple[str, ...]) -> list[str]:
    """A detector that is correct over whatever it receives.

    Reports a failure for any case named ``bad_*``. The fixture below gives it
    only good cases, so it passes -- correctly -- while the population it
    received is wrong.
    """
    return [case for case in cases if case.startswith("bad_")]


def test_the_detector_really_does_pass_over_the_reduced_set() -> None:
    """Guard: the negative control must rest on a detector that behaves correctly.

    If the detector failed over {A, B} for its own reasons, the control below
    would go red for a reason that has nothing to do with the population, and
    would prove nothing.
    """
    assert _detector(("A", "B")) == []


def test_the_omitted_member_fixture_fails_the_control_not_the_detector() -> None:
    """#453's required negative control, built exactly as the ticket specifies.

    ::

        declared population:   A, B, C
        enumerated population: A, B
        detector over {A, B}:  passes correctly

    Expected result: the CONTROL fails. A run where this fixture passes means
    the contract is decorative.
    """
    declared = ("A", "B", "C")
    enumerated = ("A", "B")

    detector_failures = _detector(enumerated)
    assert detector_failures == [], (
        "precondition: the detector must pass over what it received, so that the "
        "only thing left to fail is the population"
    )

    record = build_population_record(enumerated, declared=declared)
    assert interpret(record, detector_failures) is PopulationVerdict.UNINTERPRETABLE

    with pytest.raises(PopulationInvalidError) as caught:
        require_valid_population(record, "the omitted-member fixture")
    assert caught.value.record.missing == ("C",)
