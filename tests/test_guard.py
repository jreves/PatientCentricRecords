"""The Claude Code privacy hook (.claude/hooks/guard_private.py)."""
import importlib.util
import pathlib

import pytest

spec = importlib.util.spec_from_file_location("guard", pathlib.Path(__file__).parent.parent / ".claude" / "hooks" / "guard_private.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
ROOT = pathlib.Path("/home/user/My Records")


def bash(cmd):
    return guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}}, ROOT)


@pytest.mark.parametrize("cmd", [
    "ls Sources", "ls Sources/clinical-notes | wc -l", "cat private/identifiers.toml", "cat ./private/registry.json",
    'head "private\\verify_report.md"', "grep -r Smith sources/", "cd private && ls", "python -c \"open('Sources/x.pdf')\"",
    "cat '/home/user/My Records/private/registry.json'", "cat /home/user/My\\ Records/Sources/a.pdf",
    "Get-ChildItem G:\\My Records\\Sources", "cat ../My Records/private/x",
])
def test_blocks_guarded_folders(cmd):
    assert bash(cmd)


@pytest.mark.parametrize("cmd", [
    "python -m pipeline run", "ls filtered/notes | head", "cat /private/tmp/scratch.txt", "ls /private/var/folders",
    "python -c \"print(paths.private / 'x')\"", "git status --short -- pipeline config", "grep -n privacy README.md",
    "echo open-sources",
])
def test_allows_everything_else(cmd):
    assert not bash(cmd)


def test_search_tools_checked():
    assert guard.decide({"tool_name": "Grep", "tool_input": {"pattern": "Smith", "path": "/home/user/My Records/private"}}, ROOT)
    assert guard.decide({"tool_name": "Glob", "tool_input": {"pattern": "Sources/**/*.pdf"}}, ROOT)
    assert not guard.decide({"tool_name": "Glob", "tool_input": {"pattern": "filtered/notes/*.md"}}, ROOT)
