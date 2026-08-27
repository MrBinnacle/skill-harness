from skill_harness.executable_evaluation import (
    Authority,
    Ceiling,
    Property,
    PropertyRegistry,
    PropertyType,
    Status,
    declaration_evaluator,
    observation_hash,
    structural_mapping_evaluator,
)


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


def test_observation_hash_is_stable_across_mapping_order():
    left = {"a": 1, "b": [2, 3]}
    right = {"b": [2, 3], "a": 1}
    assert observation_hash(left) == observation_hash(right)
