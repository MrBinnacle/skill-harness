"""Mechanized mutation receipt generator, per the #341 standard. ASCII only.

Every case runs in its OWN git worktree checked out at a fixed commit. The
production tree is never mutated in place, so a failed restore cannot leave a
mutant behind or make a clean run report a mutant's numbers. That failure mode
is not hypothetical: an earlier hand-run pass restored production through a
path the interpreter could not see, and a "clean" comparison silently reported
the mutant's result.

For each mutant the receipt asserts, and records:

  repository HEAD of both worktrees
  module.__file__ actually imported in each
  digest of the clean source file
  digest of the mutant source file
  the two digests differ
  the clean baseline PASSES the targeted selection first
  the targeted test collected a nonzero number of tests
  the named assertion FAILS under the mutant
  the production tree is unchanged after the receipt is generated

Each mutant names its own target file, module and test selection. That is not
speculative generality: the generator this file is ported from hard-pinned a
single module path at import time, which is exactly why it could not be reused
and had to be copied. Add cases to MUTANTS.

The generator EXITS NON-ZERO when a case is invalid -- a stillborn mutant, a
no-op edit, a missing anchor, a red baseline, or a module resolved outside its
own worktree. An invalid case is not a result, and a receipt that contains one
attests to nothing. A SURVIVED case is a legitimate result and exits zero: a
preserved survivor is a finding, not a failure.

WHAT PINS A RECEIPT IS FILE CONTENT, NOT A COMMIT. ``commit_under_test`` is a
convenience pointer and is deliberately NOT the currency check: a rebase
rewrites it, and every commit that lands after generation moves HEAD past it,
so a receipt keyed on it goes stale for reasons that cannot have affected what
it measured. The authoritative pin is ``target_digests`` -- the SHA-256 of each
mutated file. Those change if and only if the code under test changed.
``tests/test_mutation_receipt.py`` enforces currency against them, so a receipt
whose subject has moved fails loudly, and one merely carried across a rebase
does not.

Usage:
    python scripts/mutation_receipt.py --out docs/assurance/<name>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutant:
    mutant_id: str
    obligation: str
    description: str
    target: str  # repository-relative path of the file to mutate
    module: str  # importable module for the isolation and compile assertions
    old: str
    new: str
    selection: tuple[str, ...]  # pytest node ids run as one selection


_ENGINE = "src/skill_harness/aggregation/engine.py"
_ENGINE_MODULE = "skill_harness.aggregation.engine"
_PI_LAUNCHER = "src/skill_harness/subject/pi/launcher.py"
_PI_LAUNCHER_MODULE = "skill_harness.subject.pi.launcher"
_PI_PARSER = "src/skill_harness/subject/pi/parser.py"
_PI_PARSER_MODULE = "skill_harness.subject.pi.parser"
_PI_RUNNER = "src/skill_harness/subject/pi/runner.py"
_PI_RUNNER_MODULE = "skill_harness.subject.pi.runner"
_PI_RUNNER_IDENTITY = (
    "tests/test_subject_pi_runner.py::test_parser_identity_mismatch_blocks_spend",
    "tests/test_subject_pi_runner.py::test_valid_pair_runs_and_reaches_ingest",
)
_PI_RUNNER_NONZERO = (
    "tests/test_subject_pi_runner.py::test_nonzero_epoch_refuses_before_evidence",
)
_PI_RUNNER_CONTAINER = (
    "tests/test_subject_pi_runner.py::test_runtime_version_is_measured_across_the_container_boundary",
    "tests/test_subject_pi_runner.py::test_container_version_mismatch_refuses_before_any_epoch",
)
_PI_SYMMETRY_DETECTOR = "tests/test_subject_pi.py::test_pair_symmetry_checks"
_PI_IDENTITY_DETECTORS = (
    "tests/test_subject_pi.py::test_verify_parser_identity_refuses_mismatch",
    "tests/test_subject_pi.py::test_verify_parser_identity_accepts_live",
)
_PI_MIDEPOCH_DETECTOR = "tests/test_subject_pi.py::test_parse_refuses_mid_epoch_model_change"
_CONFOUND_DETECTOR = (
    "tests/test_confound_status_e2e.py::TestConfoundStatusE2E"
    "::test_confound_events_produce_confounded_status"
)
_UNDERPOWERED_DETECTOR = (
    "tests/test_confound_status_e2e.py::TestConfoundStatusE2E"
    "::test_underpowered_discard_does_not_read_as_confounded"
)
_INGEST = "src/skill_harness/subject/ingest.py"
_INGEST_MODULE = "skill_harness.subject.ingest"
_PAIRED_DETECTOR = (
    "tests/test_paired_arm_epoch_adversarial.py::test_nan_score_is_refused_or_fails_closed"
)
_HELPER_DETECTOR = "tests/test_subject_ingest.py::test_score_to_float_refuses_non_finite_scores"
_MODEL_DETECTOR = (
    "tests/test_subject_ingest.py::test_parsed_sample_refuses_non_finite_score_at_the_model_layer"
)
# #387 (the #384 ruling): the two refusal predicates at the paired ingest seam.
_UNEXPOSED_FULL_DETECTOR = "tests/test_subject_ingest.py::test_full_arm_unexposed_refuses"
_UNEXPOSED_FULL_SEAM_DETECTOR = "tests/test_subject_ingest.py::test_unexposed_full_epoch_refuses"
_NULL_EXPOSED_DETECTOR = "tests/test_subject_ingest.py::test_null_arm_exposed_refuses"
_NULL_EXPOSED_SEAM_DETECTOR = "tests/test_subject_ingest.py::test_null_epoch_exposed_refuses"
# #389: ratification binding and count-mismatch refusal at the paired Gate-2 read.
_PAIRED_GATE2 = "src/skill_harness/cli/paired_gate2.py"
_PAIRED_GATE2_MODULE = "skill_harness.cli.paired_gate2"
_DRAFT_REFUSED = "tests/test_cli_paired_gate2.py::TestUnratifiedDesign::test_draft_record_refused"
_COUNT_MISMATCH = "tests/test_cli_paired_gate2.py::TestCountMismatch::test_pilot_k8_vs_design_n32"

_PAIRED_LAUNCH = "src/skill_harness/subject/paired_launch.py"
_PAIRED_LAUNCH_MODULE = "skill_harness.subject.paired_launch"
_SEGMENTATION_DETECTORS = (
    "tests/test_paired_launch.py::TestSimpleCommands",
    "tests/test_paired_launch.py::TestHazardCommandCases",
)
_UNDECIDED_DETECTOR = "tests/test_paired_launch.py::TestHazardCommandCases::test_case"
_UNDECIDED_COUNT_DETECTOR = (
    "tests/test_paired_launch.py::TestHazardUndecidedCounts"
    "::test_an_unreadable_epoch_is_undecided_not_avoided"
)


# #368 Path C: the ablation lane's discordant route.
_STOPPING = "src/skill_harness/ablation/stopping.py"
_STOPPING_MODULE = "skill_harness.ablation.stopping"
_PATH_C = "src/skill_harness/ablation/path_c.py"
_PATH_C_MODULE = "skill_harness.ablation.path_c"
_TIE_VERDICT_DETECTOR = (
    "tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity"
    "::test_stopping_decision_agreement"
)
_TIE_MEAN_DETECTOR = (
    "tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity"
    "::test_production_accumulator_no_longer_dilutes"
)
_EVIDENCE_BAR_DETECTOR = (
    "tests/ablation/test_stopping.py::TestBetaBinomialAccumulator"
    "::test_ties_cannot_buy_a_clause_past_the_evidence_bar"
)
_EFFECT_FLOOR_DETECTOR = (
    "tests/test_ablation_path_c.py::TestDecideClause"
    "::test_ties_reach_the_decision_rather_than_being_discarded"
)
_TIE_HEAVY_DETECTOR = (
    "tests/test_ablation_path_c.py::TestDecideClause"
    "::test_tie_heavy_win_is_held_below_the_effect_floor"
)
_UNREGISTERED_DETECTOR = (
    "tests/test_ablation_path_c.py::TestRegisteredThresholds"
    "::test_missing_threshold_refuses_rather_than_defaulting"
)

MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        "M-N1",
        "363-model-layer",
        "remove the model-layer constraint: ParsedSample.score_value accepts NaN again",
        _INGEST,
        _INGEST_MODULE,
        "    score_value: Annotated[float, Field(allow_inf_nan=False)]  # 1.0 pass | 0.0 fail",
        "    score_value: float  # 1.0 pass | 0.0 fail",
        (_PAIRED_DETECTOR, _MODEL_DETECTOR),
    ),
    Mutant(
        "M-N2",
        "363-parse-path",
        "disable the parse-path finite guard in _score_to_float",
        _INGEST,
        _INGEST_MODULE,
        "        if not math.isfinite(score):",
        "        if False:",
        (_HELPER_DETECTOR,),
    ),
    Mutant(
        "M-N3",
        "363-parse-path",
        "narrow the parse-path guard to NaN only, letting an infinite score through",
        _INGEST,
        _INGEST_MODULE,
        "        if not math.isfinite(score):",
        "        if math.isnan(score):",
        (_HELPER_DETECTOR,),
    ),
    Mutant(
        "M-C1",
        "366-reason-read",
        "stop reading the persisted inadmissibility_reason, so CONFOUNDED is unreachable again",
        _ENGINE,
        _ENGINE_MODULE,
        '                if reason == "confounded":',
        "                if False:",
        (_CONFOUND_DETECTOR,),
    ),
    Mutant(
        "M-C2",
        "366-flag-condition",
        "invert the survivor gate: fire CONFOUNDED only when admissible work DID survive",
        _ENGINE,
        _ENGINE_MODULE,
        "        all_confounded_flag = total > 0 and admissible_count == 0 and confounded > 0",
        "        all_confounded_flag = total > 0 and admissible_count > 0 and confounded > 0",
        (_CONFOUND_DETECTOR,),
    ),
    Mutant(
        "M-C3",
        "366-reason-read",
        "count every inadmissible verdict except scorer_error as confounded, so an "
        "underpowered clause reports as confounded",
        _ENGINE,
        _ENGINE_MODULE,
        '                if reason == "confounded":',
        '                if reason != "scorer_error":',
        (_UNDERPOWERED_DETECTOR, _CONFOUND_DETECTOR),
    ),
    Mutant(
        "M-X1",
        "387-unexposed-full",
        "remove refusal predicate (a): a Full-arm epoch with exposure not detected writes",
        _INGEST,
        _INGEST_MODULE,
        "    unexposed = sorted(s.epoch for s in full.samples if s.exposed_skill is not True)",
        "    unexposed = sorted(s.epoch for s in full.samples if False)",
        (_UNEXPOSED_FULL_DETECTOR, _UNEXPOSED_FULL_SEAM_DETECTOR),
    ),
    Mutant(
        "M-X2",
        "387-null-contamination",
        "narrow refusal predicate (b) back to invocation only: a Null-arm epoch with "
        "exposure detected writes",
        _INGEST,
        _INGEST_MODULE,
        "    null_contaminated_exposed = sorted("
        "s.epoch for s in null.samples if s.exposed_skill is True)",
        "    null_contaminated_exposed = sorted(s.epoch for s in null.samples if False)",
        (_NULL_EXPOSED_DETECTOR, _NULL_EXPOSED_SEAM_DETECTOR),
    ),
    Mutant(
        "M-H1",
        "438-simple-command-segmentation",
        "stop segmenting a chained command: the whole tool-call string is matched as one "
        "command again, which is the pre-#438 instrument",
        _PAIRED_LAUNCH,
        _PAIRED_LAUNCH_MODULE,
        "    return tuple(stripped for stripped in (segment.strip() for segment in segments)"
        " if stripped)",
        "    return (command.strip(),) if command.strip() else ()  # mutant: no segmentation",
        _SEGMENTATION_DETECTORS,
    ),
    Mutant(
        "M-H2",
        "438-undecided-whole-string",
        "score an unsegmentable command as an avoidance: a heredoc or an unterminated quote "
        "silently reads as the trap having been avoided",
        _PAIRED_LAUNCH,
        _PAIRED_LAUNCH_MODULE,
        "    if segments is None:\n        return HazardVerdict.UNDECIDED",
        "    if segments is None:\n        return HazardVerdict.AVOIDED  # mutant",
        (_UNDECIDED_DETECTOR,),
    ),
    Mutant(
        "M-H3",
        "438-undecided-per-segment",
        "score a command with an unreadable SEGMENT as an avoidance, keeping the "
        "whole-string refusal so the loss is invisible in the common case",
        _PAIRED_LAUNCH,
        _PAIRED_LAUNCH_MODULE,
        "    return HazardVerdict.UNDECIDED if undecided else HazardVerdict.AVOIDED",
        "    return HazardVerdict.AVOIDED  # mutant: per-segment undecided dropped",
        (_UNDECIDED_DETECTOR, _UNDECIDED_COUNT_DETECTOR),
    ),
    Mutant(
        "M-R1",
        "389-ratification-binding",
        "remove the RATIFIED status check: a DRAFT record is accepted and the command "
        "proceeds to read the design",
        _PAIRED_GATE2,
        _PAIRED_GATE2_MODULE,
        '    if record.status != "RATIFIED":',
        "    if False:  # mutant: DRAFT accepted",
        (_DRAFT_REFUSED,),
    ),
    Mutant(
        "M-R2",
        "389-count-mismatch",
        "remove the pair-count check: k=8 pairs are read against an n=32 design without refusal",
        _PAIRED_GATE2,
        _PAIRED_GATE2_MODULE,
        "    if total_pairs != design.n_pairs:",
        "    if False:  # mutant: count mismatch accepted",
        (_COUNT_MISMATCH,),
    ),
    # #368 Path C: the discordant accumulator and the registered Gate-2 route.
    Mutant(
        "M-T1",
        "368-discordant-posterior",
        "restore the half-update posterior: ties are credited to both sides again, "
        "which is the WRONG_NUMBER defect #347 measured",
        _STOPPING,
        _STOPPING_MODULE,
        "        return 1.0 + float(self._x_f), 1.0 + float(self._x_n)",
        "        return 1.0 + self.w, 1.0 + (float(self.n) - self.w)",
        (_TIE_VERDICT_DETECTOR, _TIE_MEAN_DETECTOR),
    ),
    Mutant(
        "M-T2",
        "368-evidence-bar",
        "point the N_MIN evidence gate at the TOTAL comparison count, so ties buy a "
        "clause past the bar on too few directional comparisons",
        _STOPPING,
        _STOPPING_MODULE,
        "        if self.n_discordant < N_MIN:",
        "        if self.n < N_MIN:",
        (_EVIDENCE_BAR_DETECTOR,),
    ),
    Mutant(
        "M-T3",
        "368-effect-floor",
        "size the Gate-2 design by the DISCORDANT count, discarding the tie cell and "
        "collapsing Path C to a plain drop-ties recompute with no effect-size floor",
        _PATH_C,
        _PATH_C_MODULE,
        "    n_pairs = max(decision.n_samples, 1)",
        "    n_pairs = max(decision.n_discordant, 1)",
        (_EFFECT_FLOOR_DETECTOR, _TIE_HEAVY_DETECTOR),
    ),
    Mutant(
        "M-T4",
        "368-thresholds-by-reference",
        "accept a record that omits a Gate-2 threshold, so an unregistered decision "
        "is made under a defaulted value while looking registered",
        _PATH_C,
        _PATH_C_MODULE,
        "    if missing:",
        "    if False:  # mutant: missing threshold defaulted rather than refused",
        (_UNREGISTERED_DETECTOR,),
    ),
    Mutant(
        "M-P1",
        "pi-roster-symmetry",
        "empty the cross-arm baseline check: a Full roster whose baseline differs "
        "from the Null roster launches as if the arms shared it",
        _PI_LAUNCHER,
        _PI_LAUNCHER_MODULE,
        "    if full[:-1] != null:",
        "    if False:  # mutant: cross-arm baseline asymmetry no longer refuses",
        (_PI_SYMMETRY_DETECTOR,),
    ),
    Mutant(
        "M-P2",
        "pi-parser-identity",
        "skip the declared-vs-live parser identity comparison, so an undeclared "
        "evidence pipeline spends and ingests as the declared one",
        _PI_LAUNCHER,
        _PI_LAUNCHER_MODULE,
        "    if declared is not None:",
        "    if False:  # mutant: parser identity mismatch no longer refuses",
        (_PI_IDENTITY_DETECTORS),
    ),
    Mutant(
        "M-P3",
        "pi-mid-epoch-identity",
        "drop the second-model_change count guard, so a mid-epoch model change "
        "event passes as ordinary metadata when the subject string happens to match",
        _PI_PARSER,
        _PI_PARSER_MODULE,
        "        if i > 0:\n"
        "            raise MidEpochIdentityChangeError(\n"
        '                f"session carries {len(model_changes)} model_change entries; "\n'
        '                "a mid-epoch change is an apparatus error, not metadata"\n'
        "            )",
        "        if False:  # mutant: the count guard no longer refuses\n"
        "            raise MidEpochIdentityChangeError(\n"
        '                f"session carries {len(model_changes)} model_change entries; "\n'
        '                "a mid-epoch change is an apparatus error, not metadata"\n'
        "            )",
        (_PI_MIDEPOCH_DETECTOR,),
    ),
    # --- Pi driver wiring (runner.py): the controls exist in helpers; these
    # cases prove the DRIVER calls them. A control nobody calls is dead code
    # with a docstring, which is what the driver commit exists to close.
    Mutant(
        "M-R1",
        "mr-driver-identity-gate",
        "the driver stops comparing the declared parser identity: an undeclared "
        "evidence pipeline passes the pre-spend gate and reaches spend",
        _PI_RUNNER,
        _PI_RUNNER_MODULE,
        "    parser = verify_parser_identity(spec.declared_parser_identity)",
        "    parser = verify_parser_identity(None)  # mutant: declared identity never compared",
        _PI_RUNNER_IDENTITY,
    ),
    Mutant(
        "M-R2",
        "mr-driver-nonzero-epoch",
        "the nonzero-returncode refusal no longer fires: a crashed epoch is "
        "parsed and ingested as if it had run",
        _PI_RUNNER,
        _PI_RUNNER_MODULE,
        "    if launch.returncode != 0:",
        "    if False:  # mutant: a crashed epoch no longer refuses",
        _PI_RUNNER_NONZERO,
    ),
    Mutant(
        "M-R4",
        "mr-container-version-probe",
        "the version probe stops wrapping the container prefix: the pin names "
        "the host binary's version while the epoch runs the container's copy",
        _PI_LAUNCHER,
        _PI_LAUNCHER_MODULE,
        "    argv: list[str] = []\n"
        "    if container is not None:\n"
        "        argv.extend(container.argv_prefix)\n"
        '    argv.extend([pi_bin, "--version"])',
        "    argv: list[str] = []\n"
        "    if False:  # mutant: the probe measures the host, not the container\n"
        "        argv.extend(container.argv_prefix)\n"
        '    argv.extend([pi_bin, "--version"])',
        _PI_RUNNER_CONTAINER,
    ),
    Mutant(
        "M-R5",
        "mr-driver-container-wiring",
        "the driver stops passing its container to the version probe: the "
        "helper stays correct and the measured version still names the host",
        _PI_RUNNER,
        _PI_RUNNER_MODULE,
        "    runtime_version = measure_pi_version(spec.pi_bin, container=spec.container)",
        "    runtime_version = measure_pi_version(spec.pi_bin)  # mutant: container dropped",
        _PI_RUNNER_CONTAINER,
    ),
)


# A case with one of these verdicts produced no measurement. It is not a result
# that a reader can weigh, so the generator refuses rather than writing a receipt
# that looks complete. SURVIVED is absent deliberately: a preserved survivor is a
# finding, and folding it into an exit code would create pressure to delete it.
INVALID_VERDICTS: frozenset[str] = frozenset(
    {"ANCHOR_ABSENT", "INVALID_BASELINE", "INVALID_ISOLATION", "NO_OP", "STILLBORN", "UNKNOWN"}
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str, cwd: Path) -> str:
    """Run one git command and return its stripped stdout."""
    proc = subprocess.run(  # noqa: S603 -- argv is literal, built in this file
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        check=True,
    )
    return proc.stdout.decode("utf-8", "replace").strip()


def _env(root: Path | None = None) -> dict[str, str]:
    """Environment for a subprocess, pinned to a worktree's own sources.

    Without PYTHONPATH the editable install resolves skill_harness to the MAIN
    repository, so a worktree would run its own tests against production code
    from somewhere else and every mutant would appear to survive. Each case
    asserts module.__file__ actually resolves inside its worktree, so a silent
    reversion to the editable install invalidates the receipt instead of
    quietly passing.
    """
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONUTF8": "1"}
    if root is not None:
        env["PYTHONPATH"] = str(root / "src")
    return env


def _run_pytest(root: Path, selection: tuple[str, ...]) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 -- argv is literal, built in this file
        [
            sys.executable,
            "-m",
            "pytest",
            *selection,
            "-p",
            "no:randomly",
            "-q",
            "--tb=line",
        ],
        cwd=root,
        capture_output=True,
        env=_env(root),
        check=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def _module_file(root: Path, module: str) -> str:
    proc = subprocess.run(  # noqa: S603 -- module names come from MUTANTS in this file
        [sys.executable, "-c", f"import {module} as m; print(m.__file__)"],
        cwd=root,
        capture_output=True,
        env=_env(root),
        check=False,
    )
    return proc.stdout.decode("utf-8", "replace").strip()


def _collected(output: str) -> int:
    counts = [int(n) for n in re.findall(r"(\d+) (?:passed|failed)", output)]
    return sum(counts)


@dataclass
class CaseResult:
    mutant_id: str
    obligation: str
    description: str
    selection: tuple[str, ...]
    verdict: str
    clean: dict[str, object] = field(default_factory=dict)
    mutant: dict[str, object] = field(default_factory=dict)
    killing_assertions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run_case(mutant: Mutant, commit: str, workroot: Path) -> CaseResult:
    result = CaseResult(
        mutant.mutant_id, mutant.obligation, mutant.description, mutant.selection, "UNKNOWN"
    )
    tree = workroot / mutant.mutant_id
    subprocess.run(  # noqa: S603
        ["git", "worktree", "add", "--detach", str(tree), commit],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        check=True,
    )
    try:
        target = tree / mutant.target
        head = _git("rev-parse", "HEAD", cwd=tree)

        clean_digest = _digest(target)
        clean_module = _module_file(tree, mutant.module)
        code, out = _run_pytest(tree, mutant.selection)
        result.clean = {
            "worktree_head": head,
            "module_file": clean_module,
            "source_digest": clean_digest,
            "exit_code": code,
            "tests_collected": _collected(out),
            "baseline_passes": code == 0,
        }
        if not clean_module.startswith(str(tree)):
            result.verdict = "INVALID_ISOLATION"
            result.notes.append(
                f"module resolved to {clean_module!r}, outside the worktree {str(tree)!r}; "
                "the case would have tested another tree's code"
            )
            return result
        if code != 0 or _collected(out) == 0:
            result.verdict = "INVALID_BASELINE"
            result.notes.append(
                "clean baseline did not pass with nonzero collection; no kill can be "
                "attributed against it"
            )
            return result

        source = target.read_text(encoding="utf-8")
        if mutant.old not in source:
            result.verdict = "ANCHOR_ABSENT"
            return result
        target.write_bytes(source.replace(mutant.old, mutant.new, 1).encode("utf-8"))

        mutant_digest = _digest(target)
        compiles = subprocess.run(  # noqa: S603 -- module name is literal, from MUTANTS
            [sys.executable, "-c", f"import {mutant.module}"],
            cwd=tree,
            capture_output=True,
            env=_env(tree),
            check=False,
        )
        code, out = _run_pytest(tree, mutant.selection)
        failed = re.findall(r"^FAILED (\S+)", out, re.M)
        result.mutant = {
            "worktree_head": head,
            "module_file": _module_file(tree, mutant.module),
            "source_digest": mutant_digest,
            "digests_differ": mutant_digest != clean_digest,
            "compiles": compiles.returncode == 0,
            "exit_code": code,
            "tests_collected": _collected(out),
        }
        result.killing_assertions = failed

        if compiles.returncode != 0:
            result.verdict = "STILLBORN"
            result.notes.append("mutant does not import; a stillborn mutant is not a kill")
        elif mutant_digest == clean_digest:
            result.verdict = "NO_OP"
            result.notes.append("mutation did not change the file")
        elif failed:
            result.verdict = "KILLED"
        else:
            result.verdict = "SURVIVED"
        return result
    finally:
        subprocess.run(  # noqa: S603
            ["git", "worktree", "remove", "--force", str(tree)],  # noqa: S607
            cwd=REPO,
            capture_output=True,
            check=False,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="-")
    parser.add_argument(
        "--select",
        default="",
        help=(
            "only run mutants whose obligation starts with this prefix. One receipt "
            "should attest to one repair; MUTANTS accumulates across repairs."
        ),
    )
    args = parser.parse_args(argv)

    selected = tuple(m for m in MUTANTS if m.obligation.startswith(args.select))
    if not selected:
        print(f"REFUSE: --select {args.select!r} matched no mutants", file=sys.stderr)
        return 1

    dirty = _git("status", "--porcelain", cwd=REPO)
    if dirty:
        print(
            "REFUSE: production tree is dirty. The receipt must attest to a committed "
            "tree, or its digests name nothing a reader can fetch.\n" + dirty,
            file=sys.stderr,
        )
        return 1

    commit = _git("rev-parse", "HEAD", cwd=REPO)
    targets = sorted({m.target for m in selected})
    digests_before = {t: _digest(REPO / t) for t in targets}

    workroot = Path(tempfile.mkdtemp(prefix="mutation-receipt-"))
    try:
        cases = [run_case(m, commit, workroot) for m in selected]
    finally:
        shutil.rmtree(workroot, ignore_errors=True)

    digests_after = {t: _digest(REPO / t) for t in targets}
    still_clean = _git("status", "--porcelain", cwd=REPO)

    report = {
        "commit_under_test": commit,
        "commit_under_test_is_informational": (
            "A rebase rewrites this and later commits move HEAD past it. The"
            " authoritative pin is target_digests; currency is checked against those."
        ),
        "target_files": targets,
        "target_digests": digests_after,
        "production_tree_digest_before": digests_before,
        "production_tree_digest_after": digests_after,
        "production_tree_unchanged": digests_before == digests_after and still_clean == "",
        "python": sys.version.split()[0],
        "cases": [
            {
                "mutant_id": c.mutant_id,
                "obligation": c.obligation,
                "description": c.description,
                "selection": list(c.selection),
                "verdict": c.verdict,
                "clean": c.clean,
                "mutant": c.mutant,
                "killing_assertions": c.killing_assertions,
                "notes": c.notes,
            }
            for c in cases
        ],
    }
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")

    for c in cases:
        print(
            f"{c.mutant_id} [{c.obligation}] {c.verdict}: {'; '.join(c.killing_assertions) or '-'}"
        )
    if not report["production_tree_unchanged"]:
        print("REFUSE: production tree changed during receipt generation", file=sys.stderr)
        return 1
    invalid = [c for c in cases if c.verdict in INVALID_VERDICTS]
    if invalid:
        print(
            "REFUSE: "
            + ", ".join(f"{c.mutant_id} {c.verdict}" for c in invalid)
            + ". An invalid case measured nothing, so this receipt attests to nothing.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
