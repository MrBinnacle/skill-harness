# ruff: noqa: E402  # one-off launcher: the private fixture must be on sys.path before its import
"""#419 item 3: Null-only qualification screen, task v3a, claude-sonnet-5 direct.
Authorised by the operator 2026-09-21 (S470), hard cap $5.00. Reads .private READ-ONLY;
writes the compose file and logs OUTSIDE .private. No Full arm is run."""

import sys
from pathlib import Path

FIX = Path("C:/Users/mlpgr/2026_Projects/skill-harness/.private/microrun/batch1/gitpull")
sys.path.insert(0, str(FIX))
from build_oracle import files_for_sandbox, oracle_command  # read-only import
from inspect_ai.model import ModelCost

from skill_harness.ablation.subject import PRICE_PER_MTOK
from skill_harness.subject import HarnessPin, build_paired_tasks

DRY = "--dry-run" in sys.argv
K = 8
HARD_CAP_USD = 5.00
PER_SAMPLE_CAP = HARD_CAP_USD / K  # sum over K samples <= HARD_CAP_USD by construction
MODEL = "anthropic/claude-sonnet-5"
OUT = Path(sys.argv[sys.argv.index("--out") + 1])
COMPOSE = Path(sys.argv[sys.argv.index("--compose") + 1])
SKILL_DIR = (
    Path.home() / ".claude/plugins/cache/mrbinnacle-skills/mrbinnacle-engineering/3.0.0/pull-rebase"
)
P = PRICE_PER_MTOK["claude-sonnet-5"]
cost = {
    MODEL: ModelCost(
        input=P["input"],
        output=P["output"],
        input_cache_write=P["cache_write"],
        input_cache_read=P["cache_read"],
    ),
    # task default model: the "none" provider makes no API call (sized run: zero usage under it)
    "none/none": ModelCost(input=0, output=0, input_cache_write=0, input_cache_read=0),
}
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
