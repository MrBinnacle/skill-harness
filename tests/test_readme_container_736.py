"""README honesty lock for the untrusted-skill container template (#736).

The README tells a stranger to measure a skill they did not write with a
`container` object in the run config. A template whose keys the loader does not
read would fail at run time, or worse, be accepted while an intended field is
silently ignored. The loader is the source of truth, so these tests feed the
README's own JSON to `spec_from_config` and compare it with `ContainerSpec`.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from skill_harness.subject.pi.launcher import ContainerSpec
from skill_harness.subject.pi.runner import spec_from_config

_README = Path(__file__).resolve().parents[1] / "README.md"
_HEADING = "### A skill you did not write"


def _template() -> dict[str, Any]:
    text = _README.read_text(encoding="utf-8")
    section = text.split(_HEADING, 1)[1].split("\n## ", 1)[0]
    block = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert block is not None, f"no JSON block under {_HEADING!r}"
    loaded: dict[str, Any] = json.loads(block.group(1))
    return loaded


def _minimal_config(container: dict[str, Any]) -> dict[str, Any]:
    return {
        "pi_bin": "pi",
        "provider": "anthropic",
        "model": "model-x",
        "thinking_level": "off",
        "treatment_dir": "skill",
        "skill_name": "skill",
        "prompt": "do the task",
        "oracle_command": "true",
        "workspace_template": "template",
        "workspace": "workspace",
        "artifact_root": "artifacts",
        "n_pairs": 1,
        "route": "direct",
        **container,
    }


def test_template_keys_are_exactly_the_container_spec_fields() -> None:
    fields = {field.name for field in dataclasses.fields(ContainerSpec)}

    assert set(_template()["container"]) == fields


def test_the_loader_builds_the_container_the_template_declares(tmp_path: Path) -> None:
    template = _template()
    declared = template["container"]

    spec = spec_from_config(_minimal_config(template), base_dir=tmp_path)

    assert spec.container == ContainerSpec(
        argv_prefix=tuple(declared["argv_prefix"]),
        image_digest=declared["image_digest"],
        network_policy=declared["network_policy"],
    )


def test_the_template_does_not_recommend_a_network_with_no_route_to_the_provider() -> None:
    prefix = " ".join(_template()["container"]["argv_prefix"])

    assert re.search(r"--net(work)?[= ]none\b", prefix) is None
