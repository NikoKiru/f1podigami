from pathlib import Path

from build import brand
from build._layout import nav

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def test_favicon_is_the_standalone_plate():
    assert (ASSETS / "favicon.svg").read_text(encoding="utf-8") == brand.plate_svg(
        "p-cuts", standalone=True
    )


def test_plate_is_red_board_with_masked_p():
    svg = brand.plate_svg("x1")
    assert 'fill="#e10600"' in svg and 'rx="14"' in svg
    assert 'id="x1"' in svg and 'mask="url(#x1)"' in svg
    assert 'fill-rule="evenodd"' in svg and "skewX(-10)" in svg


def test_nav_uses_two_distinct_mask_ids():
    out = nav("index.html")
    ids = [m for m in ("pm-nav", "pm-drawer") if f'id="{m}"' in out]
    assert ids == ["pm-nav", "pm-drawer"]
    assert out.count('class="brand-mark"') == 2


def test_nav_wordmark_is_stacked():
    out = nav("index.html")
    assert out.count(brand.BRAND_NAME_HTML) == 2
    assert '<span class="accent">F1</span> Podigami' not in out
