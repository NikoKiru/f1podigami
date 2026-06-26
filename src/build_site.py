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
from datetime import UTC, datetime
from pathlib import Path

SRC = Path(__file__).resolve().parent
REPO = SRC.parent
BUILD_DIR = SRC / "build"
DIST = REPO / "dist"
ASSETS = REPO / "assets"

SITE_URL = "https://nikokiru.github.io/f1podigami"

PAGE_BUILDERS = [
    "build_podigami_html.py",
    "build_combos_html.py",
    "build_overdue_html.py",
    "build_soulmates_html.py",
    "build_404_html.py",
]

PAGES = ["index.html", "combos.html", "overdue.html", "soulmates.html"]


def _write_robots_txt() -> None:
    content = f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n"
    (DIST / "robots.txt").write_text(content, encoding="utf-8")


def _last_race_date() -> str:
    from datalib import load_schedule

    today = datetime.now(UTC).date().isoformat()
    races = load_schedule().races
    past = [r.date for r in races if r.date <= today]
    return max(past) if past else today


def _write_sitemap_xml() -> None:
    lastmod = _last_race_date()
    urls = "\n".join(
        f"  <url>\n    <loc>{SITE_URL}/{page}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>"
        for page in PAGES
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )
    (DIST / "sitemap.xml").write_text(content, encoding="utf-8")


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

    _write_robots_txt()
    _write_sitemap_xml()

    print(
        f"\nSite built -> {DIST} ({len(PAGE_BUILDERS)} pages, {copied} assets, robots.txt, sitemap.xml)"
    )


if __name__ == "__main__":
    build()
