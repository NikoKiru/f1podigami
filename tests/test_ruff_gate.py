"""The commit hook runs the real script against real ruff, in a throwaway project."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "ruff_gate.py"
ALLOWED, BLOCKED = 0, 2

CLEAN = "x = 1\n"
UNUSED_IMPORT = "import os\n"
UNFORMATTED = "x=1\n"


def run_hook(project: Path, stdin: str):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
    )


def hook_on(project: Path, source: str, command: str):
    (project / "module.py").write_text(source, encoding="utf-8")
    return run_hook(project, json.dumps({"tool_input": {"command": command}}))


@pytest.mark.parametrize(
    ("source", "command", "expected"),
    [
        (CLEAN, "git commit -m 'x'", ALLOWED),
        (UNUSED_IMPORT, "git commit -m 'x'", BLOCKED),
        (UNFORMATTED, "git commit -m 'x'", BLOCKED),
        (UNUSED_IMPORT, "cd repo && git add -A && git commit -F -", BLOCKED),
        (UNUSED_IMPORT, "git -C repo -c user.name=x commit", BLOCKED),
        (UNUSED_IMPORT, "git status", ALLOWED),
        (UNUSED_IMPORT, "python -m pytest -q", ALLOWED),
    ],
    ids=[
        "clean",
        "lint-failure",
        "format-failure",
        "inside-a-chain",
        "with-git-options",
        "other-git-command",
        "not-git",
    ],
)
def test_only_a_commit_that_ci_would_fail_is_blocked(tmp_path, source, command, expected):
    assert hook_on(tmp_path, source, command).returncode == expected


def test_a_block_tells_claude_what_to_fix(tmp_path):
    result = hook_on(tmp_path, UNUSED_IMPORT, "git commit -m 'x'")
    assert "module.py" in result.stderr


@pytest.mark.parametrize("stdin", ["not json", "{}", '{"tool_input": null}'])
def test_input_it_cannot_read_never_stops_a_commit(tmp_path, stdin):
    (tmp_path / "module.py").write_text(UNUSED_IMPORT, encoding="utf-8")
    assert run_hook(tmp_path, stdin).returncode == ALLOWED
