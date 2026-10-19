"""AC4: receipt minting path reads pi_c and exposure from config_json (#388).

build_delivery() reads the ingest-written summaries verbatim. It never
recomputes pi_c or exposure — the receipt carries the same snapshot the
ingest wrote, so the two artefacts stay consistent.

Ingest config_json uses ``pi_c_hat`` (see test_run_config_records_the_pi_c_block).
The SERS delivery block emits ``hat``. Tests feed the live key shape.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from skill_harness.sers.delivery import (
    CHANNEL_BODY_AND_DESCRIPTION,
    CHANNEL_DESCRIPTION_ONLY,
    CHANNEL_NOT_INSTRUMENTED,
    build_delivery,
)

_SCHEMA_PATH = Path("docs/sers/sers.schema.json")


def _load_schema() -> dict[str, Any]:
    loaded = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _ingest_pi_c(
    *,
    invocations: int,
    trials: int,
    pi_c_hat: float,
    ci_low: float,
    ci_high: float,
    confidence: float = 0.95,
    detector: str = "v1-skill-tool-call",
) -> dict[str, Any]:
    """Shape matching runs.config_json as written by subject.ingest."""
    return {
        "detector": detector,
        "invocations": invocations,
        "trials": trials,
        "pi_c_hat": pi_c_hat,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# build_delivery reads config_json — no recomputation
# ---------------------------------------------------------------------------


def test_build_delivery_body_and_description() -> None:
    """With invocations > 0, channel is body_and_description and pi_c values match."""
    config = {
        "pi_c": _ingest_pi_c(
            invocations=5,
            trials=8,
            pi_c_hat=0.625,
            ci_low=0.245,
            ci_high=0.915,
        )
    }
    delivery = build_delivery(config)
    assert delivery["channel"] == CHANNEL_BODY_AND_DESCRIPTION
    pi_c = delivery["pi_c"]
    assert pi_c["invocations"] == 5
    assert pi_c["trials"] == 8
    assert pi_c["hat"] == 0.625
    assert pi_c["ci_low"] == 0.245
    assert pi_c["ci_high"] == 0.915
    assert pi_c["confidence"] == 0.95
    assert pi_c["detector"] == "v1-skill-tool-call"
    assert "pi_c_hat" not in pi_c


def test_build_delivery_description_only() -> None:
    """With invocations == 0, channel is description_only."""
    config = {
        "pi_c": _ingest_pi_c(
            invocations=0,
            trials=8,
            pi_c_hat=0.0,
            ci_low=0.0,
            ci_high=0.369,
        )
    }
    delivery = build_delivery(config)
    assert delivery["channel"] == CHANNEL_DESCRIPTION_ONLY
    assert delivery["pi_c"]["hat"] == 0.0
    assert delivery["pi_c"]["invocations"] == 0


def test_build_delivery_reads_ingest_pi_c_hat_key() -> None:
    """config_json carries pi_c_hat (ingest name); delivery emits hat (SERS name).

    A fixture that invents ``hat`` on config_json would green a reader that never
    touches the live key. This test feeds only the ingest key.
    """
    config = {
        "pi_c": _ingest_pi_c(
            invocations=3,
            trials=10,
            pi_c_hat=0.3,
            ci_low=0.067,
            ci_high=0.652,
        )
    }
    assert "hat" not in config["pi_c"]
    delivery = build_delivery(config)
    assert delivery["pi_c"]["hat"] == config["pi_c"]["pi_c_hat"]
    assert delivery["pi_c"]["invocations"] == config["pi_c"]["invocations"]
    assert delivery["pi_c"]["trials"] == config["pi_c"]["trials"]


def test_build_delivery_reads_not_recomputes() -> None:
    """pi_c values are copied from config_json, not recalculated from counts."""
    config = {
        "pi_c": _ingest_pi_c(
            invocations=3,
            trials=10,
            pi_c_hat=0.3,
            ci_low=0.067,
            ci_high=0.652,
        )
    }
    delivery = build_delivery(config)
    assert delivery["pi_c"]["hat"] == config["pi_c"]["pi_c_hat"]
    assert delivery["pi_c"]["invocations"] == config["pi_c"]["invocations"]
    assert delivery["pi_c"]["trials"] == config["pi_c"]["trials"]


def test_build_delivery_with_exposure() -> None:
    """Exposure data from config_json is carried through."""
    config = {
        "pi_c": _ingest_pi_c(
            invocations=6,
            trials=8,
            pi_c_hat=0.75,
            ci_low=0.349,
            ci_high=0.968,
        ),
        "exposure": {
            "value": 1.0,
            "passes": 8,
            "epochs": 8,
        },
    }
    delivery = build_delivery(config)
    assert delivery["exposure"]["value"] == 1.0
    assert delivery["exposure"]["passes"] == 8
    assert delivery["exposure"]["epochs"] == 8


def test_build_delivery_missing_pi_c_yields_not_instrumented() -> None:
    """config_json without pi_c yields not_instrumented channel."""
    delivery = build_delivery({})
    assert delivery["channel"] == CHANNEL_NOT_INSTRUMENTED
    assert delivery["pi_c"]["refusal"] == "not_instrumented"
    assert delivery["exposure"]["refusal"] == "not_instrumented"


# ---------------------------------------------------------------------------
# Delivery block validates against the schema
# ---------------------------------------------------------------------------


def test_delivery_block_conforms_to_schema() -> None:
    """A build_delivery output validates against the delivery sub-schema."""
    config = {
        "pi_c": _ingest_pi_c(
            invocations=5,
            trials=8,
            pi_c_hat=0.625,
            ci_low=0.245,
            ci_high=0.915,
        )
    }
    delivery = build_delivery(config)
    schema = _load_schema()
    delivery_schema = schema["properties"]["delivery"]
    jsonschema.Draft202012Validator(delivery_schema).validate(delivery)


def test_not_instrumented_delivery_conforms_to_schema() -> None:
    """The not_instrumented refusal shape validates against the schema."""
    delivery = build_delivery({})
    schema = _load_schema()
    delivery_schema = schema["properties"]["delivery"]
    jsonschema.Draft202012Validator(delivery_schema).validate(delivery)
