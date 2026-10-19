"""#621: the leak audit and seed audit for the silent cue pair, world A+cue and world B.

World A+cue is meant to be visible to the agent through exactly one file, the trace. The leak
audit compares the two projects path by path and passes only when world B's project equals the v4
reference and world A+cue's project differs from world B's in the trace alone, then proves the two
composes differ only in the origin seed.

The seed audit checks the origin is silent (S475): neither seed holds a hook, so origin accepts
every push; world B's seed is v4's ``seed-off``; world A+cue's is ``seed-off`` plus v4's
``attested.txt``. The attestation is read by nothing at origin; it is there for the hunt's
positive control. The consequence oracle scores the world from the SHAs it is given.

Run: PYTHONPATH=src python scripts/screens/419/cue_audit.py [--fixture-root DIR] [--v4-root DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from twin_digest import LIVE_IMAGE, remove_tree, visible_digest

from skill_harness.subject import OriginSidecar, TwinComposeError, prove_seed_only_twins
from skill_harness.subject.origin_sidecar import write_origin_compose
from skill_harness.subject.pin import HarnessPin

GITPULL = Path("C:/Users/mlpgr/2026_Projects/skill-harness/.private/microrun/batch1/gitpull")
FIXTURE_ROOT_DEFAULT = GITPULL / "v5-cue"
V4_ROOT_DEFAULT = GITPULL / "v4"
TRACE = "release-manifest.json"
PROMPT = "prompt_v4.txt"


class CueLeakError(ValueError):
    """The cue pair differs in something other than the named trace."""


@dataclass(frozen=True)
class CueAudit:
    b_vs_reference: tuple[str, ...]
    cue_vs_b: tuple[str, ...]
    trace: str

    @property
    def failures(self) -> tuple[str, ...]:
        found: list[str] = []
        if self.b_vs_reference:
            found.append(f"world B differs from the v4 reference at {list(self.b_vs_reference)}")
        if self.cue_vs_b != (self.trace,):
            found.append(
                f"world A+cue differs from world B at {list(self.cue_vs_b)}; "
                f"expected only the trace {self.trace!r}"
            )
        return tuple(found)


@dataclass(frozen=True)
class CueProof:
    audit: CueAudit
    visible_cue: str
    visible_b: str
    visible_cue_without_trace: str
    seed_a: str
    seed_b: str
    compose_a: Path
    compose_b: Path


ATTESTATION = "attested.txt"


def path_hashes(project: Path) -> dict[str, str]:
    """sha256 of every file under ``project``, ``.git`` included, keyed by its posix path.

    :raises CueLeakError: ``project`` holds a symlink, whose target a hash would silently follow.
    """
    hashes: dict[str, str] = {}
    for path in sorted(project.rglob("*")):
        if path.is_symlink():
            raise CueLeakError(f"project contains a symlink: {path}")
        if path.is_file():
            hashes[path.relative_to(project).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return hashes


def surface_diff(left: Mapping[str, str], right: Mapping[str, str]) -> tuple[str, ...]:
    """Every path present on one side only, or present on both with different content."""
    return tuple(sorted(p for p in left.keys() | right.keys() if left.get(p) != right.get(p)))


def audit_cue_pair(
    *,
    reference: Mapping[str, str],
    plain: Mapping[str, str],
    cue: Mapping[str, str],
    trace: str,
) -> CueAudit:
    """Compare world B (``plain``) with the v4 ``reference`` and world A+cue with world B."""
    return CueAudit(
        b_vs_reference=surface_diff(plain, reference),
        cue_vs_b=surface_diff(cue, plain),
        trace=trace,
    )


def seed_findings(
    *, seed_a: Path, seed_b: Path, seed_off: Path, attestation: Path
) -> tuple[str, ...]:
    """Every way the two seeds depart from the silent world; empty when both are silent.

    ``seed_off`` is v4's hookless seed and ``attestation`` is v4's ``attested.txt``.
    """
    off = path_hashes(seed_off)
    seeds = {"A": path_hashes(seed_a), "B": path_hashes(seed_b)}
    found: list[str] = []
    for label, hashes in seeds.items():
        hooks = sorted(p for p in hashes if p.split("/")[-2:-1] == ["hooks"])
        if hooks:
            found.append(f"world {label} seed holds a hook at {hooks}")
    b_diff = surface_diff(seeds["B"], off)
    if b_diff:
        found.append(f"world B seed differs from v4 seed-off at {list(b_diff)}")
    a_diff = surface_diff(seeds["A"], off)
    if a_diff != (ATTESTATION,):
        found.append(
            f"world A seed differs from v4 seed-off at {list(a_diff)}; "
            f"expected only {[ATTESTATION]}"
        )
    elif seeds["A"][ATTESTATION] != hashlib.sha256(attestation.read_bytes()).hexdigest():
        found.append(f"world A seed's {ATTESTATION} is not v4's attestation")
    return tuple(found)


def prove_cue_twins(
    pin: HarnessPin,
    *,
    reference_project: Path,
    project_cue: Path,
    seed_a: Path,
    project_b: Path,
    seed_b: Path,
    prompt: Path,
    work_dir: Path,
    trace: str = TRACE,
) -> CueProof:
    """Audit the projects path by path, then prove the rest of the visible surface matches.

    The seeds are not judged here; ``seed_findings`` does that, so the gate's negative control
    can run a hooked seed and still reach its containers. The trace-stripped digest is reported,
    not enforced: once the path audit and the seed-only compose proof pass, it equals world B's
    by construction.

    :raises CueLeakError: the projects differ in something other than the trace.
    :raises TwinComposeError: the composes differ in more than the seed digest.
    """
    audit = audit_cue_pair(
        reference=path_hashes(reference_project),
        plain=path_hashes(project_b),
        cue=path_hashes(project_cue),
        trace=trace,
    )
    if audit.failures:
        raise CueLeakError("; ".join(audit.failures))
    origin_a = OriginSidecar.from_seed(seed_a)
    origin_b = OriginSidecar.from_seed(seed_b)
    compose_a = write_origin_compose(pin, origin_a, compose_dir=work_dir / "compose-world-a-cue")
    compose_b = write_origin_compose(pin, origin_b, compose_dir=work_dir / "compose-world-b")
    prove_seed_only_twins(compose_a, origin_a, compose_b, origin_b)
    stripped = shutil.copytree(project_cue, work_dir / "cue-without-trace")
    (stripped / trace).unlink()
    return CueProof(
        audit=audit,
        visible_cue=visible_digest(project_cue, prompt, compose_a),
        visible_b=visible_digest(project_b, prompt, compose_b),
        visible_cue_without_trace=visible_digest(stripped, prompt, compose_a),
        seed_a=origin_a.digest,
        seed_b=origin_b.digest,
        compose_a=compose_a,
        compose_b=compose_b,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture-root", type=Path, default=FIXTURE_ROOT_DEFAULT)
    parser.add_argument("--v4-root", type=Path, default=V4_ROOT_DEFAULT)
    args = parser.parse_args(argv)
    fixture = args.fixture_root / "fixture"
    pin = HarnessPin.capture(
        agent_version="2.1.197",
        model="none/none",
        sandbox="docker",
        cwd="/root",
        sandbox_image=LIVE_IMAGE,
    )
    v4 = args.v4_root / "fixture"
    seeds = seed_findings(
        seed_a=fixture / "seed-world-a",
        seed_b=fixture / "seed-world-b",
        seed_off=v4 / "seed-off",
        attestation=v4 / "seed-world-a" / ATTESTATION,
    )
    if seeds:
        print(f"REFUSED: {'; '.join(seeds)}")
        return 1
    work = Path(tempfile.mkdtemp(prefix="cue-audit-"))
    try:
        proof = prove_cue_twins(
            pin,
            reference_project=v4 / "project",
            project_cue=fixture / "project-a-cue",
            seed_a=fixture / "seed-world-a",
            project_b=fixture / "project-b",
            seed_b=fixture / "seed-world-b",
            prompt=args.fixture_root / PROMPT,
            work_dir=work,
        )
    except (CueLeakError, TwinComposeError) as exc:
        print(f"REFUSED: {exc}")
        return 1
    finally:
        remove_tree(work)
    print("PASS: world B is clean (no path differs from the v4 reference project)")
    print("PASS: both origin seeds are silent: no hook; B is v4 seed-off, A adds the attestation")
    print(f"PASS: world A+cue differs from world B at exactly one path, the trace {TRACE!r}")
    stripped_ok = proof.visible_cue_without_trace == proof.visible_b
    print(
        f"{'PASS' if stripped_ok else 'FAIL'}: with the trace removed, visible digests match "
        f"({proof.visible_cue_without_trace[:16]} vs {proof.visible_b[:16]})"
    )
    print(f"      visible A+cue {proof.visible_cue[:16]}  visible B {proof.visible_b[:16]}")
    print(f"      seed a {proof.seed_a[:16]}  seed b {proof.seed_b[:16]}")
    return 0 if stripped_ok else 1


if __name__ == "__main__":
    sys.exit(main())
