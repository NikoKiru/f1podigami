"""Shared page chrome used by every page builder.

Centralising the ``<head>``, nav, and footer here guarantees all four pages
share identical chrome (and stops the drift bugs that come from copy-pasting
them). The import works both when a builder is run as a script
(``python src/build/build_*.py``) and when the builders are imported as
``build.*`` by the test-suite, because each builder adds its own directory to
``sys.path`` before importing this module.
"""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"

REPO_URL = "https://github.com/NikoKiru/f1podigami"
DATA_URL = "https://api.jolpi.ca/ergast/f1/"
SITE_URL = "https://nikokiru.github.io/f1podigami"

# Nav links in order: (href, label). The label shown for the active page is
# rendered without the trailing arrow that the Soulmates link otherwise carries.
NAV_LINKS = [
    ("index.html", "Podigami"),
    ("combos.html", "Combinations"),
    ("overdue.html", "Overdue"),
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


def nav(active: str) -> str:
    """Return the sticky site header: brand (logo + wordmark), uppercase nav
    with ``active`` (an href like ``"index.html"``) underlined, and the
    light/dark theme toggle."""
    items = []
    for href, label in NAV_LINKS:
        cls = ' class="active"' if href == active else ""
        items.append(f'            <a href="{href}"{cls}>{label}</a>')
    links = "\n".join(items)
    return f"""<nav class="nav">
    <div class="container nav-inner">
        <a class="brand" href="index.html" aria-label="F1 Podigami home">
            {_BRAND_MARK}
            <span class="brand-name"><span class="accent">F1</span> Podigami</span>
        </a>
        <div class="nav-links">
{links}
        </div>
        <button type="button" class="theme-toggle" id="theme-toggle" aria-label="Toggle light or dark theme" title="Toggle light/dark theme"></button>
    </div>
</nav>"""


FOOTER = f"""<footer>
    <div class="container footer-inner">
        <nav class="footer-nav">
            <a href="index.html">Podigami</a>
            <a href="combos.html">Combinations</a>
            <a href="overdue.html">Overdue</a>
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
