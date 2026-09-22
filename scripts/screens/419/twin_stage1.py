# ruff: noqa: E402  # one-off launcher: the dry-run exit must come before the eval import
"""#620 Stage 1: the Null headroom screen on the v4 twin worlds, 8 epochs per world.

Authorised by the operator on the Binnacle Board, gate `twin-stage1`, answered
2026-09-22T07:26:30Z: "$12 approved". Hard cap $12.00. Pricing record: the steering repo's
docs/audit/twin-screen-price-S473.md. Only the two Null cells run; no card is installed.

Run: PYTHONPATH=src python scripts/screens/419/twin_stage1.py --out DIR [--dry-run]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inspect_ai.model import ModelCost, ModelInfo, set_model_info
from twin_digest import LIVE_IMAGE
from v4_cells import FIXTURE_ROOT_DEFAULT, FULL_DIR_DEFAULT, build_cells

from skill_harness.ablation.subject import PRICE_PER_MTOK
from skill_harness.subject import HarnessPin

DRY = "--dry-run" in sys.argv
EPOCHS_PER_WORLD = 8
HARD_CAP_USD = 12.00
PER_SAMPLE_CAP = HARD_CAP_USD / (2 * EPOCHS_PER_WORLD)
MODEL = "anthropic/claude-sonnet-5"
OUT = Path(sys.argv[sys.argv.index("--out") + 1])

price = PRICE_PER_MTOK["claude-sonnet-5"]
cost = {
    MODEL: ModelCost(
        input=price["input"],
        output=price["output"],
        input_cache_write=price["cache_write"],
        input_cache_read=price["cache_read"],
    ),
}
# cost_limit needs a price for the task's default "none" provider, which makes no API call (S471).
set_model_info(
    "none/none",
    ModelInfo(cost=ModelCost(input=0, output=0, input_cache_write=0, input_cache_read=0)),
)
pin = HarnessPin.capture(
    agent_version="2.1.197", model=MODEL, sandbox="docker", cwd="/root", sandbox_image=LIVE_IMAGE
)
cells = build_cells(
    fixture_root=FIXTURE_ROOT_DEFAULT,
    full_dir=FULL_DIR_DEFAULT,
    pin=pin,
    epochs=EPOCHS_PER_WORLD,
    compose_dir=Path(tempfile.mkdtemp(prefix="twin-stage1-")),
)
tasks = [cells[("null", "a")], cells[("null", "b")]]
print("pin fingerprint:", pin.fingerprint(), "| image:", pin.sandbox_image)
print(
    f"tasks={[t.name for t in tasks]} epochs/world={EPOCHS_PER_WORLD} model={MODEL} "
    f"per-sample cost_limit=${PER_SAMPLE_CAP:.3f} total cap=${HARD_CAP_USD:.2f}"
)
if DRY:
    print("DRY RUN: no model call.")
    sys.exit(0)

from inspect_ai import eval as inspect_eval

logs = inspect_eval(
    tasks,
    log_dir=str(OUT),
    display="plain",
    retry_on_error=0,
    max_sandboxes=2,
    fail_on_error=False,
    cost_limit=PER_SAMPLE_CAP,
    model_cost_config=cost,
)
for log in logs:
    print("LOG:", log.location, "STATUS:", log.status, "run_id:", log.eval.run_id)
