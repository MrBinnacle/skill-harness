"""A git origin the agent can push to but cannot read (#620).

A policy enforced by a ``pre-receive`` hook means nothing if the agent can
``cat`` the hook, and every file in ``Sample.files`` lands in the agent's own
container. The origin therefore runs as a second compose service: ``origin``
serves a seed directory over ``git://`` and ``default`` (the agent) reaches it
on an ``internal: true`` network with no other route.

The seed is digested when it is read, copied beside the compose file, and the
copy is re-digested before the compose file names it. Two composes built from
seeds that differ only in their bytes (hook present, hook absent) differ only
in the digest, and ``prove_seed_only_twins`` checks exactly that.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from skill_harness.subject.inspect_adapter import (
    compose_directory,
    require_docker_digest_pin,
    write_compose_file,
)
from skill_harness.subject.pin import HarnessPin

_DIGEST_MASK = "<seed-digest>"

# /srv must not be a volume: the daemon serves a per-container copy, so a push
# never writes back to the host seed and epochs cannot contaminate each other.
_ORIGIN_COMPOSE_YAML = """# skill-harness pinned compose (generated from the harness pin)
# Mirrors inspect_ai's auto-compose; image is digest-pinned for admissibility.
# origin sidecar: seed digest {seed}
services:
  default:
    image: "{image}"
    command: "tail -f /dev/null"
    init: true
    networks: [skill-harness-origin]
    depends_on: [origin]
    stop_grace_period: 1s
  origin:
    image: "{image}"
    command: ["sh", "-c", "cp -a /seed/. /srv/ && chmod -R +x /srv/*.git/hooks 2>/dev/null; \
exec git daemon --reuseaddr --export-all --enable=receive-pack --base-path=/srv /srv"]
    init: true
    volumes: ["./origin-seed-{seed}:/seed:ro"]
    networks: [skill-harness-origin]
    stop_grace_period: 1s
networks:
  skill-harness-origin:
    internal: true
"""


class TwinComposeError(ValueError):
    """Two sidecar composes are not twins that differ only in their seed."""


@dataclass(frozen=True)
class OriginSidecar:
    """A seed directory for the origin service, named by its content digest.

    The digest is sha256 over each file's POSIX relative path and bytes, in
    sorted order. Mode bits are excluded because a Windows checkout cannot
    hold them; the sidecar marks hooks executable when it starts.
    """

    seed_dir: Path
    digest: str

    @classmethod
    def from_seed(cls, seed_dir: Path) -> OriginSidecar:
        """Digest ``seed_dir``, which must hold at least one ``*.git`` directory.

        :raises ValueError: ``seed_dir`` is not a directory, holds a symlink,
            or holds no bare repository directory.
        """
        if not seed_dir.is_dir():
            raise ValueError(f"origin seed {seed_dir} is not a directory")
        if not any(p.is_dir() for p in seed_dir.glob("*.git")):
            raise ValueError(f"origin seed {seed_dir} has no *.git bare repository directory")
        return cls(seed_dir=seed_dir, digest=seed_digest(seed_dir))


@dataclass(frozen=True)
class SeedTwinProof:
    """Evidence that two sidecar composes differ only in their seed digest."""

    digest_a: str
    digest_b: str
    masked_sha256: str


def seed_digest(root: Path) -> str:
    """Return the content digest of every file under ``root``.

    :raises ValueError: ``root`` contains a symlink, whose target the digest
        would silently follow.
    """
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError(f"origin seed contains a symlink: {path}")
        if path.is_file():
            data = path.read_bytes()
            rel = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(b"%d:%s%d:" % (len(rel), rel, len(data)))
            digest.update(data)
    return digest.hexdigest()


def write_origin_compose(
    pin: HarnessPin, origin: OriginSidecar, compose_dir: Path | None = None
) -> Path:
    """Write the two-service compose for ``origin`` and copy its seed beside it.

    :raises ValueError: the pin is not a digest-pinned docker pin.
    :raises RuntimeError: the copied seed no longer matches ``origin.digest``
        (the seed changed after ``from_seed``), the copy target is a symlink,
        or the compose file failed its symlink or read-back checks.
    """
    require_docker_digest_pin(pin)
    directory = compose_directory(compose_dir)
    directory.mkdir(parents=True, exist_ok=True)
    seed = origin.digest[:12]
    _copy_seed(origin, directory / f"origin-seed-{seed}")
    content = _ORIGIN_COMPOSE_YAML.format(image=pin.sandbox_image, seed=seed)
    return write_compose_file(directory, content)


def _copy_seed(origin: OriginSidecar, target: Path) -> None:
    if target.is_symlink():
        raise RuntimeError(f"refusing to copy origin seed: {target} is a symlink")
    # A copy left by an earlier call is re-digested, not overwritten: git
    # object files are read-only, and the digest check below settles it.
    if not target.exists():
        shutil.copytree(origin.seed_dir, target)
    copied = seed_digest(target)
    if copied != origin.digest:
        raise RuntimeError(
            f"origin seed digest mismatch: {target} digests to {copied}, "
            f"expected {origin.digest} (was the seed edited after from_seed?)"
        )


def prove_seed_only_twins(
    path_a: Path, origin_a: OriginSidecar, path_b: Path, origin_b: OriginSidecar
) -> SeedTwinProof:
    """Prove two sidecar composes are identical once each seed digest is masked.

    :raises TwinComposeError: the digests are equal (not twins), a compose does
        not name its own seed digest, or the masked texts differ.
    """
    if origin_a.digest == origin_b.digest:
        raise TwinComposeError("both composes name the same seed digest; they are not twins")
    masked_a = _masked_text(path_a, origin_a)
    masked_b = _masked_text(path_b, origin_b)
    if masked_a != masked_b:
        raise TwinComposeError(f"{path_a} and {path_b} differ in more than the seed digest")
    return SeedTwinProof(
        digest_a=origin_a.digest,
        digest_b=origin_b.digest,
        masked_sha256=hashlib.sha256(masked_a).hexdigest(),
    )


def _masked_text(path: Path, origin: OriginSidecar) -> bytes:
    raw = path.read_bytes()
    seed = origin.digest[:12].encode("ascii")
    if seed not in raw:
        raise TwinComposeError(f"{path} does not name its seed digest {origin.digest[:12]}")
    return raw.replace(seed, _DIGEST_MASK.encode("ascii"))
