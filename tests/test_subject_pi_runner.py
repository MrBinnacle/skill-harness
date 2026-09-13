"""Production-path tests for the Pi paired driver (subject/pi/runner.py).

These differ from ``test_subject_pi.py`` in the property they establish.
That file calls each adapter function directly and proves the function
behaves. This file drives the real entry point, ``run_paired_evaluation``,
and proves the CONTROLS FIRE ON THE PATH -- the gap that made a set of
passing unit tests coexist with two pre-spend controls that no production
caller invoked.

So every test here starts at the driver and asserts on what reached the OS
boundary. A test that called ``verify_parser_identity`` itself would prove
nothing about wiring, which is the whole point.

The Pi executable is substituted, not mocked away: ``FakePi`` replaces
``subprocess.run`` for the launcher module and records every argv it
receives. That records three distinguishable command kinds -- the version
probe, an epoch launch, and the oracle -- so a test can assert that an
epoch launch NEVER HAPPENED while the (free) version probe did. No model is
called and nothing is spent at any point.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from skill_harness.storage.migrations import open_evidence
from skill_harness.subject.ingest import (
    NullArmContaminationError,
)
from skill_harness.subject.pi.launcher import ContainerSpec, ParserIdentityMismatchError
from skill_harness.subject.pi.parser import MidEpochIdentityChangeError, parser_identity
from skill_harness.subject.pi.roster import PiRosterError
from skill_harness.subject.pi.runner import (
    PairedRunSpec,
    RuntimeVersionMismatchError,
    run_paired_evaluation,
    validate_pre_spend,
)
from tests.test_subject_pi import (
    MODEL,
    PROVIDER,
    SKILL_MD,
    THINKING,
    make_epoch_dir,
)

RUNTIME_VERSION = "0.85.1"


class FakePi:
    """A substituted Pi binary that records what it was asked to run.

    Three command kinds are told apart by argv, which is how a test can
    prove an epoch never launched:

    * ``--version``  -- the free runtime probe, part of the pre-spend gate;
    * ``bash -lc``   -- the oracle, run after the epoch;
    * anything else  -- AN EPOCH LAUNCH, i.e. the spend boundary.

    On an epoch launch it materialises the capture artifacts the real Pi
    capture extension would have written, using the same synthetic builders
    the seam tests use, so the parse layer downstream is exercised for real.
    """

    def __init__(
        self,
        *,
        root: Path,
        skill_dir: Path,
        treatment_name: str,
        roster_names: list[str],
        roster_paths: dict[str, Path],
        null_exposed: bool = False,
        full_invoked: bool = True,
        model_changes: int = 1,
        returncode: int = 0,
        container_prefix: tuple[str, ...] = (),
        container_version: str = RUNTIME_VERSION,
        host_version: str = RUNTIME_VERSION,
    ) -> None:
        self.container_prefix = container_prefix
        self.container_version = container_version
        self.host_version = host_version
        self.root = root
        self.skill_dir = skill_dir
        self.treatment_name = treatment_name
        self.roster_names = roster_names
        self.roster_paths = roster_paths
        self.null_exposed = null_exposed
        self.full_invoked = full_invoked
        self.model_changes = model_changes
        self.returncode = returncode
        self.version_probes: list[list[str]] = []
        self.epoch_launches: list[list[str]] = []
        self.oracle_calls: list[list[str]] = []

    @property
    def spent(self) -> bool:
        """True once a provider-facing epoch has been launched."""
        return bool(self.epoch_launches)

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "--version" in argv:
            self.version_probes.append(list(argv))
            # The two boundaries report DIFFERENT versions, which is what
            # makes the provenance defect observable: a probe that skips the
            # container prefix measures the host copy.
            through_container = bool(self.container_prefix) and (
                tuple(argv[: len(self.container_prefix)]) == self.container_prefix
            )
            version = self.container_version if through_container else self.host_version
            return subprocess.CompletedProcess(argv, 0, version + "\n", "")
        # The oracle is also wrapped in the container prefix, so match on the
        # bash invocation wherever it sits rather than at argv[0].
        rest = list(argv[len(self.container_prefix) :]) if self.container_prefix else list(argv)
        if rest[:2] == ["bash", "-lc"]:
            self.oracle_calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        self.epoch_launches.append(list(argv))
        condition = "full" if str(self.skill_dir) in " ".join(argv) else "null"
        env = kwargs.get("env") or {}
        capture_dir = Path(env["PI_CAPTURE_DIR"])
        name = capture_dir.name
        built = make_epoch_dir(
            capture_dir.parent,
            name,
            exposed=(condition == "full") or self.null_exposed,
            invoked=(condition == "full") and self.full_invoked,
            skill_dir=self.skill_dir,
            model_changes=self.model_changes,
            roster=(
                self.roster_names
                if condition == "full"
                else [n for n in self.roster_names if n != self.treatment_name]
            ),
        )
        assert built == capture_dir

        # The synthetic builder writes each roster member's filePath under
        # its own root. The real runtime reports the actual skill
        # directories, and the parser's roster attestation compares against
        # them, so point them at the real dirs here rather than relaxing the
        # attestation to accept either.
        agent_start_path = capture_dir / "agent_start.json"
        agent_start = json.loads(agent_start_path.read_text(encoding="utf-8"))
        for entry in agent_start["systemPromptOptions"]["skills"]:
            entry["filePath"] = str(self.roster_paths[entry["name"]] / "SKILL.md")
        agent_start_path.write_text(json.dumps(agent_start), encoding="utf-8")

        return subprocess.CompletedProcess(argv, self.returncode, "", "")


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_evidence(tmp_path / "evidence.db")
    yield connection
    connection.close()


@pytest.fixture
def skills(tmp_path: Path) -> tuple[Path, Path]:
    """The treatment and one baseline member, laid out as the roster needs."""
    treatment = tmp_path / "rebase-trap"
    treatment.mkdir()
    (treatment / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    baseline = tmp_path / "baseline-skill"
    baseline.mkdir()
    (baseline / "SKILL.md").write_text(
        "---\nname: baseline-skill\ndescription: A baseline member.\n---\nbody\n",
        encoding="utf-8",
    )
    return treatment, baseline


def _spec(
    tmp_path: Path,
    skills: tuple[Path, Path],
    *,
    baseline_dirs: tuple[Path, ...] | None = None,
    declared_parser_identity: dict[str, str] | None = None,
    n_pairs: int = 1,
    container: ContainerSpec | None = None,
    expected_runtime_version: str | None = RUNTIME_VERSION,
) -> PairedRunSpec:
    treatment, baseline = skills
    template = tmp_path / "template"
    template.mkdir(exist_ok=True)
    (template / "task.txt").write_text("do the task\n", encoding="utf-8")
    return PairedRunSpec(
        pi_bin="pi",
        provider=PROVIDER,
        model=MODEL,
        thinking_level=THINKING,
        tool_allowlist=("read", "bash"),
        baseline_dirs=baseline_dirs if baseline_dirs is not None else (baseline,),
        treatment_dir=treatment,
        skill_name="rebase-trap",
        prompt="Do the task.",
        oracle_command="true",
        workspace_template=template,
        workspace=tmp_path / "ws",
        artifact_root=tmp_path / "artifacts",
        n_pairs=n_pairs,
        declared_env={"PATH": "/usr/bin"},
        secret_env={},
        container=container,
        expected_runtime_version=expected_runtime_version,
        declared_parser_identity=declared_parser_identity,
        route="openrouter",
    )


def _install(monkeypatch: pytest.MonkeyPatch, fake: FakePi) -> None:
    monkeypatch.setattr("skill_harness.subject.pi.launcher.subprocess.run", fake)


def _fake_for(tmp_path: Path, skills: tuple[Path, Path], **kwargs: Any) -> FakePi:
    treatment, baseline = skills
    return FakePi(
        root=tmp_path,
        skill_dir=treatment,
        treatment_name="rebase-trap",
        roster_names=["baseline-skill", "rebase-trap"],
        roster_paths={"baseline-skill": baseline, "rebase-trap": treatment},
        **kwargs,
    )


# ---------------------------------------------------------------------------
# A -- parser identity blocks spend
# ---------------------------------------------------------------------------


def test_parser_identity_mismatch_blocks_spend(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declared identity that is not the live one refuses before launch.

    The assertion that matters is ``not fake.spent``: the refusal is worth
    nothing if it fires after the money is gone.
    """
    fake = _fake_for(tmp_path, skills)
    _install(monkeypatch, fake)
    declared = dict(parser_identity())
    declared["content_hash"] = "0" * 64

    spec = _spec(tmp_path, skills, declared_parser_identity=declared)
    with pytest.raises(ParserIdentityMismatchError):
        run_paired_evaluation(spec, conn)

    assert not fake.spent, "an epoch was launched despite the identity refusal"
    assert fake.epoch_launches == []
    assert fake.oracle_calls == []
    assert fake.version_probes == [], (
        "identity is checked before the runtime probe, so nothing should have run at all"
    )
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# B -- roster refusal blocks spend
# ---------------------------------------------------------------------------


def test_roster_refusal_blocks_spend(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid roster refuses before launch.

    The case used is a baseline member whose name collides with the
    treatment, which Pi would resolve first-wins so that the mounted
    treatment is not the one tested.

    On cross-arm symmetry specifically, note what this test can and cannot
    establish. The driver builds both rosters from one baseline tuple, so
    Full = Null + treatment holds by construction and
    ``verify_pair_symmetry`` cannot fail on this path. It is called anyway
    (``validate_pre_spend``), as a standing assertion against a future
    caller that assembles the two arms separately. Its discriminating
    coverage remains the direct unit test and mutant M-P1; this test proves
    the roster gate as a whole precedes spend.
    """
    treatment, _baseline = skills
    collider = tmp_path / "collider"
    collider.mkdir()
    (collider / "SKILL.md").write_text(
        "---\nname: rebase-trap\ndescription: A colliding baseline.\n---\nbody\n",
        encoding="utf-8",
    )
    fake = _fake_for(tmp_path, skills)
    _install(monkeypatch, fake)

    spec = _spec(tmp_path, skills, baseline_dirs=(collider,))
    with pytest.raises(PiRosterError):
        run_paired_evaluation(spec, conn)

    assert not fake.spent, "an epoch was launched despite the roster refusal"
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert treatment.is_dir()


# ---------------------------------------------------------------------------
# C -- the valid path reaches the existing write path
# ---------------------------------------------------------------------------


def test_valid_pair_runs_and_reaches_ingest(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """entry -> validations -> launch -> capture -> parse -> ingest.

    Asserts the handoff actually occurred by reading the evidence store,
    not by trusting the returned object.
    """
    fake = _fake_for(tmp_path, skills)
    _install(monkeypatch, fake)

    result = run_paired_evaluation(_spec(tmp_path, skills), conn)

    assert len(fake.epoch_launches) == 2, "one Full and one Null epoch"
    assert len(fake.oracle_calls) == 2
    assert len(fake.version_probes) == 1, "the runtime is measured once, before spend"

    rows = conn.execute("SELECT run_id, run_kind, config_json FROM runs").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "evaluate_skill"
    assert rows[0][0] == result.run_id
    config = json.loads(rows[0][2])
    assert config["runner"]["runtime"]["name"] == "pi", (
        "the runtime discriminator must survive into the stored config"
    )
    assert config["runner"]["parser"]["version"] == parser_identity()["version"]

    samples = conn.execute(
        "SELECT condition, harness_pin_fingerprint FROM samples ORDER BY condition"
    ).fetchall()
    assert {r[0] for r in samples} == {"full", "null"}
    assert len({r[1] for r in samples}) == 1, (
        "both arms must share one pin fingerprint or every verdict writes inadmissible"
    )


# ---------------------------------------------------------------------------
# D -- exposed Full / uninvoked Full is admissible (the #384 shape)
# ---------------------------------------------------------------------------


def test_exposed_but_uninvoked_full_is_accepted(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero invocation with full exposure is accepted, through the driver.

    Treatment is exposure, not invocation. This is the historically
    important case: the pair must be written, not refused.
    """
    fake = _fake_for(tmp_path, skills, full_invoked=False)
    _install(monkeypatch, fake)

    result = run_paired_evaluation(_spec(tmp_path, skills), conn)

    # Exposure and invocation are summarised on the result and in the run's
    # config, not as sample columns.
    assert result.exposure.exposed_count == 1, "the Full arm was exposed"
    assert result.pi_c.invocations == 0, "and invoked the skill zero times"
    assert result.pi_c.trials == 1
    assert result.admissibility_state == "admissible", (
        "zero invocation under full exposure is ADMISSIBLE: treatment is exposure, not invocation"
    )
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# E -- Null contamination is reached through the driver
# ---------------------------------------------------------------------------


def test_null_contamination_refuses_through_the_driver(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exposed Null arm reaches the EXISTING scientific refusal.

    The driver does not re-implement this; it must simply not swallow it.
    """
    fake = _fake_for(tmp_path, skills, null_exposed=True)
    _install(monkeypatch, fake)

    with pytest.raises(NullArmContaminationError):
        run_paired_evaluation(_spec(tmp_path, skills), conn)

    assert fake.spent, "this refusal is post-spend by nature: the epochs ran"
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0, (
        "a contaminated pair must leave no run behind"
    )


# ---------------------------------------------------------------------------
# F -- a mid-epoch identity change is refused before ingest
# ---------------------------------------------------------------------------


def test_mid_epoch_identity_change_refuses_before_ingest(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second model_change entry refuses at parse, before evidence exists."""
    fake = _fake_for(tmp_path, skills, model_changes=2)
    _install(monkeypatch, fake)

    with pytest.raises(MidEpochIdentityChangeError):
        run_paired_evaluation(_spec(tmp_path, skills), conn)

    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Fail-closed on a nonzero epoch
# ---------------------------------------------------------------------------


def test_nonzero_epoch_refuses_before_evidence(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An epoch that did not complete is apparatus failure, not an outcome."""
    from skill_harness.subject.pi.runner import EpochExecutionError

    fake = _fake_for(tmp_path, skills, returncode=1)
    _install(monkeypatch, fake)

    with pytest.raises(EpochExecutionError):
        run_paired_evaluation(_spec(tmp_path, skills), conn)

    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# The dry-run gate spends nothing
# ---------------------------------------------------------------------------


CONTAINER = ContainerSpec(
    argv_prefix=("docker", "run", "--rm", "--network", "none", "img@sha256:abc"),
    image_digest="img@sha256:abc",
    network_policy="none",
)


def test_runtime_version_is_measured_across_the_container_boundary(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pinned version comes from the binary that actually runs.

    The substituted Pi reports DIFFERENT versions on the two boundaries. The
    host copy is deliberately a version the run does not declare, so a probe
    that skips the container prefix measures something the pin must never
    carry.

    Without the fix the driver measured the host copy and pinned it, while
    the epoch executed the container's. Both values are real Pi versions, so
    nothing downstream could tell the pin was describing a process that
    never ran.
    """
    fake = _fake_for(
        tmp_path,
        skills,
        container_prefix=CONTAINER.argv_prefix,
        container_version=RUNTIME_VERSION,
        host_version="9.9.9-host-copy",
    )
    _install(monkeypatch, fake)

    result = run_paired_evaluation(_spec(tmp_path, skills, container=CONTAINER), conn)

    assert fake.version_probes, "the runtime must be measured"
    for probe in fake.version_probes:
        assert tuple(probe[: len(CONTAINER.argv_prefix)]) == CONTAINER.argv_prefix, (
            "the version probe must cross the same boundary as the epoch"
        )

    pin_json = conn.execute("SELECT harness_pin_json FROM samples LIMIT 1").fetchone()[0]
    pinned = json.loads(pin_json)
    assert pinned["runtime_version"] == RUNTIME_VERSION
    assert pinned["runtime_version"] != "9.9.9-host-copy", (
        "the pin recorded the host copy's version for a process that ran in a container"
    )
    assert pinned["image_digest"] == CONTAINER.image_digest
    assert result.admissibility_state == "admissible"


def test_container_version_mismatch_refuses_before_any_epoch(
    tmp_path: Path,
    skills: tuple[Path, Path],
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """driver -> version check -> mismatch -> refusal -> no epoch launch.

    The container reports a version the run did not declare. The refusal
    must fire before the spend boundary, not after.
    """
    fake = _fake_for(
        tmp_path,
        skills,
        container_prefix=CONTAINER.argv_prefix,
        container_version="0.86.0-unpinned",
        host_version=RUNTIME_VERSION,
    )
    _install(monkeypatch, fake)

    spec = _spec(tmp_path, skills, container=CONTAINER)
    with pytest.raises(RuntimeVersionMismatchError):
        run_paired_evaluation(spec, conn)

    assert not fake.spent, "an epoch launched despite the runtime-version refusal"
    assert fake.epoch_launches == []
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_validate_pre_spend_launches_no_epoch(
    tmp_path: Path, skills: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate is reachable without spending, and reports what it checked."""
    fake = _fake_for(tmp_path, skills)
    _install(monkeypatch, fake)

    validated = validate_pre_spend(_spec(tmp_path, skills))

    assert not fake.spent
    assert validated.checks == (
        "parser_identity",
        "runtime_version",
        "roster_full",
        "roster_null",
        "pair_symmetry",
        "pin_constructed",
    )
    assert validated.runtime_version == RUNTIME_VERSION
    assert [e.name for e in validated.full_roster] == ["baseline-skill", "rebase-trap"]
    assert [e.name for e in validated.null_roster] == ["baseline-skill"]
    assert validated.treatment.name == "rebase-trap"
