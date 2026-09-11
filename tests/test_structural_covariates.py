from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from skill_harness.subject.structural_covariates import (
    StructuralCovariates,
    StructuralRegistration,
    StructuralUnmeasuredReason,
    WorktreeMutationError,
    collect_structural_covariates,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args), cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _candidate(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "candidate"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (repo / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text(
        "from src.app import VALUE\nraise SystemExit(0 if VALUE == 1 else 1)\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "src" / "app.py").write_text("VALUE = 2\nEXTRA = 3\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text(
        "from src.app import VALUE\nraise SystemExit(0 if VALUE == 2 else 1)\n",
        encoding="utf-8",
    )
    return repo, base


def _registration(base: str, **updates: Any) -> StructuralRegistration:
    values: dict[str, Any] = {
        "base_commit": base,
        "allowed_paths": ("src", "tests"),
        "reverse_test_paths": ("tests/test_app.py",),
        "reverse_test_argv": ("python", "tests/test_app.py"),
        "mechanical_check_argvs": (("python", "-m", "compileall", "-q", "src"),),
    }
    values.update(updates)
    return StructuralRegistration(**values)


def test_collects_all_registered_channels_without_candidate_mutation(tmp_path: Path) -> None:
    repo, base = _candidate(tmp_path)
    before = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")

    result = collect_structural_covariates(repo=repo, registration=_registration(base))

    assert result.state == "measured"
    assert result.reverse_test_pass is True
    assert result.scope_files_ok is True
    assert result.scope_net_line_growth == 1
    assert result.scope_changed_file_count == 2
    assert result.mechanical_checks_ok is True
    identity = json.loads(result.command_identity_json or "{}")
    assert identity["reverse_test"]["argv"] == ["python", "tests/test_app.py"]
    assert identity["reverse_test"]["returncode"] != 0
    assert identity["mechanical_checks"][0]["returncode"] == 0
    assert _git(repo, "status", "--porcelain=v1", "--untracked-files=all") == before


def test_missing_channel_is_typed_unmeasured(tmp_path: Path) -> None:
    repo, base = _candidate(tmp_path)
    registration = _registration(base, mechanical_check_argvs=())

    result = collect_structural_covariates(repo=repo, registration=registration)

    assert result.state == "unmeasured"
    assert result.unmeasured_reason is StructuralUnmeasuredReason.MISSING_MECHANICAL_CHECKS
    assert result.reverse_test_pass is None
    assert result.scope_files_ok is None
    assert result.scope_net_line_growth is None
    assert result.scope_changed_file_count is None
    assert result.mechanical_checks_ok is None


def test_registration_rejects_post_hoc_symbolic_commit_and_shell_string(tmp_path: Path) -> None:
    _repo, base = _candidate(tmp_path)
    with pytest.raises(ValidationError):
        _registration("HEAD")
    with pytest.raises(ValidationError):
        _registration(base, reverse_test_argv="python tests/test_app.py")


def test_registration_rejects_reverse_path_outside_allowlist(tmp_path: Path) -> None:
    _repo, base = _candidate(tmp_path)
    with pytest.raises(ValidationError, match="outside the registered allowlist"):
        _registration(base, allowed_paths=("src",), reverse_test_paths=("tests/test_app.py",))


def test_mixed_refusal_and_measurement_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StructuralCovariates(
            state="unmeasured",
            unmeasured_reason=StructuralUnmeasuredReason.NO_CHANGED_FILES,
            base_commit=None,
            registration_json=None,
            command_identity_json=None,
            reverse_test_pass=True,
            scope_files_ok=None,
            scope_net_line_growth=None,
            scope_changed_file_count=None,
            mechanical_checks_ok=None,
        )


def test_mechanical_check_mutation_is_rejected(tmp_path: Path) -> None:
    repo, base = _candidate(tmp_path)
    mutation = (
        "python",
        "-c",
        "from pathlib import Path; Path('src/app.py').write_text('MUTATED\\n')",
    )
    with pytest.raises(WorktreeMutationError):
        collect_structural_covariates(
            repo=repo,
            registration=_registration(base, mechanical_check_argvs=(mutation,)),
        )


def test_decision_modules_do_not_import_structural_covariates() -> None:
    root = Path(__file__).resolve().parent.parent / "src" / "skill_harness"
    decision_roots = (root / "aggregation", root / "cli" / "paired_gate2.py")
    hits: list[str] = []
    for decision_root in decision_roots:
        paths = decision_root.rglob("*.py") if decision_root.is_dir() else (decision_root,)
        for path in paths:
            if "structural_covariates" in path.read_text(encoding="utf-8"):
                hits.append(path.relative_to(root).as_posix())
    assert hits == []
