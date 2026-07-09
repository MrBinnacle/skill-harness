"""Harness pin — the subject-harness configuration as an admissibility field.

Published agentic-benchmark experience puts harness-induced variance at 10-20
percentage points on identical model weights — larger than most skill effects.
A trial whose harness configuration is not recorded, or differs between arms,
is therefore inadmissible evidence (v0.2 gate, "Harness pin" row).

The pin is captured from the LIVE environment (installed package versions via
importlib.metadata), never hand-typed — a hand-typed pin is a claim, not a
measurement.
"""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version

from pydantic import BaseModel, ConfigDict

_UNINSTALLED = "NOT-INSTALLED"


class HarnessPin(BaseModel):
    """Exact subject-harness configuration for one trial (identical across arms)."""

    model_config = ConfigDict(frozen=True, strict=True)

    inspect_ai_version: str
    inspect_swe_version: str
    agent_version: str  # claude_code(version=...) — an exact version, never "auto"
    model: str  # Inspect model id the bridge routes agent calls to
    sandbox: str  # e.g. "docker"
    cwd: str  # agent working directory; outcome oracles resolve against this

    @classmethod
    def capture(cls, *, agent_version: str, model: str, sandbox: str, cwd: str) -> HarnessPin:
        """Build a pin from the live environment plus the caller's run choices.

        :raises ValueError: if ``agent_version`` is "auto" — an unpinned agent
            version cannot yield admissible evidence (the agent could differ
            between arms or between repeats).
        """
        if agent_version == "auto":
            raise ValueError(
                "agent_version='auto' is not pinnable: resolve to an exact "
                "version first (inadmissible otherwise, per the v0.2 gate)"
            )
        return cls(
            inspect_ai_version=_installed_version("inspect-ai"),
            inspect_swe_version=_installed_version("inspect-swe"),
            agent_version=agent_version,
            model=model,
            sandbox=sandbox,
            cwd=cwd,
        )

    def fingerprint(self) -> str:
        """Stable SHA-256 over the canonical JSON form (arm-equality checks)."""
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _installed_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return _UNINSTALLED
