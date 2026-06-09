"""Tests for --subject-model CLI flag and _resolve_subject_model_with_fallback.

TDD discipline: tests written BEFORE implementation (RED first).

Covers:
1-8.  Unit tests for _resolve_subject_model_with_fallback across
      the (model_class, key_availability) matrix.
9-10. CLI-level tests: --subject-model flag acceptance + default.
11.   Integration: _execute_ablation_run passes subject_model to factory.

Mock discipline (A32 / PRD §12.1):
- All tests are offline (pytest-socket discipline preserved).
- monkeypatch for env isolation — never mutate os.environ directly.
- make_subject_client patched at factory level for integration test.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from skill_harness.cli.main import _resolve_subject_model_with_fallback, cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke(*args: str, env: dict[str, str] | None = None) -> object:
    """Invoke CLI with given args; COLUMNS=200 for rich-table width."""
    runner = CliRunner(mix_stderr=False)
    merged_env: dict[str, str] = {"COLUMNS": "200"}
    if env is not None:
        merged_env.update(env)
    return runner.invoke(cli, list(args), env=merged_env, catch_exceptions=False)


def _empty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all three API key env vars so tests start from a clean slate."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# 1. claude-* + ANTHROPIC_API_KEY: pass-through, no warning
# ---------------------------------------------------------------------------


def test_resolver_claude_with_anthropic_key_passes_through(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ANTHROPIC_API_KEY set + claude-* model: returns model unchanged, no stderr."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    result = _resolve_subject_model_with_fallback("claude-sonnet-4-6")
    assert result == "claude-sonnet-4-6"

    captured = capsys.readouterr()
    assert captured.err == ""


# ---------------------------------------------------------------------------
# 2. claude-* + only OPENROUTER_API_KEY: rewrites + warns
# ---------------------------------------------------------------------------


def test_resolver_claude_with_only_openrouter_key_rewrites(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No ANTHROPIC_API_KEY but OPENROUTER_API_KEY set: rewrite to 'anthropic/<model>'
    and emit a stderr warning naming the rewrite and the reason."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    result = _resolve_subject_model_with_fallback("claude-sonnet-4-6")
    assert result == "anthropic/claude-sonnet-4-6"

    captured = capsys.readouterr()
    assert "anthropic/claude-sonnet-4-6" in captured.err
    assert "ANTHROPIC_API_KEY" in captured.err


# ---------------------------------------------------------------------------
# 3. claude-* + no keys: raise with both var names
# ---------------------------------------------------------------------------


def test_resolver_claude_with_no_keys_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither ANTHROPIC_API_KEY nor OPENROUTER_API_KEY: raise ClickException naming both."""
    import click

    _empty_env(monkeypatch)

    with pytest.raises(click.ClickException) as exc_info:
        _resolve_subject_model_with_fallback("claude-sonnet-4-6")

    msg = exc_info.value.format_message()
    assert "ANTHROPIC_API_KEY" in msg
    assert "OPENROUTER_API_KEY" in msg


# ---------------------------------------------------------------------------
# 4. gpt-* + OPENAI_API_KEY: pass-through, no warning
# ---------------------------------------------------------------------------


def test_resolver_gpt_with_openai_key_passes_through(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """OPENAI_API_KEY set + gpt-* model: returns model unchanged, no stderr."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    result = _resolve_subject_model_with_fallback("gpt-5.5")
    assert result == "gpt-5.5"

    captured = capsys.readouterr()
    assert captured.err == ""


# ---------------------------------------------------------------------------
# 5. gpt-* + only OPENROUTER_API_KEY: rewrites + warns
# ---------------------------------------------------------------------------


def test_resolver_gpt_with_only_openrouter_rewrites(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No OPENAI_API_KEY but OPENROUTER_API_KEY set: rewrite to 'openai/<model>' + warn."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    result = _resolve_subject_model_with_fallback("gpt-5.5")
    assert result == "openai/gpt-5.5"

    captured = capsys.readouterr()
    assert "openai/gpt-5.5" in captured.err
    assert "OPENAI_API_KEY" in captured.err


# ---------------------------------------------------------------------------
# 6. o<N>-* (o-series) + only OPENROUTER_API_KEY: rewrites + warns
# ---------------------------------------------------------------------------


def test_resolver_o_series_with_only_openrouter_rewrites(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """o4-mini with no OPENAI_API_KEY but OPENROUTER_API_KEY: rewrite to 'openai/o4-mini'."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    result = _resolve_subject_model_with_fallback("o4-mini")
    assert result == "openai/o4-mini"

    captured = capsys.readouterr()
    assert "openai/o4-mini" in captured.err
    assert "OPENAI_API_KEY" in captured.err


# ---------------------------------------------------------------------------
# 7. explicit OpenRouter form + no OPENROUTER_API_KEY: raise
# ---------------------------------------------------------------------------


def test_resolver_explicit_openrouter_form_requires_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit 'provider/model' form without OPENROUTER_API_KEY: raise ClickException."""
    import click

    _empty_env(monkeypatch)

    with pytest.raises(click.ClickException) as exc_info:
        _resolve_subject_model_with_fallback("anthropic/claude-sonnet-4-6")

    msg = exc_info.value.format_message()
    assert "OPENROUTER_API_KEY" in msg


# ---------------------------------------------------------------------------
# 8. explicit OpenRouter form + OPENROUTER_API_KEY: pass-through unchanged
# ---------------------------------------------------------------------------


def test_resolver_explicit_openrouter_form_passes_with_openrouter_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Explicit 'provider/model' + OPENROUTER_API_KEY set: pass-through unchanged."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    result = _resolve_subject_model_with_fallback("anthropic/claude-sonnet-4-6")
    assert result == "anthropic/claude-sonnet-4-6"

    captured = capsys.readouterr()
    assert captured.err == ""


# ---------------------------------------------------------------------------
# 8a. gpt-* + no keys: raise with both var names (mirror of test 3 for OpenAI)
# ---------------------------------------------------------------------------


def test_resolver_gpt_with_no_keys_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither OPENAI_API_KEY nor OPENROUTER_API_KEY: raise ClickException naming both."""
    import click

    _empty_env(monkeypatch)

    with pytest.raises(click.ClickException) as exc_info:
        _resolve_subject_model_with_fallback("gpt-5.5")

    msg = exc_info.value.format_message()
    assert "OPENAI_API_KEY" in msg
    assert "OPENROUTER_API_KEY" in msg


# ---------------------------------------------------------------------------
# 8b. o-series + no keys: raise with both var names (mirror of test 3 for o-series)
# ---------------------------------------------------------------------------


def test_resolver_o_series_with_no_keys_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither OPENAI_API_KEY nor OPENROUTER_API_KEY: raise ClickException naming both."""
    import click

    _empty_env(monkeypatch)

    with pytest.raises(click.ClickException) as exc_info:
        _resolve_subject_model_with_fallback("o4-mini")

    msg = exc_info.value.format_message()
    assert "OPENAI_API_KEY" in msg
    assert "OPENROUTER_API_KEY" in msg


# ---------------------------------------------------------------------------
# 8c. Bare o-series name (no dash) + only OPENROUTER_API_KEY: rewrites + warns
#     Regression guard for resolver/factory regex alignment (quality review on
#     a9bdacc): factory accepts bare 'o4' via `model[0]=='o' and model[1].isdigit()`;
#     resolver must match to avoid routing bare names through the unrecognized-model
#     probe and missing the OpenRouter fallback contract.
# ---------------------------------------------------------------------------


def test_resolver_o_series_bare_with_only_openrouter_rewrites(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bare 'o4' (no dash) with no OPENAI_API_KEY but OPENROUTER_API_KEY: rewrite."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    result = _resolve_subject_model_with_fallback("o4")
    assert result == "openai/o4"

    captured = capsys.readouterr()
    assert "openai/o4" in captured.err
    assert "OPENAI_API_KEY" in captured.err


# ---------------------------------------------------------------------------
# 9. CLI: --subject-model flag is accepted (not an unknown option)
# ---------------------------------------------------------------------------


def test_run_ablation_accepts_subject_model_flag() -> None:
    """run ablation --help must list --subject-model as a known option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "ablation", "--help"])
    assert result.exit_code == 0, f"--help failed:\n{result.output}"
    assert "--subject-model" in result.output, (
        f"--subject-model not found in help:\n{result.output}"
    )


# ---------------------------------------------------------------------------
# 10. CLI: default subject model is claude-sonnet-4-6
# ---------------------------------------------------------------------------


def test_run_ablation_default_subject_model_is_claude_sonnet() -> None:
    """--help output must show default 'claude-sonnet-4-6' for --subject-model."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "ablation", "--help"])
    assert result.exit_code == 0
    assert "claude-sonnet-4-6" in result.output, (
        f"Default 'claude-sonnet-4-6' not shown in help:\n{result.output}"
    )


# ---------------------------------------------------------------------------
# 11. Integration: _execute_ablation_run passes subject_model to make_subject_client
# ---------------------------------------------------------------------------


def test_execute_ablation_passes_subject_model_to_factory(
    tmp_path: Path,
) -> None:
    """_execute_ablation_run must call make_subject_client with the exact model id passed."""
    from skill_harness.cli.main import _execute_ablation_run
    from skill_harness.storage.migrations import open_evidence, open_runtime
    from skill_harness.storage.models import ClauseWrite, SkillWrite
    from skill_harness.storage.repositories.evidence.clauses import insert_clause
    from skill_harness.storage.repositories.evidence.skills import insert_skill
    from skill_harness.storage.transaction import writer_transaction

    # Seed a minimal DB so the runner can find clauses
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")

    _ts = "2026-06-09T00:00:00.000000+00:00"
    _sha = "b" * 64
    _skill_id = "sk-factory-wiring-test"

    with writer_transaction(ev):
        insert_skill(
            ev,
            SkillWrite(
                skill_id=_skill_id,
                name="Factory Wiring Test Skill",
                source_path="/test/factory.md",
                source_sha256=_sha,
                imported_at=_ts,
            ),
        )
        insert_clause(
            ev,
            ClauseWrite(
                clause_id="c-factory-001",
                skill_id=_skill_id,
                clause_index=0,
                rendering_index=0,
                clause_text="Always begin with 'Certainly!'.",
                axis="verbosity",
                comparator="increase",
                oracle_tier=1,
                vacuity_flag="none",
                falsifying_case_schema_sha256="abc123",
                created_at=_ts,
            ),
        )

    ev.close()
    rt.close()

    mock_client = MagicMock()
    # Make the runner return immediately without actual API calls
    mock_runner = MagicMock()
    mock_runner.run_ablation.return_value = []

    # _execute_ablation_run does `from skill_harness.ablation.subject import make_subject_client`
    # so we patch the authoritative location in the subject module.
    with (
        patch(
            "skill_harness.ablation.subject.make_subject_client",
            return_value=mock_client,
        ) as mock_factory,
        patch("skill_harness.ablation.runner.AblationRunner") as mock_runner_cls,
    ):
        mock_runner_cls.return_value = mock_runner

        with contextlib.suppress(Exception):
            _execute_ablation_run(
                skill_id=_skill_id,
                clause_id=None,
                subject_model="gpt-5.5",
                user_message="Test task.",
                max_usd=1.0,
                resume_run_id=None,
                evidence_db=tmp_path / "evidence.db",
                runtime_db=tmp_path / "runtime.db",
            )

        # Factory must have been called with "gpt-5.5"
        all_calls = mock_factory.call_args_list
        called_models = [c.args[0] if c.args else c.kwargs.get("model") for c in all_calls]
        assert "gpt-5.5" in called_models, (
            f"make_subject_client not called with 'gpt-5.5'. All calls: {all_calls}"
        )
