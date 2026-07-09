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

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from skill_harness.extractor.parser import ParsedSkill, parse_skill_file

# ---------------------------------------------------------------------------
# Spec constants (Anthropic skill-authoring spec, fetched 2026-07-09)
# ---------------------------------------------------------------------------

NAME_MAX_CHARS = 64
DESCRIPTION_MAX_CHARS = 1024
BODY_MAX_LINES = 500  # "Keep SKILL.md body under 500 lines for optimal performance"

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
# Public entry point
# ---------------------------------------------------------------------------


def audit_skill_artifact(path: Path) -> ArtifactAuditReport:
    """Run the full offline audit on one skill artifact.

    :raises MalformedSkillError: empty/whitespace-only body or invalid UTF-8
        (propagated from the parser — same contract as ``skill init``).
    :raises OSError: unreadable file (propagated).
    """
    parsed = parse_skill_file(path)
    findings = [
        *_check_name(parsed),
        *_check_description(parsed),
        *_check_body(parsed),
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
    )
