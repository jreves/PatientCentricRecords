"""Claude Code PreToolUse hook: keep hosted Claude out of Sources/ (raw records) and private/ (identifiers, staging).

The permission deny rules in .claude/settings.json cover Read/Edit/Write, but not shell commands or searches. This hook
denies any Bash/PowerShell command, Grep or Glob whose text names either folder of this project. It errs on the side of
blocking: a command that merely mentions the path (an echo, a commit message) is refused too. The pipeline itself never
needs the path on the command line (`python -m pipeline run` reads the sources from the config).

Input: the hook JSON on stdin. Output: a deny decision on stdout, or nothing (allow). Unreadable input is denied.
"""
import json
import os
import pathlib
import re
import sys

GUARDED = ("sources", "private")
ROOT = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or pathlib.Path(__file__).resolve().parent.parent.parent)
END = r"(?=[\\/\"'`\s)*;|&,]|$)"


def patterns(root=ROOT):
    names = "|".join(GUARDED)
    # A relative path: the folder name at the start of a word, optionally after ./ (but not /private/tmp on macOS).
    rel = rf"(?:^|[\s\"'`=(,;|&<>])(?:\.[\\/])?(?:{names}){END}"
    # An absolute or ../ path through this project's folder, written with either slash.
    base = re.escape(root.name).replace(r"\ ", r"(?:\\?\s)")
    via_root = rf"{base}[\\/]+(?:{names}){END}"
    return [re.compile(rel, re.I), re.compile(via_root, re.I)]


def touches_private(text, root=ROOT):
    return any(p.search(text) for p in patterns(root))


def texts(event):
    tool, inp = event.get("tool_name", ""), event.get("tool_input", {}) or {}
    if tool in ("Bash", "PowerShell"):
        return [inp.get("command", "")]
    if tool in ("Grep", "Glob", "Read", "Edit", "Write", "NotebookEdit"):
        return [str(inp.get(k, "")) for k in ("path", "pattern", "glob", "file_path", "notebook_path")]
    return []


def decide(event, root=ROOT):
    if any(touches_private(t, root) for t in texts(event) if t):
        return ("This project's Sources/ and private/ folders hold raw patient data; hosted Claude must not access them, "
                "not even to list file names. Run the pipeline (python -m pipeline ...) instead, or ask the user to "
                "check the file locally.")
    return None


def main():
    try:
        event = json.load(sys.stdin)
        reason = decide(event)
    except Exception:
        reason = "The privacy hook could not read this tool call, so it is refused."
    if reason:
        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                          "permissionDecisionReason": reason}}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
