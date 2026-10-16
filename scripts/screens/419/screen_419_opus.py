# ruff: noqa: E402  # one-off launcher: the private fixture must be on sys.path before its import
"""#419 item 3, second screen: Null-only qualification, task v3a, claude-opus-5 direct.

Same design as screen_419.py (k = 8, pattern of record, natural mode). Only the subject and the
cap change. Priced in docs/findings/gitpull-v3a-null-qualification-screen.md Amendment 2 from the
Sonnet 5 run's token profile at Opus 5 list prices: about $2.02 expected, $14.14 no-discount worst
case. Hard cap $16.00, enforced as a $2.00 per-sample cost_limit. Runs only on a dated
authorisation that names that amount. Reads .private READ-ONLY; writes outside it.
"""

import sys
from pathlib import Path

FIX = Path("C:/Users/mlpgr/2026_Projects/skill-harness/.private/microrun/batch1/gitpull")
sys.path.insert(0, str(FIX))
from build_oracle import files_for_sandbox, oracle_command  # read-only import
from inspect_ai.model import ModelCost, ModelInfo, set_model_info

from skill_harness.subject import HarnessPin, build_paired_tasks

DRY = "--dry-run" in sys.argv
K = 8
HARD_CAP_USD = 16.00
PER_SAMPLE_CAP = HARD_CAP_USD / K  # sum over K samples <= HARD_CAP_USD by construction
MODEL = "anthropic/claude-opus-5"
OUT = Path(sys.argv[sys.argv.index("--out") + 1])
COMPOSE = Path(sys.argv[sys.argv.index("--compose") + 1])
SKILL_DIR = (
    Path.home() / ".claude/plugins/cache/mrbinnacle-skills/mrbinnacle-engineering/3.0.0/pull-rebase"
)
# PRICE_PER_MTOK has no claude-opus-5 row yet; these are the Anthropic list prices per MTok on
# 2026-09-21 (input, output, cache write at 1.25x, cache read at 0.1x).
OPUS5 = {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50}
cost = {
    MODEL: ModelCost(
        input=OPUS5["input"],
        output=OPUS5["output"],
        input_cache_write=OPUS5["cache_write"],
        input_cache_read=OPUS5["cache_read"],
    ),
}
# The task's default model is the "none" provider, which makes no API call. cost_limit needs a
# price for it, and set_model_cost refuses a model absent from inspect's database, so it is
# registered as custom model info with a zero cost (the S471 fix that let the first screen run).
set_model_info(
    "none/none",
    ModelInfo(cost=ModelCost(input=0, output=0, input_cache_write=0, input_cache_read=0)),
)
prompt = (FIX / "prompt_v3a_pushdiv.txt").read_text(encoding="utf-8")
pin = HarnessPin.capture(agent_version="2.1.197", model=MODEL, sandbox="docker", cwd="/root")
tasks = build_paired_tasks(
    skill_dir=SKILL_DIR,
    prompt=prompt,
    oracle="command_succeeds",
    oracle_arg=oracle_command(),
    pin=pin,
    epochs=K,
    compose_dir=COMPOSE,
    files=files_for_sandbox(),
)
print("pin fingerprint:", pin.fingerprint(), "| image:", pin.sandbox_image)
print(
    f"k={K} model={MODEL} per-sample cost_limit=${PER_SAMPLE_CAP:.3f} total cap=${HARD_CAP_USD:.2f}"
)
print("prompt bytes:", len(prompt.encode()), "| tasks:", sorted(tasks), "| running: null only")
if DRY:
    print("DRY RUN: no model call.")
    sys.exit(0)
from inspect_ai import eval as inspect_eval

logs = inspect_eval(
    [tasks["null"]],
    log_dir=str(OUT),
    display="plain",
    retry_on_error=0,
    max_sandboxes=3,
    fail_on_error=False,
    cost_limit=PER_SAMPLE_CAP,
    model_cost_config=cost,
)
for log in logs:
    print("LOG:", log.location, "STATUS:", log.status, "run_id:", log.eval.run_id)
