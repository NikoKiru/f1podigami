import struct
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


def _png_size(p):
    b = p.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", b[16:24])


def test_icon_pngs_have_the_platform_sizes():
    assert _png_size(ASSETS / "apple-touch-icon.png") == (180, 180)
    assert _png_size(ASSETS / "og-image.png") == (1200, 630)


def test_render_script_exists_and_is_not_part_of_the_build():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src" / "build" / "render_brand_assets.py").is_file()
    src = (root / "src" / "build_site.py").read_text(encoding="utf-8")
    assert "render_brand_assets" not in src
