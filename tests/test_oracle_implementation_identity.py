"""Instance 6b of the store-bricking deadlock: oracle self-hash x metric_versions.

Sibling of ``tests/test_store_bricking_deadlock.py``, which owns instance 6a and
its repair (#169). This module owns 6b (#209).

The shape, stated once and identical to 6a: **safeguard A detects that a shipped
file changed; safeguard B forbids correcting the record that would clear it.**
Here safeguard A is ``_oracle_implementation_hash()``, which hashes its own
module's raw bytes, and safeguard B is the append-only ``metric_versions`` row
that pins the registered hash. Editing a comment in ``subject/ingest.py``
therefore refused every further verdict under the registered measurement
identity.

**The remedy is NOT 6a's.** SQL ``--`` comments cannot carry behaviour, so
stripping them is sound. Python docstrings CAN: a threshold, prompt or rubric can
live in one and be read at runtime. The maintainer ruling on #209 is therefore an
**AST-shape identity digest with docstrings preserved as behaviour**:

* comments and formatting are not identity-bearing -- the ``ast`` module discards
  comments outright, so that is a property of the representation rather than a
  stripping pass that could be got wrong;
* docstrings ARE identity-bearing -- they are ordinary ``Expr(Constant(str))``
  nodes and are simply not special-cased out;
* executable code, constants, annotations, decorators, defaults, type comments,
  control flow and imports remain identity-bearing;
* source-location metadata is excluded;
* the raw-byte hash is PRESERVED as the tamper-evidence layer -- the AST digest is
  a second question, never a replacement;
* on raw mismatch with an identical AST digest, a compensating restamp is
  APPENDED; nothing is rewritten or deleted;
* on AST mismatch, parse failure, unsupported syntax or ambiguous
  canonicalisation, the runner FAILS CLOSED;
* the canonicalisation algorithm is versioned, because CPython's AST
  serialisation is not a stable interface across releases.

The test numbering below follows the ruling's ten required tests so the mapping
from decision to evidence is checkable rather than asserted.
"""

from __future__ import annotations

import ast
import hashlib
import sqlite3
from pathlib import Path

import pytest

from skill_harness.storage.models import MetricVersionWrite
from skill_harness.storage.repositories.evidence.metric_identity import (
    DriftClassification,
    append_implementation_restamp,
    classify_implementation_drift,
    effective_implementation_hash,
    record_semantic_digest,
    recorded_semantic_digest,
)
from skill_harness.storage.repositories.evidence.metric_versions import (
    get_metric_version,
    insert_metric_version,
)
from skill_harness.storage.transaction import writer_transaction
from skill_harness.subject.implementation_identity import (
    IDENTITY_DIGEST_ALGO_VERSION,
    ImplementationIdentityError,
    semantic_digest,
)

_METRIC_ID = "subject.outcome.pass_at_1"
_VERSION = "0.3.0"


def _raw(source: str) -> str:
    """The tamper-evidence layer, reproduced here so both digests are visible."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _seed(
    conn: sqlite3.Connection, *, implementation_hash: str, semantic: str | None = None
) -> None:
    """Register a metric identity, optionally with its semantic digest recorded."""
    with writer_transaction(conn):
        insert_metric_version(
            conn,
            MetricVersionWrite(
                metric_id=_METRIC_ID,
                version=_VERSION,
                implementation_hash=implementation_hash,
                tier=1,
                audited=0,
                mechanical_validity_test_passed=1,
                registered_at="2026-08-11T00:00:00.000Z",
            ),
        )
        if semantic is not None:
            record_semantic_digest(
                conn,
                metric_id=_METRIC_ID,
                version=_VERSION,
                implementation_hash=implementation_hash,
                semantic=semantic,
            )


_BASE = '''\
"""Module docstring, behaviour-bearing."""

import os
from typing import Final

THRESHOLD: Final[float] = 0.5


@staticmethod
def score(value: float, *, scale: int = 2) -> bool:
    """Decide the outcome."""
    if value > THRESHOLD:
        return True
    return bool(os.environ.get("X")) and scale > 1
'''


# ---------------------------------------------------------------------------
# Ruling tests 1 and 2 -- commentary and formatting are not identity
# ---------------------------------------------------------------------------


class TestCommentaryIsNotIdentity:
    def test_1_comment_only_edit_keeps_the_identity(self) -> None:
        """Raw digest moves; AST digest does not; the identity stays usable."""
        edited = "# a brand new leading comment\n" + _BASE.replace(
            "    if value > THRESHOLD:", "    # decide it\n    if value > THRESHOLD:"
        )
        assert _raw(edited) != _raw(_BASE), "the edit did not change the raw bytes"
        assert semantic_digest(edited) == semantic_digest(_BASE), (
            "a comment-only edit changed the AST identity digest"
        )

    def test_2_whitespace_and_format_only_edit_keeps_the_identity(self) -> None:
        formatted = _BASE.replace("\n\n", "\n\n\n").replace(
            "def score(value: float, *, scale: int = 2) -> bool:",
            "def score(\n    value: float,\n    *,\n    scale: int = 2,\n) -> bool:",
        )
        assert _raw(formatted) != _raw(_BASE)
        assert semantic_digest(formatted) == semantic_digest(_BASE), (
            "reformatting changed the AST identity digest"
        )

    def test_crlf_line_endings_are_not_identity(self) -> None:
        """Windows checkouts must not mint a different measurement identity.

        CI runs windows-latest as well as ubuntu-latest, so a digest sensitive to
        line endings would make one commit two identities.
        """
        assert semantic_digest(_BASE.replace("\n", "\r\n")) == semantic_digest(_BASE)

    def test_trailing_newline_is_not_identity(self) -> None:
        assert semantic_digest(_BASE.rstrip("\n")) == semantic_digest(_BASE)


# ---------------------------------------------------------------------------
# Ruling tests 3, 4 and 5 -- what MUST remain identity-bearing
# ---------------------------------------------------------------------------


class TestBehaviourIsIdentity:
    def test_3_docstring_edit_changes_the_identity(self) -> None:
        """The ruling's central distinction from 6a.

        A docstring is reachable at runtime through ``__doc__``, so a threshold,
        prompt or rubric can live in one. Treating it as commentary -- which a
        docstring-stripping digest would -- is a hole in the tamper detector, not
        a repair of it.
        """
        for original, replacement in (
            ('"""Module docstring, behaviour-bearing."""', '"""Reworded module docstring."""'),
            ('"""Decide the outcome."""', '"""Decide the outcome, using THRESHOLD."""'),
        ):
            edited = _BASE.replace(original, replacement)
            assert edited != _BASE, f"fixture did not apply: {original}"
            assert semantic_digest(edited) != semantic_digest(_BASE), (
                f"a docstring edit did not change the identity: {original}"
            )

    def test_docstring_removal_changes_the_identity(self) -> None:
        edited = _BASE.replace('    """Decide the outcome."""\n', "")
        assert semantic_digest(edited) != semantic_digest(_BASE)

    def test_4_code_and_constant_edits_change_the_identity(self) -> None:
        cases = {
            "constant value": ("THRESHOLD: Final[float] = 0.5", "THRESHOLD: Final[float] = 0.6"),
            "comparison operator": ("if value > THRESHOLD:", "if value >= THRESHOLD:"),
            "returned value": ("        return True", "        return False"),
            "boolean operator": ("and scale > 1", "or scale > 1"),
            "identifier": ("THRESHOLD: Final[float] = 0.5", "THRESHOLI: Final[float] = 0.5"),
        }
        for label, (original, replacement) in cases.items():
            edited = _BASE.replace(original, replacement)
            assert edited != _BASE, f"fixture did not apply: {label}"
            assert semantic_digest(edited) != semantic_digest(_BASE), (
                f"{label} edit did not change the identity"
            )

    def test_5_decorator_annotation_default_and_import_edits_change_the_identity(self) -> None:
        cases = {
            "decorator": ("@staticmethod", "@classmethod"),
            "annotation": ("value: float", "value: int"),
            "return annotation": ("-> bool:", "-> int:"),
            "default value": ("scale: int = 2", "scale: int = 3"),
            "import": ("import os", "import sys"),
            "from-import": ("from typing import Final", "from typing import Any as Final"),
        }
        for label, (original, replacement) in cases.items():
            edited = _BASE.replace(original, replacement)
            assert edited != _BASE, f"fixture did not apply: {label}"
            assert semantic_digest(edited) != semantic_digest(_BASE), (
                f"{label} edit did not change the identity"
            )

    def test_5b_type_comments_are_identity_bearing(self) -> None:
        """``# type:`` comments are the one comment class that IS behaviour.

        They are only visible to ``ast`` when parsing with ``type_comments=True``,
        so that flag is load-bearing rather than optional. A digest parsed without
        it would report a changed type comment as no change, which is exactly the
        hole the ruling's rule 5 closes.
        """
        base = "x = []  # type: list[int]\n"
        changed = "x = []  # type: list[str]\n"
        assert semantic_digest(base) != semantic_digest(changed), (
            "a type-comment change did not move the identity digest"
        )
        # ...and an ordinary comment on its OWN line is still not identity.
        # Measured, not assumed: a trailing comment on the SAME line is swallowed
        # into the type comment by CPython's parser (``# type: list[int]  # trailing``
        # yields the type_comment string ``"list[int]  # trailing"``), so it does move
        # the digest. That is CPython's tokenisation, not a defect here, and
        # asserting otherwise would be asserting a false claim about the parser.
        assert semantic_digest(base) == semantic_digest("x = []  # type: list[int]\n# noqa\n")

    def test_a_malformed_type_comment_is_still_identity_bearing(self) -> None:
        """CPython captures the type comment verbatim without validating it.

        So ``# type: list[`` is not a parse error -- it is a string field. It
        therefore stays identity-bearing rather than being a hole, which is the
        reason it is NOT in the fail-closed cases above.
        """
        assert semantic_digest("x = []  # type: list[\n") != semantic_digest(
            "x = []  # type: dict[\n"
        )

    def test_star_args_and_keyword_only_structure_is_identity_bearing(self) -> None:
        assert semantic_digest("def f(a, b): pass\n") != semantic_digest("def f(a, *, b): pass\n")

    def test_docstring_whitespace_is_identity_bearing(self) -> None:
        """Inside a string, whitespace is data -- the 6a lesson, carried over.

        6a's first draft collapsed whitespace inside SQL string literals and so
        equated two different CHECK constraints. The analogous mistake here would
        be normalising whitespace inside a docstring.
        """
        assert semantic_digest('"""a  b"""\n') != semantic_digest('"""a b"""\n')


# ---------------------------------------------------------------------------
# Ruling test 6 -- fail closed
# ---------------------------------------------------------------------------


class TestFailsClosed:
    @pytest.mark.parametrize(
        "source",
        [
            "def f(:\n",
            "if True\n    pass\n",
            "x = (1\n",
            "x = '''unterminated\n",
            "def f(): return\treturn\n",
        ],
    )
    def test_6_unparseable_source_fails_closed(self, source: str) -> None:
        """Refusal, never a digest. A digest over unparseable text would be a
        number standing in for an answer nobody computed."""
        with pytest.raises(ImplementationIdentityError):
            semantic_digest(source)

    def test_6b_an_unrecognised_node_type_fails_closed(self) -> None:
        """Syntax this canonicaliser does not know must refuse, not guess.

        The allowlist is what makes a future Python release a loud failure rather
        than a silent identity change. Simulated by removing a node type the
        fixture provably contains.
        """
        from skill_harness.subject import implementation_identity as ident

        assert "Module" in ident.ALLOWED_NODE_TYPES, "fixture assumption broken"
        tree = ast.parse("x = 1\n")
        original = ident.ALLOWED_NODE_TYPES
        try:
            ident.ALLOWED_NODE_TYPES = frozenset(original - {"Assign"})
            with pytest.raises(ImplementationIdentityError, match="Assign"):
                ident.canonicalize(tree)
        finally:
            ident.ALLOWED_NODE_TYPES = original

    def test_6c_the_allowlist_covers_every_node_type_this_interpreter_has(self) -> None:
        """A new Python release adding a node type must fail HERE, deliberately.

        Asserted as frozen-superset-of-interpreter rather than equality: a release
        that REMOVES a deprecated node leaves a harmless extra in the allowlist,
        while a release that ADDS one is caught. This is the test that turns the
        ruling's versioning clause from a promise into a tripwire.
        """
        from skill_harness.subject import implementation_identity as ident

        live = {
            name
            for name, obj in vars(ast).items()
            if isinstance(obj, type) and issubclass(obj, ast.AST) and not name.startswith("_")
        }
        missing = sorted(live - set(ident.ALLOWED_NODE_TYPES) - set(ident.IGNORED_NODE_TYPES))
        assert missing == [], (
            "this interpreter exposes AST node types the canonicaliser has never "
            f"been reviewed against: {missing}. Review each, add it to "
            "ALLOWED_NODE_TYPES or IGNORED_NODE_TYPES, and bump "
            "IDENTITY_DIGEST_ALGO_VERSION if the canonical form changed."
        )


# ---------------------------------------------------------------------------
# Ruling test 10 -- determinism across the supported matrix
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_10_frozen_golden_digests(self) -> None:
        """Frozen expected digests, so CI proves cross-cell determinism.

        This discharges the ruling's "prove stability across the supported Python
        matrix" clause mechanically: all four cells (ubuntu/windows x
        py3.12/py3.13) run this test against the same committed constants, so a
        cell whose ``ast`` produces a different shape fails here instead of
        silently minting a second identity for one commit.

        These constants are RECORDED from a measured run, not derived
        independently, so they are evidence of AGREEMENT and not of correctness --
        the behavioural tests above are what establish correctness. Agreement is
        the property that actually matters for a stored identity.

        NOTE: if this fails after a Python upgrade, do NOT re-freeze the values to
        make it pass. A changed digest means every stored identity in every
        existing store no longer matches. Bump IDENTITY_DIGEST_ALGO_VERSION and
        treat it as a new algorithm, which is what it is.

        The corpus deliberately spans the syntax surface rather than sampling it.
        An earlier version of this test froze three toy cases -- empty source, one
        assignment and the fixture above -- and would have MISSED a real
        divergence: 3.13 added ``default_value`` to ``TypeVar`` (PEP 696), so the
        ``pep695_generics`` case digested differently on 3.12 and 3.13, and none of
        the three toy cases uses a type parameter. A golden test only proves
        agreement over the syntax it actually contains.
        """
        assert IDENTITY_DIGEST_ALGO_VERSION == "ast-shape-1"
        golden = {
            "empty": ("", "2d7ab7ab0b82ebcf10ec9d23293f5f21ae69096f913b3ce6a57f115d75cf9d3d"),
            "assign": (
                "x = 1\n",
                "8dbce3aca1b0adbbcb1050903f1202aea62dbf3d0c20938c833494464e64d9bc",
            ),
            "base_fixture": (
                _BASE,
                "3d5267e3b681f44a42184246df8c080f85d97a7a8ac03fc9cb87c0f0fe90d1aa",
            ),
            "match_stmt": (
                "match x:\n    case [1, 2, *rest]: pass\n    case {'k': v}: pass\n"
                "    case _: pass\n",
                "4737f6531ee519d7d9b858188f0877e4e770aa59bad7f521b9c5df6bf2964a09",
            ),
            "walrus_and_fstring": (
                "if (n := len(s)) > 2:\n    y = f'{n!r:>{w}} tail'\n",
                "a005dc98f59d51eda14d972254e874a45c909d9dbd0c725cf9d30c130135ad79",
            ),
            # The case that caught the 3.12-vs-3.13 divergence. Keep it.
            "pep695_generics": (
                "type Alias[T] = list[T]\ndef f[T](x: T) -> T: return x\n",
                "0b3db5e3aabfb7af1bd9161cffecf8ee70e6c03fe53a7d5ef4a3f5ef5d374e6b",
            ),
            "async_await": (
                "async def g():\n    async with a as b:\n        async for i in c:\n"
                "            await d(i)\n",
                "553a4cf1b6f9e69ae7e91788dde796329df9e3b2d4f29a08550d58889a37cc8e",
            ),
            "try_star": (
                "try:\n    pass\nexcept* ValueError as e:\n    raise\n",
                "2f452ac5de8c55c08d61cea5de8682565c8812b26ea91021af7a2c08abe5bbd4",
            ),
            "decorators_defaults": (
                "@a.b(c=1)\ndef h(p, /, q=2, *args, r=3, **kw) -> None: ...\n",
                "fb43c491ccb7f632b1cb4dd1f65e6692d7db2d99458abf4bf19a7d96dfa1da31",
            ),
            "comprehensions": (
                "z = [i async for i in a if i]\nw = {k: v for k, v in p}\ns = {i for i in q}\n",
                "d1d3e51b8b0f6edc3babb764cd1338910674a4f3dd049bf2d1500064554e776d",
            ),
            "lambda_slices": (
                "f = lambda a=1, *, b=2: a\nv = m[1:2:3, ..., None]\n",
                "72dce9b7c366061a0d74c9c081280df593c6e3eda427b90d9814b2c29f4de8dc",
            ),
            "constants": (
                "a = (1, 1.0, True, None, b'\\x00', 1j, 'x', ...)\n",
                "195512941a920f5a5188433c80058ad5358cd3cd1a9f2b0625a74492919095f2",
            ),
            "type_comment": (
                "x = []  # type: list[int]\n",
                "d9fdf42ae22fe064dc8220049369b907a762463c072f95562f973a84bd4d9524",
            ),
            "nested_class": (
                "class A(B, metaclass=M):\n    '''doc'''\n    __slots__ = ('x',)\n"
                "    def m(self): return super().m()\n",
                "b8e4796f06a0f2ef54e37c6b98470731bdab118fb9af8a329c249813390b3c80",
            ),
            "global_nonlocal_del": (
                "def f():\n    global g\n    del g\n    x = 1\n    def i():\n        nonlocal x\n",
                "04216f99e97c6594fb4f28325f8253dd01187032326160e092d3df38b57e8cdb",
            ),
        }
        actual = {label: semantic_digest(source) for label, (source, _) in golden.items()}
        expected = {label: digest for label, (_, digest) in golden.items()}
        assert actual == expected

    def test_a_none_valued_field_and_an_absent_field_render_alike(self) -> None:
        """The rule that makes the canonical form version-independent.

        3.13's ``TypeVar`` carries ``default_value``; 3.12's does not. Rendering a
        None-valued field as absent is what makes those two agree. Pinned as a
        property so the rule cannot be dropped as an optimisation.
        """
        from skill_harness.subject import implementation_identity as ident

        form = ident.canonical_form("type Alias[T] = list[T]\n")
        assert "=None" not in form, f"a None-valued field leaked into the canonical form: {form}"

    def test_the_none_literal_is_still_distinguishable(self) -> None:
        """The carve-out: for ``Constant``, None is the literal, not an absent field."""
        from skill_harness.subject import implementation_identity as ident

        assert "value=None" in ident.canonical_form("x = None\n")
        assert semantic_digest("x = None\n") != semantic_digest("x = 0\n")
        assert semantic_digest("x = None\n") != semantic_digest("x = False\n")
        assert semantic_digest("x = None\n") != semantic_digest("x = ...\n")

    def test_digest_is_stable_across_repeated_calls(self) -> None:
        assert semantic_digest(_BASE) == semantic_digest(_BASE)

    def test_digest_is_a_sha256_hexdigest(self) -> None:
        digest = semantic_digest(_BASE)
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")


# ---------------------------------------------------------------------------
# The live oracle module -- the file the finding actually names
# ---------------------------------------------------------------------------


class TestAgainstTheRealOracleModule:
    @staticmethod
    def _oracle_source() -> str:
        from skill_harness.subject import ingest as ingest_module

        return Path(ingest_module.__file__).read_text(encoding="utf-8")

    def test_the_real_module_has_a_computable_identity(self) -> None:
        """Fixture evidence is not evidence about the shipped file."""
        assert len(semantic_digest(self._oracle_source())) == 64

    def test_a_comment_edit_to_the_real_module_keeps_its_identity(self) -> None:
        source = self._oracle_source()
        edited = "# an added comment that changes no behaviour\n" + source
        assert _raw(edited) != _raw(source), "the raw tamper digest did not move"
        assert semantic_digest(edited) == semantic_digest(source), (
            "a comment added to the real oracle module changed its identity"
        )

    def test_a_docstring_edit_to_the_real_module_changes_its_identity(self) -> None:
        source = self._oracle_source()
        marker = '"""SHA-256 over this module'
        assert marker in source, "the anchor docstring moved; update this test"
        head, _, tail = source.partition(marker)
        _, _, rest = tail.partition('"""')
        edited = head + '"""Reworded, and therefore a new identity."""' + rest
        assert edited != source, "the docstring edit did not apply"
        assert semantic_digest(edited) != semantic_digest(source)

    def test_the_raw_hash_still_covers_raw_module_bytes(self) -> None:
        """Rule: the raw hash is PRESERVED as the tamper-evidence layer.

        The 6a analogue is ``test_sha_covers_comments_not_just_schema``. If this
        ever fails, the repair has been mistaken for a licence to normalise the
        tamper detector itself.
        """
        from skill_harness.subject import ingest as ingest_module

        assert "Path(__file__).read_bytes()" in self._oracle_source(), (
            "the oracle hash no longer covers raw module bytes"
        )
        assert (
            ingest_module._oracle_implementation_hash()
            == hashlib.sha256(Path(ingest_module.__file__).read_bytes()).hexdigest()
        )


# ---------------------------------------------------------------------------
# Ruling tests 7, 8 and 9 -- the store-level repair
# ---------------------------------------------------------------------------


class TestStoreLevelRepair:
    def test_a_comment_only_drift_is_classified_restampable(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        semantic = semantic_digest(_BASE)
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic)

        edited = "# comment only\n" + _BASE
        verdict = classify_implementation_drift(
            evidence_db,
            metric_id=_METRIC_ID,
            version=_VERSION,
            recorded_hash=_raw(_BASE),
            live_hash=_raw(edited),
            live_semantic=semantic_digest(edited),
        )
        assert verdict.restampable is True, verdict.reason
        assert verdict.superseded_hash == _raw(_BASE)

    def test_a_docstring_drift_is_refused(self, evidence_db: sqlite3.Connection) -> None:
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic_digest(_BASE))

        edited = _BASE.replace('"""Decide the outcome."""', '"""Changed."""')
        verdict = classify_implementation_drift(
            evidence_db,
            metric_id=_METRIC_ID,
            version=_VERSION,
            recorded_hash=_raw(_BASE),
            live_hash=_raw(edited),
            live_semantic=semantic_digest(edited),
        )
        assert verdict.restampable is False
        assert "differ" in verdict.reason.lower()

    def test_an_identity_never_recorded_is_refused(self, evidence_db: sqlite3.Connection) -> None:
        """A store registered before this repair holds no evidence the edit was harmless."""
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=None)

        edited = "# comment only\n" + _BASE
        verdict = classify_implementation_drift(
            evidence_db,
            metric_id=_METRIC_ID,
            version=_VERSION,
            recorded_hash=_raw(_BASE),
            live_hash=_raw(edited),
            live_semantic=semantic_digest(edited),
        )
        assert verdict.restampable is False
        assert "no semantic digest" in verdict.reason.lower()

    def test_7_repeated_restamping_is_idempotent(self, evidence_db: sqlite3.Connection) -> None:
        """Latest restamp wins, so a later open sees no drift at all."""
        semantic = semantic_digest(_BASE)
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic)
        edited = "# comment only\n" + _BASE

        for _ in range(3):
            live_hash = _raw(edited)
            in_force = effective_implementation_hash(
                evidence_db,
                metric_id=_METRIC_ID,
                version=_VERSION,
                ledger_hash=_raw(_BASE),
            )
            if in_force == live_hash:
                continue
            verdict = classify_implementation_drift(
                evidence_db,
                metric_id=_METRIC_ID,
                version=_VERSION,
                recorded_hash=_raw(_BASE),
                live_hash=live_hash,
                live_semantic=semantic_digest(edited),
            )
            assert verdict.restampable, verdict.reason
            with writer_transaction(evidence_db):
                append_implementation_restamp(evidence_db, verdict)

        rows = evidence_db.execute(
            "SELECT superseded_hash, implementation_hash FROM metric_implementation_restamps"
        ).fetchall()
        assert len(rows) == 1, f"restamping was not idempotent: {rows}"
        assert rows[0][0] == _raw(_BASE)
        assert rows[0][1] == _raw(edited)
        assert effective_implementation_hash(
            evidence_db, metric_id=_METRIC_ID, version=_VERSION, ledger_hash=_raw(_BASE)
        ) == _raw(edited)

    def test_the_original_metric_row_is_never_rewritten(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        semantic = semantic_digest(_BASE)
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic)
        edited = "# comment only\n" + _BASE
        verdict = classify_implementation_drift(
            evidence_db,
            metric_id=_METRIC_ID,
            version=_VERSION,
            recorded_hash=_raw(_BASE),
            live_hash=_raw(edited),
            live_semantic=semantic_digest(edited),
        )
        with writer_transaction(evidence_db):
            append_implementation_restamp(evidence_db, verdict)

        row = get_metric_version(evidence_db, _METRIC_ID, _VERSION)
        assert row is not None
        assert row["implementation_hash"] == _raw(_BASE), (
            "the append-only metric_versions row was modified by the repair"
        )

    def test_8_the_new_tables_are_append_only(self, evidence_db: sqlite3.Connection) -> None:
        """Safeguard B is not relaxed, and the correction ledger is itself protected."""
        semantic = semantic_digest(_BASE)
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic)

        for table in ("metric_semantic_digests", "metric_implementation_restamps"):
            triggers = {
                row[0]
                for row in evidence_db.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                    (table,),
                ).fetchall()
            }
            assert any("no_update" in t for t in triggers), f"{table} lost its UPDATE guard"
            assert any("no_delete" in t for t in triggers), f"{table} lost its DELETE guard"

        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            evidence_db.execute("UPDATE metric_semantic_digests SET semantic_digest = 'x'")
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            evidence_db.execute("DELETE FROM metric_semantic_digests")

    def test_8b_metric_versions_keeps_its_append_only_triggers(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        # A row must exist first: an UPDATE or DELETE matching zero rows never
        # fires a BEFORE trigger, so an unseeded version of this test would pass
        # while asserting nothing. (It did, until it was caught.)
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic_digest(_BASE))
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            evidence_db.execute("UPDATE metric_versions SET implementation_hash = 'corrected'")
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            evidence_db.execute("DELETE FROM metric_versions")

    def test_9_a_version_bump_still_mints_a_new_identity(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """The named escape is not this repair, and must not be confused with it.

        Bumping the version declares a NEW measurement identity: evidence either
        side is no longer the same measurement. The repair, by contrast, keeps the
        identity and records that the bytes moved without the behaviour moving.
        The observable difference asserted here is that a bump inherits none of the
        old version's bookkeeping, so a drift against it is refused rather than
        silently clearing itself on the old version's evidence.
        """
        semantic = semantic_digest(_BASE)
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic)

        bumped = "0.4.0"
        bumped_source = _BASE + "\nEXTRA = 1\n"
        with writer_transaction(evidence_db):
            insert_metric_version(
                evidence_db,
                MetricVersionWrite(
                    metric_id=_METRIC_ID,
                    version=bumped,
                    implementation_hash=_raw(bumped_source),
                    tier=1,
                    audited=0,
                    mechanical_validity_test_passed=1,
                    registered_at="2026-08-11T01:00:00.000Z",
                ),
            )

        # Two distinct identities coexist; neither was corrected into the other.
        assert get_metric_version(evidence_db, _METRIC_ID, _VERSION) is not None
        assert get_metric_version(evidence_db, _METRIC_ID, bumped) is not None
        assert (
            recorded_semantic_digest(
                evidence_db,
                metric_id=_METRIC_ID,
                version=bumped,
                implementation_hash=_raw(_BASE),
            )
            is None
        )
        verdict = classify_implementation_drift(
            evidence_db,
            metric_id=_METRIC_ID,
            version=bumped,
            recorded_hash=_raw(bumped_source),
            live_hash=_raw(_BASE),
            live_semantic=semantic,
        )
        assert verdict.restampable is False, (
            "a version bump inherited the old version's semantic evidence"
        )

    def test_the_restamp_records_the_algorithm_version(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """A digest is only comparable against digests from the same algorithm.

        Without the recorded version, a future algorithm change would compare new
        digests against old ones and read every store as drifted -- or worse,
        collide and restamp something it should have refused.
        """
        semantic = semantic_digest(_BASE)
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic)
        stored = evidence_db.execute(
            "SELECT digest_algo_version FROM metric_semantic_digests"
        ).fetchone()
        assert stored[0] == IDENTITY_DIGEST_ALGO_VERSION

    def test_a_digest_from_another_algorithm_version_is_refused(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """Fail closed on ambiguous canonicalisation, per the ruling."""
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic_digest(_BASE))
        with writer_transaction(evidence_db):
            evidence_db.execute(
                "INSERT INTO metric_semantic_digests (metric_id, version, implementation_hash, "
                "semantic_digest, digest_algo_version, recorded_at) VALUES (?,?,?,?,?,?)",
                (
                    _METRIC_ID,
                    _VERSION,
                    "otherhash",
                    semantic_digest(_BASE),
                    "ast-shape-0-obsolete",
                    "2026-08-11T02:00:00.000Z",
                ),
            )
        verdict = classify_implementation_drift(
            evidence_db,
            metric_id=_METRIC_ID,
            version=_VERSION,
            recorded_hash="otherhash",
            live_hash=_raw(_BASE),
            live_semantic=semantic_digest(_BASE),
        )
        assert verdict.restampable is False
        assert "algorithm" in verdict.reason.lower()


class TestEndToEndThroughThePublicSurface:
    """The behavioural requirement, expressed without importing anything new.

    These are the tests that are RED on ``main`` for the right reason rather than
    for a missing import. The trick is to patch only the RAW hash: that is exactly
    what a comment-only edit does to the real module -- the bytes move, the AST
    does not -- so the live semantic digest stays genuinely unchanged and no
    stubbing of the new mechanism is involved.
    """

    # The audit-metric act is deliberately restricted to the subject scorers that
    # carry mechanical-validity evidence (PAIRED_FREEZE_BINARY_METRIC_IDS), so
    # these tests must use one of those rather than the synthetic id above.
    AUDIT_METRIC_ID = "subject:file_contains"

    @classmethod
    def _register(cls, conn: sqlite3.Connection) -> None:
        from skill_harness.storage.repositories.evidence.metric_versions import (
            register_audited_metric,
        )

        register_audited_metric(conn, cls.AUDIT_METRIC_ID)

    def test_a_comment_only_edit_to_the_oracle_must_not_refuse(
        self, evidence_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED on main: refuses with implementation drift. GREEN after the repair."""
        from skill_harness.storage.repositories.evidence import metric_versions as mv
        from skill_harness.subject import ingest as ingest_module

        self._register(evidence_db)

        real_hash = ingest_module._oracle_implementation_hash()
        drifted = hashlib.sha256((real_hash + "comment").encode("utf-8")).hexdigest()
        monkeypatch.setattr(ingest_module, "_oracle_implementation_hash", lambda: drifted)

        plan = mv.plan_audited_metric_registration(evidence_db, self.AUDIT_METRIC_ID)
        assert plan.action == "restamp", (
            "a byte-only change to the oracle module refused the registered identity"
        )

        # Executing the act appends the correction, and the identity is then
        # settled: a second pass sees no drift at all.
        mv.register_audited_metric(evidence_db, self.AUDIT_METRIC_ID)
        assert (
            evidence_db.execute("SELECT COUNT(*) FROM metric_implementation_restamps").fetchone()[0]
            == 1
        )
        assert mv.plan_audited_metric_registration(evidence_db, self.AUDIT_METRIC_ID).action == (
            "already_audited"
        )

    def test_a_behaviour_change_to_the_oracle_still_refuses(
        self, evidence_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other side: safeguard A must still fire on a real change.

        Both hashes are moved, which is what a behaviour change does. If this ever
        stops raising, the repair has become a bypass.
        """
        from skill_harness.storage.repositories.evidence import metric_versions as mv
        from skill_harness.subject import ingest as ingest_module

        self._register(evidence_db)

        monkeypatch.setattr(ingest_module, "_oracle_implementation_hash", lambda: "0" * 64)
        monkeypatch.setattr(ingest_module, "_oracle_semantic_digest", lambda: "1" * 64)

        with pytest.raises(ValueError, match="drift"):
            mv.plan_audited_metric_registration(evidence_db, self.AUDIT_METRIC_ID)


class TestClassificationIsReadOnly:
    def test_classify_writes_nothing(self, evidence_db: sqlite3.Connection) -> None:
        """``plan_audited_metric_registration`` is documented read-only and calls this.

        Asserted by forbidding writes at the connection level, which is the only
        form of this assertion that cannot be satisfied by accident.
        """
        _seed(evidence_db, implementation_hash=_raw(_BASE), semantic=semantic_digest(_BASE))
        edited = "# comment only\n" + _BASE
        evidence_db.execute("PRAGMA query_only = ON")
        try:
            verdict = classify_implementation_drift(
                evidence_db,
                metric_id=_METRIC_ID,
                version=_VERSION,
                recorded_hash=_raw(_BASE),
                live_hash=_raw(edited),
                live_semantic=semantic_digest(edited),
            )
            assert isinstance(verdict, DriftClassification)
        finally:
            evidence_db.execute("PRAGMA query_only = OFF")
