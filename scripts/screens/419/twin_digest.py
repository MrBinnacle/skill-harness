"""#620: refuse a twin-world pair whose agent-visible surfaces differ.

The agent sees three things: the project tree (``.git`` included), the prompt
file, and the ``default`` service of the compose. Each world's surface is
digested over exactly those, and the pair is refused unless the two digests
match. The ``origin`` service is not on the surface; ``prove_seed_only_twins``
checks that the two composes differ only in the seed digest the origin names.

Run: python scripts/screens/419/twin_digest.py --fixture <v4 fixture dir> --prompt <prompt file>
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from skill_harness.subject import (
    OriginSidecar,
    TwinComposeError,
    prove_seed_only_twins,
)
from skill_harness.subject.origin_sidecar import seed_digest, write_origin_compose
from skill_harness.subject.pin import HarnessPin

__all__ = [
    "TwinComposeError",
    "TwinProof",
    "TwinWorldError",
    "default_stanza",
    "prove_twin_worlds",
    "remove_tree",
    "visible_digest",
]

LIVE_IMAGE = (
    "aisiuk/inspect-tool-support@sha256:"
    "fb045da8203aea656785c758f7147b003cfe21f213e9048a38be0a33242a5b3d"
)


class TwinWorldError(ValueError):
    """The two worlds do not present one agent-visible surface."""


@dataclass(frozen=True)
class TwinProof:
    visible_a: str
    visible_b: str
    seed_a: str
    seed_b: str
    masked_compose_sha256: str
    compose_a: Path
    compose_b: Path


def default_stanza(compose_text: str) -> str:
    """Return the ``default`` service block: its key line and every deeper line."""
    lines = compose_text.splitlines(keepends=True)
    try:
        start = lines.index("  default:\n")
    except ValueError:
        raise TwinWorldError("compose has no '  default:' service stanza") from None
    end = start + 1
    while end < len(lines) and lines[end].startswith("    "):
        end += 1
    return "".join(lines[start:end])


def visible_digest(project: Path, prompt: Path, compose: Path) -> str:
    """sha256 over the project tree digest, the prompt bytes and the default stanza."""
    digest = hashlib.sha256()
    for part in (
        seed_digest(project).encode("ascii"),
        prompt.read_bytes(),
        default_stanza(compose.read_text(encoding="utf-8")).encode("utf-8"),
    ):
        digest.update(b"%d:" % len(part))
        digest.update(part)
    return digest.hexdigest()


def prove_twin_worlds(
    pin: HarnessPin,
    *,
    project_a: Path,
    seed_a: Path,
    project_b: Path,
    seed_b: Path,
    prompt: Path,
    work_dir: Path,
) -> TwinProof:
    """Write each world's compose under ``work_dir`` and prove the pair are twins.

    :raises TwinComposeError: the composes differ in more than the seed digest,
        or the seeds are identical.
    :raises TwinWorldError: the visible digests differ.
    """
    origin_a = OriginSidecar.from_seed(seed_a)
    origin_b = OriginSidecar.from_seed(seed_b)
    compose_a = write_origin_compose(pin, origin_a, compose_dir=work_dir / "compose-world-a")
    compose_b = write_origin_compose(pin, origin_b, compose_dir=work_dir / "compose-world-b")
    compose_proof = prove_seed_only_twins(compose_a, origin_a, compose_b, origin_b)
    visible_a = visible_digest(project_a, prompt, compose_a)
    visible_b = visible_digest(project_b, prompt, compose_b)
    if visible_a != visible_b:
        raise TwinWorldError(f"visible surfaces differ: world a {visible_a}, world b {visible_b}")
    return TwinProof(
        visible_a=visible_a,
        visible_b=visible_b,
        seed_a=origin_a.digest,
        seed_b=origin_b.digest,
        masked_compose_sha256=compose_proof.masked_sha256,
        compose_a=compose_a,
        compose_b=compose_b,
    )


def remove_tree(root: Path) -> None:
    """Remove ``root`` even where git left its object files read-only."""

    def _writable_then_retry(func: object, path: str, _exc: BaseException) -> None:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        os.unlink(path)

    shutil.rmtree(root, onexc=_writable_then_retry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    args = parser.parse_args(argv)
    pin = HarnessPin.capture(
        agent_version="2.1.197",
        model="none/none",
        sandbox="docker",
        cwd="/root",
        sandbox_image=LIVE_IMAGE,
    )
    project = args.fixture / "project"
    work = Path(tempfile.mkdtemp(prefix="twin-digest-"))
    try:
        proof = prove_twin_worlds(
            pin,
            project_a=project,
            seed_a=args.fixture / "seed-world-a",
            project_b=project,
            seed_b=args.fixture / "seed-world-b",
            prompt=args.prompt,
            work_dir=work,
        )
    except (TwinComposeError, TwinWorldError) as exc:
        print(f"REFUSED: {exc}")
        return 1
    finally:
        remove_tree(work)
    print(f"PASS: visible digest {proof.visible_a} for both worlds")
    print(f"      seed a {proof.seed_a}  seed b {proof.seed_b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
