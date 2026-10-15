#!/bin/sh
# Runs guard_private.py with whichever Python is on PATH (python on Windows, often only python3 on macOS/Linux).
# If no Python is found, refuse the tool call rather than let it through unchecked.
PY=$(command -v python || command -v python3)
if [ -z "$PY" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"No Python found to run the privacy hook (.claude/hooks/guard_private.py)."}}'
  exit 0
fi
exec "$PY" "$(dirname "$0")/guard_private.py"
