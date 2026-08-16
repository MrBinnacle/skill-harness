"""Check the issue #174 assurance document's operator copy rule."""

from __future__ import annotations

import sys
from pathlib import Path


def main(path: Path) -> int:
    text = path.read_text(encoding="utf-8").lower()
    banned = [term for term in ("earned", "earn its place") if term in text]
    if banned:
        print(f"banned assurance vocabulary: {', '.join(banned)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
