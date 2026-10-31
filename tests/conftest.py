"""Shared fixtures: build the site once per test session."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

try:
    from playwright.sync_api import Browser
except ImportError:  # CI's unit-test jobs don't install it
    Browser = None

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

# Make src/ importable so tests can exercise pure helpers
# (e.g. `from compute import compute_podigami`, `from build import ...`).
sys.path.insert(0, str(REPO / "src"))

# What welcome.js leaves behind once it has shown the first-visit card.
_SEEN_WELCOME = "try { localStorage.setItem('welcomed', '1'); } catch (e) {}"


@pytest.fixture(autouse=True)
def returning_visitor(request, monkeypatch):
    """Browser tests open pages as a returning visitor, because every test starts
    with empty storage and the first-visit card could otherwise sit on top of
    whatever it clicks. The card's own tests opt out with ``new_visitor``."""
    if Browser is None or request.node.get_closest_marker("new_visitor"):
        return
    new_context, new_page = Browser.new_context, Browser.new_page

    def context_seen_welcome(self, *args, **kwargs):
        context = new_context(self, *args, **kwargs)
        context.add_init_script(_SEEN_WELCOME)
        return context

    def page_seen_welcome(self, *args, **kwargs):
        page = new_page(self, *args, **kwargs)
        page.add_init_script(_SEEN_WELCOME)
        return page

    monkeypatch.setattr(Browser, "new_context", context_seen_welcome)
    monkeypatch.setattr(Browser, "new_page", page_seen_welcome)


def load_data(name: str):
    """Load a committed data/*.json dataset."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def data():
    """All committed datasets, keyed by filename stem."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in DATA.glob("*.json")}


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
    assert result.returncode == 0, f"build_site.py failed:\n{result.stdout}\n{result.stderr}"
    dist_dir = repo / "dist"
    assert dist_dir.is_dir(), "dist/ was not created"
    return dist_dir
