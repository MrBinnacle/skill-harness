"""Paired Full/Null Inspect tasks — the v0.2 primary contrast, as an adapter.

Design constraints (all load-bearing, all POC-established 2026-07-09):

- The two arms are IDENTICAL except for the one skill under test, passed via
  ``inspect_swe.claude_code(skills=[...])``. The Null arm is the STOCK agent
  environment — built-in skills remain present in both arms. The contrast
  answers "does adding this skill to a normal setup change outcomes."
- The agent's working directory is pinned explicitly and outcome oracles
  resolve paths against it — the sandbox default cwd differs from the agent's.
- The sandbox image is ENFORCED, not merely recorded: both arms run a
  generated compose file whose image is the pin's digest reference (Inspect's
  own default compose uses the floating tag "aisiuk/inspect-tool-support",
  which can drift under an unchanged config). ``env`` and
  ``disallowed_tools`` likewise flow from the SAME pin into both arms.
- ``inspect_ai`` / ``inspect_swe`` are an OPTIONAL extra: imports are lazy so
  the core package (audit, evidence store, aggregation) works without them.
"""

from __future__ import annotations

import base64
import hashlib
import tempfile
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

# Mirrors inspect_ai's auto-generated COMPOSE_GENERIC_YAML exactly, except the
# image is the pin's digest reference instead of the floating default tag.
_PINNED_COMPOSE_YAML = """# skill-harness pinned compose (generated from the harness pin)
# Mirrors inspect_ai's auto-compose; image is digest-pinned for admissibility.
services:
  default:
    image: "{image}"
    command: "tail -f /dev/null"
    init: true
    network_mode: none
    stop_grace_period: 1s
"""


class SubjectLayerNotInstalledError(RuntimeError):
    """Raised when inspect_ai/inspect_swe are missing (optional extra)."""


def files_as_data_uris(files: dict[str, str]) -> dict[str, str]:
    """Encode sample-file contents as data URIs for verbatim delivery.

    Inspect resolves each ``Sample.files`` VALUE against the local
    filesystem first: a value naming an existing directory is copied
    recursively (an EMPTY STRING resolves to the cwd and pulls the whole
    working directory into the sandbox), a value naming an existing file is
    replaced by that file's bytes, and inline text is only the fallback
    (``inspect_ai._eval.task.sandbox.resolve_sample_files``). Data URIs
    short-circuit that resolution, so contents arrive verbatim by
    construction. Pure stdlib — testable without the optional extra.
    """
    return {
        dest: "data:text/plain;base64," + base64.b64encode(content.encode("utf-8")).decode("ascii")
        for dest, content in files.items()
    }


def write_pinned_compose(pin: HarnessPin, compose_dir: Path | None = None) -> Path:
    """Write the digest-pinned compose file for ``pin`` and return its path.

    Content is a pure function of the pin's ``sandbox_image``, so the file
    name carries a content hash and rewrites are idempotent. Pure stdlib —
    testable without the optional extra.

    :raises ValueError: ``pin.sandbox`` is not "docker" (compose injection is
        a docker mechanism; other sandbox types have no pinned path yet) or
        ``pin.sandbox_image`` is not a digest reference.
    """
    if pin.sandbox != "docker":
        raise ValueError(
            f"sandbox {pin.sandbox!r} has no pinned-image mechanism; only 'docker' is supported"
        )
    if "@sha256:" not in pin.sandbox_image:
        raise ValueError(
            f"sandbox_image {pin.sandbox_image!r} is not digest-pinned; "
            "capture the pin via HarnessPin.capture()"
        )
    directory = compose_dir if compose_dir is not None else Path(tempfile.gettempdir())
    content = _PINNED_COMPOSE_YAML.format(image=pin.sandbox_image)
    name_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    path = directory / f"skill-harness-compose-{name_hash}.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def build_paired_tasks(
    *,
    skill_dir: Path,
    prompt: str,
    oracle: Literal["file_contains", "command_succeeds"],
    oracle_arg: str,
    oracle_target: str = "",
    pin: HarnessPin,
    epochs: int = 1,
    compose_dir: Path | None = None,
    files: dict[str, str] | None = None,
    retry_uncaught_errors: int | None = None,
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
        paths and agent paths agree, ``pin.sandbox_image`` is injected into
        both arms via a generated compose file, and ``pin.env`` /
        ``pin.disallowed_tools`` flow into both agents. The SAME pin object
        builds both arms — cross-arm pin equality holds by construction.
    :param epochs: paired repeats per arm (one .eval log per arm carries all
        epochs; the ingest write path pairs verdicts by epoch).
    :param compose_dir: where the pinned compose file is written (defaults to
        the system temp dir; the file must outlive the eval() call).
    :param files: sandbox files materialized before the agent runs (Inspect
        ``Sample.files``: destination path → contents), e.g. a fixture repo
        the task operates on. Contents are data-URI-encoded before reaching
        Inspect so they are delivered verbatim (see ``files_as_data_uris``
        for the path-resolution footgun this defends against). The SAME
        mapping goes to both arms.
    :param retry_uncaught_errors: passed through to ``inspect_swe.claude_code``
        — in-place retries when the agent binary exits 1 with empty stderr
        (inspect_swe's documented "scaffold bug" class). A resilience knob,
        not an agent-capability change, so it is NOT part of the pin
        fingerprint; the same value goes to both arms.
    :raises SubjectLayerNotInstalledError: optional extra not installed.
    :raises FileNotFoundError: ``skill_dir`` has no SKILL.md.
    :raises ValueError: pin not digest-pinned or sandbox type unsupported.
    """
    try:
        from inspect_ai import Task
        from inspect_ai.dataset import Sample
        from inspect_swe import claude_code
    except ImportError as exc:  # pragma: no cover — exercised only sans extra
        raise SubjectLayerNotInstalledError(_INSTALL_HINT) from exc

    if not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError(f"no SKILL.md in skill_dir: {skill_dir}")

    compose_path = write_pinned_compose(pin, compose_dir)
    scorer = _build_scorer(oracle, oracle_arg, oracle_target, pin.cwd)

    def make_task(condition: Condition) -> Task:
        agent = claude_code(
            skills=[skill_dir] if condition == "full" else None,
            model=pin.model,
            version=pin.agent_version,
            cwd=pin.cwd,
            env=dict(pin.env) if pin.env else None,
            disallowed_tools=list(pin.disallowed_tools) if pin.disallowed_tools else None,
            retry_uncaught_errors=retry_uncaught_errors,
        )
        return Task(
            dataset=[
                Sample(
                    input=prompt,
                    target=oracle_target or oracle_arg,
                    files=files_as_data_uris(files) if files else None,
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
            sandbox=(pin.sandbox, str(compose_path)),
            epochs=epochs,
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
