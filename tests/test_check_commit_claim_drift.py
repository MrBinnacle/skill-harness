"""Controls for ``scripts/check_commit_claim_drift.py`` (steering repo issue 61).

The check derives the commit counts the page asserts and fails on disagreement. The
controls here are the important half: a fixture whose figure disagrees with the derived
count must fail, and fail FOR THAT REASON - the assertions read the disagreement line by
name, never the exit code alone. A derivation that cannot run must exit 2, so a skip never
reads as clean.

The derivation is injected through ``main(derive=...)`` so the controls touch neither the
network nor the sibling clones. The real derivation is exercised separately against a
throwaway git repository built in ``tmp_path``, including the fresh-clone path the page
promises a reader, with a file path standing in for the GitHub URL.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "check_commit_claim_drift.py"
_LIVE_PAGE = _REPO_ROOT / "docs" / "why-this-exists.md"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_commit_claim_drift", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_commit_claim_drift"] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load()

_COLLECTION_CMD = (
    "git clone https://github.com/MrBinnacle/skills.git        "
    "&& git -C skills        rev-list --count HEAD"
)
_MACHINERY_CMD = (
    "git clone https://github.com/MrBinnacle/skill-harness.git "
    "&& git -C skill-harness rev-list --count HEAD"
)


def _page(collection: int = 152, machinery: int = 511, commands: str | None = None) -> str:
    """A fixture page in the live page's shape, figures parameterised."""
    if commands is None:
        commands = f"{_COLLECTION_CMD}\n{_MACHINERY_CMD}"
    return (
        "# Why this exists\n\n## Before\n\nprose\n\n"
        "## The size of the detour\n\n"
        f"Measured on 2026-09-02: **{collection} commits of collection against "
        f"{machinery} commits of machinery built\nto find out whether it is worth anything.**\n\n"
        "The basis is a fresh clone at `HEAD`:\n\n"
        f"```bash\n{commands}\n```\n\n"
        "## After\n\nmore prose\n"
    )


def _write_page(tmp_path: Path, text: str) -> Path:
    page = tmp_path / "why-this-exists.md"
    page.write_text(text, encoding="utf-8")
    return page


def _fake_derive(counts: dict[str, int]) -> Callable[[Any], int]:
    """A derivation keyed by the directory the page's command clones into."""

    def derive(derivation: Any) -> int:
        directory: str = derivation.directory
        return counts[directory]

    return derive


# --- parsing -----------------------------------------------------------------


def test_section_text_returns_only_the_named_section() -> None:
    section = MODULE.section_text(_page())
    assert section.startswith("## The size of the detour")
    assert "## After" not in section
    assert "## Before" not in section


def test_section_text_refuses_when_heading_is_absent() -> None:
    with pytest.raises(MODULE.CannotMeasure, match="section '## The size of the detour' not found"):
        MODULE.section_text("# Page\n\n## Other\n\ntext\n")


def test_parse_claim_reads_date_and_both_figures() -> None:
    claim = MODULE.parse_claim(MODULE.section_text(_page(7, 31)))
    assert (claim.measured_on, claim.collection, claim.machinery) == ("2026-09-02", 7, 31)


def test_parse_claim_refuses_a_section_without_the_sentence() -> None:
    with pytest.raises(MODULE.CannotMeasure, match="no dated commit-count claim"):
        MODULE.parse_claim("## The size of the detour\n\nNo figures here.\n")


def test_parse_derivations_keys_collection_first_and_machinery_second() -> None:
    derivations = MODULE.parse_derivations(MODULE.section_text(_page()))
    assert derivations["collection"] == MODULE.Derivation(
        "https://github.com/MrBinnacle/skills.git", "skills", "HEAD"
    )
    assert derivations["machinery"] == MODULE.Derivation(
        "https://github.com/MrBinnacle/skill-harness.git", "skill-harness", "HEAD"
    )


def test_parse_derivations_refuses_anything_but_two_commands() -> None:
    with pytest.raises(MODULE.CannotMeasure, match=r"expected 2 derivation commands.*found 1"):
        MODULE.parse_derivations(MODULE.section_text(_page(commands=_COLLECTION_CMD)))


# --- the controls, through main() --------------------------------------------


def test_positive_control_agreeing_figures_exit_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _write_page(tmp_path, _page(152, 511))
    code = MODULE.main(
        ["--page", str(page)], derive=_fake_derive({"skills": 152, "skill-harness": 511})
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "PASS: both figures on the page match a fresh derivation." in out
    assert "FAIL" not in out


def test_negative_control_stale_collection_figure_exits_1_for_that_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _write_page(tmp_path, _page(152, 511))
    code = MODULE.main(
        ["--page", str(page)], derive=_fake_derive({"skills": 159, "skill-harness": 511})
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL: 1 stale figure(s) on the page." in out
    assert "collection: page asserts 152, derivation yields 159" in out
    assert "machinery: page asserts" not in out, "the agreeing figure must not be reported stale"
    assert "REFUSED" not in out, "a disagreement is a FAIL, never a refusal to measure"


def test_negative_control_both_figures_stale_names_both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _write_page(tmp_path, _page(71, 323))
    code = MODULE.main(
        ["--page", str(page)], derive=_fake_derive({"skills": 152, "skill-harness": 511})
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL: 2 stale figure(s) on the page." in out
    assert "collection: page asserts 71, derivation yields 152" in out
    assert "machinery: page asserts 323, derivation yields 511" in out


def test_cannot_measure_control_derivation_failure_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _write_page(tmp_path, _page(152, 511))

    def derive(_derivation: object) -> int:
        raise MODULE.CannotMeasure("git is not installed or not on PATH")

    code = MODULE.main(["--page", str(page)], derive=derive)
    out = capsys.readouterr().out
    assert code == 2
    assert "REFUSED: git is not installed or not on PATH" in out
    assert "This is not a PASS." in out
    assert "PASS:" not in out


def test_cannot_measure_control_missing_page_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = MODULE.main(
        ["--page", str(tmp_path / "absent.md")],
        derive=_fake_derive({"skills": 1, "skill-harness": 1}),
    )
    out = capsys.readouterr().out
    assert code == 2
    assert "REFUSED: page not found" in out


def test_cannot_measure_control_page_without_commands_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _write_page(tmp_path, _page(commands="echo no derivation here"))
    code = MODULE.main(
        ["--page", str(page)], derive=_fake_derive({"skills": 152, "skill-harness": 511})
    )
    out = capsys.readouterr().out
    assert code == 2
    assert "REFUSED: expected 2 derivation commands" in out


def test_malformed_local_argument_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _write_page(tmp_path, _page())
    code = MODULE.main(["--page", str(page), "--local", "skills"])
    assert code == 2
    assert "REFUSED: --local expects NAME=PATH" in capsys.readouterr().out


# --- format_report ------------------------------------------------------------


def test_format_report_marks_each_surface() -> None:
    claim = MODULE.Claim("2026-09-02", 10, 20)
    result = MODULE.Result(claim, {"collection": 10, "machinery": 25}, ["machinery: x"])
    report = MODULE.format_report(result)
    assert "measured on 2026-09-02" in report
    assert "ok   collection" in report
    assert "FAIL machinery" in report
    assert "  machinery: x" in report
    assert report.isascii(), "report text must survive a cp1252 console"


# --- the real derivation, against a throwaway repository ------------------------


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def three_commit_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(["init", "--quiet", "-b", "main"], cwd=repo)
    for n in range(3):
        (repo / f"f{n}.txt").write_text(str(n), encoding="utf-8")
        _git(["add", "."], cwd=repo)
        _git(["commit", "--quiet", "-m", f"c{n}"], cwd=repo)
    return repo


def test_count_commits_via_local_substitute(three_commit_repo: Path) -> None:
    derivation = MODULE.Derivation("https://example.invalid/never-cloned.git", "skills", "HEAD")
    assert MODULE.count_commits(derivation, {"skills": three_commit_repo}) == 3


def test_count_commits_via_fresh_clone_of_a_file_source(three_commit_repo: Path) -> None:
    """The default path is the page's own command: clone, then count in the clone."""
    derivation = MODULE.Derivation(three_commit_repo.as_posix(), "skills", "HEAD")
    assert MODULE.count_commits(derivation) == 3


def test_count_commits_refuses_a_missing_local_clone(tmp_path: Path) -> None:
    derivation = MODULE.Derivation("https://example.invalid/x.git", "skills", "HEAD")
    with pytest.raises(MODULE.CannotMeasure, match="local clone for 'skills' not found"):
        MODULE.count_commits(derivation, {"skills": tmp_path / "nowhere"})


def test_count_commits_refuses_a_failing_clone(tmp_path: Path) -> None:
    derivation = MODULE.Derivation((tmp_path / "no-such-repo").as_posix(), "skills", "HEAD")
    with pytest.raises(MODULE.CannotMeasure, match=r"git clone .* failed"):
        MODULE.count_commits(derivation)


def test_count_commits_refuses_an_unknown_ref(three_commit_repo: Path) -> None:
    derivation = MODULE.Derivation("unused", "skills", "no-such-ref")
    with pytest.raises(MODULE.CannotMeasure, match="rev-list --count no-such-ref failed"):
        MODULE.count_commits(derivation, {"skills": three_commit_repo})


def test_check_end_to_end_against_a_throwaway_repo(three_commit_repo: Path) -> None:
    """The whole path, no seam: page commands point at the tmp repo, real git derives."""
    src = three_commit_repo.as_posix()
    commands = (
        f"git clone {src} && git -C skills rev-list --count HEAD\n"
        f"git clone {src} && git -C skill-harness rev-list --count HEAD"
    )
    passing = MODULE.check(_page(3, 3, commands), MODULE.count_commits)
    assert passing.agrees and passing.derived == {"collection": 3, "machinery": 3}
    stale = MODULE.check(_page(3, 4, commands), MODULE.count_commits)
    assert stale.disagreements == ["machinery: page asserts 4, derivation yields 3"]
    assert stale.derived["machinery"] == 3, "a stale page does not move the derived count"


# --- the live page is in the shape this check reads -----------------------------


def test_live_page_parses_into_a_claim_and_two_derivations() -> None:
    """Shape only, no derivation: the live figures are checked by running the script."""
    section = MODULE.section_text(_LIVE_PAGE.read_text(encoding="utf-8"))
    claim = MODULE.parse_claim(section)
    derivations = MODULE.parse_derivations(section)
    assert claim.collection > 0 and claim.machinery > claim.collection
    assert derivations["collection"].directory == "skills"
    assert derivations["machinery"].directory == "skill-harness"
    assert {d.ref for d in derivations.values()} == {"HEAD"}
