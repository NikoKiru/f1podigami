"""Build the deployable static site into dist/.

Runs the four page builders (which read data/ and write dist/*.html), then
copies the source assets (CSS/JS) from assets/ into dist/ so dist/ is a
self-contained, deployable folder.

This step needs no network — it works entirely from the committed data/*.json,
which is what makes it safe to run in CI and on every deploy.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
REPO = SRC.parent
BUILD_DIR = SRC / "build"
DIST = REPO / "dist"
ASSETS = REPO / "assets"

PAGE_BUILDERS = [
    "build_podigami_html.py",
    "build_combos_html.py",
    "build_overdue_html.py",
    "build_soulmates_html.py",
]


def build() -> None:
    DIST.mkdir(parents=True, exist_ok=True)

    for script in PAGE_BUILDERS:
        result = subprocess.run([sys.executable, str(BUILD_DIR / script)])
        if result.returncode != 0:
            print(f"\nBuild failed: {script}", file=sys.stderr)
            sys.exit(result.returncode)

    # Copy CSS/JS into dist/ so the bare hrefs in the generated HTML resolve.
    copied = 0
    for asset in ASSETS.iterdir():
        if asset.is_file():
            shutil.copy2(asset, DIST / asset.name)
            copied += 1

    print(f"\nSite built -> {DIST} ({len(PAGE_BUILDERS)} pages, {copied} assets)")


if __name__ == "__main__":
    build()
