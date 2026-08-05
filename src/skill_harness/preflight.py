"""Offline SKILL.md preflight audit — no API calls, no DB, no cost.

This is the first-run surface of the harness's posture: before any money is
spent, report (a) structural findings against Anthropic's published skill
authoring spec and best practices, and (b) an evaluability preflight — which
axes a paid evaluation could mechanically measure TODAY, and which claims
would honestly come back UNMEASURED rather than as an estimated score.

Everything in this module is deterministic and offline. The structural rules
implemented here are the machine-checkable subset of:
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
(name/description constraints, body line budget, path style, point of view).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from skill_harness.extractor.parser import ParsedSkill, parse_skill_file

# ---------------------------------------------------------------------------
# Spec constants (Anthropic skill-authoring spec, fetched 2026-07-09)
# ---------------------------------------------------------------------------

NAME_MAX_CHARS = 64
DESCRIPTION_MAX_CHARS = 1024
BODY_MAX_LINES = 500  # "Keep SKILL.md body under 500 lines for optimal performance"

# Offline cl100k_base counts run ~1.128x under the exact tokenizer
# (measured range 1.084-1.179). Raw is a floor; never silently apply the factor.
STANDING_COST_CALIBRATION_FACTOR: Final[float] = 1.128
STANDING_COST_CALIBRATION_RANGE: Final[tuple[float, float]] = (1.084, 1.179)

_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
_RESERVED_NAME_WORDS = ("anthropic", "claude")
_XML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
# Two backslash-joined path segments of >=2 chars each ("scripts\helper.py").
# Single-char escapes like "\n" or "\t" inside strings do not match.
_WINDOWS_PATH = re.compile(r"\b[A-Za-z0-9_.:-]{2,}\\[A-Za-z0-9_.\\-]{2,}\b")
_FIRST_PERSON = re.compile(r"^\s*I\b|\bI can\b|\bI will\b|\bI help\b")
_TRIGGER_VOCAB = re.compile(
    r"\buse (this )?when\b|\bwhen (the user|you|working|asked)\b", re.IGNORECASE
)

FindingLevel = Literal["pass", "warn", "info"]


class AuditFinding(BaseModel):
    """One structural check result."""

    model_config = ConfigDict(frozen=True, strict=True)

    level: FindingLevel
    code: str
    message: str


class ArtifactAuditReport(BaseModel):
    """Full offline audit of one skill artifact."""

    model_config = ConfigDict(frozen=True, strict=True)

    source_path: str
    source_sha256: str
    name: str
    frontmatter_keys: tuple[str, ...]
    body_lines: int
    body_words: int
    findings: tuple[AuditFinding, ...]
    measurable_axes: tuple[str, ...]
    # Standing cost: router-listing tokens (name + description). None when the
    # frontmatter could not be parsed well enough to measure — never silently 0.
    standing_cost_raw: int | None
    standing_cost_calibrated: int | None
    standing_cost_calibration_factor: float
    standing_cost_calibration_range: tuple[float, float]
    # Fired cost: body tokens charged when the skill runs. Always measured when
    # the artifact parses (empty body is a hard parser error, not a zero).
    fired_cost_raw: int | None
    fired_cost_calibrated: int | None
    # Aux cost: other documentation beside the skill (progressive disclosure).
    # Real zero when none; None only when an aux file cannot be read as text.
    aux_cost_raw: int | None
    aux_cost_calibrated: int | None

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.level == "warn")

    @property
    def pass_count(self) -> int:
        return sum(1 for f in self.findings if f.level == "pass")


# ---------------------------------------------------------------------------
# Structural checks (each returns a list so it can emit pass AND warn lines)
# ---------------------------------------------------------------------------


def _check_name(parsed: ParsedSkill) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    fm_name = parsed.frontmatter.get("name")
    if fm_name is None:
        findings.append(
            AuditFinding(
                level="warn",
                code="name-missing",
                message="frontmatter has no 'name' field (spec: required); "
                f"falling back to filename stem {parsed.name!r}",
            )
        )
        return findings
    if len(fm_name) > NAME_MAX_CHARS:
        findings.append(
            AuditFinding(
                level="warn",
                code="name-too-long",
                message=f"name is {len(fm_name)} chars (spec max {NAME_MAX_CHARS})",
            )
        )
    if not _NAME_PATTERN.match(fm_name):
        findings.append(
            AuditFinding(
                level="warn",
                code="name-charset",
                message="name must be lowercase letters, digits, and hyphens only "
                f"(got {fm_name!r})",
            )
        )
    lowered = fm_name.lower()
    for word in _RESERVED_NAME_WORDS:
        if word in lowered:
            findings.append(
                AuditFinding(
                    level="warn",
                    code="name-reserved-word",
                    message=f"name contains reserved word {word!r} (spec: rejected)",
                )
            )
    if not findings:
        findings.append(
            AuditFinding(level="pass", code="name", message=f"name {fm_name!r} meets spec")
        )
    return findings


_YAML_BLOCK_SCALAR_INDICATORS = frozenset({"|", ">", "|-", ">-", "|+", ">+"})


def _check_description(parsed: ParsedSkill) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    desc = parsed.frontmatter.get("description", "")
    if desc.strip() in _YAML_BLOCK_SCALAR_INDICATORS:
        # The shared frontmatter parser is intentionally single-line-only; a
        # block scalar leaves us holding the indicator character. Refusing to
        # judge is the honest verdict — pretending ">" is the description is
        # exactly the confident-wrong-answer this tool exists to prevent.
        findings.append(
            AuditFinding(
                level="info",
                code="description-unparsed-block-scalar",
                message="description uses a multi-line YAML block scalar, which this "
                "audit's minimal frontmatter parser cannot read — description content "
                "checks skipped (UNMEASURED, not passed)",
            )
        )
        return findings
    if not desc.strip():
        findings.append(
            AuditFinding(
                level="warn",
                code="description-missing",
                message="frontmatter has no non-empty 'description' — the model "
                "cannot discover this skill (spec: required, discovery-critical)",
            )
        )
        return findings
    if len(desc) > DESCRIPTION_MAX_CHARS:
        findings.append(
            AuditFinding(
                level="warn",
                code="description-too-long",
                message=f"description is {len(desc)} chars (spec max {DESCRIPTION_MAX_CHARS})",
            )
        )
    if _XML_TAG.search(desc):
        findings.append(
            AuditFinding(
                level="warn",
                code="description-xml",
                message="description contains XML tags (spec: rejected)",
            )
        )
    if _FIRST_PERSON.search(desc):
        findings.append(
            AuditFinding(
                level="warn",
                code="description-first-person",
                message="description uses first person; spec requires third person "
                "(injected into the system prompt — POV mismatch hurts discovery)",
            )
        )
    if not _TRIGGER_VOCAB.search(desc):
        findings.append(
            AuditFinding(
                level="info",
                code="description-no-trigger-vocab",
                message="description has no 'use when …' trigger vocabulary; "
                "best practices: state both what the skill does AND when to use it",
            )
        )
    if not any(f.level == "warn" for f in findings):
        findings.append(
            AuditFinding(
                level="pass",
                code="description",
                message=f"description present ({len(desc)} chars) and within spec",
            )
        )
    return findings


def _check_body(parsed: ParsedSkill) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    n_lines = len(parsed.body.splitlines())
    if n_lines > BODY_MAX_LINES:
        findings.append(
            AuditFinding(
                level="warn",
                code="body-too-long",
                message=f"body is {n_lines} lines (best practices: under {BODY_MAX_LINES}; "
                "split into referenced files — progressive disclosure)",
            )
        )
    else:
        findings.append(
            AuditFinding(
                level="pass",
                code="body-length",
                message=f"body {n_lines} lines (budget {BODY_MAX_LINES})",
            )
        )
    win_paths = _WINDOWS_PATH.findall(parsed.body)
    if win_paths:
        sample = ", ".join(repr(p) for p in win_paths[:3])
        findings.append(
            AuditFinding(
                level="warn",
                code="windows-paths",
                message=f"{len(win_paths)} Windows-style path(s) found ({sample}…); "
                "best practices: forward slashes only — backslash paths break on Unix",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Standing cost (mechanical router-listing tax — every turn, used or not)
# ---------------------------------------------------------------------------


def _description_is_unparsed_block_scalar(parsed: ParsedSkill) -> bool:
    desc = parsed.frontmatter.get("description", "")
    return desc.strip() in _YAML_BLOCK_SCALAR_INDICATORS


def _router_listing_is_readable(parsed: ParsedSkill) -> bool:
    """True when name + description can support a standing-cost measurement.

    The router listing line is those two keys. Readable only if both are present,
    non-empty, and description is not a bare YAML block-scalar indicator the
    minimal parser cannot expand.
    """
    name = parsed.frontmatter.get("name")
    if name is None or not str(name).strip():
        return False
    description = parsed.frontmatter.get("description")
    if description is None or not str(description).strip():
        return False
    return not _description_is_unparsed_block_scalar(parsed)


def _is_disable_model_invocation(parsed: ParsedSkill) -> bool:
    flag = parsed.frontmatter.get("disable-model-invocation", "")
    return flag.strip().lower() == "true"


def _compute_standing_cost(
    parsed: ParsedSkill,
) -> tuple[int | None, int | None, list[AuditFinding]]:
    """Return (raw, calibrated, extra findings) for the per-turn standing tax.

    Standing cost is the cl100k_base token count of the router listing line
    (frontmatter ``name`` + ``description``). A skill with
    ``disable-model-invocation: true`` is never listed → raw/calibrated 0.
    When the listing line cannot be read, refuse the number entirely.
    """
    findings: list[AuditFinding] = []

    if _is_disable_model_invocation(parsed):
        return 0, 0, findings

    if not _router_listing_is_readable(parsed):
        findings.append(
            AuditFinding(
                level="warn",
                code="standing-cost-unparseable",
                message="router listing line (frontmatter name + description) is not "
                "readable as a single-line pair — standing cost UNMEASURED "
                "(no number; a silent default would understate the per-turn tax)",
            )
        )
        return None, None, findings

    # Lazy import: count_tokens loads tiktoken on first use; audit stays import-safe.
    from skill_harness.oracles.tier1.verbosity import count_tokens

    name = parsed.frontmatter.get("name", "")
    description = parsed.frontmatter.get("description", "")
    raw = count_tokens(name) + count_tokens(description)
    calibrated = round(raw * STANDING_COST_CALIBRATION_FACTOR)
    return raw, calibrated, findings


# ---------------------------------------------------------------------------
# Fired cost (mechanical — body tokens when the skill actually runs)
# ---------------------------------------------------------------------------


def _compute_fired_cost(parsed: ParsedSkill) -> tuple[int, int]:
    """Return (raw, calibrated) cl100k token counts for the skill body."""
    from skill_harness.oracles.tier1.verbosity import count_tokens

    raw = count_tokens(parsed.body)
    return raw, round(raw * STANDING_COST_CALIBRATION_FACTOR)


# ---------------------------------------------------------------------------
# Aux cost (mechanical — progressive-disclosure docs beside the skill)
# ---------------------------------------------------------------------------

# Documentation suffixes counted as aux. Scripts/binaries are not documentation.
_AUX_DOC_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".markdown", ".txt", ".rst"})


def _enumerate_aux_doc_files(skill_path: Path) -> list[Path]:
    """List documentation files in the skill directory, excluding the skill file.

    Resolves the skill path first so a skill directory reached via symlink is
    entered once. Walk does not follow symlinks outward; each real file is
    counted at most once.
    """
    skill_resolved = skill_path.resolve()
    root = skill_resolved.parent
    seen: set[Path] = set()
    found: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        # Do not descend into symlinked subdirectories (outward or cross-linked).
        dirnames[:] = [d for d in dirnames if not (Path(dirpath) / d).is_symlink()]
        for name in filenames:
            candidate = Path(dirpath) / name
            if candidate.suffix.lower() not in _AUX_DOC_SUFFIXES:
                continue
            if candidate.is_symlink():
                # Symlink file: only count if the target stays inside the skill dir.
                try:
                    real = candidate.resolve()
                except OSError:
                    continue
                try:
                    real.relative_to(root)
                except ValueError:
                    continue
            else:
                if not candidate.is_file():
                    continue
                real = candidate.resolve()
            if real == skill_resolved:
                continue
            if real in seen:
                continue
            seen.add(real)
            found.append(real)

    return sorted(found)


def _compute_aux_cost(
    skill_path: Path,
) -> tuple[int | None, int | None, list[AuditFinding]]:
    """Return (raw, calibrated, findings) for progressive-disclosure aux docs.

    A skill with no aux documentation reports raw/calibrated 0 (a real zero).
    Unreadable aux text refuses the number entirely.
    """
    from skill_harness.oracles.tier1.verbosity import count_tokens

    findings: list[AuditFinding] = []
    total = 0
    for doc in _enumerate_aux_doc_files(skill_path):
        try:
            text = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                AuditFinding(
                    level="warn",
                    code="aux-cost-unreadable",
                    message=f"aux documentation file {doc.name!r} could not be read "
                    f"as UTF-8 text ({exc}) — aux cost UNMEASURED "
                    "(no number; a silent skip would understate progressive-disclosure tax)",
                )
            )
            return None, None, findings
        total += count_tokens(text)

    return total, round(total * STANDING_COST_CALIBRATION_FACTOR), findings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def audit_skill_artifact(path: Path) -> ArtifactAuditReport:
    """Run the full offline audit on one skill artifact.

    :raises MalformedSkillError: empty/whitespace-only body or invalid UTF-8
        (propagated from the parser — same contract as ``skill init``).
    :raises OSError: unreadable file (propagated).
    """
    parsed = parse_skill_file(path)
    standing_raw, standing_cal, standing_findings = _compute_standing_cost(parsed)
    fired_raw, fired_cal = _compute_fired_cost(parsed)
    aux_raw, aux_cal, aux_findings = _compute_aux_cost(path)
    findings = [
        *_check_name(parsed),
        *_check_description(parsed),
        *_check_body(parsed),
        *standing_findings,
        *aux_findings,
    ]

    # Evaluability preflight: the authoritative list of mechanically scorable
    # axes is whatever the Tier-1 scorer registry actually exposes — never a
    # hardcoded copy that can drift.
    from skill_harness.ablation.confound import get_default_tier1_scorers

    measurable_axes = tuple(sorted(get_default_tier1_scorers().keys()))

    return ArtifactAuditReport(
        source_path=parsed.source_path,
        source_sha256=parsed.source_sha256,
        name=parsed.name,
        frontmatter_keys=tuple(sorted(parsed.frontmatter.keys())),
        body_lines=len(parsed.body.splitlines()),
        body_words=len(parsed.body.split()),
        findings=tuple(findings),
        measurable_axes=measurable_axes,
        standing_cost_raw=standing_raw,
        standing_cost_calibrated=standing_cal,
        standing_cost_calibration_factor=STANDING_COST_CALIBRATION_FACTOR,
        standing_cost_calibration_range=STANDING_COST_CALIBRATION_RANGE,
        fired_cost_raw=fired_raw,
        fired_cost_calibrated=fired_cal,
        aux_cost_raw=aux_raw,
        aux_cost_calibrated=aux_cal,
    )
