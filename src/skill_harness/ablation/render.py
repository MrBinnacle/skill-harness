"""ConditionRenderer — renders Full / Ablated_k / Null conditions (A13, A39, A43).

Design:
- Given a skill (list of clause texts) + target clause index k, produces the three
  conditions required by the differential ablation protocol:
    Full     — all clauses present (system prompt includes the complete skill)
    Ablated_k — clause k replaced by the AblationOperator's placeholder
    Null     — no skill text in the system prompt

- Cache-marker placement (A43):
    ``system`` is rendered as a list of typed blocks (not a bare string) so that
    prompt-cache ``cache_control: {type: ephemeral}`` markers can be placed at:
      1. End of the base system block (before skill text begins)
      2. End of the skill-prefix block (before the ablated clause — which is
         rendered LAST to maximize the shared cacheable prefix across Full and
         Ablated_k calls for the same clause k)

- Ablated-clause-last ordering (A43 / A13):
    The ablated clause is moved to the LAST position in the rendered system so
    that the prefix (base system + all other clauses) is shared and cacheable
    across Full, Ablated_k, and re-runs of the same clause. Authoring order
    (``clause_index``) is preserved in Full and Null; only Ablated_k reorders.

- The renderer returns a dict keyed by condition name:
    {
      "full":       {"system_text": str, "system_blocks": list[dict]},
      "null":       {"system_text": str, "system_blocks": list[dict]},
      "ablated_k":  {"system_text": str, "system_blocks": list[dict],
                     "ablated_clause_marker": str},
    }
  where ``system_text`` is the faithful concatenation of the block texts (the
  wire prompt the model receives), ``system_blocks`` is the block list for the
  SDK ``system`` parameter, and ``ablated_clause_marker`` is the inspection
  label returned SEPARATELY (never injected into block text — A39 invariant).

- A39 length-axis invariant: the ABLATED_CLAUSE_MARKER must NEVER be included
  in any block text sent to the subject model. Injecting it would add tokens to
  the ablated side only, contaminating the length axis. The marker is returned
  as a separate metadata field for --show-rendered / test introspection only.

- This module builds the request STRUCTURE only — it does NOT call the SDK.
  The runner (D.2) injects the blocks into the SDK call.

Per CLAUDE.md load-bearing invariants:
- The deterministic Python layer constructs all prompts — no model call here.
- Directional/comparative only — the renderer is neutral.
"""

from __future__ import annotations

from typing import Any

from skill_harness.ablation.operator import AblationOperator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Base system prompt prefix (before skill text).
# Semantically neutral: identifies the role and the evaluation context.
_BASE_SYSTEM: str = (
    "You are a helpful assistant. "
    "Follow the instructions provided in the skill block below precisely."
)

# Sentinel marker for inspection / --show-rendered / test introspection.
# Format: "[CLAUSE {k} — ABLATED]".
# INVARIANT (A39): this marker must NEVER be placed in any system_blocks block text
# sent to the subject model. Doing so adds tokens to the ablated side only,
# contaminating the length axis. The marker is returned as a separate metadata field
# ("ablated_clause_marker") in the ablated condition dict — never in block text.
ABLATED_CLAUSE_MARKER: str = "[CLAUSE {k} — ABLATED]"


# ---------------------------------------------------------------------------
# ConditionRenderer
# ---------------------------------------------------------------------------


class ConditionRenderer:
    """Renders Full / Ablated_k / Null conditions for a skill clause inventory.

    Parameters
    ----------
    operator : AblationOperator | None
        The ablation operator that produces the matched-length placeholder.
        If None, a default AblationOperator() is constructed.
    base_system : str
        The base system prompt prefix (before the skill text).
        Defaults to ``_BASE_SYSTEM``.
    """

    def __init__(
        self,
        operator: AblationOperator | None = None,
        base_system: str = _BASE_SYSTEM,
    ) -> None:
        self._operator: AblationOperator = operator if operator is not None else AblationOperator()
        self._base_system: str = base_system

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_conditions(
        self,
        clauses: list[str],
        target_clause_index: int,
    ) -> dict[str, dict[str, Any]]:
        """Render all three conditions for the given clause inventory.

        :param clauses: Ordered list of clause texts (authoring order).
        :param target_clause_index: Index (0-based) of the clause being ablated.
        :returns: Dict with keys ``"full"``, ``"null"``, ``f"ablated_{k}"``.
            Each value is ``{"system_text": str, "system_blocks": list[dict]}``.
        :raises IndexError: If ``target_clause_index`` is out of range.
        """
        k = target_clause_index
        if not (0 <= k < len(clauses)):
            raise IndexError(f"target_clause_index {k} is out of range for {len(clauses)} clauses")

        placeholder = self._operator.render(clauses[k])

        return {
            "full": self._render_full(clauses),
            "null": self._render_null(),
            f"ablated_{k}": self._render_ablated(clauses, k, placeholder),
        }

    # ------------------------------------------------------------------
    # Private renderers
    # ------------------------------------------------------------------

    def _render_full(self, clauses: list[str]) -> dict[str, Any]:
        """Render the Full condition: all clauses present in authoring order."""
        # Block 1: base system with cache marker (end-of-system breakpoint)
        base_block: dict[str, Any] = {
            "type": "text",
            "text": self._base_system,
            "cache_control": {"type": "ephemeral"},
        }

        # Block 2: full skill text (all clauses) with cache marker (end-of-skill-prefix)
        skill_text = self._format_clauses(clauses)
        skill_block: dict[str, Any] = {
            "type": "text",
            "text": skill_text,
            "cache_control": {"type": "ephemeral"},
        }

        blocks = [base_block, skill_block]
        return {
            "system_text": "".join(b["text"] for b in blocks),
            "system_blocks": blocks,
        }

    def _render_null(self) -> dict[str, Any]:
        """Render the Null condition: no skill text."""
        base_block: dict[str, Any] = {
            "type": "text",
            "text": self._base_system,
            "cache_control": {"type": "ephemeral"},
        }
        blocks = [base_block]
        return {
            "system_text": "".join(b["text"] for b in blocks),
            "system_blocks": blocks,
        }

    def _render_ablated(
        self,
        clauses: list[str],
        k: int,
        placeholder: str,
    ) -> dict[str, Any]:
        """Render the Ablated_k condition.

        Rendering order (A43 ablated-clause-last):
          - Base system block [cache marker 1: end-of-system]
          - Skill prefix: all clauses EXCEPT clause k [cache marker 2: end-of-skill-prefix]
          - Ablated clause block: the placeholder for clause k (rendered last)

        This ordering maximises the shared cacheable prefix across Full and Ablated_k
        calls for the same clause k, because:
          Full:      [base] [all clauses]
          Ablated_k: [base] [clauses except k] [placeholder at end]
        The shared prefix = [base] + clauses-up-to-but-not-including-the-reordered-k.
        """
        # Block 1: base system with cache marker
        base_block: dict[str, Any] = {
            "type": "text",
            "text": self._base_system,
            "cache_control": {"type": "ephemeral"},
        }

        # Skill prefix: all clauses in authoring order except clause k
        other_clauses = [c for i, c in enumerate(clauses) if i != k]
        prefix_text = self._format_clauses(other_clauses)

        # Ablated-clause block (last — maximizes shared prefix per A43).
        # INVARIANT (A39): the block text contains ONLY the placeholder — never the
        # ABLATED_CLAUSE_MARKER. Injecting the marker adds tokens to the ablated side
        # only, contaminating the length axis. The marker is returned as a separate
        # metadata field for --show-rendered / test introspection.
        ablated_block: dict[str, Any] = {
            "type": "text",
            "text": placeholder,
        }

        if prefix_text:
            # Non-empty prefix: include the prefix block with cache marker so the shared
            # prefix [base] + [other clauses] is cacheable across Full and Ablated_k.
            prefix_block: dict[str, Any] = {
                "type": "text",
                "text": prefix_text,
                "cache_control": {"type": "ephemeral"},
            }
            blocks = [base_block, prefix_block, ablated_block]
        else:
            # Empty prefix (e.g. single-clause skill or single-clause --clause run):
            # omit the prefix block entirely — an empty text block with cache_control
            # is rejected by the API (400 "cache_control cannot be set for empty text blocks").
            blocks = [base_block, ablated_block]

        # system_text is the faithful concatenation of block texts — the wire prompt
        # the model receives. This equals the Full condition's system_text with clause k
        # substituted by the placeholder (authoring order, no marker).
        # Faithful wire = concatenated block texts (no extra content).
        system_text = "".join(b["text"] for b in blocks)

        # Inspection marker returned as SEPARATE field — never in block text (A39).
        marker = ABLATED_CLAUSE_MARKER.format(k=k)

        return {
            "system_text": system_text,
            "system_blocks": blocks,
            "ablated_clause_marker": marker,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_clauses(clauses: list[str]) -> str:
        """Format a list of clause texts into a single skill block string.

        Each clause is placed on its own line, separated by blank lines.
        """
        if not clauses:
            return ""
        return "\n\n".join(clause.strip() for clause in clauses)
