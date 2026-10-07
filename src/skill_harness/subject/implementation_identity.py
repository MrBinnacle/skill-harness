"""AST-shape implementation-identity digest for the outcome oracle (#209).

Instance 6b of the store-bricking deadlock: ``_oracle_implementation_hash()``
hashes its own module's raw bytes, and the registered hash lives in the
append-only ``metric_versions`` table. Editing a comment in the oracle module
therefore refused every further verdict under the registered measurement
identity, and the append-only row could not be corrected.

The repair follows the maintainer ruling recorded on #209. It is NOT instance
6a's repair, and the difference is the whole point:

* 6a normalises SQL by stripping ``--`` comments, which is sound because a SQL
  comment cannot carry behaviour.
* Python **docstrings can**. They are live module data, reachable through
  ``__doc__``, so a threshold, prompt or rubric can sit in one. A digest that
  ignored docstrings would report a changed rubric as "no behaviour change" --
  a hole in the tamper detector rather than a repair of it.

So identity is the **AST shape with docstrings preserved as behaviour**:

* comments and formatting are excluded, and this is a property of the
  representation rather than a stripping pass -- ``ast`` discards comments
  outright, so there is no stripping logic here that could be got wrong;
* docstrings are ordinary ``Expr(Constant(str))`` nodes and are simply not
  special-cased out;
* executable code, constants, annotations, decorators, defaults, type comments,
  control flow and imports are all identity-bearing;
* source-location metadata (``lineno``, ``col_offset`` and friends) is excluded;
* anything unrecognised **fails closed**.

The raw-byte hash is untouched and remains the tamper-evidence layer. This digest
answers a second question -- *did the behaviour change?* -- and never replaces the
first.
"""

from __future__ import annotations

import ast
import hashlib

__all__ = [
    "IDENTITY_DIGEST_ALGO_VERSION",
    "ImplementationIdentityError",
    "canonicalize",
    "semantic_digest",
]

# Bump on ANY change to the canonical form, including a Python upgrade that moves
# it. A digest is only ever comparable against digests carrying the same version
# string: the store records this alongside every digest so that a future change
# cannot silently compare across algorithms. See the golden-digest test, which is
# what detects an accidental move.
IDENTITY_DIGEST_ALGO_VERSION = "ast-shape-1"


class ImplementationIdentityError(Exception):
    """Raised when an identity digest cannot be computed and must not be guessed.

    Every arm is a refusal: unparseable source, a node type this canonicaliser
    has never been reviewed against, or a field whose value cannot be rendered
    unambiguously. Callers translate this into their own fail-closed refusal.
    """


# Node types whose canonical rendering has been reviewed. This is an ALLOWLIST on
# purpose: a Python release that adds a node type must produce a loud failure
# rather than a silent identity change, which is what the ruling's versioning
# clause requires. ``test_6c_the_allowlist_covers_every_node_type_this_interpreter_has``
# is the tripwire.
#
# Kept as a frozen literal rather than derived from ``vars(ast)`` at import time.
# Deriving it would auto-accept whatever the interpreter offers, which is exactly
# the failure the allowlist exists to prevent.
# fmt: off
# Kept hand-grouped: one entry per line would make this a 100-line wall in which
# a missing node type is harder to spot, not easier.
ALLOWED_NODE_TYPES = frozenset(
    {
        # --- module / statement level -------------------------------------
        "Module", "Interactive", "Expression", "FunctionType",
        "FunctionDef", "AsyncFunctionDef", "ClassDef", "Return", "Delete",
        "Assign", "AugAssign", "AnnAssign", "For", "AsyncFor", "While", "If",
        "With", "AsyncWith", "Match", "Raise", "Try", "TryStar", "Assert",
        "Import", "ImportFrom", "Global", "Nonlocal", "Expr", "Pass", "Break",
        "Continue",
        # --- expressions ---------------------------------------------------
        "BoolOp", "NamedExpr", "BinOp", "UnaryOp", "Lambda", "IfExp", "Dict",
        "Set", "ListComp", "SetComp", "DictComp", "GeneratorExp", "Await",
        "Yield", "YieldFrom", "Compare", "Call", "FormattedValue", "JoinedStr",
        "Constant", "Attribute", "Subscript", "Starred", "Name", "List",
        "Tuple", "Slice",
        # --- operators (singletons; rendered by class name) ----------------
        "And", "Or",
        "Add", "Sub", "Mult", "MatMult", "Div", "Mod", "Pow", "LShift",
        "RShift", "BitOr", "BitXor", "BitAnd", "FloorDiv",
        "Invert", "Not", "UAdd", "USub",
        "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE", "Is", "IsNot", "In", "NotIn",
        # --- expression context --------------------------------------------
        "Load", "Store", "Del",
        # --- helper nodes ---------------------------------------------------
        "comprehension", "ExceptHandler", "arguments", "arg", "keyword",
        "alias", "withitem",
        # --- structural pattern matching ------------------------------------
        "match_case", "MatchValue", "MatchSingleton", "MatchSequence",
        "MatchMapping", "MatchClass", "MatchStar", "MatchAs", "MatchOr",
        # --- PEP 695 type parameters (3.12+) --------------------------------
        "TypeAlias", "TypeVar", "ParamSpec", "TypeVarTuple",
        # --- abstract bases: never instantiated, listed so the tripwire test
        #     does not flag them as unreviewed -----------------------------
        "AST", "mod", "stmt", "expr", "expr_context", "boolop", "operator",
        "unaryop", "cmpop", "excepthandler", "pattern", "type_param",
        "type_ignore",
        # --- deprecated legacy classes -------------------------------------
        # Still exported by ``ast`` but never produced by the current parser:
        # AugLoad/AugStore/Param are unused expr_context values, Index/ExtSlice
        # were folded into ordinary expressions and Tuple in 3.9, Suite is a dead
        # mod variant, and ``slice`` is their abstract base. Listed as ALLOWED
        # rather than IGNORED on purpose: if one ever did appear it would be
        # rendered structurally, whereas ignoring it would silently erase it from
        # the identity.
        "AugLoad", "AugStore", "ExtSlice", "Index", "Param", "Suite", "slice",
    }
)
# fmt: on

# Present in ``ast`` but deliberately NOT part of identity.
#
# ``TypeIgnore`` records a ``# type: ignore`` comment. It is a suppression
# directive for external checkers and changes no runtime behaviour, so it is the
# one ``ast``-visible comment class excluded here. ``# type:`` annotations proper
# ARE included -- they arrive as ``type_comment`` string fields on the statement
# nodes, not as ``TypeIgnore``.
IGNORED_NODE_TYPES = frozenset({"TypeIgnore"})

# Attributes carrying source position. Excluded per the ruling: moving a
# statement down a line changes none of these projects' behaviour.
_LOCATION_FIELDS = frozenset({"lineno", "col_offset", "end_lineno", "end_col_offset"})


def semantic_digest(source: str) -> str:
    """SHA-256 over the canonical AST shape of ``source``.

    :raises ImplementationIdentityError: source does not parse, or its tree
        contains something this canonicaliser has not been reviewed against.
        Never returns a digest it could not justify.
    """
    return hashlib.sha256(canonical_form(source).encode("utf-8")).hexdigest()


def canonical_form(source: str) -> str:
    """The canonical string whose hash is the identity. Exposed for debugging.

    ``type_comments=True`` is load-bearing, not incidental: without it ``ast``
    discards ``# type:`` annotations entirely and a changed one would read as no
    change. It also makes a malformed type comment a parse error, which is the
    correct fail-closed outcome.
    """
    try:
        tree = ast.parse(source, type_comments=True)
    except (SyntaxError, ValueError, MemoryError, RecursionError) as exc:
        # ValueError covers source containing null bytes; SyntaxError covers both
        # ordinary syntax errors and malformed type comments.
        raise ImplementationIdentityError(
            f"cannot compute an implementation identity: source does not parse ({exc})"
        ) from exc
    return canonicalize(tree)


def canonicalize(node: object) -> str:
    """Render an AST node as a canonical, location-free string.

    Fields are emitted **sorted by field name** rather than in ``_fields`` order.
    ``_fields`` is an implementation detail whose order a release is free to
    change; sorting removes that as a source of cross-version drift, which is one
    half of what the ruling's determinism clause asks for. (The other half is the
    golden-digest test.)
    """
    if isinstance(node, ast.AST):
        name = type(node).__name__
        if name in IGNORED_NODE_TYPES:
            return ""
        if name not in ALLOWED_NODE_TYPES:
            raise ImplementationIdentityError(
                f"unreviewed AST node type {name!r}: refusing to compute an "
                "implementation identity over syntax this canonicaliser has not "
                "been reviewed against. Add it to ALLOWED_NODE_TYPES or "
                "IGNORED_NODE_TYPES and bump IDENTITY_DIGEST_ALGO_VERSION if the "
                "canonical form changed."
            )
        parts = []
        for field in sorted(f for f in node._fields if f not in _LOCATION_FIELDS):
            value = getattr(node, field, None)
            # A field that is None is OMITTED, so that "the interpreter has no
            # such field" and "the field is unset" render identically. This is
            # what makes the canonical form version-independent, and it is not a
            # micro-optimisation: Python 3.13 added `default_value` to TypeVar,
            # ParamSpec and TypeVarTuple (PEP 696), so `type Alias[T] = list[T]`
            # produced a DIFFERENT digest on 3.12 and 3.13 -- measured across both
            # supported versions, not predicted. One commit would have had two
            # measurement identities depending on the cell that computed it.
            #
            # Sound because None means "absent" for every AST field except
            # Constant.value, where None is the literal `None`. That one is
            # carved out below rather than special-cased silently.
            if value is None and not (name == "Constant" and field == "value"):
                continue
            parts.append(f"{field}={canonicalize(value)}")
        return f"{name}({','.join(parts)})"

    if isinstance(node, list):
        return "[" + ",".join(canonicalize(item) for item in node) + "]"

    return _render_leaf(node)


def _render_leaf(value: object) -> str:
    """Render a non-AST field value unambiguously, or refuse.

    Type-tagged on purpose. ``repr`` alone would make the string ``"1"`` and the
    integer ``1`` render identically, so a constant's type would drop out of the
    identity -- and ``x = 1`` and ``x = "1"`` are not the same implementation.
    """
    if value is None:
        return "None"
    if isinstance(value, bool):
        # Before int: bool is a subclass of int, and True must not render as 1.
        return f"bool:{value}"
    if isinstance(value, int):
        return f"int:{value}"
    if isinstance(value, float):
        # repr round-trips floats exactly in CPython, including -0.0 and inf.
        return f"float:{value!r}"
    if isinstance(value, complex):
        return f"complex:{value!r}"
    if isinstance(value, str):
        # Length-prefixed so that concatenation cannot make two different field
        # sequences render alike -- the same class of collision that 6a's
        # whitespace handling had to close.
        return f"str:{len(value)}:{value}"
    if isinstance(value, bytes):
        return f"bytes:{value.hex()}"
    if value is Ellipsis:
        return "Ellipsis"
    raise ImplementationIdentityError(
        f"unreviewed AST field value of type {type(value).__name__!r}: refusing to "
        "compute an implementation identity over a value this canonicaliser cannot "
        "render unambiguously."
    )
