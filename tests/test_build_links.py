"""Build-output wiring: internal links resolve, race sources are sound, and the
build is deterministic. Also checks the orchestration step lists stay valid.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

import build_site
import update

REPO = Path(__file__).resolve().parents[1]
PAGES = ["index.html", "combos.html", "overdue.html", "soulmates.html"]


# --- orchestration wiring ------------------------------------------------------


def test_page_builders_exist():
    for script in build_site.PAGE_BUILDERS:
        assert (REPO / "src" / "build" / script).is_file(), f"missing builder {script}"


def test_update_steps_point_to_real_scripts():
    for _, rel in update.STEPS:
        assert (REPO / "src" / rel).is_file(), f"update.py references missing {rel}"


# --- internal links + assets resolve ------------------------------------------


@pytest.mark.parametrize("page", PAGES)
def test_internal_html_links_resolve(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    for href in re.findall(r'href="([^"]+\.html)"', html):
        if href.startswith("http"):
            continue
        assert (dist / href).is_file(), f"{page} links to missing {href}"


@pytest.mark.parametrize("page", PAGES)
def test_css_and_js_resolve(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    # refs carry a cache-busting query (e.g. style.css?v=ab12cd34); capture both.
    refs = re.findall(r'href="([^"]+\.css(?:\?[^"]*)?)"', html) + re.findall(
        r'src="([^"]+\.js(?:\?[^"]*)?)"', html
    )
    assert refs, f"{page} should reference at least one css/js asset"
    for ref in refs:
        if ref.startswith("http"):
            continue
        path, _, query = ref.partition("?")
        assert (dist / path).is_file(), f"{page} references missing asset {path}"
        # local code assets must be cache-busted so deploys can't serve stale JS/CSS
        assert query.startswith("v="), f"{page} asset {ref} is not cache-busted"


NAV_PAGES = ["index.html", "combos.html", "overdue.html"]


def test_every_page_has_full_nav(dist):
    for page in PAGES:
        html = (dist / page).read_text(encoding="utf-8")
        for target in NAV_PAGES:
            assert f'href="{target}"' in html, f"{page} nav missing link to {target}"


# --- external race-report sources ---------------------------------------------


def test_race_report_links_are_official_f1(dist):
    html = (dist / "combos.html").read_text(encoding="utf-8")
    links = re.findall(r'<a class="race-pill" href="([^"]+)"', html)
    assert links, "combos page should have race-report links"
    for url in links:
        # every pill links to F1's result page, or (rarely) the wiki fallback
        assert url.startswith("https://www.formula1.com/en/results/") or url.startswith(
            "https://en.wikipedia.org/wiki/"
        )
        assert " " not in url
    # the whole point of the feature: the vast majority resolve to F1.
    # Match on the full prefix, not a bare "formula1.com" substring — the latter
    # also matches a lookalike host (formula1.com.example.com) and trips CodeQL's
    # incomplete-URL-substring-sanitization rule.
    f1 = [u for u in links if u.startswith("https://www.formula1.com/en/results/")]
    assert len(f1) > len(links) // 2, "expected most race links to be official F1 URLs"


def test_timeline_embed_uses_official_f1_urls(dist):
    # The landing-page timeline is rendered client-side by podigami.js from the
    # embedded bySeason data; that data must carry official F1 result URLs so the
    # slider links out to F1, not Wikipedia.
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert '"url": "https://www.formula1.com/en/results/' in html
    assert '"url": "https://en.wikipedia.org/wiki/' not in html  # no wiki fallback in the embed


# --- determinism ---------------------------------------------------------------


def _hash_dist(dist: Path) -> dict:
    out = {}
    for p in sorted(dist.glob("*")):
        if p.is_file():
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_build_is_deterministic(dist):
    before = _hash_dist(dist)
    result = subprocess.run(
        [sys.executable, str(REPO / "src" / "build_site.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    after = _hash_dist(dist)
    assert before == after, "rebuilding from the same data produced different output"
