"""Shared fixtures: build the site once per test session."""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO


@pytest.fixture(scope="session")
def dist(repo: Path) -> Path:
    """Build dist/ from the committed data and return its path."""
    result = subprocess.run(
        [sys.executable, str(repo / "src" / "build_site.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"build_site.py failed:\n{result.stdout}\n{result.stderr}"
    )
    dist_dir = repo / "dist"
    assert dist_dir.is_dir(), "dist/ was not created"
    return dist_dir
