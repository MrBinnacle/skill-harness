"""Build the SERS 1.2.0 delivery block from ingest summaries (#388).

Reads pi_c and exposure from the run's config_json — never recomputes.
The config_json is written once at ingest time (subject/ingest.py) and
immutable thereafter; this function is a reader, not a calculator.
"""

from __future__ import annotations

from typing import Any

# Channel vocabulary — closed, checked for equality against the schema enum in CI.
CHANNEL_DESCRIPTION_ONLY = "description_only"
CHANNEL_BODY_AND_DESCRIPTION = "body_and_description"
CHANNEL_NOT_INSTRUMENTED = "not_instrumented"


def build_delivery(config_json: dict[str, Any]) -> dict[str, Any]:
    """Construct the ``delivery`` block from a run's config_json.

    Reads ``pi_c`` (written by ingest) and any ``exposure`` summary.
    Never recomputes either figure — the receipt carries the ingest's own
    snapshot so the two artefacts stay consistent.

    Parameters
    ----------
    config_json:
        The parsed ``runs.config_json`` dict.  Must contain ``"pi_c"`` with
        at least ``"invocations"`` and ``"hat"`` when the channel is
        ``body_and_description`` or ``description_only``.

    Returns
    -------
    dict
        A conforming ``delivery`` block with ``channel``, ``pi_c``, and
        ``exposure`` keys.
    """
    pi_c_raw = config_json.get("pi_c")
    if not isinstance(pi_c_raw, dict):
        return _not_instrumented_delivery("pi_c absent from config_json")

    invocations = pi_c_raw.get("invocations")
    hat = pi_c_raw.get("hat")

    # Determine channel from pi_c data — the ingest wrote the summary,
    # this function reads it.
    if not isinstance(invocations, int) or not isinstance(hat, (int, float)):
        return _not_instrumented_delivery("pi_c missing invocations or hat")

    channel = CHANNEL_DESCRIPTION_ONLY if invocations == 0 else CHANNEL_BODY_AND_DESCRIPTION

    pi_c = {
        "invocations": pi_c_raw["invocations"],
        "trials": pi_c_raw["trials"],
        "hat": pi_c_raw["hat"],
        "ci_low": pi_c_raw["ci_low"],
        "ci_high": pi_c_raw["ci_high"],
        "confidence": pi_c_raw["confidence"],
        "detector": pi_c_raw["detector"],
    }

    # Exposure is optional — not all ingest paths write it yet (#387).
    exposure_raw = config_json.get("exposure")
    if isinstance(exposure_raw, dict) and "value" in exposure_raw:
        exposure: dict[str, Any] = {"value": exposure_raw["value"]}
        if "passes" in exposure_raw:
            exposure["passes"] = exposure_raw["passes"]
        if "epochs" in exposure_raw:
            exposure["epochs"] = exposure_raw["epochs"]
    else:
        exposure = {"refusal": "not_instrumented"}

    return {
        "channel": channel,
        "pi_c": pi_c,
        "exposure": exposure,
    }


def _not_instrumented_delivery(detail: str) -> dict[str, Any]:
    return {
        "channel": CHANNEL_NOT_INSTRUMENTED,
        "pi_c": {"refusal": "not_instrumented", "detail": detail},
        "exposure": {"refusal": "not_instrumented", "detail": detail},
    }
