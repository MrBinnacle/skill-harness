import json
from pathlib import Path

import pytest

from skill_harness.executable_evaluation import (
    Authority,
    Ceiling,
    Property,
    PropertyRegistry,
    PropertyType,
    Status,
    declaration_evaluator,
    make_receipt,
    observation_hash,
    structural_mapping_evaluator,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ts_go"


def test_property_id_is_stable_and_content_addressed():
    kwargs = dict(
        statement="Generated Go contains the required declarations.",
        type=PropertyType.MECHANICALLY_DECIDABLE,
        deterministic_authority=Authority.AUTHORITATIVE,
        judgment_authority=Authority.PROHIBITED,
        ceiling=Ceiling(
            establishes=("required declarations are present",),
            does_not_establish=("semantic equivalence",),
        ),
    )
    assert Property(**kwargs).id == Property(**kwargs).id
    assert Property(**kwargs).id.startswith("sha256:")


def test_registry_is_immutable():
    registry = PropertyRegistry()
    prop = Property(
        statement="x",
        type=PropertyType.MECHANICALLY_DECIDABLE,
        deterministic_authority=Authority.AUTHORITATIVE,
        judgment_authority=Authority.PROHIBITED,
        ceiling=Ceiling(("x",), ("y",)),
    )
    updated = registry.register_property(prop)
    assert registry.properties == ()
    assert updated.properties == (prop,)


def test_declaration_evaluator_is_deterministic_and_fails_on_mismatch():
    evaluator = declaration_evaluator((("type", "User"), ("func", "main")))
    observations = {
        "go_declarations": [
            {"name": "main", "kind": "func"},
            {"name": "User", "kind": "type"},
        ]
    }
    assert evaluator.evaluate("package main", observations)[0] is Status.PASS
    assert evaluator.evaluate("package main", observations) == evaluator.evaluate("package main", observations)

    bad = {"go_declarations": [{"name": "User", "kind": "type"}]}
    assert evaluator.evaluate("package main", bad)[0] is Status.FAIL


def test_structural_mapping_evaluator_is_order_independent():
    evaluator = structural_mapping_evaluator(
        (("interface User", "type User struct"), ("function f", "func f"))
    )
    observations = {
        "structural_mappings": [
            {"source": "function f", "target": "func f"},
            {"source": "interface User", "target": "type User struct"},
        ]
    }
    assert evaluator.evaluate("package main", observations)[0] is Status.PASS


def test_ts_go_fixture_goldens():
    observations = json.loads((FIXTURE / "basic_observations.json").read_text())
    go_source = (FIXTURE / "basic.go").read_text()
    declarations = declaration_evaluator((("func", "Greet"), ("type", "User")))
    mappings = structural_mapping_evaluator(
        (("function greet", "func Greet"), ("interface User", "type User struct"))
    )
    assert declarations.evaluate(go_source, observations)[0] is Status.PASS
    assert mappings.evaluate(go_source, observations)[0] is Status.PASS


def test_observation_hash_is_stable_across_mapping_order():
    left = {"a": 1, "b": [2, 3]}
    right = {"b": [2, 3], "a": 1}
    assert observation_hash(left) == observation_hash(right)


def test_registry_rejects_evaluator_that_exceeds_property_ceiling():
    property = Property(
        statement="declarations exist",
        type=PropertyType.MECHANICALLY_DECIDABLE,
        deterministic_authority=Authority.AUTHORITATIVE,
        judgment_authority=Authority.PROHIBITED,
        ceiling=Ceiling(("declarations exist",), ("semantics",)),
    )
    evaluator = declaration_evaluator((("type", "User"),))
    registry = PropertyRegistry().register_property(property).register_evaluator(evaluator.spec)
    with pytest.raises(ValueError):
        registry.bind(property.id, evaluator.spec.id)


def test_receipt_points_to_hashes_only():
    property = Property(
        statement="declarations exist",
        type=PropertyType.MECHANICALLY_DECIDABLE,
        deterministic_authority=Authority.AUTHORITATIVE,
        judgment_authority=Authority.PROHIBITED,
        ceiling=Ceiling(("required declarations are present",), ("semantics",)),
    )
    evaluator = declaration_evaluator((("type", "User"),))
    receipt = make_receipt(
        property,
        evaluator.spec,
        {"go_declarations": [{"kind": "type", "name": "User"}]},
        Status.PASS,
        {"observed": (("type", "User"),)},
    )
    assert receipt.property_id == property.id
    assert receipt.evaluator_id == evaluator.spec.id
    assert receipt.observation_hash.startswith("sha256:")
