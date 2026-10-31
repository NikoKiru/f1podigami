"""PreToolUse hook: stop a `git commit` that CI's "Lint & format" check would fail.

Runs the same two ruff commands as CI, from the project root. Exit 2 blocks the
commit and hands stderr to Claude. Every other path exits 0, because a hook that
can't do its job (no ruff, unreadable input) must never be what stops a commit.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys

GIT_COMMIT = re.compile(r"\bgit\s+(?:-\S+\s+(?:\S+\s+)?)*commit\b")
CHECKS = (["check", "."], ["format", "--check", "."])


def is_commit(stdin: str) -> bool:
    try:
        command = json.loads(stdin)["tool_input"]["command"]
    except (ValueError, KeyError, TypeError):
        return False
    return bool(GIT_COMMIT.search(command))


def main() -> int:
    if not is_commit(sys.stdin.read()) or importlib.util.find_spec("ruff") is None:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    failed = False
    for args in CHECKS:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", *args], cwd=root, capture_output=True, text=True
        )
        if result.returncode != 0:
            failed = True
            print(f"ruff {' '.join(args)}:\n{result.stdout}{result.stderr}", file=sys.stderr)
    if failed:
        print(
            "Commit blocked: CI would fail this. Run `ruff format .`, fix, retry.", file=sys.stderr
        )
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
