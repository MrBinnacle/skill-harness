"""#620: read a twin-screen log directory into one row per epoch and a per-cell summary. No model.

An epoch with no model usage is VOID: the agent never started, so it is an apparatus fault,
not a result, and the summary excludes it. Each row carries the cell (from the task metadata),
the first integration action (from the agent's Bash commands), the world-conditioned
consequence (from the oracle's printed facts), whether the push was refused, whether the
card's skill was invoked, and the epoch's cost.

Run: PYTHONPATH=src python scripts/screens/419/twin_readout.py LOG_DIR [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from consequence_v4 import REFUSALS, classify, parse_facts
from inspect_ai.log import read_eval_log

from skill_harness.ablation.subject import PRICE_PER_MTOK

PRICE = PRICE_PER_MTOK["claude-sonnet-5"]


@dataclass(frozen=True)
class EpochRow:
    arm: str
    world: str
    epoch: int
    first_action: str
    final_world_correct: bool
    refused: bool
    recovered: bool
    silent_violation: bool
    completed: bool
    skill_invoked: bool
    usd: float
    void: bool


def _usd(sample: Any) -> float:
    total = 0.0
    for usage in (sample.model_usage or {}).values():
        total += (
            (usage.input_tokens or 0) * PRICE["input"]
            + (usage.output_tokens or 0) * PRICE["output"]
            + (usage.input_tokens_cache_write or 0) * PRICE["cache_write"]
            + (usage.input_tokens_cache_read or 0) * PRICE["cache_read"]
        ) / 1e6
    return total


def _trace(sample: Any) -> tuple[list[str], str, bool]:
    commands: list[str] = []
    texts: list[str] = []
    skill_invoked = False
    for message in sample.messages:
        for call in getattr(message, "tool_calls", None) or []:
            if call.function == "Bash":
                commands.append(str(call.arguments.get("command", "")))
            if call.function == "Skill":
                skill_invoked = True
        texts.append(str(getattr(message, "text", "") or ""))
    return commands, "\n".join(texts), skill_invoked


def read_rows(log_dir: Path) -> list[EpochRow]:
    rows: list[EpochRow] = []
    for path in sorted(log_dir.glob("*.eval")):
        log = read_eval_log(str(path))
        meta = log.eval.metadata or {}
        arm, world = str(meta["cell_arm"]), str(meta["cell_world"])
        for sample in log.samples or []:
            score = next(iter((sample.scores or {}).values()))
            facts_text = (score.explanation or "").split(":", 1)[-1]
            commands, log_text, skill_invoked = _trace(sample)
            c = classify(world, parse_facts(facts_text), commands, log_text)
            rows.append(
                EpochRow(
                    arm=arm,
                    world=world,
                    epoch=int(sample.epoch),
                    first_action=c.first_integration_action,
                    final_world_correct=c.final_world_correct,
                    refused=REFUSALS[world] in log_text,
                    recovered=c.recovered,
                    silent_violation=c.silent_violation,
                    completed=c.completed,
                    skill_invoked=skill_invoked,
                    usd=round(_usd(sample), 4),
                    void=not sample.model_usage,
                )
            )
    return rows


def summarise(rows: list[EpochRow]) -> dict[str, Any]:
    cells: dict[str, list[EpochRow]] = defaultdict(list)
    for row in rows:
        if not row.void:
            cells[f"{row.arm}/{row.world}"].append(row)
    out: dict[str, Any] = {}
    for cell, group in sorted(cells.items()):
        out[cell] = {
            "n": len(group),
            "first_action": dict(Counter(r.first_action for r in group)),
            "correct": sum(r.final_world_correct for r in group),
            "refused": sum(r.refused for r in group),
            "recovered": sum(r.recovered for r in group),
            "silent_violation": sum(r.silent_violation for r in group),
            "skill_invoked": sum(r.skill_invoked for r in group),
            "usd": round(sum(r.usd for r in group), 4),
        }
    out["void_epochs"] = [f"{r.arm}/{r.world}#{r.epoch}" for r in rows if r.void]
    out["total_usd"] = round(sum(r.usd for r in rows), 4)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log_dir", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    rows = read_rows(args.log_dir)
    for row in rows:
        print(json.dumps(asdict(row)))
    summary = summarise(rows)
    print(json.dumps(summary, indent=2))
    if args.json:
        args.json.write_text(
            json.dumps({"rows": [asdict(r) for r in rows], "summary": summary}, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
