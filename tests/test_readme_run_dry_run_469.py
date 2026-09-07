"""README honesty lock for the `run` dry-run claim (#469).

The README told a stranger that "every `run` subcommand is dry-run by default;
`--execute` is required to spend". That was true of one subcommand of three.
`run evaluate-skill` declares no `--execute` and takes an inverted `--dry-run`
opt-out; `run evaluate-paired` declares neither flag and is read-only.

The claim is about the CLI, so the CLI is the source of truth. These tests read
the click commands and require the README to state what they actually do. A flag
added or removed fails a test here, which is what stops the sentence drifting
again.

Every assertion about a subcommand is scoped to the README window that names
that subcommand. A document-wide regex would let a qualifier written about one
subcommand satisfy an assertion about another.
"""

from __future__ import annotations

import re
from pathlib import Path

from skill_harness.cli.main import run

_README = Path(__file__).resolve().parents[1] / "README.md"

# How much README text around a subcommand's name counts as describing it.
_WINDOW = 600


def _readme() -> str:
    return _README.read_text(encoding="utf-8")


def _long_opts(command_name: str) -> set[str]:
    command = run.commands[command_name]
    return {opt for param in command.params for opt in param.opts if opt.startswith("--")}


def _windows_naming(text: str, needle: str) -> list[str]:
    """Every README passage that mentions ``needle``, with surrounding context."""
    return [
        text[max(0, m.start() - _WINDOW) : min(len(text), m.end() + _WINDOW)]
        for m in re.finditer(re.escape(needle), text)
    ]


def test_the_run_group_holds_exactly_the_three_subcommands_the_readme_describes() -> None:
    """A new `run` subcommand fails here until the README accounts for it."""
    assert set(run.commands) == {"ablation", "evaluate-skill", "evaluate-paired"}


def test_only_ablation_takes_execute() -> None:
    """The spend opt-in exists on one subcommand of three."""
    assert "--execute" in _long_opts("ablation")
    assert "--execute" not in _long_opts("evaluate-skill")
    assert "--execute" not in _long_opts("evaluate-paired")


def test_evaluate_skill_takes_an_inverted_dry_run_opt_out() -> None:
    """`evaluate-skill` aggregates by default; `--dry-run` is how a reader stops it."""
    assert "--dry-run" in _long_opts("evaluate-skill")
    assert "--dry-run" not in _long_opts("ablation")
    assert "--dry-run" not in _long_opts("evaluate-paired")


def test_readme_makes_no_blanket_dry_run_claim() -> None:
    """The retired sentence, and any restatement of its shape."""
    text = _readme()
    assert "Every `run` subcommand is dry-run by default" not in text
    assert not re.search(
        r"(every|all|each)\s+`?run`?\s+subcommands?\s+(is|are)\s+dry-run",
        text,
        re.IGNORECASE,
    ), "a blanket dry-run claim covers three subcommands with one property; only one has it"


def test_readme_scopes_the_spend_opt_in_to_ablation() -> None:
    """`--execute` is described where `run ablation` is named, and only there."""
    text = _readme()
    windows = _windows_naming(text, "run ablation")
    assert windows, "expected the README to name `run ablation`"
    assert any("--execute" in w for w in windows), (
        "the README must say that `run ablation` takes `--execute` to spend"
    )


def test_readme_states_that_evaluate_skill_makes_no_model_call() -> None:
    """The property a reader needs: this subcommand reads stored evidence."""
    text = _readme()
    windows = _windows_naming(text, "evaluate-skill")
    assert windows, "expected the README to name `run evaluate-skill`"
    assert any(
        re.search(r"no model call|makes no .*call|no API call|spends nothing", w, re.IGNORECASE)
        for w in windows
    ), "the README must say that `run evaluate-skill` makes no model call"
    assert any("--dry-run" in w for w in windows), (
        "the README must name `--dry-run` as this subcommand's opt-out"
    )


def test_readme_states_that_evaluate_paired_is_read_only() -> None:
    text = _readme()
    windows = _windows_naming(text, "evaluate-paired")
    assert windows, "expected the README to name `run evaluate-paired`"
    assert any(re.search(r"read-only", w, re.IGNORECASE) for w in windows), (
        "the README must say that `run evaluate-paired` is read-only"
    )


def test_readme_names_the_database_files_the_snippet_writes() -> None:
    """The snippet creates files in the reader's current directory. Say so."""
    text = _readme()
    for artefact in ("evidence.db", "runtime.db", "--evidence-db", "--runtime-db"):
        assert artefact in text, f"the README must name {artefact}"
    windows = _windows_naming(text, "evidence.db")
    assert any(
        re.search(r"current directory|working directory|directory you run", w, re.IGNORECASE)
        for w in windows
    ), "the README must say where the database files land"


def test_database_defaults_are_relative_so_the_readme_claim_holds() -> None:
    """The README says 'current directory' because the defaults are relative."""
    for command_name in ("ablation", "evaluate-skill"):
        command = run.commands[command_name]
        defaults = {
            param.name: param.default
            for param in command.params
            if param.name in {"evidence_db", "runtime_db"}
        }
        assert defaults, f"{command_name} declares no database path options"
        for name, default in defaults.items():
            assert not Path(str(default)).is_absolute(), (
                f"{command_name} --{name.replace('_', '-')} default {default!r} is absolute; "
                "the README's 'current directory' claim would be false"
            )
