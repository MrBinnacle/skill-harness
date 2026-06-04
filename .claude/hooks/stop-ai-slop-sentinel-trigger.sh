#!/usr/bin/env bash
# Stop hook: trigger ai-slop-sentinel fresh-context review when the last
# assistant turn edited any src/skill_harness/**/*.py file.
#
# Per PLAN §1.3 + Phase 1.3 council discipline.
# Per `claude-code-stop-hook-envelope` skill: Stop hooks receive the JSON
# envelope on stdin, NOT the response text. Read transcript_path, extract
# tool_use entries from the current turn, filter by file_path glob.
#
# Failure mode discipline: fail open (exit 0) on missing/malformed transcript
# or missing jq. A discipline trigger that loudly errors blocks every Stop;
# a silent no-op is the right default for "we couldn't decide."

set -euo pipefail

# 1. Read envelope.
HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# 2. Loop guard: if stop_hook_active is true, we already blocked once and
# Claude is responding to the trigger. Do not block again.
STOP_HOOK_ACTIVE=$(echo "$HOOK_INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo "false")
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

# 3. Resolve transcript path. Missing or unreadable → no-op.
TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || echo "")
if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

# 4. Find timestamp of the most recent REAL user message (not a tool_result).
# Real user messages have at least one content entry with type == "text".
# Tool-result responses (which carry role=="user" in the transcript) have
# type == "tool_result" and no "text" entries.
LAST_USER_TS=$(jq -rs '
  [.[]
    | select(((.message // {}).role) == "user")
    | select((((.message // {}).content // []) | map(.type)) | any(. == "text"))
    | (.timestamp // "")
  ] | last // ""
' "$TRANSCRIPT_PATH" 2>/dev/null || echo "")

if [ -z "$LAST_USER_TS" ]; then
  exit 0
fi

# 5. Collect file_paths from Edit/Write/MultiEdit tool_uses by ASSISTANT
# entries with timestamp > LAST_USER_TS. Normalize backslashes to forward
# slashes so Windows paths match the glob. Filter to src/skill_harness/...*.py.
TOUCHED=$(jq -rs --arg ts "$LAST_USER_TS" '
  [.[]
    | select(((.message // {}).role) == "assistant")
    | select((.timestamp // "") > $ts)
    | ((.message // {}).content // [])[]?
    | select(.type == "tool_use")
    | select(.name == "Edit" or .name == "Write" or .name == "MultiEdit")
    | (.input.file_path // empty)
  ]
  | map(gsub("\\\\"; "/"))
  | map(select(. != "" and test("src/skill_harness/.*\\.py$")))
  | unique
  | .[]
' "$TRANSCRIPT_PATH" 2>/dev/null || true)

if [ -z "$TOUCHED" ]; then
  # No qualifying edits this turn. Silent pass.
  exit 0
fi

# 6. Emit decision:block with explicit guidance. Claude continues, sees the
# reason, and (per skill discipline) invokes ai-slop-sentinel as a fresh-
# context reviewer on the touched files.
FILES_CSV=$(echo "$TOUCHED" | paste -sd ',' -)

jq -nc \
  --arg files "$FILES_CSV" \
  '{
    decision: "block",
    reason: ("[ai-slop-sentinel auto-trigger] This turn edited storage-layer Python: " + $files + ". Per PLAN §1.3 + the ai-slop-sentinel skill discipline (fresh-context reviewer at review-before-done gate), invoke the ai-slop-sentinel skill on the diff for these files BEFORE this turn ends. After the review returns, summarize findings inline and address any BLOCKER/MAJOR before stopping. This is an automated discipline trigger, not user-requested work.")
  }'

exit 0
