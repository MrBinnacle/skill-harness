"""Temporary console-width probe for #561. Not committed to the pull request."""

import os
import shutil
import sys


def test_report_console_width() -> None:
    from rich.console import Console

    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    ttys = {fd: os.isatty(fd) for fd in (0, 1, 2)}
    print(
        f"WIDTHPROBE worker={worker} "
        f"COLUMNS={os.environ.get('COLUMNS')!r} "
        f"TERM={os.environ.get('TERM')!r} "
        f"get_terminal_size={tuple(shutil.get_terminal_size())} "
        f"rich_width={Console().width} "
        f"rich_file_width={Console(file=sys.stdout).width} "
        f"isatty={ttys}",
        file=sys.stderr,
    )
