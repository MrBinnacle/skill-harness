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


def _run_gate(version: str, issue_states: dict[int, str]) -> subprocess.CompletedProcess[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            issue = int(self.path.rsplit("/", 1)[-1])
            body = json.dumps({"state": issue_states[issue]}).encode()
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
            [sys.executable, str(GATE)],
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
