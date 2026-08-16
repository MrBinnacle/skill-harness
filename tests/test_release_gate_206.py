"""External release-gate contracts for issue #206."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "release_gate.py"


def _run_gate(
    version: str,
    issue_states: dict[int, str],
    workflow_runs: list[dict[str, str]] | None = None,
    gate: Path = GATE,
) -> subprocess.CompletedProcess[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.endswith("/actions/workflows/assurance.yml/runs"):
                payload: object = {"workflow_runs": workflow_runs or []}
            else:
                issue = int(self.path.rsplit("/", 1)[-1])
                payload = {"state": issue_states[issue]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    env = os.environ | {
        "RELEASE_GATE_VERSION": version,
        "RELEASE_GATE_GITHUB_API_URL": f"http://127.0.0.1:{server.server_port}",
    }
    try:
        return subprocess.run(
            [sys.executable, str(gate)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_minor_release_is_blocked_while_an_assurance_issue_is_open() -> None:
    states = {issue: "open" if issue == 169 else "closed" for issue in range(167, 175)}
    result = _run_gate("0.3.0", states)

    assert result.returncode == 1
    assert "#169 is open" in result.stdout


def test_minor_release_is_blocked_without_a_green_assurance_lane_result() -> None:
    result = _run_gate("0.3.0", dict.fromkeys(range(167, 175), "closed"), workflow_runs=[])

    assert result.returncode == 1
    assert "no successful assurance.yml workflow run recorded" in result.stdout


def test_patch_release_023_stays_unblocked_without_assurance_state(tmp_path: Path) -> None:
    result = _run_gate("0.2.3", {})

    assert result.returncode == 0
    assert "RELEASE GATE: PASS" in result.stdout

    source = GATE.read_text(encoding="utf-8")
    exemption = '    if version.split(".")[:2] != ["0", "3"]:\n        return\n'
    assert source.count(exemption) == 2
    mutant = tmp_path / "release_gate.py"
    mutant.write_text(source.replace(exemption, ""), encoding="utf-8")
    poisoned = _run_gate("0.2.3", {}, gate=mutant)
    assert poisoned.returncode == 1
