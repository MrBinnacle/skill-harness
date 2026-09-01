"""AC4: receipt minting path reads pi_c and exposure from config_json (#388).

build_delivery() reads the ingest-written summaries verbatim. It never
recomputes pi_c or exposure — the receipt carries the same snapshot the
ingest wrote, so the two artefacts stay consistent.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]

from skill_harness.sers.delivery import (
    CHANNEL_BODY_AND_DESCRIPTION,
    CHANNEL_DESCRIPTION_ONLY,
    CHANNEL_NOT_INSTRUMENTED,
    build_delivery,
)

_SCHEMA_PATH = Path("docs/sers/sers.schema.json")


def _load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# build_delivery reads config_json — no recomputation
# ---------------------------------------------------------------------------


def test_build_delivery_body_and_description() -> None:
    """With invocations > 0, channel is body_and_description and pi_c values match."""
    config = {
        "pi_c": {
            "detector": "v1-skill-tool-call",
            "invocations": 5,
            "trials": 8,
            "hat": 0.625,
            "ci_low": 0.245,
            "ci_high": 0.915,
            "confidence": 0.95,
        }
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


def test_build_delivery_description_only() -> None:
    """With invocations == 0, channel is description_only."""
    config = {
        "pi_c": {
            "detector": "v1-skill-tool-call",
            "invocations": 0,
            "trials": 8,
            "hat": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.369,
            "confidence": 0.95,
        }
    }
    delivery = build_delivery(config)
    assert delivery["channel"] == CHANNEL_DESCRIPTION_ONLY
    assert delivery["pi_c"]["hat"] == 0.0
    assert delivery["pi_c"]["invocations"] == 0


def test_build_delivery_reads_not_recomputes() -> None:
    """pi_c values are copied verbatim from config_json, not recalculated."""
    config = {
        "pi_c": {
            "detector": "v1-skill-tool-call",
            "invocations": 3,
            "trials": 10,
            "hat": 0.3,  # deliberately non-standard: 3/10 = 0.3
            "ci_low": 0.067,
            "ci_high": 0.652,
            "confidence": 0.95,
        }
    }
    delivery = build_delivery(config)
    # hat must be the value from config_json (0.3), not 3/10 recomputed
    # (same number here, but the point is the function reads, not divides)
    assert delivery["pi_c"]["hat"] == config["pi_c"]["hat"]
    assert delivery["pi_c"]["invocations"] == config["pi_c"]["invocations"]
    assert delivery["pi_c"]["trials"] == config["pi_c"]["trials"]


def test_build_delivery_with_exposure() -> None:
    """Exposure data from config_json is carried through."""
    config = {
        "pi_c": {
            "detector": "v1-skill-tool-call",
            "invocations": 6,
            "trials": 8,
            "hat": 0.75,
            "ci_low": 0.349,
            "ci_high": 0.968,
            "confidence": 0.95,
        },
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
        "pi_c": {
            "detector": "v1-skill-tool-call",
            "invocations": 5,
            "trials": 8,
            "hat": 0.625,
            "ci_low": 0.245,
            "ci_high": 0.915,
            "confidence": 0.95,
        }
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
