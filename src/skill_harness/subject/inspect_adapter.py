"""Paired Full/Null Inspect tasks — the v0.2 primary contrast, as an adapter.

Design constraints (all load-bearing, all POC-established 2026-07-09):

- The two arms are IDENTICAL except for the one skill under test, passed via
  ``inspect_swe.claude_code(skills=[...])``. The Null arm is the STOCK agent
  environment — built-in skills remain present in both arms. The contrast
  answers "does adding this skill to a normal setup change outcomes."
- The agent's working directory is pinned explicitly and outcome oracles
  resolve paths against it — the sandbox default cwd differs from the agent's.
- ``inspect_ai`` / ``inspect_swe`` are an OPTIONAL extra: imports are lazy so
  the core package (audit, evidence store, aggregation) works without them.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from skill_harness.subject.pin import HarnessPin

if TYPE_CHECKING:  # pragma: no cover — typing only; runtime import is lazy
    from inspect_ai import Task

_INSTALL_HINT = (
    'the agentic subject layer requires the optional extra: pip install "skill-harness[inspect]"'
)

Condition = Literal["full", "null"]
AGENT_CWD = "/root"  # inspect_swe claude_code default; oracles resolve against this


class SubjectLayerNotInstalledError(RuntimeError):
    """Raised when inspect_ai/inspect_swe are missing (optional extra)."""


def build_paired_tasks(
    *,
    skill_dir: Path,
    prompt: str,
    oracle: Literal["file_contains", "command_succeeds"],
    oracle_arg: str,
    oracle_target: str = "",
    pin: HarnessPin,
) -> dict[Condition, Task]:
    """Return {'full': Task, 'null': Task} differing ONLY by the skill.

    :param skill_dir: directory containing the SKILL.md under test (Full arm).
    :param prompt: the task given to the agent — identical in both arms.
    :param oracle: outcome oracle kind.
        ``file_contains`` — read ``oracle_arg`` (path relative to the agent
        cwd) from the sandbox and pass iff ``oracle_target`` is a substring.
        ``command_succeeds`` — run ``oracle_arg`` in the sandbox at the agent
        cwd and pass iff exit code 0 (the tests-pass oracle shape).
    :param pin: harness pin; ``pin.cwd`` is passed to the agent so oracle
        paths and agent paths agree. The SAME pin object builds both arms —
        cross-arm pin equality holds by construction.
    :raises SubjectLayerNotInstalledError: optional extra not installed.
    :raises FileNotFoundError: ``skill_dir`` has no SKILL.md.
    """
    try:
        from inspect_ai import Task
        from inspect_ai.dataset import Sample
        from inspect_swe import claude_code
    except ImportError as exc:  # pragma: no cover — exercised only sans extra
        raise SubjectLayerNotInstalledError(_INSTALL_HINT) from exc

    if not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError(f"no SKILL.md in skill_dir: {skill_dir}")

    scorer = _build_scorer(oracle, oracle_arg, oracle_target, pin.cwd)

    def make_task(condition: Condition) -> Task:
        agent = claude_code(
            skills=[skill_dir] if condition == "full" else None,
            model=pin.model,
            version=pin.agent_version,
            cwd=pin.cwd,
        )
        return Task(
            dataset=[
                Sample(
                    input=prompt,
                    target=oracle_target or oracle_arg,
                    metadata={
                        "condition": condition,
                        "skill": skill_dir.name,
                        "harness_pin": pin.model_dump(),
                        "harness_pin_fingerprint": pin.fingerprint(),
                    },
                )
            ],
            solver=agent,
            scorer=scorer,
            sandbox=pin.sandbox,
            name=f"{skill_dir.name}-{condition}",
        )

    return {"full": make_task("full"), "null": make_task("null")}


def _build_scorer(
    oracle: Literal["file_contains", "command_succeeds"],
    oracle_arg: str,
    oracle_target: str,
    cwd: str,
) -> Any:
    """Build the outcome scorer. All paths/commands resolve against the agent cwd."""
    from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, scorer
    from inspect_ai.solver import TaskState
    from inspect_ai.util import sandbox

    if oracle == "file_contains":
        path = oracle_arg if oracle_arg.startswith("/") else f"{cwd}/{oracle_arg}"

        @scorer(metrics=[accuracy()], name="file_contains")  # type: ignore[untyped-decorator]
        def file_contains() -> Any:
            async def score(state: TaskState, target: Target) -> Score:
                _ = state, target
                try:
                    content = await sandbox().read_file(path)
                except Exception as exc:  # missing file = fail, not crash
                    return Score(value=INCORRECT, explanation=f"read failed: {exc}")
                ok = oracle_target in content
                return Score(value=CORRECT if ok else INCORRECT, explanation=content[:200])

            return score

        return file_contains()

    @scorer(metrics=[accuracy()], name="command_succeeds")  # type: ignore[untyped-decorator]
    def command_succeeds() -> Any:
        async def score(state: TaskState, target: Target) -> Score:
            _ = state, target
            result = await sandbox().exec(["bash", "-lc", oracle_arg], cwd=cwd)
            explanation = (result.stdout + result.stderr)[-300:]
            return Score(
                value=CORRECT if result.success else INCORRECT,
                explanation=f"exit={result.returncode}: {explanation}",
            )

        return score

    return command_succeeds()
