"""Oracle-specific exception hierarchy.

All oracle exceptions derive from OracleError so callers can catch
at any granularity they need.

Design mirrors extractor/errors.py (Track B); the Track-C carryover pattern:
"OracleError base + OracleAPIError(OracleError) wrapping SDK errors."
"""

from __future__ import annotations


class OracleError(Exception):
    """Base class for all oracle errors."""


class OracleAPIError(OracleError):
    """Raised when an Anthropic API call fails during oracle evaluation.

    Wraps transport errors, rate limit errors, and other SDK-level failures.
    Mirrors Track B's ExtractorClaudeError pattern.
    """
