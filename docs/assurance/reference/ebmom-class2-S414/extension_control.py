"""Rule-1 control for the S414 burned-root extension.

Worlds 0 to 999 of the R = 4000 low_heterogeneity dump must reproduce the committed R = 1000
class-2 dump row for row, in every column of the per-world table. A difference voids the
extension. Also prints the admitted 6c cell over the new worlds (1000-3999) per column, read
straight from the rows, as a cross-check on clustered_bound.py.

Usage: python extension_control.py <committed R1000 all-regime dump> <R4000 regime dump>
ASCII only.
"""
from __future__ import annotations

import json
import sys


def load_regime(path: str, regime: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["regimes"][regime]


def main(committed: str, extended: str, regime: str = "low_heterogeneity") -> int:
    a = load_regime(committed, regime)["per_world"]
    b = load_regime(extended, regime)["per_world"]
    if set(a) != set(b):
        print(f"VOID: column sets differ: {sorted(a)} vs {sorted(b)}")
        return 2
    n_committed = None
    bad = 0
    for col in sorted(a):
        ra, rb = a[col], b[col]
        n_committed = len(ra) if n_committed is None else n_committed
        head = rb[: len(ra)]
        diff = [i for i, (x, y) in enumerate(zip(ra, head)) if x != y]
        print(f"{col:10s} committed rows {len(ra):5d}  extended rows {len(rb):5d}  "
              f"differing rows in prefix: {len(diff)}" + (f"  first {diff[:5]}" if diff else ""))
        bad += len(diff)
    if bad:
        print("VOID: the prefix does not reproduce the committed dump")
        return 1
    print("CONTROL PASSED: every committed row is reproduced in the extension prefix")
    print()
    print(f"admitted 6c over worlds {n_committed}-{len(next(iter(b.values()))) - 1}, per column"
          " (false FAIL / FAIL decisions, decision-bearing worlds, false-bearing worlds):")
    for col in sorted(b):
        rows = [r for r in b[col][n_committed:] if r[1] == "admitted"]
        fails = sum(r[4] for r in rows)
        false = sum(r[5] for r in rows)
        g = sum(1 for r in rows if r[4] > 0)
        gf = sum(1 for r in rows if r[5] > 0)
        worlds = [r[0] for r in rows if r[4] > 0]
        print(f"  {col:10s} {false:3d} / {fails:3d}   G={g:3d}  g={gf:3d}  worlds={worlds[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
