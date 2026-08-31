"""Every production verdict call must name the value class it is judging.

Falsification-plan item 9. `screen_verdict` and `matched_gate2_verdict` emit
`CUT(subsumed)` and `CUT(no_lift)` only for `ValueClass.TRANSFORMATIVE_LIFT`. The guard
exists because a false CUT on a trap-discipline or a calibration skill is the dominant real
portfolio failure, and those are the classes this instrument mostly holds.

The guard is defeated by omission, not by argument. `value_class` defaults to `None`, and
`None` is treated exactly like any non-transformative class, so a call site that simply
forgets the keyword looks correct and behaves correctly until the day the verdict path it
feeds starts mattering. Nothing about the omission is visible at the call site.

This module makes the omission visible. It parses production sources and requires every call
to either function to pass `value_class=` explicitly.

What counts as passing it
-------------------------
- `value_class=value_class_for(name)` - the registry lookup, the intended form.
- `value_class=ValueClass.SOMETHING` - an explicit constant, reviewable in the diff.
- `value_class=some_variable` - the decision was made by a caller and threaded here.

The third form is deliberately allowed. Threading the class down from a caller that knows
the subject is the correct layering, and a scan that forbade it would push authors toward
hard-coding a constant, which is worse. What the scan refuses is the call that says nothing.

Why tests are out of scope
--------------------------
Test call sites omit the argument on purpose, to pin the default-`None` and
`wrong_instrument` behaviour. Scanning them would forbid the tests that prove the default
works.

Prior art: `tests/test_structural_bans.py`. That module's bans are mirrored into
`.pre-commit-config.yaml` and cross-checked so the two cannot drift. This one is not
mirrored, and the reason is stated rather than assumed: the property here is the absence of
a keyword argument in a call node, which a line-oriented regex cannot express without
false positives on multi-line calls. An AST check is the honest implementation, and pytest
is where it runs.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SRC_ROOT: Final[Path] = REPO_ROOT / "src"

GUARDED_FUNCTIONS: Final[frozenset[str]] = frozenset({"screen_verdict", "matched_gate2_verdict"})

VALUE_CLASS_KEYWORD: Final[str] = "value_class"

# Production modules permitted to call a guarded function without naming a value class.
# Empty by intent. A reviewed entry belongs here only when the call genuinely has no subject
# identity in scope AND threading one down is impossible; record why beside it, because an
# allowlist that does not say why is a silence.
REVIEWED_EXEMPT: Final[frozenset[Path]] = frozenset()

# The definitions themselves, and the module that documents the intended call form, are not
# call sites. They are excluded by construction rather than by allowlist: this scan only ever
# inspects ast.Call nodes, so a `def` or a docstring cannot match.


def _called_name(node: ast.Call) -> str | None:
    """Return the bare function name a Call node invokes, if it has one."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _describe_value(node: ast.expr) -> str:
    """Return a short, stable description of what an argument expression is."""
    if isinstance(node, ast.Call):
        inner = _called_name(node)
        return f"{inner}(...)" if inner else "a call"
    if isinstance(node, ast.Attribute):
        return f"{ast.unparse(node)}"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return ast.unparse(node)


def _production_modules() -> list[Path]:
    """Return every tracked production module, skipping caches and build artefacts."""
    return sorted(
        path
        for path in SRC_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and ".sandcastle" not in path.parts
    )


def _guarded_calls() -> list[tuple[Path, int, str, ast.Call]]:
    """Return every production call to a guarded function, as (path, line, name, node)."""
    found: list[tuple[Path, int, str, ast.Call]] = []
    for path in _production_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _called_name(node)
            if name in GUARDED_FUNCTIONS:
                found.append((path.relative_to(REPO_ROOT), node.lineno, name, node))
    return found


def test_the_scan_finds_the_guarded_calls_at_all() -> None:
    """The scan must find calls, or every other assertion here is vacuously true.

    A refactor that renames these functions, or a walk that silently stops matching, would
    otherwise turn this module green while guarding nothing. That is the failure this
    repository's success-test-accepts-any-output card describes.
    """
    calls = _guarded_calls()
    assert calls, (
        "the static scan found no production call to "
        f"{sorted(GUARDED_FUNCTIONS)}. Either the functions were renamed and this guard "
        "needs updating, or the scan stopped walking production sources. A guard that "
        "matches nothing passes everything."
    )


def test_every_production_verdict_call_names_a_value_class() -> None:
    """A production call that omits `value_class=` defeats the CUT guard by silence."""
    offenders: list[str] = []
    for path, line, name, node in _guarded_calls():
        if path in REVIEWED_EXEMPT:
            continue
        keywords = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
        if VALUE_CLASS_KEYWORD not in keywords:
            offenders.append(f"{path}:{line} calls {name}() without value_class=")

    assert not offenders, (
        "production calls omit the value-class guard:\n  "
        + "\n  ".join(offenders)
        + "\n\nvalue_class defaults to None, and None withholds the CUT exactly as a "
        "non-transformative class does, so an omitted argument reads as safe and is not. "
        "Pass value_class=value_class_for(<skill name>), an explicit ValueClass constant, "
        "or thread the class down from a caller that knows the subject."
    )


def test_value_class_arguments_come_from_a_reviewable_source() -> None:
    """The argument must be a registry lookup, a named constant, or a threaded variable.

    A literal `None` written at the call site is refused. It is indistinguishable in effect
    from omitting the argument, and writing it makes the omission look deliberate without
    making it reviewable.
    """
    offenders: list[str] = []
    for path, line, name, node in _guarded_calls():
        if path in REVIEWED_EXEMPT:
            continue
        for keyword in node.keywords:
            if keyword.arg != VALUE_CLASS_KEYWORD:
                continue
            value = keyword.value
            if isinstance(value, ast.Constant) and value.value is None:
                offenders.append(
                    f"{path}:{line} passes value_class=None to {name}(), which has the "
                    "same effect as omitting it"
                )
            elif not isinstance(value, (ast.Call, ast.Attribute, ast.Name)):
                offenders.append(
                    f"{path}:{line} passes value_class={_describe_value(value)} to "
                    f"{name}(), which is not a registry lookup, a named constant, or a "
                    "threaded variable"
                )

    assert not offenders, (
        "production calls pass a value class that cannot be reviewed:\n  " + "\n  ".join(offenders)
    )


def test_the_exemption_list_records_only_real_modules() -> None:
    """An allowlist entry for a module that no longer exists is stale permission."""
    missing = sorted(str(path) for path in REVIEWED_EXEMPT if not (REPO_ROOT / path).is_file())
    assert not missing, (
        f"the reviewed-exemption list names modules that do not exist: {missing}. "
        "Remove them; a stale exemption grants permission nobody asked for."
    )
