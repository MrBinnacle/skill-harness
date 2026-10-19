"""Extractor-specific exception hierarchy.

All extractor exceptions derive from ExtractionError so callers can catch
at any granularity they need.
"""

from __future__ import annotations


class ExtractionError(Exception):
    """Base class for all extractor errors."""


class MalformedSkillError(ExtractionError):
    """Raised when the skill source file cannot be parsed into a valid document.

    Examples: binary content, empty body, unparseable frontmatter.
    """


class ExtractorClaudeError(ExtractionError):
    """Raised when the Claude API call fails or returns unusable output.

    Wraps transport errors, validation errors from the tool-use response,
    or cases where Claude returned zero clauses.
    """
