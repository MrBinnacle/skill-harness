"""Schedule staleness check tests (#703).

Every test injects run data. No test calls the GitHub API: the script's
fetching half is never invoked here, only the pure evaluation half.
"""

from __future__ import annotations

import base64
import importlib.util
import io
import json
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    path = _REPO_ROOT / "scripts" / "schedule_staleness.py"
    spec = importlib.util.spec_from_file_location("schedule_staleness", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ss = _load()
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("cron", "period"),
    [
        ("30 1 * * 6", timedelta(days=7)),
        ("17 6 * * *", timedelta(days=1)),
        ("*/15 * * * *", timedelta(minutes=15)),
        ("0 0,12 * * *", timedelta(hours=12)),
        ("0 9 * * 1-5", timedelta(days=3)),
    ],
)
def test_cron_period_is_the_longest_gap_between_firings(cron: str, period: timedelta) -> None:
    assert ss.cron_period(cron) == period


def _schedule(last_success: datetime | None, cron: str = "30 1 * * 6") -> object:
    return ss.Schedule(
        repo="o/r",
        path=".github/workflows/x.yml",
        crons=(cron,),
        state="active",
        last_success=last_success,
    )


def test_old_last_success_is_flagged() -> None:
    stale = _schedule(NOW - timedelta(days=15))
    assert ss.stale_schedules([stale], NOW) == [stale]


def test_fresh_last_success_is_not_flagged() -> None:
    fresh = _schedule(NOW - timedelta(days=13))
    assert ss.stale_schedules([fresh], NOW) == []


def test_never_succeeded_is_flagged() -> None:
    never = _schedule(None)
    assert ss.stale_schedules([never], NOW) == [never]


def test_disabled_workflow_is_flagged_even_when_recent() -> None:
    disabled = ss.Schedule(
        repo="o/r",
        path=".github/workflows/x.yml",
        crons=("30 1 * * 6",),
        state="disabled_inactivity",
        last_success=NOW - timedelta(days=1),
    )
    assert ss.stale_schedules([disabled], NOW) == [disabled]


def test_shortest_cron_sets_the_threshold() -> None:
    two = ss.Schedule(
        repo="o/r",
        path=".github/workflows/x.yml",
        crons=("30 1 * * 6", "17 6 * * *"),
        state="active",
        last_success=NOW - timedelta(days=3),
    )
    assert ss.stale_schedules([two], NOW) == [two]


def test_crons_are_read_from_workflow_text() -> None:
    text = "on:\n  schedule:\n    - cron: \"23 7 * * 1\"\n    - cron: '0 0 * * *'\n"
    assert ss.parse_crons(text) == ("23 7 * * 1", "0 0 * * *")


def test_report_names_each_stale_workflow() -> None:
    body = ss.render_report([_schedule(None)], NOW)
    assert "o/r" in body and ".github/workflows/x.yml" in body and "never" in body


def test_every_api_request_goes_to_the_github_https_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = "on:\n  schedule:\n    - cron: '30 1 * * 6'\n"
    replies = iter(
        [
            {"workflows": [{"path": ".github/workflows/a.yml", "id": 1, "state": "active"}]},
            {"content": base64.b64encode(workflow.encode()).decode()},
            {"workflow_runs": []},
        ]
    )
    urls: list[str] = []

    class _Response(io.StringIO):
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> _Response:
        urls.append(request.full_url)
        return _Response(json.dumps(next(replies)))

    monkeypatch.setattr(ss.urllib.request, "urlopen", fake_urlopen)
    ss.fetch_schedules("owner/repo", "token")
    assert len(urls) == 3
    assert all(url.startswith("https://api.github.com/repos/owner/repo/") for url in urls)
