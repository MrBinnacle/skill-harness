"""External release-gate contracts for the 0.3 assurance gate (#206).

Every test here drives ``scripts/release_gate.py`` as a subprocess against a
seeded repo tree (``--root``) and a local stand-in for the GitHub REST API. The
seeded tree passes G1-G6 by construction, so any ``FAIL`` line a run prints is
attributable to the assurance checks G7/G8 and nothing else — the assertions
compare the whole failure list, not a substring of it.

The tree is seeded rather than the version overridden: pointing the gate at a
version the tree does not declare would decouple the version checked from the
version shipped, which is the drift the gate exists to catch.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "release_gate.py"
RED_RECEIPT = ROOT / "docs" / "assurance" / "release-gate-red-206.md"
ASSURANCE_ISSUES = range(167, 175)
GREEN_RUN = {"status": "completed", "conclusion": "success"}
RUNS_PATH = "/actions/workflows/assurance.yml/runs"

# One SHA-pinned action so G5 passes on a populated workflows directory rather
# than on an empty one.
_PINNED_WORKFLOW = """\
jobs:
  build:
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
"""


def _seed_tree(root: Path, version: str) -> Path:
    """Write the minimal tree that satisfies G1-G5 at ``version``."""
    files = {
        "pyproject.toml": f'[project]\nname = "skill-harness-seed"\nversion = "{version}"\n',
        "src/skill_harness/__init__.py": f'__version__ = "{version}"\n',
        "CHANGELOG.md": (
            f"# Changelog\n\n## [Unreleased]\n\n## [{version}] — 2026-08-16\n\n"
            "### Added\n- Seeded entry.\n\n"
            f"[{version}]: https://github.com/MrBinnacle/skill-harness/releases\n"
        ),
        "README.md": (
            f"# Seed\n\nStatus: v{version} on PyPI. "
            "[PyPI](https://pypi.org/project/skill-harness/)\n"
        ),
        ".github/workflows/ci.yml": _PINNED_WORKFLOW,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _gate_env(api_url: str) -> dict[str, str]:
    """Gate environment: seeded API base, no inherited tag ref (G6)."""
    env = os.environ | {"RELEASE_GATE_GITHUB_API_URL": api_url}
    for tag_var in ("GITHUB_REF", "GITHUB_REF_NAME"):
        env.pop(tag_var, None)
    return env


def _invoke(root: Path, api_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(root)],
        cwd=str(ROOT),
        env=_gate_env(api_url),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _run_gate(
    root: Path,
    issue_states: dict[int, str],
    workflow_runs: list[dict[str, str]],
) -> subprocess.CompletedProcess[str]:
    """Run the gate against ``root`` with the GitHub answers seeded locally."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == RUNS_PATH:
                self._respond(200, {"workflow_runs": workflow_runs})
                return
            if self.path.startswith("/issues/"):
                issue = int(self.path.removeprefix("/issues/"))
                state = issue_states.get(issue)
                if state is None:
                    self._respond(404, {"message": f"issue #{issue} not seeded"})
                    return
                self._respond(200, {"state": state})
                return
            self._respond(404, {"message": f"unseeded path {self.path}"})

        def _respond(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            """Silence the stderr access log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        return _invoke(root, f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _failures(result: subprocess.CompletedProcess[str]) -> list[str]:
    """The gate's listed failures, in order, without the ``FAIL`` prefix."""
    return [
        line.strip().removeprefix("FAIL").strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("FAIL")
    ]


def _closed() -> dict[int, str]:
    return dict.fromkeys(ASSURANCE_ISSUES, "closed")


def test_zero_three_release_passes_when_assurance_is_closed_and_green(tmp_path: Path) -> None:
    """The positive case: G7/G8 are satisfiable, not a permanent block.

    Without this, both blocked cases below would stay green if G7/G8 appended
    their failures unconditionally.
    """
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    result = _run_gate(root, _closed(), [GREEN_RUN])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RELEASE GATE: PASS" in result.stdout
    assert _failures(result) == []


def test_zero_three_release_is_blocked_while_an_assurance_issue_is_open(tmp_path: Path) -> None:
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    states = _closed() | {169: "open"}
    result = _run_gate(root, states, [GREEN_RUN])

    assert result.returncode == 1
    assert _failures(result) == ["G7: assurance issue #169 is open"]


@pytest.mark.parametrize(
    ("runs", "case"),
    [
        ([], "no run at all"),
        ([{"status": "completed", "conclusion": "failure"}], "a completed red run"),
        ([{"status": "in_progress", "conclusion": ""}], "a run still in flight"),
    ],
    ids=["no-runs", "red-run", "in-flight-run"],
)
def test_zero_three_release_is_blocked_without_a_successful_assurance_run(
    tmp_path: Path, runs: list[dict[str, str]], case: str
) -> None:
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    result = _run_gate(root, _closed(), runs)

    assert result.returncode == 1, f"{case} must not satisfy G8"
    assert _failures(result) == ["G8: no successful assurance.yml workflow run recorded"]


def test_zero_three_release_is_blocked_when_the_assurance_state_is_unreadable(
    tmp_path: Path,
) -> None:
    """Fail closed: an API the gate cannot read is not evidence of a green lane."""
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]
    result = _invoke(root, f"http://127.0.0.1:{dead_port}")

    assert result.returncode == 1
    assert "RELEASE GATE: PASS" not in result.stdout
    failures = _failures(result)
    assert any(f.startswith("G7: could not read assurance issue #167") for f in failures), failures
    assert "G8: could not read assurance workflow runs" in " ".join(failures)


def test_patch_release_is_exempt_from_the_assurance_gate(tmp_path: Path) -> None:
    """The same seed that blocks 0.3.0 leaves a 0.2.x patch releasable.

    Differential pair with the two blocked tests above: identical GitHub state,
    identical tree apart from the declared version, opposite verdict. That is
    the exemption's external behaviour; no source-text inspection can show it.
    """
    root = _seed_tree(tmp_path / "tree", "0.2.4")
    states = dict.fromkeys(ASSURANCE_ISSUES, "open")
    result = _run_gate(root, states, [])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RELEASE GATE: PASS" in result.stdout
    assert _failures(result) == []


def _recorded_transcript() -> list[str]:
    """The lines of the receipt's fenced output block."""
    text = RED_RECEIPT.read_text(encoding="utf-8")
    _, _, after = text.partition("```text\n")
    block, fence, _ = after.partition("```")
    assert fence, "the RED receipt has no ```text output block"
    return [line for line in block.splitlines() if line.strip()]


def test_red_receipt_records_the_output_the_gate_actually_prints(tmp_path: Path) -> None:
    """The receipt is checked against the run, not just read for keywords.

    The recorded transcript is the demonstration's evidence. Comparing it to
    prose only would let the gate's copy change under it — the receipt would
    keep asserting a line the program no longer prints.
    """
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    result = _run_gate(root, _closed() | {169: "open"}, [])

    assert result.returncode == 1
    recorded = _recorded_transcript()
    assert recorded, "the RED receipt records no output"
    printed = [line for line in result.stdout.splitlines() if line.strip()]
    assert recorded == printed, (
        "receipt transcript has drifted from the gate's output:\n"
        f"recorded:\n{chr(10).join(recorded)}\n\nactual:\n{result.stdout}"
    )


def test_red_receipt_names_the_command_and_exit_code() -> None:
    text = RED_RECEIPT.read_text(encoding="utf-8")

    assert "RELEASE_GATE_GITHUB_API_URL" in text
    assert "python scripts/release_gate.py --root" in text
    assert "Exit code: `1`" in text
