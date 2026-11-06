"""Regenerate the home-screen icon and the link-preview image from the brand plate.

A dev tool, run by hand after the mark changes; it is not part of build_site.py.
It needs Playwright with Chromium, which is not in requirements.txt:

    python src/build/render_brand_assets.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build import brand  # noqa: E402

ASSETS = Path(__file__).resolve().parents[2] / "assets"

# iOS rounds the home-screen icon itself, so the plate goes in full-bleed square.
SQUARE_PLATE = brand.plate_svg("pm-icon").replace(' rx="14"', "")

ICON_HTML = (
    "<!doctype html><meta charset=utf-8>"
    "<style>html,body{margin:0;background:#e10600}svg{display:block;width:180px;height:180px}</style>"
    + SQUARE_PLATE
)

OG_HTML = (
    "<!doctype html><meta charset=utf-8><style>"
    "html,body{margin:0}"
    "body{width:1200px;height:630px;background:#0b0d12;display:flex;flex-direction:column;"
    "align-items:center;justify-content:center;gap:34px;"
    "font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif}"
    ".plate{width:170px;height:170px}"
    ".brand-name{display:grid;gap:8px;line-height:1;white-space:nowrap;text-align:center}"
    ".brand-kicker{font-size:22px;font-weight:700;letter-spacing:.32em;text-transform:uppercase;"
    "color:#9aa3af;margin-right:-.32em}"
    ".brand-word{font-size:64px;font-weight:900;font-style:italic;letter-spacing:.02em;"
    "text-transform:uppercase;color:#f3f4f6}"
    ".tag{font-size:28px;font-weight:600;color:#9aa3af;margin-top:6px}"
    "</style>"
    + brand.plate_svg("pm-og", "plate")
    + brand.BRAND_NAME_HTML
    + '<div class="tag">Every F1 podium combination since 1950</div>'
)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Run: pip install playwright && "
            "python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for html, size, name in (
            (ICON_HTML, (180, 180), "apple-touch-icon.png"),
            (OG_HTML, (1200, 630), "og-image.png"),
        ):
            page = browser.new_page(viewport={"width": size[0], "height": size[1]})
            page.set_content(html)
            page.screenshot(path=str(ASSETS / name))
            page.close()
            print(f"wrote assets/{name}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
