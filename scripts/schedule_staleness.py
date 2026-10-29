"""Schedule staleness check: report scheduled workflows that stopped succeeding.

A scheduled workflow that fails, or that GitHub disables after 60 days of
repository inactivity, reports nothing unless it files its own issue. This
script lists every workflow with a ``schedule:`` trigger in the named
repositories, reads each one's last successful run, and flags it when that
run is older than twice its shortest cron period, when it never succeeded,
or when the workflow is not ``active``.

Advisory: it always exits 0 once the data is read. It writes a Markdown
report to ``--out`` and prints ``STALE <n>``; the calling workflow opens or
updates one issue from that report. Exit 2 means the API could not be read.

Run locally: ``GITHUB_TOKEN=... python scripts/schedule_staleness.py
--repo OWNER/A --repo OWNER/B --out report.md``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

_CRON_LINE = re.compile(r"""^\s*-?\s*cron:\s*["']?([^"'#\n]+?)["']?\s*(?:#.*)?$""", re.MULTILINE)
_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
_WINDOW_DAYS = 70


@dataclass(frozen=True)
class Schedule:
    repo: str
    path: str
    crons: tuple[str, ...]
    state: str
    last_success: datetime | None


def parse_crons(workflow_text: str) -> tuple[str, ...]:
    return tuple(m.group(1).strip() for m in _CRON_LINE.finditer(workflow_text))


def _expand(field: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()
    for part in field.split(","):
        base, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if base == "*":
            start, end = low, high
        elif "-" in base:
            first, last = base.split("-")
            start, end = int(first), int(last)
        else:
            start = int(base)
            end = high if step_text else start
        values.update(range(start, end + 1, step))
    return frozenset(v % 7 if high == 6 else v for v in values)


def _firings(cron: str, start: datetime, days: int) -> Iterable[datetime]:
    fields = cron.split()
    minutes, hours, doms, months, dows = (
        _expand(f, lo, hi) for f, (lo, hi) in zip(fields, _FIELD_RANGES, strict=True)
    )
    dom_any, dow_any = fields[2] == "*", fields[4] == "*"
    for offset in range(days):
        day = start + timedelta(days=offset)
        dom_ok, dow_ok = day.day in doms, (day.isoweekday() % 7) in dows
        day_ok = dom_ok and dow_ok if dom_any or dow_any else dom_ok or dow_ok
        if day.month not in months or not day_ok:
            continue
        for hour in sorted(hours):
            for minute in sorted(minutes):
                yield day.replace(hour=hour, minute=minute)


def cron_period(cron: str) -> timedelta:
    """Longest gap between consecutive firings over a fixed 70-day window."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    times = list(_firings(cron, start, _WINDOW_DAYS))
    if len(times) < 2:
        return timedelta(days=_WINDOW_DAYS)
    return max(later - earlier for earlier, later in pairwise(times))


def stale_schedules(schedules: Sequence[Schedule], now: datetime) -> list[Schedule]:
    stale = []
    for schedule in schedules:
        threshold = 2 * min(cron_period(c) for c in schedule.crons)
        if (
            schedule.state != "active"
            or schedule.last_success is None
            or now - schedule.last_success > threshold
        ):
            stale.append(schedule)
    return stale


def render_report(stale: Sequence[Schedule], now: datetime) -> str:
    lines = [
        f"Checked at {now:%Y-%m-%d %H:%M} UTC. A scheduled workflow is listed when its "
        "last success is older than twice its shortest cron period, it never "
        "succeeded, or it is not active.",
        "",
        "| Repository | Workflow | Cron | State | Last success |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in stale:
        last = f"{s.last_success:%Y-%m-%d %H:%M}" if s.last_success else "never"
        crons = ", ".join(f"`{c}`" for c in s.crons)
        lines.append(f"| {s.repo} | `{s.path}` | {crons} | {s.state} | {last} |")
    return "\n".join(lines) + "\n"


def _get(url: str, token: str) -> Any:
    request = urllib.request.Request(  # noqa: S310, RUF100 - URL is fixed to GitHub's HTTPS API origin
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def fetch_schedules(repo: str, token: str) -> list[Schedule]:
    api = f"https://api.github.com/repos/{repo}"
    schedules = []
    for wf in _get(f"{api}/actions/workflows?per_page=100", token)["workflows"]:
        if not wf["path"].startswith(".github/workflows/"):
            continue
        content = _get(f"{api}/contents/{wf['path']}", token)["content"]
        crons = parse_crons(base64.b64decode(content).decode("utf-8"))
        if not crons:
            continue
        runs = _get(f"{api}/actions/workflows/{wf['id']}/runs?status=success&per_page=1", token)[
            "workflow_runs"
        ]
        last = datetime.fromisoformat(runs[0]["updated_at"]) if runs else None
        schedules.append(Schedule(repo, wf["path"], crons, wf["state"], last))
    return schedules


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        schedules = [s for repo in args.repo for s in fetch_schedules(repo, token)]
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        print(f"SCHEDULE STALENESS: REFUSED ({exc})", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    stale = stale_schedules(schedules, now)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(render_report(stale, now))
    print(f"checked {len(schedules)} scheduled workflows")
    print(f"STALE {len(stale)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
