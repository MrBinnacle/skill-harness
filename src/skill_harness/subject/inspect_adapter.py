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

import atexit
import base64
import hashlib
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from skill_harness.subject.pin import HarnessPin

if TYPE_CHECKING:  # pragma: no cover — typing only; runtime import is lazy
    from inspect_ai import Task

_INSTALL_HINT = (
    'the agentic subject layer requires the optional extra: pip install "skill-harness[inspect]"'
)


def _yaml() -> Any:
    """Import PyYAML lazily, with this module's own install hint on failure.

    Module scope would be wrong here. PyYAML reaches this environment as a
    transitive dependency of ``inspect-swe``, which ships only in the optional
    ``[inspect]`` extra, while this module is deliberately importable WITHOUT
    that extra -- every inspect_ai symbol sits behind TYPE_CHECKING and a lazy
    runtime import for exactly that reason. A top-level ``import yaml`` makes a
    core install fail at import time with a bare ImportError naming a package
    the user never asked for, instead of the typed hint below.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - core install without the extra
        raise ImportError(f"skill frontmatter normalisation needs PyYAML: {_INSTALL_HINT}") from exc
    return yaml


Condition = Literal["full", "null"]
AGENT_CWD = "/root"  # inspect_swe claude_code default; oracles resolve against this

# Keys that the agentskills.io schema recognises (required + optional).
# Mirrors inspect_ai.tool._tools._skill.read._skill_schema properties.
_AGENTSKILLS_SCHEMA_KEYS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)
# Maximum description length enforced by the agentskills.io schema.
_AGENTSKILLS_DESCRIPTION_MAX_LENGTH = 1024

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


# ---------------------------------------------------------------------------
# F-6 (S55 hostile review): per-call mkdtemp cleanup
# ---------------------------------------------------------------------------
#
# write_pinned_compose()'s default (no compose_dir) path creates a fresh
# private directory per call via tempfile.mkdtemp() and nothing ever removed
# it -- every eval() run leaked one directory. The returned path must outlive
# the call (Inspect reads it later), so deletion-before-return is wrong; the
# fix is process-lifetime cleanup, not call-time cleanup. Caller-supplied
# compose_dir is NEVER tracked here -- the caller owns that directory's
# lifecycle (build_paired_tasks already passes one when it wants the
# idempotent-same-path behavior; ownership must stay with whoever created it).
_auto_created_compose_dirs: set[Path] = set()
_atexit_cleanup_registered = False


def _track_auto_created_compose_dir(directory: Path) -> None:
    """Register a mkdtemp-created compose dir for best-effort atexit cleanup."""
    global _atexit_cleanup_registered
    _auto_created_compose_dirs.add(directory)
    if not _atexit_cleanup_registered:
        atexit.register(_cleanup_auto_created_compose_dirs)
        _atexit_cleanup_registered = True


def _cleanup_auto_created_compose_dirs() -> None:
    """Best-effort rmtree of every auto-created compose dir at process exit.

    ``ignore_errors=True``: a cleanup failure (already removed, permissions,
    a concurrent eval() still reading the file) must never raise during
    interpreter shutdown -- atexit callbacks that raise print a warning and
    are otherwise swallowed, so failing loudly here would buy nothing while
    risking noisy shutdown output.
    """
    for directory in _auto_created_compose_dirs:
        shutil.rmtree(directory, ignore_errors=True)


class NormalisedSkillResult:
    """Result of normalising a skill directory's frontmatter.

    ``temp_dir`` is a skill directory suitable for ``read_skills`` /
    ``claude_code``.  When normalisation rewrote the card, that directory is
    a temporary copy (owned); otherwise it is the original ``skill_dir``.
    ``cleanup`` removes only an owned temporary root — never the original
    on-disk card.
    """

    def __init__(
        self,
        temp_dir: Path,
        dropped_keys: list[str],
        *,
        owned_temp_root: Path | None = None,
    ) -> None:
        self.temp_dir = temp_dir
        self.dropped_keys = dropped_keys
        self._owned_temp_root = owned_temp_root

    def cleanup(self) -> None:
        """Remove the owned temporary root, if any. Never touches the original card."""
        if self._owned_temp_root is not None:
            shutil.rmtree(self._owned_temp_root, ignore_errors=True)


def normalise_skill_frontmatter(skill_dir: Path) -> NormalisedSkillResult:
    """Read SKILL.md, drop keys outside the agentskills.io schema, write a
    temporary normalised copy, and return it.

    The on-disk SKILL.md is never modified.  The returned
    ``NormalisedSkillResult`` carries a skill directory suitable for
    ``read_skills`` / ``claude_code`` and the list of keys that were dropped.

    Normalisation rules (deliberately conservative — drop unknown keys; only
    coerce shapes the schema rejects without changing tool identity):

    - Any key not in the agentskills.io schema is dropped.
    - ``allowed-tools`` given as a list (Claude Code accepts it; the spec
      requires a string) is converted to a space-delimited string.
    - ``description`` exceeding the schema's 1024-character cap is
      truncated to 1024 characters.
    - Invalid YAML at the top level is re-raised (the card is genuinely
      broken).

    When a temporary copy is written, the full skill tree (scripts/,
    references/, assets/, and any other sibling of SKILL.md) is preserved;
    only the frontmatter of SKILL.md is rewritten.
    """
    skill_dir = skill_dir.resolve()
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"no SKILL.md in skill_dir: {skill_dir}")

    content = skill_file.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(content)

    if not frontmatter:
        return NormalisedSkillResult(temp_dir=skill_dir, dropped_keys=[])

    dropped_keys: list[str] = []
    normalised: dict[str, Any] = {}
    needs_normalisation = False

    for key, raw_value in frontmatter.items():
        if key not in _AGENTSKILLS_SCHEMA_KEYS:
            dropped_keys.append(str(key))
            needs_normalisation = True
            continue
        coerced: Any = raw_value
        if key == "allowed-tools" and isinstance(raw_value, list):
            coerced = " ".join(str(v) for v in raw_value)
            needs_normalisation = True
        if (
            key == "description"
            and isinstance(raw_value, str)
            and len(raw_value) > _AGENTSKILLS_DESCRIPTION_MAX_LENGTH
        ):
            coerced = raw_value[:_AGENTSKILLS_DESCRIPTION_MAX_LENGTH]
            needs_normalisation = True
        normalised[key] = coerced

    if not needs_normalisation:
        return NormalisedSkillResult(temp_dir=skill_dir, dropped_keys=[])

    # Full tree copy so scripts/references/assets survive; only SKILL.md is rewritten.
    tmp_root = Path(tempfile.mkdtemp(prefix="skill-harness-normalise-"))
    _track_auto_created_compose_dir(tmp_root)

    skill_name = normalised.get("name", skill_dir.name)
    if not isinstance(skill_name, str) or not skill_name:
        skill_name = skill_dir.name
    normalised_skill_dir = tmp_root / skill_name
    shutil.copytree(skill_dir, normalised_skill_dir)

    yaml_str = _yaml().dump(normalised, default_flow_style=False, sort_keys=False)
    (normalised_skill_dir / "SKILL.md").write_text(
        f"---\n{yaml_str}---\n\n{body}", encoding="utf-8"
    )

    return NormalisedSkillResult(
        temp_dir=normalised_skill_dir,
        dropped_keys=dropped_keys,
        owned_temp_root=tmp_root,
    )


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Returns (frontmatter dict, markdown body).  Returns ({}, content) when
    there is no frontmatter block.
    """
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    frontmatter_str = parts[1].strip()
    body = parts[2].lstrip("\n")
    # Bound once: naming _yaml() in the except clause would re-enter the import
    # while an exception is already in flight, and a failure there would mask
    # the YAML error it was supposed to catch.
    yaml = _yaml()
    try:
        fm = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter: {exc}") from exc
    return (fm if isinstance(fm, dict) else {}), body


def _validate_against_agentskills_schema(skill_dir: Path) -> None:
    """Raise ValueError when skill_dir would fail agentskills frontmatter validation.

    Mirrors inspect_ai's ``read_skills`` frontmatter checks (required keys,
    additionalProperties false, name matches directory) so coverage can refuse
    the same cards the harness refuses without requiring the inspect extra at
    report time. When inspect is installed, prefer its ``read_skills``.
    """
    try:
        from inspect_ai.tool import read_skills

        read_skills([skill_dir])
        return
    except ImportError:
        pass
    except Exception as exc:
        raise ValueError(str(exc)) from exc

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise ValueError(f"SKILL.md not found in: {skill_dir}")
    content = skill_file.read_text(encoding="utf-8")
    frontmatter, _body = _parse_frontmatter(content)
    try:
        from jsonschema import Draft7Validator
    except ImportError as exc:  # pragma: no cover — jsonschema is a core dep via inspect; fallback
        if "name" not in frontmatter or "description" not in frontmatter:
            raise ValueError("frontmatter missing required name or description") from exc
        unknown = set(frontmatter) - _AGENTSKILLS_SCHEMA_KEYS
        if unknown:
            raise ValueError(f"additional properties not allowed: {sorted(unknown)}") from None
        return

    schema = {
        "type": "object",
        "required": ["name", "description"],
        "properties": {
            "name": {
                "type": "string",
                "maxLength": 64,
                "pattern": r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
            },
            "description": {"type": "string", "maxLength": 1024},
            "license": {"type": "string"},
            "compatibility": {"type": "string", "maxLength": 500},
            "metadata": {"type": "object"},
            "allowed-tools": {"type": "string"},
        },
        "additionalProperties": False,
    }
    errors = list(Draft7Validator(schema).iter_errors(frontmatter))
    if errors:
        raise ValueError(
            "Found {n} validation error(s) parsing SKILL.md:\n{msgs}".format(
                n=len(errors),
                msgs="\n".join(f"- {e.message}" for e in errors),
            )
        )
    name = frontmatter.get("name")
    if name != skill_dir.name:
        raise ValueError(f"Skill name '{name}' does not match directory name '{skill_dir.name}'")


def files_as_data_uris(files: Mapping[str, str | bytes]) -> dict[str, str]:
    """Encode sample-file contents as data URIs for verbatim delivery.

    Inspect resolves each ``Sample.files`` VALUE against the local
    filesystem first: a value naming an existing directory is copied
    recursively (an EMPTY STRING resolves to the cwd and pulls the whole
    working directory into the sandbox), a value naming an existing file is
    replaced by that file's bytes, and inline text is only the fallback
    (``inspect_ai._eval.task.sandbox.resolve_sample_files``). Data URIs
    short-circuit that resolution, so contents arrive verbatim by
    construction. ``bytes`` values are delivered as-is (binary fixtures,
    e.g. OOXML archives); ``str`` values are UTF-8-encoded. Inspect's write
    path base64-decodes either form back to the same bytes
    (``read_sandboxenv_file``). Pure stdlib — testable without the extra.
    """

    def _encode(content: str | bytes) -> str:
        if isinstance(content, bytes):
            return "data:application/octet-stream;base64," + base64.b64encode(content).decode(
                "ascii"
            )
        return "data:text/plain;base64," + base64.b64encode(content.encode("utf-8")).decode("ascii")

    return {dest: _encode(content) for dest, content in files.items()}


def write_pinned_compose(pin: HarnessPin, compose_dir: Path | None = None) -> Path:
    """Write the digest-pinned compose file for ``pin`` and return its path.

    Content is a pure function of the pin's ``sandbox_image``, so the file
    name carries a content hash and rewrites to the SAME ``compose_dir`` are
    idempotent (same path, same bytes). Pure stdlib — testable without the
    optional extra.

    S3 hardening: when ``compose_dir`` is omitted, this used to write to
    ``tempfile.gettempdir()`` under a filename derived purely from
    ``pin.sandbox_image`` — predictable and, on a shared host, guessable
    ahead of time by any other tenant of that directory (a symlink pre-plant
    at that exact path would make ``write_text`` follow the symlink and
    overwrite whatever it points at). With no ``compose_dir``, each call now
    gets its own private ``tempfile.mkdtemp()`` directory instead — no shared
    namespace, nothing to pre-plant into. This changes the DEFAULT path's
    idempotency: repeated no-``compose_dir`` calls for the same pin no longer
    return the same path (each gets a fresh private directory); callers that
    want the idempotent-same-path behavior should pass an explicit
    ``compose_dir`` they control, as ``build_paired_tasks`` already does when
    given one, and as the test suite does throughout.

    Independent of which directory is used, the write is followed by a
    read-back content check (closes the window where a second writer races
    this call between the write and Inspect's later read of the same path),
    and a pre-write check refuses to write through an existing symlink or
    other non-regular-file entry at the target path.

    :raises ValueError: ``pin.sandbox`` is not "docker" (compose injection is
        a docker mechanism; other sandbox types have no pinned path yet) or
        ``pin.sandbox_image`` is not a digest reference.
    :raises RuntimeError: the target path exists and is not a regular file
        (possible symlink pre-plant), or the file's content did not match
        what was just written when read back (possible TOCTOU race).
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

    if compose_dir is not None:
        directory = compose_dir
    else:
        # S3: a private, unpredictable-named directory per call — nothing to
        # pre-plant a symlink into ahead of time (unlike the shared system
        # temp dir this used to write into directly).
        directory = Path(tempfile.mkdtemp(prefix="skill-harness-compose-"))
        # F-6: only auto-created dirs are tracked for cleanup -- an explicit
        # compose_dir is caller-owned and must never be removed out from under it.
        _track_auto_created_compose_dir(directory)

    content = _PINNED_COMPOSE_YAML.format(image=pin.sandbox_image)
    name_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    path = directory / f"skill-harness-compose-{name_hash}.yaml"

    # S3: refuse to write through a pre-existing symlink or other non-regular
    # entry — write_text() would otherwise follow a symlink and overwrite
    # whatever it points at with our content (a confused-deputy overwrite of
    # an attacker-chosen target, even though the content itself is ours).
    if path.exists() and not path.is_file():
        raise RuntimeError(
            f"refusing to write compose file: {path} exists and is not a regular "
            "file (possible symlink pre-plant)"
        )
    if path.is_symlink():
        raise RuntimeError(f"refusing to write compose file: {path} is a symlink")

    path.write_text(content, encoding="utf-8")

    # S3: read back and verify — catches a second writer racing this call
    # between the write above and Inspect's later read of the same path.
    if path.read_text(encoding="utf-8") != content:
        raise RuntimeError(
            f"compose file content mismatch after write: {path} (possible TOCTOU race)"
        )

    return path


def build_paired_tasks(
    *,
    skill_dir: Path,
    prompt: str,
    oracle: Literal["file_contains", "command_succeeds", "invariant_oracle", "completion_oracle"],
    oracle_arg: str,
    oracle_target: str = "",
    pin: HarnessPin,
    epochs: int = 1,
    compose_dir: Path | None = None,
    files: Mapping[str, str | bytes] | None = None,
    setup: str | None = None,
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

        TRUST BOUNDARY (S6): ``oracle_arg`` is interpolated into a shell
        string (``bash -lc <oracle_arg>`` for ``command_succeeds``; an
        f-string sandbox path for ``file_contains``) with no shell-escaping
        or path normalization. This is safe ONLY because ``oracle_arg`` is an
        operator-authored harness-config value (a task-definition parameter
        the eval author writes, like ``prompt`` and ``skill_dir``), never
        content extracted from a skill, an agent transcript, or any other
        untrusted/ingested source. ``network_mode: none`` on the sandbox
        (module docstring) bounds the blast radius if that assumption is
        ever violated, but it is not a substitute for it: a future caller
        that derives ``oracle_arg`` from task or skill material would need
        argv-based execution and path validation first.
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
    :param setup: bash script CONTENTS run in the sandbox before the agent
        starts (Inspect ``Sample.setup``) — the delivery mechanism for
        anything the bytes-only ``files`` path cannot express, e.g. the +x
        bit on a planted stub CLI. The SAME script goes to both arms, so
        cross-arm environment equality is preserved by construction, and it
        is serialized into the ``.eval`` log so ingest provenance
        (``source_eval_sha256``) covers it. Must be script CONTENTS, never a
        path: Inspect resolves a value naming an existing local file into
        that file's contents (the same footgun ``files_as_data_uris``
        defends against), so path-shaped values are refused outright.
    :param retry_uncaught_errors: passed through to ``inspect_swe.claude_code``
        — in-place retries when the agent binary exits 1 with empty stderr
        (inspect_swe's documented "scaffold bug" class). A resilience knob,
        not an agent-capability change, so it is NOT part of the pin
        fingerprint; the same value goes to both arms.
    :raises SubjectLayerNotInstalledError: optional extra not installed.
    :raises FileNotFoundError: ``skill_dir`` has no SKILL.md.
    :raises ValueError: pin not digest-pinned, sandbox type unsupported,
        ``oracle_target`` is empty while ``oracle="file_contains"``, or
        ``oracle_arg``/``oracle_target`` contains a NUL byte.
    """
    # S6 defense-in-depth: reject NUL bytes before oracle_arg reaches the shell
    # string / f-string path below. Never valid in a shell command or a POSIX
    # path, so this rejects nothing a legitimate operator-authored value would
    # ever contain — it only closes off string-truncation-style confusion if
    # this call site is ever reached with less-trusted input than today's
    # operator-authored harness config (see the TRUST BOUNDARY note above).
    if "\x00" in oracle_arg or "\x00" in oracle_target:
        raise ValueError("oracle_arg/oracle_target must not contain a NUL byte")

    if setup is not None:
        if "\x00" in setup:
            raise ValueError("setup must not contain a NUL byte")
        # Inspect resolves a setup value naming an existing file into that
        # file's contents — demand contents so delivery is verbatim by
        # construction (multi-line scripts can never collide with a path).
        if "\n" not in setup and Path(setup).exists():
            raise ValueError(
                "setup must be script CONTENTS, not a path to a script file "
                f"(got an existing path: {setup!r}) — read the file yourself "
                "and pass its text"
            )

    if oracle == "file_contains" and not oracle_target:
        raise ValueError(
            "oracle_target is required when oracle='file_contains' "
            "(an empty string would make the substring check vacuously true — "
            "every existing file would pass)"
        )

    try:
        from inspect_ai import Task
        from inspect_ai.dataset import Sample
        from inspect_swe import claude_code
    except ImportError as exc:  # pragma: no cover — exercised only sans extra
        raise SubjectLayerNotInstalledError(_INSTALL_HINT) from exc

    if not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError(f"no SKILL.md in skill_dir: {skill_dir}")

    # Normalise the frontmatter so cards with keys outside the agentskills.io
    # schema (e.g. disable-model-invocation, argument-hint) can still be
    # measured.  The on-disk SKILL.md is never modified — the normalised copy
    # lives in a temporary directory.
    normalised = normalise_skill_frontmatter(skill_dir)
    effective_skill_dir = normalised.temp_dir
    dropped_keys = normalised.dropped_keys

    compose_path = write_pinned_compose(pin, compose_dir)
    scorer = _build_scorer(oracle, oracle_arg, oracle_target, pin.cwd)

    def make_task(condition: Condition) -> Task:
        agent = claude_code(
            skills=[effective_skill_dir] if condition == "full" else None,
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
                    setup=setup,
                    metadata={
                        "condition": condition,
                        "skill": skill_dir.name,
                        "harness_pin": pin.model_dump(),
                        "harness_pin_fingerprint": pin.fingerprint(),
                        "normalised_keys_dropped": dropped_keys,
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
    oracle: Literal["file_contains", "command_succeeds", "invariant_oracle", "completion_oracle"],
    oracle_arg: str,
    oracle_target: str,
    cwd: str,
) -> Any:
    """Build the outcome scorer. All paths/commands resolve against the agent cwd.

    #424: ``invariant_oracle`` and ``completion_oracle`` are the split oracle
    scorers for trap-discipline cards. Each runs a separate bash command:
    - ``invariant_oracle``: checks if original local SHAs are ancestors of HEAD.
    - ``completion_oracle``: checks if teammate's work is integrated and pushed.
    """
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
                except FileNotFoundError as exc:
                    # missing file = a genuine wrong answer, not an apparatus
                    # fault — this is the ONLY exception we score rather than
                    # raise. Anything else (TimeoutError, PermissionError,
                    # ConnectionError, OSError, ...) is an infra/sandbox
                    # failure and must propagate: Inspect's eval() harness
                    # then marks the run as errored, which the ingest write
                    # path already refuses to admit rather than silently
                    # scoring it (see EvalLogNotSuccessError).
                    return Score(value=INCORRECT, explanation=f"read failed: {exc}")
                ok = oracle_target in content
                return Score(value=CORRECT if ok else INCORRECT, explanation=content[:200])

            return score

        return file_contains()

    if oracle in ("invariant_oracle", "completion_oracle"):
        scorer_name = oracle

        @scorer(metrics=[accuracy()], name=scorer_name)  # type: ignore[untyped-decorator]
        def _split_scorer() -> Any:
            async def score(state: TaskState, target: Target) -> Score:
                _ = state, target
                result = await sandbox().exec(["bash", "-lc", oracle_arg], cwd=cwd)
                explanation = (result.stdout + result.stderr)[-300:]
                return Score(
                    value=CORRECT if result.success else INCORRECT,
                    explanation=f"exit={result.returncode}: {explanation}",
                )

            return score

        return _split_scorer()

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


class SkillCorpusCoverage:
    """Coverage report for a corpus of skill cards.

    Records the set of candidate cards, how many were constructible (their
    frontmatter normalised successfully), and how many were refused (with
    reasons).  The refused set is always a subset of the candidate set.
    """

    def __init__(self) -> None:
        self.candidates: list[Path] = []
        self.constructible: list[Path] = []
        self.refused: list[tuple[Path, str]] = []

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def constructible_count(self) -> int:
        return len(self.constructible)

    @property
    def refused_count(self) -> int:
        return len(self.refused)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for config_json or JSON output."""
        return {
            "candidate_count": self.candidate_count,
            "constructible_count": self.constructible_count,
            "refused_count": self.refused_count,
            "refused": [{"path": str(p), "reason": r} for p, r in self.refused],
        }


def skill_corpus_coverage(corpus_dir: Path) -> SkillCorpusCoverage:
    """Measure how many cards in a directory can be loaded by the harness.

    Iterates over immediate subdirectories of ``corpus_dir``, each expected
    to contain a ``SKILL.md``.  For each, normalises frontmatter then validates
    the result against the agentskills schema (the same gate ``read_skills``
    applies at task construction). Records constructible vs refused with reasons.

    The on-disk cards are never modified.
    """
    report = SkillCorpusCoverage()
    if not corpus_dir.is_dir():
        return report

    for entry in sorted(corpus_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            continue
        report.candidates.append(entry)
        result: NormalisedSkillResult | None = None
        try:
            result = normalise_skill_frontmatter(entry)
            _validate_against_agentskills_schema(result.temp_dir)
            report.constructible.append(entry)
        except Exception as exc:
            report.refused.append((entry, str(exc)))
        finally:
            if result is not None:
                result.cleanup()

    return report
