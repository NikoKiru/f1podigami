"""Runs the real script against a fake `gh` that plays back a PR's life."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".claude" / "scripts" / "wait_for_pr.sh"


def find_bash():
    """On Windows, the bash that comes with Git, not the first `bash` on PATH.

    That one is usually WSL's launcher. It can't run a Windows script path, and it
    fails outright when the only distro has no bash, as Docker Desktop's doesn't.
    """
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    bash = Path(git).resolve().parents[1] / "bin" / "bash.exe" if git else None
    return str(bash) if bash and bash.exists() else None


BASH = find_bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")

# One line per poll: "<state> <fail count> <pending count>", or "<state> none"
# when GitHub hasn't registered any checks yet, which `gh pr checks` reports by
# exiting non-zero. The last line repeats, so a wrong wait can't run forever.
FAKE_GH = r"""#!/usr/bin/env bash
dir=$(dirname "$0")
tick() { cat "$dir/tick" 2>/dev/null || echo 1; }
line() { sed -n "$(tick)p" "$dir/script"; }
case "$1 $2" in
  "pr view")
    case "$*" in
      *baseRefName*) echo develop ;;
      *state*)
        set -- $(line)
        echo "$1"
        ;;
    esac
    ;;
  "pr checks")
    read -r state fail pending <<<"$(line)"
    case "$*" in
      *pending*) # the last query of a poll, so the next one reads the next line
        next=$(($(tick) + 1))
        [ -n "$(sed -n "${next}p" "$dir/script")" ] && echo "$next" >"$dir/tick"
        ;;
    esac
    case "$*" in
      *--json*)
        [ "$fail" = none ] && { echo "no checks reported" >&2; exit 1; }
        case "$*" in
          *pending*) echo "$pending" ;;
          *) echo "$fail" ;;
        esac
        ;;
      *) printf 'Test\tpass\t1s\n' ;;
    esac
    ;;
esac
"""


def wait_for(tmp_path, *polls):
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8", newline="\n")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "script").write_text("\n".join(polls) + "\n", encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "WAIT_INTERVAL": "0",
    }
    return subprocess.run(
        [BASH, str(SCRIPT), "1"], capture_output=True, text=True, env=env, timeout=30
    )


def test_a_push_with_no_checks_yet_is_not_a_failure(tmp_path):
    result = wait_for(tmp_path, "OPEN none", "OPEN 0 3", "MERGED 0 0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MERGED, 0 failed" in result.stdout


def test_a_failed_check_stops_the_wait(tmp_path):
    result = wait_for(tmp_path, "OPEN 0 3", "OPEN 1 2")
    assert result.returncode == 1
    assert "1 failed" in result.stdout


def test_a_merge_with_checks_still_running_keeps_waiting(tmp_path):
    """Auto-merge only waits for required checks, so E2E can outlive the merge."""
    result = wait_for(tmp_path, "MERGED 0 1", "MERGED 1 0")
    assert result.returncode == 1
    assert "1 failed" in result.stdout
