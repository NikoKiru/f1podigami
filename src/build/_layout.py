"""Shared page chrome used by every page builder.

Centralising the ``<head>``, nav, and footer here guarantees every page
shares identical chrome (and stops the drift bugs that come from copy-pasting
them). The import works both when a builder is run as a script
(``python src/build/build_*.py``) and when the builders are imported as
``build.*`` by the test-suite, because each builder adds its own directory to
``sys.path`` before importing this module.
"""

from __future__ import annotations

import hashlib
import urllib.parse
from functools import cache
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"

REPO_URL = "https://github.com/NikoKiru/f1podigami"
DATA_URL = "https://api.jolpi.ca/ergast/f1/"
SITE_URL = "https://nikokiru.github.io/f1podigami"

# Nav links in order: (href, label).
NAV_LINKS = [
    ("index.html", "Podigami"),
    ("combos.html", "Combinations"),
    ("overdue.html", "Overdue"),
    ("unlikeliest.html", "Unlikeliest"),
    ("soulmates.html", "Soulmates"),
]

# Applied before first paint so the stored/OS theme never flashes. Kept as a
# plain string (not an f-string) so its braces need no escaping by callers.
_THEME_INIT = (
    "<script>(function(){"
    'try{var t=localStorage.getItem("theme");'
    'if(t!=="light"&&t!=="dark")'
    't=window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";'
    'document.documentElement.setAttribute("data-theme",t);}'
    "catch(e){}})();</script>"
)


def wiki_url(season: str, race_name: str) -> str:
    """Wikipedia race-report URL — the same source the Ergast/Jolpica API cites."""
    title = f"{season} {race_name}".replace(" ", "_")
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title)


def race_url(links: dict, season: str, rnd, race_name: str) -> str:
    """Official F1 result-page URL for a race, falling back to Wikipedia.

    ``links`` is the ``season -> round -> RaceLink`` map from
    ``datalib.load_race_links``. A race absent from the map (data gap, brand-new
    race, or a season F1 and we disagree on) falls back to its Wikipedia report.
    """
    link = links.get(season, {}).get(str(rnd))
    if link is not None:
        return (
            f"https://www.formula1.com/en/results/{season}/races/{link.id}/{link.slug}/race-result"
        )
    return wiki_url(season, race_name)


def abbr_name(name: str) -> str:
    """ "Esteban Ocon" -> "E. Ocon": first initial + surname, for narrow screens."""
    parts = name.strip().split()
    if len(parts) < 2:
        return name
    return parts[0][0] + ". " + parts[-1]


@cache
def _asset_version(name: str) -> str:
    """Short content hash of an asset in ``assets/``, or "" if it isn't there."""
    try:
        digest = hashlib.sha1((_ASSETS_DIR / name).read_bytes()).hexdigest()
    except OSError:
        return ""
    return digest[:8]


def asset(name: str) -> str:
    """Asset URL carrying a content-hash ``?v=`` token.

    GitHub Pages serves static assets with ``Cache-Control: max-age=600`` and no
    fingerprinting, so a freshly deployed HTML page can pair with a stale cached
    script/stylesheet for up to 10 minutes. Versioning the URL by content makes
    every deploy bust the cache immediately and rules out that HTML/asset skew.
    Unknown files fall back to the bare name (e.g. for assets generated outside
    ``assets/``).
    """
    version = _asset_version(name)
    return f"{name}?v={version}" if version else name


def head(
    title: str,
    *css_files: str,
    description: str = "",
    page_path: str = "",
    keywords: str = "",
) -> str:
    """Return ``<!DOCTYPE html>`` through ``</head>`` for a page.

    ``style.css`` is always linked first; ``css_files`` are the page-specific
    stylesheets (e.g. ``"podigami.css"``).
    """
    links = "\n".join(
        f'<link rel="stylesheet" href="{asset(href)}">' for href in ("style.css", *css_files)
    )
    canonical = f"{SITE_URL}/{page_path}" if page_path else f"{SITE_URL}/"
    seo = ""
    if description:
        seo += f'\n<meta name="description" content="{description}">'
        seo += f'\n<meta property="og:description" content="{description}">'
    if keywords:
        seo += f'\n<meta name="keywords" content="{keywords}">'
    seo += f'\n<link rel="canonical" href="{canonical}">'
    seo += f'\n<meta property="og:title" content="{title}">'
    seo += '\n<meta property="og:type" content="website">'
    seo += f'\n<meta property="og:url" content="{canonical}">'
    seo += '\n<meta property="og:site_name" content="F1 Podigami">'
    seo += f'\n<meta property="og:image" content="{SITE_URL}/og-image.png">'
    seo += '\n<meta property="og:image:width" content="1200">'
    seo += '\n<meta property="og:image:height" content="630">'
    seo += '\n<meta name="twitter:card" content="summary_large_image">'
    seo += f'\n<meta name="twitter:title" content="{title}">'
    if description:
        seo += f'\n<meta name="twitter:description" content="{description}">'
    seo += f'\n<meta name="twitter:image" content="{SITE_URL}/og-image.png">'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0d12">
<meta name="google-site-verification" content="hLESDF63VKsCV-0eJeHsA00GDM6K4CRWjjBnPnB8Dr8">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
{_THEME_INIT}
<title>{title}</title>{seo}
{links}
</head>"""


# Small podium logo mark for the header brand (matches the favicon).
_BRAND_MARK = (
    '<svg class="brand-mark" viewBox="0 0 64 64" aria-hidden="true">'
    '<rect x="6" y="28" width="16" height="26" rx="2" fill="#c0c0c0"/>'
    '<rect x="24" y="17" width="16" height="37" rx="2" fill="#f4c430"/>'
    '<rect x="42" y="35" width="16" height="19" rx="2" fill="#cd7f32"/>'
    '<rect x="5" y="54" width="54" height="5" rx="2.5" fill="#e10600"/>'
    "</svg>"
)


# Progressive enhancement for the mobile drawer: the checkbox hack works with
# no JS at all; this layer only adds aria state, Escape-to-close, keyboard
# toggling on the burger label, and a body scroll lock while open.
_DRAWER_SCRIPT = (
    "<script>(function(){"
    'var t=document.getElementById("nav-drawer-toggle");if(!t)return;'
    'var b=document.querySelector(".nav-burger");'
    "function sync(){"
    'b.setAttribute("aria-expanded",t.checked?"true":"false");'
    'document.documentElement.classList.toggle("drawer-open",t.checked);}'
    't.addEventListener("change",sync);sync();'
    'b.addEventListener("keydown",function(e){'
    'if(e.key==="Enter"||e.key===" "){e.preventDefault();t.checked=!t.checked;sync();}});'
    'document.addEventListener("keydown",function(e){'
    'if(e.key==="Escape"&&t.checked){t.checked=false;sync();}});'
    "})();</script>"
)


def nav(active: str) -> str:
    """Return the sticky site header: brand (logo + wordmark), uppercase nav
    with ``active`` (an href like ``"index.html"``) underlined, and the
    light/dark theme toggle. On mobile the links collapse behind a burger that
    opens a left slide-out drawer (pure-CSS checkbox core + JS a11y layer)."""
    items = []
    drawer_items = []
    for href, label in NAV_LINKS:
        cls = ' class="active"' if href == active else ""
        items.append(f'            <a href="{href}"{cls}>{label}</a>')
        drawer_items.append(f'            <a href="{href}"{cls}>{label}</a>')
    links = "\n".join(items)
    drawer_links = "\n".join(drawer_items)
    return f"""<nav class="nav">
    <div class="container nav-inner">
        <input type="checkbox" id="nav-drawer-toggle" class="nav-drawer-toggle">
        <label for="nav-drawer-toggle" class="nav-burger" role="button" tabindex="0" aria-label="Toggle navigation menu" aria-expanded="false" aria-controls="nav-drawer">
            <span></span><span></span><span></span>
        </label>
        <a class="brand" href="index.html" aria-label="F1 Podigami home">
            {_BRAND_MARK}
            <span class="brand-name"><span class="accent">F1</span> Podigami</span>
        </a>
        <div class="nav-links">
{links}
        </div>
        <button type="button" class="theme-toggle" id="theme-toggle" aria-label="Toggle light or dark theme" title="Toggle light/dark theme"></button>
        <label for="nav-drawer-toggle" class="nav-scrim" aria-hidden="true"></label>
        <aside class="nav-drawer" id="nav-drawer" aria-label="Site navigation">
            <div class="nav-drawer-head">
                {_BRAND_MARK}
                <span class="brand-name"><span class="accent">F1</span> Podigami</span>
            </div>
{drawer_links}
        </aside>
    </div>
</nav>
{_DRAWER_SCRIPT}"""


FOOTER = f"""<footer>
    <div class="container footer-inner">
        <nav class="footer-nav">
            <a href="index.html">Podigami</a>
            <a href="combos.html">Combinations</a>
            <a href="overdue.html">Overdue</a>
            <a href="unlikeliest.html">Unlikeliest</a>
            <a href="soulmates.html">Soulmates</a>
        </nav>
        <p class="footer-meta">
            Data from <a href="{DATA_URL}" target="_blank" rel="noopener">Jolpica F1 API</a> (Ergast)
            &middot; F1 World Championship podiums since 1950
            &middot; For fun, not betting
            &middot; Circuit outlines <a href="https://github.com/bacinger/f1-circuits" target="_blank" rel="noopener">f1-circuits</a> (ODbL)
            &middot; <a href="{REPO_URL}" target="_blank" rel="noopener">Source on GitHub</a>
            &middot; <a href="{REPO_URL}/blob/main/RELEASE_NOTES.md" target="_blank" rel="noopener">Release Notes</a>
        </p>
    </div>
</footer>"""
