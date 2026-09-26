"""#647 render claim level sentences.

Proves the three rendered sentences for the claim level ladder, including
the "(same designer)" qualifier and the negative-side wording.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

from skill_harness.sitegen.render import render_claim_level_sentence

# ---------------------------------------------------------------------------
# AC1 — KEEP sentence
# ---------------------------------------------------------------------------


class TestKeepSentence:
    def test_keep_sentence(self) -> None:
        sentence = render_claim_level_sentence(
            claim_level="KEEP",
            family_replication=1,
            designer="alice",
            designer_independent=False,
        )
        assert "single registration" in sentence.lower()
        assert "scoped" in sentence.lower()

    def test_keep_sentence_ignores_designer(self) -> None:
        """KEEP does not mention designer — it is a single registration."""
        sentence = render_claim_level_sentence(
            claim_level="KEEP",
            family_replication=1,
            designer="alice",
            designer_independent=True,
        )
        assert "alice" not in sentence.lower()


# ---------------------------------------------------------------------------
# AC2 — REPLICATED sentence
# ---------------------------------------------------------------------------


class TestReplicatedSentence:
    def test_replicated_sentence_same_designer(self) -> None:
        sentence = render_claim_level_sentence(
            claim_level="REPLICATED",
            family_replication=2,
            designer="alice",
            designer_independent=False,
        )
        assert "2 families" in sentence
        assert "(same designer)" in sentence
        assert "replicated" in sentence.lower()

    def test_replicated_sentence_independent_designer(self) -> None:
        sentence = render_claim_level_sentence(
            claim_level="REPLICATED",
            family_replication=3,
            designer="bob",
            designer_independent=True,
        )
        assert "3 families" in sentence
        assert "(same designer)" not in sentence
        assert "replicated" in sentence.lower()

    def test_replicated_sentence_program_policy(self) -> None:
        sentence = render_claim_level_sentence(
            claim_level="REPLICATED",
            family_replication=2,
            designer="alice",
            designer_independent=False,
        )
        assert "program policy" in sentence.lower()


# ---------------------------------------------------------------------------
# AC3 — ROBUST sentence
# ---------------------------------------------------------------------------


class TestRobustSentence:
    def test_robust_sentence(self) -> None:
        sentence = render_claim_level_sentence(
            claim_level="ROBUST",
            family_replication=3,
            designer="alice",
            designer_independent=False,
        )
        assert "3 families" in sentence
        assert "robust" in sentence.lower()
        assert "program policy" in sentence.lower()

    def test_robust_sentence_requires_independent(self) -> None:
        """ROBUST mandates at least one independent designer."""
        sentence = render_claim_level_sentence(
            claim_level="ROBUST",
            family_replication=3,
            designer="alice",
            designer_independent=False,
        )
        assert "independent" in sentence.lower()

    def test_robust_sentence_with_independent(self) -> None:
        sentence = render_claim_level_sentence(
            claim_level="ROBUST",
            family_replication=4,
            designer="bob",
            designer_independent=True,
        )
        assert "4 families" in sentence
        assert "robust" in sentence.lower()


# ---------------------------------------------------------------------------
# AC4 — null claim level renders empty
# ---------------------------------------------------------------------------


class TestNullClaimLevel:
    def test_null_claim_level_renders_empty(self) -> None:
        sentence = render_claim_level_sentence(
            claim_level=None,
            family_replication=1,
            designer="alice",
            designer_independent=False,
        )
        assert sentence == ""
