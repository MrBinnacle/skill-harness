"""Budget / cost reconciliation tests — falsification-plan item 7.

Property: every model that appears in the evidence store's samples table
must have a corresponding row in PRICE_PER_MTOK.  A missing row means the
reconciler and frontier projections cannot price that model's spend, and
the budget gate is blind to its cost.

Detection of pricing-table drift vs vendor: if a model is used in
production evidence but lacks a price row, project_pair_usd /
project_trial_usd raise KeyError, and cost projections return REFUSED.
This test catches that gap at test time, before merge.
"""

from __future__ import annotations

import os
import sqlite3

import pytest


def test_pythonhashseed_set() -> None:
    assert os.environ.get("PYTHONHASHSEED") == "0", (
        "PYTHONHASHSEED must be set to 0 for deterministic tests. Run with: PYTHONHASHSEED=0 pytest"
    )


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from skill_harness.ablation.subject import (  # noqa: E402
    PRICE_PER_MTOK,
    resolve_price_key,
)
from skill_harness.oracles.calibration.cost_projection import (  # noqa: E402
    project_pair_usd,
    project_trial_usd,
)
from skill_harness.storage.models import RunWrite, SkillWrite  # noqa: E402
from skill_harness.storage.repositories.evidence import (  # noqa: E402
    runs as runs_repo,
)
from skill_harness.storage.repositories.evidence import (  # noqa: E402
    skills as skills_repo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHA = "a" * 64
_TS = "2026-07-10T12:00:00.000Z"


def _seed_evidence_prereqs(conn: sqlite3.Connection) -> None:
    """Insert the FK chain required for samples rows: skills -> runs."""
    skills_repo.insert_skill(
        conn,
        SkillWrite(
            skill_id="skill-1",
            name="Test",
            source_path="/x",
            source_sha256=_SHA,
            imported_at=_TS,
        ),
    )
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "clause-1",
            "skill-1",
            0,
            0,
            "Test clause",
            "citation_support",
            "increase",
            1,
            "none",
            _TS,
        ),
    )
    runs_repo.insert_run(
        conn,
        RunWrite(
            run_id="run-1",
            skill_id="skill-1",
            run_kind="ablation",
            config_json="{}",
            started_at=_TS,
            completed_at=None,
        ),
    )


def _insert_sample(
    conn: sqlite3.Connection,
    *,
    run_id: str = "run-1",
    clause_id: str = "clause-1",
    subject_model: str = "claude-sonnet-5",
    sample_id: str = "s1",
    sample_index: int = 0,
) -> None:
    """Insert a minimal evidence sample row (prereqs must already exist)."""
    conn.execute(
        "INSERT INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, output_text, "
        "output_sha256, sampled_at, sample_index) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (sample_id, run_id, clause_id, "full", subject_model, "text", _SHA, _TS, sample_index),
    )


# ---------------------------------------------------------------------------
# Drift-guard: every evidence-store model must have a price row
# ---------------------------------------------------------------------------


class TestPricingTableCoversEvidenceModels:
    """Falsification-plan item 7 (supply-chain: pricing-table drift vs vendor).

    If a model appears in evidence.samples but has no PRICE_PER_MTOK entry,
    project_pair_usd / project_trial_usd raise KeyError and cost projections
    return REFUSED.  This class catches that gap: insert a sample, then
    assert the projection functions succeed for that model.
    """

    def test_sonnet_5_has_price_row(self, evidence_db: sqlite3.Connection) -> None:
        """claude-sonnet-5 evidence must be priceable (the 2026-07-10 paired run)."""
        _seed_evidence_prereqs(evidence_db)
        _insert_sample(evidence_db, subject_model="claude-sonnet-5")

        models = {
            row[0]
            for row in evidence_db.execute("SELECT DISTINCT subject_model FROM samples").fetchall()
        }
        assert "claude-sonnet-5" in models

        # This is the drift guard: if the price row is missing, KeyError.
        usd_pair = project_pair_usd(
            "claude-sonnet-5",
            input_tokens_per_pair=486212.75,
            output_tokens_per_pair=54777.625,
        )
        assert usd_pair > 0

        usd_trial = project_trial_usd(
            "claude-sonnet-5",
            input_tokens_per_trial=249623.25,
            output_tokens_per_trial=29456,
        )
        assert usd_trial > 0

    def test_provider_prefixed_sonnet_5_is_priceable(self, evidence_db: sqlite3.Connection) -> None:
        """The routed form the production store records must price (#302).

        Both runs that anchor the collection's cost projections were made
        through the OpenRouter fallback, so ``samples.subject_model`` holds
        ``anthropic/claude-sonnet-5``, not ``claude-sonnet-5``. Seeding the
        bare name (the #299 guard) never exercises that string.
        """
        prefixed = "anthropic/claude-sonnet-5"

        _seed_evidence_prereqs(evidence_db)
        _insert_sample(evidence_db, subject_model=prefixed)

        models = {
            row[0]
            for row in evidence_db.execute("SELECT DISTINCT subject_model FROM samples").fetchall()
        }
        assert prefixed in models
        assert prefixed not in PRICE_PER_MTOK, (
            "The canonical pricing key is the bare vendor name; a provider-prefixed "
            "row would defeat the normalisation this test guards."
        )

        usd_pair = project_pair_usd(
            prefixed,
            input_tokens_per_pair=486212.75,
            output_tokens_per_pair=54777.625,
        )
        assert usd_pair > 0

        usd_trial = project_trial_usd(
            prefixed,
            input_tokens_per_trial=249623.25,
            output_tokens_per_trial=29456,
        )
        assert usd_trial > 0

        # Canonical form (a): the route does not change the price, so the
        # prefixed identifier must project the same USD as the bare one.
        assert usd_pair == project_pair_usd(
            "claude-sonnet-5",
            input_tokens_per_pair=486212.75,
            output_tokens_per_pair=54777.625,
        )
        assert usd_trial == project_trial_usd(
            "claude-sonnet-5",
            input_tokens_per_trial=249623.25,
            output_tokens_per_trial=29456,
        )

    def test_unknown_model_behind_provider_prefix_raises_keyerror(self) -> None:
        """Stripping the route must not widen the lookup: the model still has to exist."""
        with pytest.raises(KeyError):
            project_pair_usd(
                "anthropic/claude-nonexistent-model",
                input_tokens_per_pair=1000,
                output_tokens_per_pair=100,
            )

    def test_all_evidence_models_are_priceable(self, evidence_db: sqlite3.Connection) -> None:
        """Every model in the evidence store must have a PRICE_PER_MTOK row."""
        _seed_evidence_prereqs(evidence_db)

        # Seed evidence with the models used across the test suite, in both
        # forms the production store actually carries: the bare vendor name,
        # and the routed 'provider/model' form the OpenRouter fallback writes.
        known_models = [
            "claude-sonnet-4-6",
            "claude-opus-4-7",
            "claude-sonnet-5",
            "gpt-5.5",
            "anthropic/claude-sonnet-5",
        ]
        for i, model in enumerate(known_models):
            _insert_sample(evidence_db, subject_model=model, sample_id=f"s{i}", sample_index=i)

        evidence_models = {
            row[0]
            for row in evidence_db.execute("SELECT DISTINCT subject_model FROM samples").fetchall()
        }

        missing = {
            model for model in evidence_models if resolve_price_key(model) not in PRICE_PER_MTOK
        }
        assert not missing, (
            f"Models in evidence store without a PRICE_PER_MTOK row: {missing}. "
            f"Add rows to skill_harness.ablation.subject.PRICE_PER_MTOK before merging."
        )

    def test_unknown_model_raises_keyerror(self) -> None:
        """Inverse guard: a model NOT in PRICE_PER_MTOK must raise, not default-price."""
        with pytest.raises(KeyError):
            project_pair_usd(
                "claude-nonexistent-model",
                input_tokens_per_pair=1000,
                output_tokens_per_pair=100,
            )
