"""Harness pin — the subject-harness configuration as an evidence-admissibility field.

Published agentic-benchmark experience puts harness-induced variance at 10-20
percentage points on identical model weights — larger than most skill effects.
A trial whose harness configuration is not recorded, or differs between arms,
is therefore inadmissible evidence (v0.2 gate, "Harness pin" row).

The pin is captured from the LIVE environment (installed package versions via
importlib.metadata; the sandbox image digest from the Docker daemon), never
hand-typed — a hand-typed pin is a claim, not a measurement. A digest
reference (``repo@sha256:...``) is the one acceptable pre-resolved input:
it is content-addressed, so the runtime either runs exactly those bits or
fails — an enforceable claim, unlike a floating tag.

Fields (completing the pre-reg "Harness pin" row):
    inspect_ai_version / inspect_swe_version — measured from the live env
    agent_version — exact claude_code version, never "auto"
    model — Inspect model id the bridge routes agent calls to
    sandbox — sandbox type (e.g. "docker")
    sandbox_image — DIGEST-PINNED image reference; the adapter injects this
        into both arms via a generated compose file, so the pin is enforced,
        not merely recorded (Inspect's own default is the floating tag
        "aisiuk/inspect-tool-support")
    cwd — agent working directory; outcome oracles resolve against this
    env — extra environment for the agent process (both arms)
    disallowed_tools — agent tool restrictions (both arms; sorted at capture
        for canonical fingerprinting)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from importlib.metadata import PackageNotFoundError, version

from pydantic import BaseModel, ConfigDict, Field

_UNINSTALLED = "NOT-INSTALLED"

# The image Inspect's auto-generated compose would use (a floating tag).
# We resolve it to a digest at capture time and inject it explicitly.
DEFAULT_SANDBOX_IMAGE = "aisiuk/inspect-tool-support"

_DOCKER_INSPECT_TIMEOUT_S = 60
_DOCKER_PULL_TIMEOUT_S = 600


class HarnessPin(BaseModel):
    """Exact subject-harness configuration for one trial (identical across arms)."""

    model_config = ConfigDict(frozen=True, strict=True)

    inspect_ai_version: str
    inspect_swe_version: str
    agent_version: str  # claude_code(version=...) — an exact version, never "auto"
    model: str  # Inspect model id the bridge routes agent calls to
    sandbox: str  # e.g. "docker"
    sandbox_image: str  # digest-pinned reference: repo@sha256:...
    cwd: str  # agent working directory; outcome oracles resolve against this
    env: dict[str, str] = Field(default_factory=dict)
    disallowed_tools: tuple[str, ...] = ()

    @classmethod
    def capture(
        cls,
        *,
        agent_version: str,
        model: str,
        sandbox: str,
        cwd: str,
        sandbox_image: str = DEFAULT_SANDBOX_IMAGE,
        env: dict[str, str] | None = None,
        disallowed_tools: tuple[str, ...] = (),
    ) -> HarnessPin:
        """Build a pin from the live environment plus the caller's run choices.

        ``sandbox_image`` may be a digest reference (``repo@sha256:...``),
        used as-is, or a tag/name, resolved to its digest via the local
        Docker daemon (pulling if absent).

        :raises ValueError: if ``agent_version`` is "auto" — an unpinned agent
            version cannot yield admissible evidence (the agent could differ
            between arms or between repeats).
        :raises ValueError: if ``sandbox_image`` cannot be resolved to a
            digest (daemon down, image unpullable, or locally-built image
            with no repo digest) — an unpinned image cannot yield admissible
            evidence either.
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
            sandbox_image=resolve_image_digest(sandbox_image),
            cwd=cwd,
            env=dict(env or {}),
            disallowed_tools=tuple(sorted(disallowed_tools)),
        )

    def fingerprint(self) -> str:
        """Stable SHA-256 over the canonical JSON form (arm-equality checks)."""
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_image_digest(image: str) -> str:
    """Resolve an image reference to its digest-pinned form via Docker.

    A reference that already carries ``@sha256:`` is returned as-is
    (content-addressed — enforceable without consulting the daemon).
    Otherwise the local daemon is asked for the image's repo digest,
    pulling the image first if it is not present.

    :raises ValueError: daemon unreachable, image unpullable, or the image
        has no repo digest (e.g. built locally, never pushed) — refuse, per
        the measurement-not-claim rule.
    """
    if "@sha256:" in image:
        return image

    digest = _docker_repo_digest(image)
    if digest is None:
        _docker_pull(image)
        digest = _docker_repo_digest(image)
    if digest is None:
        raise ValueError(
            f"sandbox_image {image!r} has no repo digest even after pull "
            "(locally-built image?) — an unpinned image is inadmissible, "
            "per the v0.2 gate"
        )
    return digest


def _docker_repo_digest(image: str) -> str | None:
    """Return the image's first repo digest, or None if not present locally."""
    result = _run_docker(
        ["docker", "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"],
        timeout=_DOCKER_INSPECT_TIMEOUT_S,
    )
    if result.returncode != 0:
        return None
    digest = result.stdout.strip()
    return digest if "@sha256:" in digest else None


def _docker_pull(image: str) -> None:
    result = _run_docker(["docker", "pull", image], timeout=_DOCKER_PULL_TIMEOUT_S)
    if result.returncode != 0:
        raise ValueError(
            f"cannot pull sandbox_image {image!r}: {result.stderr.strip()[:300]} "
            "— resolve a digest reference manually or start the Docker daemon"
        )


def _run_docker(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    # Fixed argv (no shell, no user-interpolated strings); docker is resolved
    # from PATH by design — the pin measures the operator's live daemon.
    try:
        return subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(
            f"docker unavailable while resolving the sandbox image ({exc}) "
            "— an unpinned image is inadmissible, per the v0.2 gate"
        ) from exc


def _installed_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return _UNINSTALLED
