"""Tests for the seeded random-subset arm (#667).

Part of the collection-effect screen (#663); blocked on #664's delivered
listing. Per-ticket rule: write the test first, watch it fail for the right
reason, then make it pass. A test that passed before the change pins nothing.

Mock discipline: all API calls mocked at the SDK boundary
(anthropic.Anthropic.messages.create) per A32 precedent. No live calls.
"""

from __future__ import annotations

from skill_harness.ablation.subset_arm import SUBSET_ARM_NAME, draw_subset_arm

# Seeds pinned for AC1: same seed, same subset; these two differ.
_SEED_A = 1729
_SEED_B = 2718

# The exact subset seed 1729 draws from the 14-card package. Pinned so a
# change to the sampling stream fails this assertion instead of silently
# redefining what "the same subset" means.
_EXPECTED_SEED_A = (
    "card-00",
    "card-02",
    "card-06",
    "card-07",
    "card-08",
    "card-10",
    "card-12",
)


def _package(size: int = 14) -> dict[str, str]:
    """A subject package of ``size`` cards in fixed order (name -> description)."""
    return {
        f"card-{i:02d}": f"Description of card {i:02d}: distinct body {i:02d}." for i in range(size)
    }


# ---------------------------------------------------------------------------
# AC1: the same package and seed give the same subset on every call; a
# different seed gives a different subset for a package of 14.
# ---------------------------------------------------------------------------


class TestSameSeedSameSubset:
    def test_same_package_and_seed_give_the_same_subset_on_every_call(self) -> None:
        """AC1: two draws of the same package at the same seed are identical,
        names and assembly bodies alike."""
        package = _package(14)
        first = draw_subset_arm(package, seed=_SEED_A)
        second = draw_subset_arm(package, seed=_SEED_A)

        assert first.seed == second.seed == _SEED_A
        assert first.card_names == second.card_names
        assert first.arm.body_texts == second.arm.body_texts
        assert first.arm.name == second.arm.name == SUBSET_ARM_NAME

    def test_every_drawn_name_is_a_package_card_and_bodies_match(self) -> None:
        """AC1: the subset is drawn from the package; each chosen name carries
        its own description into the assembly body."""
        package = _package(14)
        draw = draw_subset_arm(package, seed=_SEED_A)

        assert set(draw.card_names) <= set(package)
        assert draw.arm.body_texts == tuple(package[name] for name in draw.card_names)

    def test_a_different_seed_gives_a_different_subset_for_a_package_of_14(self) -> None:
        """AC1: seed 1729 and seed 2718 draw different halves of the 14-card package."""
        package = _package(14)
        draw_a = draw_subset_arm(package, seed=_SEED_A)
        draw_b = draw_subset_arm(package, seed=_SEED_B)

        assert draw_a.card_names != draw_b.card_names

    def test_the_pinned_seed_draws_the_pinned_subset(self) -> None:
        """AC1: seed 1729 on the 14-card package draws exactly these names —
        the regression pin for the sampling stream itself."""
        package = _package(14)
        draw = draw_subset_arm(package, seed=_SEED_A)
        assert draw.card_names == _EXPECTED_SEED_A

    def test_the_seed_a_caller_passes_is_the_seed_recorded(self) -> None:
        """AC1: a passed seed is used verbatim; the draw reports it."""
        package = _package(14)
        draw = draw_subset_arm(package, seed=_SEED_A)
        assert draw.seed == _SEED_A
