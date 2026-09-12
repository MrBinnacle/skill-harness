"""Non-decision structural covariates for code-producing subject samples."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import tempfile
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "StructuralCovariateError",
    "StructuralCovariates",
    "StructuralRegistration",
    "StructuralUnmeasuredReason",
    "WorktreeMutationError",
    "collect_structural_covariates",
]

_FULL_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class StructuralCovariateError(Exception):
    """The registered structural measurement cannot run safely."""


class WorktreeMutationError(StructuralCovariateError):
    """A measurement command changed the candidate worktree."""


class StructuralUnmeasuredReason(StrEnum):
    """Closed refusal vocabulary for the first structural prototype."""

    NOT_GIT_REPOSITORY = "not_git_repository"
    BASE_COMMIT_UNAVAILABLE = "base_commit_unavailable"
    MISSING_ALLOWED_PATHS = "missing_allowed_paths"
    MISSING_REVERSE_TEST_PATHS = "missing_reverse_test_paths"
    MISSING_REVERSE_TEST_ARGV = "missing_reverse_test_argv"
    MISSING_MECHANICAL_CHECKS = "missing_mechanical_checks"
    NO_CHANGED_FILES = "no_changed_files"
    REVERSE_TEST_PATH_MISSING = "reverse_test_path_missing"
    SCOPE_GROWTH_UNAVAILABLE = "scope_growth_unavailable"


def _registered_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parts[0] == ".git"
    ):
        raise ValueError(
            f"registered path must be a normalized repository-relative path: {value!r}"
        )
    return value


def _argv(value: tuple[str, ...]) -> tuple[str, ...]:
    if not value or any(not part or "\x00" in part for part in value):
        raise ValueError("registered argv must contain non-empty arguments")
    return value


class StructuralRegistration(BaseModel):
    """Structural commands and scope fixed before subject execution."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    base_commit: str
    allowed_paths: tuple[str, ...]
    reverse_test_paths: tuple[str, ...]
    reverse_test_argv: tuple[str, ...]
    mechanical_check_argvs: tuple[tuple[str, ...], ...]

    @field_validator("base_commit")
    @classmethod
    def _full_commit(cls, value: str) -> str:
        if _FULL_COMMIT_RE.fullmatch(value) is None:
            raise ValueError("base_commit must be a registered full lowercase commit SHA")
        return value

    @field_validator("allowed_paths", "reverse_test_paths")
    @classmethod
    def _paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_registered_path(path) for path in value)

    @field_validator("reverse_test_argv")
    @classmethod
    def _reverse_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _argv(value)

    @field_validator("mechanical_check_argvs")
    @classmethod
    def _mechanical_argvs(cls, value: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, ...], ...]:
        return tuple(_argv(argv) for argv in value)

    @model_validator(mode="after")
    def _reverse_paths_inside_allowlist(self) -> Self:
        outside = [
            path
            for path in self.reverse_test_paths
            if not any(_path_is_allowed(path, allowed) for allowed in self.allowed_paths)
        ]
        if outside:
            raise ValueError(f"reverse-test path outside the registered allowlist: {outside}")
        return self


class StructuralCovariates(BaseModel):
    """One all-measured row or one typed refusal."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    state: Literal["measured", "unmeasured"]
    unmeasured_reason: StructuralUnmeasuredReason | None
    base_commit: str | None
    registration_json: str | None
    command_identity_json: str | None
    reverse_test_pass: bool | None
    scope_files_ok: bool | None
    scope_net_line_growth: int | None
    scope_changed_file_count: int | None
    mechanical_checks_ok: bool | None

    @model_validator(mode="after")
    def _all_measured_or_refused(self) -> Self:
        measured = (
            self.base_commit,
            self.registration_json,
            self.command_identity_json,
            self.reverse_test_pass,
            self.scope_files_ok,
            self.scope_net_line_growth,
            self.scope_changed_file_count,
            self.mechanical_checks_ok,
        )
        if self.state == "measured":
            if self.unmeasured_reason is not None or any(value is None for value in measured):
                raise ValueError("a measured row requires every channel and no refusal reason")
        elif self.unmeasured_reason is None or any(value is not None for value in measured[3:]):
            raise ValueError("an unmeasured row requires one typed reason and no measured channel")
        return self

    @classmethod
    def unmeasured(
        cls,
        reason: StructuralUnmeasuredReason,
        *,
        registration: StructuralRegistration | None = None,
    ) -> StructuralCovariates:
        return cls(
            state="unmeasured",
            unmeasured_reason=reason,
            base_commit=None if registration is None else registration.base_commit,
            registration_json=(None if registration is None else registration.model_dump_json()),
            command_identity_json=None,
            reverse_test_pass=None,
            scope_files_ok=None,
            scope_net_line_growth=None,
            scope_changed_file_count=None,
            mechanical_checks_ok=None,
        )


def _run(repo: Path, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    # The registration preserves argv boundaries and never invokes a shell.
    return subprocess.run(  # noqa: S603
        argv,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(repo, ("git", *args))


def _snapshot(repo: Path) -> tuple[str, str]:
    head = _git(repo, "rev-parse", "HEAD")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if head.returncode != 0 or status.returncode != 0:
        raise StructuralCovariateError("candidate worktree state cannot be read")
    return head.stdout.strip(), status.stdout


def _path_is_allowed(path: str, allowed: str) -> bool:
    prefix = allowed.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _changed_paths(repo: Path, base_commit: str) -> tuple[str, ...]:
    tracked = _git(repo, "diff", "--name-only", "-z", "--no-renames", base_commit, "--")
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked.returncode != 0 or untracked.returncode != 0:
        raise StructuralCovariateError("candidate changed paths cannot be read")
    values = (tracked.stdout + untracked.stdout).split("\x00")
    return tuple(sorted({value for value in values if value}))


def _scope_growth(repo: Path, base_commit: str, untracked: set[str]) -> int | None:
    diff = _git(repo, "diff", "--numstat", "-z", "--no-renames", base_commit, "--")
    if diff.returncode != 0:
        raise StructuralCovariateError("candidate line growth cannot be read")
    growth = 0
    for record in diff.stdout.split("\x00"):
        if not record:
            continue
        added, deleted, _path = record.split("\t", 2)
        if added == "-" or deleted == "-":
            return None
        growth += int(added) - int(deleted)
    for relative in untracked:
        data = (repo / relative).read_bytes()
        if b"\x00" in data:
            return None
        growth += len(data.decode("utf-8").splitlines())
    return growth


def _command_identity(
    registration: StructuralRegistration,
    *,
    reverse_returncode: int,
    mechanical_returncodes: list[int],
    git_version: str,
) -> str:
    return json.dumps(
        {
            "tool_runtime": {
                "git": git_version,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "reverse_test": {
                "argv": list(registration.reverse_test_argv),
                "returncode": reverse_returncode,
            },
            "mechanical_checks": [
                {"argv": list(argv), "returncode": returncode}
                for argv, returncode in zip(
                    registration.mechanical_check_argvs, mechanical_returncodes, strict=True
                )
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def collect_structural_covariates(
    *, repo: Path, registration: StructuralRegistration
) -> StructuralCovariates:
    """Measure registered structure without changing the candidate or any verdict."""
    repo = repo.resolve()
    inside = _git(repo, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.NOT_GIT_REPOSITORY, registration=registration
        )
    if not registration.allowed_paths:
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.MISSING_ALLOWED_PATHS, registration=registration
        )
    if not registration.reverse_test_paths:
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.MISSING_REVERSE_TEST_PATHS, registration=registration
        )
    if not registration.reverse_test_argv:
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.MISSING_REVERSE_TEST_ARGV, registration=registration
        )
    if not registration.mechanical_check_argvs:
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.MISSING_MECHANICAL_CHECKS, registration=registration
        )

    resolved = _git(repo, "rev-parse", "--verify", f"{registration.base_commit}^{{commit}}")
    ancestor = _git(repo, "merge-base", "--is-ancestor", registration.base_commit, "HEAD")
    if (
        resolved.returncode != 0
        or resolved.stdout.strip() != registration.base_commit
        or ancestor.returncode != 0
    ):
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.BASE_COMMIT_UNAVAILABLE, registration=registration
        )

    before = _snapshot(repo)
    paths = _changed_paths(repo, registration.base_commit)
    if not paths:
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.NO_CHANGED_FILES, registration=registration
        )
    changed = set(paths)
    if any(
        path not in changed or not (repo / path).is_file()
        for path in registration.reverse_test_paths
    ):
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.REVERSE_TEST_PATH_MISSING, registration=registration
        )

    untracked_process = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked_process.returncode != 0:
        raise StructuralCovariateError("candidate untracked paths cannot be read")
    untracked = {path for path in untracked_process.stdout.split("\x00") if path}
    growth = _scope_growth(repo, registration.base_commit, untracked)
    if growth is None:
        return StructuralCovariates.unmeasured(
            StructuralUnmeasuredReason.SCOPE_GROWTH_UNAVAILABLE, registration=registration
        )
    scope_ok = all(
        any(_path_is_allowed(path, allowed) for allowed in registration.allowed_paths)
        for path in paths
    )

    git_version_process = _git(repo, "--version")
    if git_version_process.returncode != 0:
        raise StructuralCovariateError("git command identity cannot be measured")

    reverse_returncode: int | None = None
    mechanical_returncodes: list[int] = []
    worktree = Path(tempfile.mkdtemp(prefix="skill-harness-structural-"))
    worktree.rmdir()
    try:
        added = _git(
            repo,
            "worktree",
            "add",
            "--detach",
            worktree.as_posix(),
            registration.base_commit,
        )
        if added.returncode != 0:
            raise StructuralCovariateError(
                f"disposable worktree creation failed: {added.stderr.strip()}"
            )
        for relative in registration.reverse_test_paths:
            destination = worktree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / relative, destination)
        reverse_returncode = _run(worktree, registration.reverse_test_argv).returncode
        for argv in registration.mechanical_check_argvs:
            mechanical_returncodes.append(_run(repo, argv).returncode)
    finally:
        if worktree.exists():
            removed = _git(repo, "worktree", "remove", "--force", worktree.as_posix())
            if removed.returncode != 0:
                shutil.rmtree(worktree, ignore_errors=True)
                _git(repo, "worktree", "prune")
        after = _snapshot(repo)
        if after != before:
            raise WorktreeMutationError("structural measurement changed the candidate worktree")

    if reverse_returncode is None:
        raise StructuralCovariateError("reverse test did not run")
    return StructuralCovariates(
        state="measured",
        unmeasured_reason=None,
        base_commit=registration.base_commit,
        registration_json=registration.model_dump_json(),
        command_identity_json=_command_identity(
            registration,
            reverse_returncode=reverse_returncode,
            mechanical_returncodes=mechanical_returncodes,
            git_version=git_version_process.stdout.strip(),
        ),
        reverse_test_pass=reverse_returncode != 0,
        scope_files_ok=scope_ok,
        scope_net_line_growth=growth,
        scope_changed_file_count=len(paths),
        mechanical_checks_ok=all(code == 0 for code in mechanical_returncodes),
    )
