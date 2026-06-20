"""Shared page chrome used by every page builder.

Centralising the ``<head>``, nav, and footer here guarantees all four pages
share identical chrome (and stops the drift bugs that come from copy-pasting
them). The import works both when a builder is run as a script
(``python src/build/build_*.py``) and when the builders are imported as
``build.*`` by the test-suite, because each builder adds its own directory to
``sys.path`` before importing this module.
"""

from __future__ import annotations

REPO_URL = "https://github.com/NikoKiru/f1_podigami"
DATA_URL = "https://api.jolpi.ca/ergast/f1/"

# Nav links in order: (href, label). The label shown for the active page is
# rendered without the trailing arrow that the Soulmates link otherwise carries.
NAV_LINKS = [
    ("index.html", "Podigami"),
    ("combos.html", "Combinations"),
    ("overdue.html", "Overdue"),
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


def head(title: str, *css_files: str) -> str:
    """Return ``<!DOCTYPE html>`` through ``</head>`` for a page.

    ``style.css`` is always linked first; ``css_files`` are the page-specific
    stylesheets (e.g. ``"podigami.css"``).
    """
    links = "\n".join(
        f'<link rel="stylesheet" href="{href}">' for href in ("style.css", *css_files)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0d12">
{_THEME_INIT}
<title>{title}</title>
{links}
</head>"""


def nav(active: str) -> str:
    """Return the site nav with ``active`` (an href like ``"index.html"``)
    marked, including the light/dark theme toggle."""
    items = []
    for href, label in NAV_LINKS:
        is_active = href == active
        text = label
        if href == "soulmates.html" and not is_active:
            text = "Soulmates &rarr;"
        cls = ' class="active"' if is_active else ""
        items.append(f'        <a href="{href}"{cls}>{text}</a>')
    links = "\n".join(items)
    return f"""<nav class="nav">
    <div class="container nav-inner">
{links}
        <button type="button" class="theme-toggle" id="theme-toggle" aria-label="Toggle light or dark theme" title="Toggle light/dark theme"></button>
    </div>
</nav>"""


FOOTER = f"""<footer>
    <div class="container footer-inner">
        <nav class="footer-nav">
            <a href="index.html">Podigami</a>
            <a href="combos.html">Combinations</a>
            <a href="overdue.html">Overdue</a>
            <a href="soulmates.html">Soulmates</a>
        </nav>
        <p class="footer-meta">
            Data from <a href="{DATA_URL}" target="_blank" rel="noopener">Jolpica F1 API</a> (Ergast)
            &middot; F1 World Championship podiums since 1950
            &middot; For fun, not betting
            &middot; <a href="{REPO_URL}" target="_blank" rel="noopener">Source on GitHub</a>
        </p>
    </div>
</footer>"""
