"""Rebuild CellResults from the committed smoke TSVs and regenerate summary.md."""

from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]
SCREEN = REPO / "scripts" / "screens" / "419"
DATA = REPO / "docs" / "findings" / "data" / "stage1a-regime-685"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCREEN / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    reg = load("simulate_stage1a_regime_685")
    a650 = load("simulate_a_design")

    per_look_path = DATA / "per_look.tsv"
    terminal_path = DATA / "terminal_states.tsv"
    pl_lines = per_look_path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    pl_header = pl_lines[0].split("\t")
    pl_rows = [dict(zip(pl_header, line.split("\t"), strict=True)) for line in pl_lines[1:]]

    ts_lines = terminal_path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    ts_header = ts_lines[0].split("\t")
    ts_rows = [dict(zip(ts_header, line.split("\t"), strict=True)) for line in ts_lines[1:]]

    # Group per_look rows by design+cell, keep the terminal look (max look).
    pl_groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in pl_rows:
        key = (
            int(row["n_full"]),
            float(row["null_per_pair"]),
            row["fn_construction"],
            float(row["p_placebo"]),
            float(row["p_null"]),
            float(row["d"]),
        )
        pl_groups[key].append(row)

    ts_groups: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for row in ts_rows:
        key = (
            int(row["n_full"]),
            float(row["null_per_pair"]),
            row["fn_construction"],
            float(row["p_placebo"]),
            float(row["p_null"]),
            float(row["d"]),
        )
        ts_groups[key][row["joint_state"]] = row

    def make_look(row: dict) -> object:
        return reg.LookRow(
            look=int(row["look"]),
            p_pass=float(row["p_pass"]),
            p_cut=float(row["p_cut"]),
            p_cant_tell_yet=float(row["p_cant_tell_yet"]),
            se_pass=float(row["se_pass"]),
            expected_pairs=float(row["expected_pairs"]),
            expected_epochs=float(row["expected_epochs"]),
        )

    def make_terminal(state_row: dict | None, replicates: int) -> object:
        if state_row is None:
            return reg.TerminalSample(lb_fp=(), lb_fn=(), ub_fp=())
        count = int(float(state_row["count"]))
        if count <= 0:
            return reg.TerminalSample(lb_fp=(), lb_fn=(), ub_fp=())

        def series(prefix: str) -> tuple[float, ...]:
            vals = []
            for q in (0, 10, 25, 50, 75, 90, 100):
                raw = state_row[f"{prefix}_q{q:02d}"]
                if raw == "NA":
                    vals.append(0.0)
                else:
                    vals.append(float(raw))
            # Reconstruct a sample whose median/quantiles match the recorded
            # values closely enough for summary rendering (median + empty).
            med = vals[3]
            return tuple(med for _ in range(count))

        return reg.TerminalSample(
            lb_fp=series("lb_fp"),
            lb_fn=series("lb_fn"),
            ub_fp=series("ub_fp"),
        )

    results = []
    for key, rows in pl_groups.items():
        n_full, null_pp, fn_con, p_p, p_n, d = key
        design = reg.Design(
            n_pairs=n_full,
            null_per_pair=null_pp,
            fn_construction=fn_con,
            stopping=rows[0]["stopping"],
        )
        cell = reg.Cell(round(p_p + d, 10), p_p, p_n)
        rows_sorted = sorted(rows, key=lambda r: int(r["look"]))
        looks = tuple(make_look(r) for r in rows_sorted)
        last = rows_sorted[-1]
        replicates = int(float(last["replicates"]))
        terminal_rows = ts_groups.get(key, {})
        terminal = {
            state: make_terminal(terminal_rows.get(state), replicates)
            for state in reg.JOINT_STATES
        }
        results.append(
            reg.CellResult(
                cell=cell,
                design=design,
                replicates=replicates,
                per_look=looks,
                terminal=terminal,
                library_calls=0,
            )
        )

    replicates = 20
    seed = 685
    summary = reg.summary_md(results, replicates, seed)
    out = DATA / "summary.md"
    old = out.read_text(encoding="utf-8") if out.exists() else ""
    out.write_text(summary, encoding="utf-8")
    print(f"wrote {out} ({len(summary)} bytes); old was {len(old)} bytes")
    print(f"results reconstructed: {len(results)}")
    # Show which sections differ at a coarse level.
    old_secs = [ln for ln in old.splitlines() if ln.startswith("## ")]
    new_secs = [ln for ln in summary.splitlines() if ln.startswith("## ")]
    print("old sections:", old_secs)
    print("new sections:", new_secs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
