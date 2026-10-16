"""Emit the two receipt identities of amendment v1 section 8, plus the v2 SHA.

Specification: docs/assurance/ebmom-peel-preregistration-amendment.md section 8,
FROZEN. "Neither identity alone supports independent replay, so the confirmatory
receipt carries both." v2 section 8 keeps that unchanged and adds this document's
own SHA.

The MEASUREMENT identity says what was measured: the amendment SHAs, the
estimator, alpha / B / R, the registered regimes and their generative
parameters, the oracle definitions, and the acceptance matrix with its kill
criterion. The EXECUTION identity says what actually ran: the branch SHA, the
interpreter and numerical library versions, the harness and verifier digests,
the root seed and how every regime and replicate seed derives from it, a
manifest hash over the raw outputs, and the exact command lines.

Why this is its own file rather than a field on the run report. The digests it
records are of the harness and the verifier AS THEY RAN, so it has to be
generated after the run and cannot be written by the run itself without the
script hashing its own source mid-execution. Keeping it separate also means a
receipt can be re-identified against a later tree without re-running a scan that
takes hours -- and a re-identification that disagrees is the finding.

Usage:

    python scripts/ebmom_receipt_identity.py \\
        --output docs/assurance/ebmom-v2-reproduction-R1000-f95e4de5.json \\
        --command "<the exact command line that produced it>" \\
        --out docs/assurance/ebmom-v2-reproduction-identity-f95e4de5.json

`--output` and `--command` are repeatable and are matched in order, so one
identity can cover a set of runs that share a root. ASCII only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

AMENDMENT_V1 = "docs/assurance/ebmom-peel-preregistration-amendment.md"
AMENDMENT_V2 = "docs/assurance/ebmom-peel-preregistration-amendment-v2.md"
HARNESS = "scripts/ebmom_acceptance_matrix.py"
VERIFIER = "scripts/ebmom_form_b_reproduction.py"
ESTIMATOR = "src/skill_harness/aggregation/fit.py"


def digest(relative: str) -> str:
    return hashlib.sha256((REPO / relative).read_bytes()).hexdigest()


def head_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        check=True,
    )
    return proc.stdout.decode("utf-8").strip()


def library_version(name: str) -> str:
    try:
        module = __import__(name)
    except ImportError:  # pragma: no cover -- both are dev-extra installs
        return "not installed"
    return str(getattr(module, "__version__", "unknown"))


def measurement_identity() -> dict[str, object]:
    """What was measured. Every entry is a digest or a value read from the code."""
    sys.path.insert(0, str(REPO / "scripts"))
    sys.path.insert(0, str(REPO / "src"))
    import ebmom_acceptance_matrix as harness

    return {
        "amendment_v1_sha256": digest(AMENDMENT_V1),
        "amendment_v2_sha256": digest(AMENDMENT_V2),
        "estimator_definition_sha256": digest(ESTIMATOR),
        "estimator_definition_file": ESTIMATOR,
        "alpha": harness.HETEROGENEITY_TEST_ALPHA,
        "registered_replicates": harness.R_REPLICATES,
        "pass_p": harness.PASS_P,
        "fail_p": harness.FAIL_P,
        "kill_null_p": harness.V2_NULL_P,
        "kill_test_level": harness.V2_TEST_LEVEL,
        "world_block_bound_B": harness.BOUND_B,
        "registered_regimes": {
            regime.name: {
                "a_true": regime.a_true,
                "b_true": regime.b_true,
                "n_trials": regime.n_trials,
                "k_clauses": regime.k_clauses,
                "tie_rate": regime.tie_rate,
                "homogeneous_p": regime.homogeneous_p,
                "true_latent_variance": regime.true_latent_variance,
                "decisive_threshold": regime.decisive_threshold,
            }
            for regime in harness.REGIMES
        },
        "oracle_definition": (
            "ebmom_acceptance_matrix.oracle_decisions: the exact tie-model posterior "
            "Beta(a_true + W, b_true + L) on the decisive rate for a tie regime with "
            "heterogeneity, the moment-matched Beta otherwise, and the degenerate "
            "0-or-1 verdict where the true latent variance is zero"
        ),
        "acceptance_matrix": (
            "v2 section 5: rows 1 to 4 from v1; rows 5c and 6c per path under the "
            "section 2.1 exact test; 5c* and 6c* for the oracle as a harness "
            "self-check; rows 5, 6 and 7 against the oracle reported with the paired "
            "excess; row 8 the world-block bound; row 9 the reliability table; row 10 "
            "the production-faithfulness fixture"
        ),
        "kill_criterion": (
            "v2 section 5: any rejection in any 5c or 6c cell, on either path, in any "
            "registered regime rejects the candidate. Rollback state is main. A cell "
            "with no decisions of its kind is not testable and is never passed."
        ),
        "candidate_column": harness.V2_CANDIDATE_COLUMN,
    }


def execution_identity(outputs: list[Path], commands: list[str]) -> dict[str, object]:
    """What actually ran. The manifest hash is over the raw outputs in path order."""
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in outputs}
    manifest_material = "\n".join(f"{name}  {value}" for name, value in sorted(manifest.items()))
    roots = set()
    replicates = {}
    for path in outputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        roots.add(payload["root_seed"])
        replicates[path.name] = payload["replicates"]
    return {
        "branch_sha": head_sha(),
        "python": platform.python_version(),
        "numpy": library_version("numpy"),
        "scipy": library_version("scipy"),
        "platform": platform.platform(),
        "harness_file": HARNESS,
        "harness_sha256": digest(HARNESS),
        "verifier_file": VERIFIER,
        "verifier_sha256": digest(VERIFIER),
        "root_seed": sorted(roots),
        "replicates_per_output": replicates,
        "seed_derivation": (
            "every seed is the first eight bytes, big-endian, of SHA-256 over a "
            "'|'-joined label path beginning with the root: the world draw uses "
            "<root>|<regime>|<world>; the one-per-world kill selection uses "
            "<root>|<regime>|<world>|<row>; the world-block bound uses "
            "<root label>|<regime>|<column>|<path>|<row>, where the label carries the "
            "world range on a sub-range so a sub-range is not a subset of the full "
            "run's draws"
        ),
        "raw_output_manifest": manifest,
        "raw_output_manifest_sha256": hashlib.sha256(manifest_material.encode("utf-8")).hexdigest(),
        "command_lines": commands,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit the v1 section 8 receipt identities.")
    parser.add_argument(
        "--output", action="append", required=True, help="raw run output; repeatable"
    )
    parser.add_argument(
        "--command",
        action="append",
        required=True,
        help="the exact command line that produced the matching --output; repeatable",
    )
    parser.add_argument("--out", default="-")
    args = parser.parse_args(argv)

    outputs = [Path(value) for value in args.output]
    if len(outputs) != len(args.command):
        print(
            f"REFUSE: {len(outputs)} output(s) and {len(args.command)} command line(s). "
            "They are matched in order, so an unequal count would attach a command to "
            "the wrong run.",
            file=sys.stderr,
        )
        return 1
    missing = [str(path) for path in outputs if not path.is_file()]
    if missing:
        print(f"REFUSE: no such output(s): {missing}", file=sys.stderr)
        return 1

    identity = {
        "specification": (
            "docs/assurance/ebmom-peel-preregistration-amendment.md section 8, "
            "carried unchanged by v2 section 8"
        ),
        "is_confirmatory": False,
        "measurement_identity": measurement_identity(),
        "execution_identity": execution_identity(outputs, list(args.command)),
    }

    payload = json.dumps(identity, indent=2, sort_keys=True)
    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
