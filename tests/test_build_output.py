"""Output / HTML validation: the built site is complete and well-formed."""

import pytest

# page -> assets it must reference (and which must end up in dist/)
PAGES = {
    "index.html": ["podigami.css", "podigami.js", "theme.js"],
    "combos.html": ["index.css", "index.js", "theme.js"],
    "overdue.html": ["podigami.css", "theme.js"],
    "soulmates.html": ["soulmates.css", "theme.js"],
}

ALL_ASSETS = [
    "style.css",
    "index.css",
    "soulmates.css",
    "podigami.css",
    "index.js",
    "podigami.js",
    "theme.js",
    "favicon.svg",
]


def test_pages_link_favicon(dist):
    for page in PAGES:
        html = (dist / page).read_text(encoding="utf-8")
        assert '<link rel="icon" href="favicon.svg" type="image/svg+xml">' in html
    assert (dist / "favicon.svg").is_file()


@pytest.mark.parametrize("page", PAGES)
def test_page_built_and_nonempty(dist, page):
    f = dist / page
    assert f.is_file(), f"{page} was not generated"
    assert f.stat().st_size > 500, f"{page} looks suspiciously small"


@pytest.mark.parametrize("page", PAGES)
def test_page_head_essentials(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert 'name="viewport"' in html
    assert "width=device-width, initial-scale=1.0" in html
    assert '<link rel="stylesheet" href="style.css">' in html


def test_landing_h1_keyword_has_real_space(dist):
    # the <h1> text content must read "F1 Podigami" (real space, not just CSS gap)
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert '<h1><span class="accent">F1</span> Podigami</h1>' in html


def test_google_site_verification_present(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert (
        '<meta name="google-site-verification" '
        'content="hLESDF63VKsCV-0eJeHsA00GDM6K4CRWjjBnPnB8Dr8">'
    ) in html


@pytest.mark.parametrize("page,assets", PAGES.items())
def test_page_assets_referenced_and_copied(dist, page, assets):
    html = (dist / page).read_text(encoding="utf-8")
    for asset in assets:
        assert asset in html, f"{page} should reference {asset}"
        assert (dist / asset).is_file(), f"{asset} should be copied into dist/"


def test_all_assets_copied(dist):
    for asset in ALL_ASSETS:
        assert (dist / asset).is_file(), f"missing asset in dist/: {asset}"


def test_combos_has_nav_and_combo_rows(dist):
    html = (dist / "combos.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert "<table" in html
    assert 'class="combo"' in html


def test_index_is_podigami_predictor(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert 'class="hero"' in html  # next-podigami hero
    assert 'id="tl-slider"' in html  # year-slider timeline
    assert 'id="podigami-data"' in html  # embedded slider data


@pytest.mark.parametrize("page", PAGES)
def test_page_has_theme_toggle_and_no_flash_script(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    # the nav toggle button drives the light/dark switch
    assert 'id="theme-toggle"' in html, f"{page} is missing the theme toggle"
    # a blocking inline script applies the stored/OS theme before first paint
    assert 'setAttribute("data-theme"' in html, f"{page} lacks the no-flash theme script"
    assert "prefers-color-scheme: light" in html, f"{page} should honour the OS preference"


def test_landing_page_has_broadcast_driver_treatment(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert "--team:" in html  # team-colour custom property drives the accents
    assert 'class="tower-row"' in html  # timing-tower current-form rows
    assert 'class="d-code"' in html  # hero TLA codes
    assert 'class="tr-num"' in html  # car-number chips


def test_landing_page_has_faq_section(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert "faq-section" in html  # dedicated FAQ section
    assert "Frequently asked questions" in html
    assert 'class="faq-item"' in html  # expandable items
    assert 'class="acc-badge"' in html  # compact backtest badge still present


def test_landing_page_has_info_tooltips(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="info-tip"' in html  # "i" info affordance
    assert 'class="info-bubble"' in html  # hover/focus explanation


def test_landing_page_has_next_race_box(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="next-race"' in html
    assert "data-datetime=" in html  # countdown/local-time hook
    assert 'class="nr-track"' in html  # circuit outline SVG


def test_display_name_uppercases_surname_only():
    from build.build_podigami_html import display_name

    assert display_name("Max Verstappen") == "Max VERSTAPPEN"
    assert display_name("Andrea Kimi Antonelli") == "Andrea Kimi ANTONELLI"
    assert display_name("Kimi Räikkönen") == "Kimi RÄIKKÖNEN"  # unicode-safe
    assert display_name("") == ""


def test_landing_candidate_tooltip_uses_broadcast_name(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    # candidate hover tooltips show the broadcast full name (surname uppercased)
    assert "ANTONELLI" in html


def test_team_styling_only_on_landing_page(dist):
    # historical/data pages stay plain — no team colours should leak in
    for page in ("combos.html", "overdue.html", "soulmates.html"):
        html = (dist / page).read_text(encoding="utf-8")
        assert "--team:" not in html, f"team styling leaked into {page}"


def _footer_block(html: str) -> str:
    start = html.index("<footer>")
    end = html.index("</footer>") + len("</footer>")
    return html[start:end]


def test_footer_is_identical_across_pages(dist):
    footers = {p: _footer_block((dist / p).read_text(encoding="utf-8")) for p in PAGES}
    unique = set(footers.values())
    assert len(unique) == 1, (
        f"footers differ across pages: { {p: f[:60] for p, f in footers.items()} }"
    )


@pytest.mark.parametrize("page", PAGES)
def test_footer_has_universal_details(dist, page):
    footer = _footer_block((dist / page).read_text(encoding="utf-8"))
    assert "Jolpica F1 API" in footer  # data source attribution
    assert "github.com/NikoKiru/f1podigami" in footer  # source link
    assert 'class="footer-nav"' in footer  # cross-page nav
    for link in ("index.html", "combos.html", "overdue.html"):
        assert link in footer, f"footer should link to {link}"


def test_stylesheet_defines_light_theme(dist):
    css = (dist / "style.css").read_text(encoding="utf-8")
    assert '[data-theme="light"]' in css, "style.css must define a light theme"
    assert ".theme-toggle" in css, "style.css must style the theme toggle"


def test_overdue_has_two_ranked_lists(dist):
    html = (dist / "overdue.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert html.count('class="cand-list"') == 2  # all-time + current grid
    assert "All-time near-misses" in html
    assert 'class="cand-meta"' in html  # "raced N times together"
