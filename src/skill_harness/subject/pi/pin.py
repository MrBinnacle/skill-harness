"""Pi-namespaced harness pin for the Pi paired subject lane.

The Inspect lane pins ``HarnessPin`` (``subject/pin.py``): an Inspect-shaped
record whose fields name Inspect versions, the claude_code agent and its
sandbox. The Pi lane cannot reuse that model without fabricating Inspect
metadata, which the adapter boundary forbids. It also cannot change the
write path, which stores ``harness_pin_json`` / ``harness_pin_fingerprint``
as opaque per-sample strings and checks only that every fingerprint in a
pair is present and identical (``subject/ingest.py::_pin_admissibility``).

So the pin here is a plain mapping in its own ``harness: "pi"`` namespace,
canonicalised with the exact recipe the evidence layer already relies on
(``json.dumps(sort_keys=True)`` + SHA-256 — the same recipe
``HarnessPin.fingerprint`` and ``aggregation/binding.py`` use). Nothing
downstream parses the pin, so a new namespace passes through untouched.

**Treatment membership is not in the pin.** The arms of a paired run are
required to share one fingerprint, so the pin carries the arm-SHARED
baseline roster only. The Full arm's extra roster member (the skill under
test) is the treatment itself; it is declared in the runner block's
``delivery_realization`` and attested per epoch by the roster manifest, and
its description is what the exposure detector looks for. Putting the
treatment member in the pin would make the cross-arm fingerprints differ
by construction and every pair would write inadmissible.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, NamedTuple

__all__ = ["BaselineSkill", "PiHarnessPin"]


class BaselineSkill(NamedTuple):
    """One baseline-roster member as pinned: name, resolved path, content id."""

    name: str
    path: str
    skill_md_sha256: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "path": self.path, "skill_md_sha256": self.skill_md_sha256}


class PiHarnessPin(NamedTuple):
    """The arm-shared identity of one Pi paired epoch.

    Every field is pinned (it affects what the subject saw or how the epoch
    ran) rather than merely recorded. ``runtime_version`` is measured from
    the live Pi binary at launch, never assumed from the install request.
    ``declared_env`` is the complete non-secret environment the epoch
    received; secrets are declared by NAME ONLY — a value never enters the
    pin, because the pin JSON lands in the evidence store.
    """

    harness: str  # always "pi" — the namespace discriminator
    runtime_version: str
    provider: str
    model: str
    thinking_level: str
    tool_allowlist: tuple[str, ...]
    cwd: str
    image_digest: str
    network_policy: str
    declared_env: Mapping[str, str]
    secret_env_names: tuple[str, ...]
    baseline_roster: tuple[BaselineSkill, ...]
    capture_extension_sha256: str

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "runtime_version": self.runtime_version,
            "provider": self.provider,
            "model": self.model,
            "thinking_level": self.thinking_level,
            "tool_allowlist": sorted(self.tool_allowlist),
            "cwd": self.cwd,
            "image_digest": self.image_digest,
            "network_policy": self.network_policy,
            "declared_env": dict(sorted(self.declared_env.items())),
            "secret_env_names": sorted(self.secret_env_names),
            "baseline_roster": [s.as_dict() for s in self.baseline_roster],
            "capture_extension_sha256": self.capture_extension_sha256,
        }

    def canonical_json(self) -> str:
        """The string persisted per sample as ``harness_pin_json``."""
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))

    def fingerprint(self) -> str:
        """SHA-256 over the canonical JSON — same recipe as HarnessPin."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
