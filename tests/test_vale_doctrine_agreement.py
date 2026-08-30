"""Vale doctrine-to-rule agreement tests (#304).

Proves that every Taste rule file's message names an existing doctrine row,
every fixture is parseable by Vale, fail fixtures report exactly one finding
for the named row, pass fixtures report none, and the poison control passes.

Fixture-only: no network, no model calls. Requires the Vale binary on PATH
(or at ~/.local/bin/vale), pinned to the same version the CI workflow installs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STYLES_DIR = _REPO_ROOT / "styles" / "Taste"
_FIXTURES_DIR = _REPO_ROOT / "fixtures" / "vale"

_EXPECTED_ROWS = {
    "Dressing",
    "Evidence",
    "Generic-ness",
    "Voice",
    "Register",
    "Brevity-and-order",
}


def _resolve_vale_bin() -> Path:
    """Locate the Vale binary: PATH first, then the local install path used in docs."""
    found = shutil.which("vale")
    if found:
        return Path(found)
    local = Path.home() / ".local" / "bin" / "vale"
    if local.is_file() and os.access(local, os.X_OK):
        return local
    raise FileNotFoundError(
        "Vale binary not found on PATH or at ~/.local/bin/vale. "
        "Install the version pinned in .github/workflows/ci.yml before running these tests."
    )


_MISSING_VALE_REASON = (
    "Vale binary not found on PATH or at ~/.local/bin/vale; install the version "
    "pinned in .github/workflows/ci.yml"
)

try:
    _RESOLVED_VALE_BIN: Path | None = _resolve_vale_bin()
except FileNotFoundError:
    # Raising here would abort pytest during COLLECTION, so a contributor without
    # the binary could not run ANY test in this repository, not merely this
    # module. The repo's idiom for an absent tool is a skip that names what to
    # install (tests/test_fuzz_170.py does this for atheris).
    #
    # One job installs Vale and must fail loudly if it is missing there, because
    # a skip would convert a regressed install step into a green run. Every other
    # job legitimately has no Vale and must skip.
    #
    # The signal is an explicit opt-in, NOT the generic CI variable. GitHub sets
    # CI=true in every job, including `calibration`, which never installs Vale
    # and whose `pytest -m calibration` still IMPORTS this module during
    # collection. Keying on CI therefore reddened four calibration cells that
    # were never meant to need the binary. The env var below is set only by the
    # job whose own steps install it, so the invariant it asserts is true by
    # construction.
    if os.environ.get("SKILL_HARNESS_REQUIRE_VALE") == "1":
        raise
    _RESOLVED_VALE_BIN = None

pytestmark = pytest.mark.skipif(_RESOLVED_VALE_BIN is None, reason=_MISSING_VALE_REASON)

# Every test in this module is skipped when the binary is absent, so this value
# is only ever read on a path where the resolution succeeded.
_VALE_BIN = _RESOLVED_VALE_BIN if _RESOLVED_VALE_BIN is not None else Path("vale")


def _get_rule_files() -> list[Path]:
    return list(_STYLES_DIR.glob("*.yml"))


def _extract_row_name_from_message(content: str) -> str | None:
    """Extract the row name from a rule file's message field.

    Messages follow the pattern: "RowName: '%s' ..."
    """
    for line in content.splitlines():
        if line.startswith("message:"):
            msg = line.split("message:", 1)[1].strip()
            if ":" in msg:
                return msg.split(":")[0].strip().strip("'\"")
    return None


def _run_vale_json(file_path: Path) -> dict[str, list[dict[str, object]]]:
    """Run Vale with JSON output and return the parsed alert map."""
    result = subprocess.run(
        [
            str(_VALE_BIN),
            "--config",
            str(_REPO_ROOT / ".vale.ini"),
            "--output=JSON",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode in (0, 1), (
        f"Vale failed on {file_path.name}: rc={result.returncode} stderr={result.stderr}"
    )
    if not result.stdout.strip():
        return {}
    data = json.loads(result.stdout)
    assert isinstance(data, dict)
    return data


def _alerts_for(file_path: Path) -> list[dict[str, object]]:
    data = _run_vale_json(file_path)
    alerts: list[dict[str, object]] = []
    for items in data.values():
        assert isinstance(items, list)
        alerts.extend(items)
    return alerts


class TestDoctrineToRuleAgreement:
    """Test that doctrine rows and rule files agree."""

    def test_all_rule_files_exist(self) -> None:
        """Every expected doctrine row has a corresponding rule file."""
        rule_files = {f.stem for f in _get_rule_files()}
        missing = _EXPECTED_ROWS - rule_files
        assert not missing, f"Missing rule files for rows: {missing}"

    def test_rule_messages_name_existing_rows(self) -> None:
        """Every rule file's message names an existing doctrine row."""
        for rule_file in _get_rule_files():
            content = rule_file.read_text(encoding="utf-8")
            row_name = _extract_row_name_from_message(content)
            assert row_name is not None, f"No message found in {rule_file.name}"
            assert row_name in _EXPECTED_ROWS, (
                f"Rule {rule_file.name} message names '{row_name}', "
                f"which is not in the expected rows"
            )

    def test_no_landing_rule(self) -> None:
        """No rule file or fixture is named 'Landing'."""
        rule_files = {f.stem for f in _get_rule_files()}
        assert "Landing" not in rule_files, "A rule file named 'Landing' exists"
        fixture_files = {f.stem for f in _FIXTURES_DIR.glob("*.md")}
        assert "Landing" not in fixture_files, "A fixture named 'Landing' exists"

    def test_all_fixtures_are_parseable(self) -> None:
        """Every fixture file can be parsed by Vale without errors."""
        for fixture in _FIXTURES_DIR.glob("*.md"):
            _run_vale_json(fixture)

    def test_pass_fixtures_have_zero_findings(self) -> None:
        """Pass fixtures produce zero Vale findings."""
        for fixture in sorted(_FIXTURES_DIR.glob("*-pass.md")):
            alerts = _alerts_for(fixture)
            assert alerts == [], (
                f"Pass fixture {fixture.name} has {len(alerts)} finding(s): {alerts}"
            )

    def test_fail_fixtures_have_exactly_one_finding_for_named_row(self) -> None:
        """Each fail fixture yields exactly one finding for its doctrine row."""
        for fixture in sorted(_FIXTURES_DIR.glob("*-fail.md")):
            row = fixture.stem.removesuffix("-fail")
            assert row in _EXPECTED_ROWS, f"Unexpected fail fixture row: {row}"
            alerts = _alerts_for(fixture)
            assert len(alerts) == 1, (
                f"Fail fixture {fixture.name} has {len(alerts)} finding(s), "
                f"expected exactly 1. Alerts: {alerts}"
            )
            check = str(alerts[0].get("Check", ""))
            message = str(alerts[0].get("Message", ""))
            expected_check = f"Taste.{row}"
            assert check == expected_check, (
                f"Fail fixture {fixture.name} reported Check={check!r}, expected {expected_check!r}"
            )
            assert message.startswith(f"{row}:"), (
                f"Fail fixture {fixture.name} message {message!r} does not name row {row!r}"
            )

    def test_poison_control_has_zero_findings(self) -> None:
        """The poison control fixture produces zero Vale findings."""
        poison_fixture = _FIXTURES_DIR / "poison-empty.md"
        assert poison_fixture.is_file(), "poison-empty.md is required"
        alerts = _alerts_for(poison_fixture)
        assert alerts == [], f"Poison control fixture has {len(alerts)} finding(s): {alerts}"
