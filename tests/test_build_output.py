"""Output / HTML validation: the built site is complete and well-formed."""

import json
import re

import pytest

SITE_URL = "https://nikokiru.github.io/f1podigami"

# page -> assets it must reference (and which must end up in dist/)
PAGES = {
    "index.html": ["podigami.css", "podigami.js", "theme.js"],
    "combos.html": ["index.css", "index.js", "theme.js"],
    "overdue.html": ["podigami.css", "overdue.js", "theme.js"],
    "soulmates.html": ["soulmates.css", "theme.js"],
}

ALL_ASSETS = [
    "style.css",
    "index.css",
    "soulmates.css",
    "podigami.css",
    "index.js",
    "podigami.js",
    "overdue.js",
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
    # style.css is linked with a cache-busting ?v= token
    assert '<link rel="stylesheet" href="style.css?v=' in html


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
    for link in ("index.html", "combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert link in footer, f"footer should link to {link}"


# All five generated pages must carry identical chrome with all five links.
ALL_PAGES = ["index.html", "combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"]


@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_links_soulmates_in_nav_and_footer(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    nav = html[html.index('<nav class="nav">') : html.index("</nav>")]
    assert 'href="soulmates.html"' in nav, f"{page} nav is missing Soulmates"
    assert ">Soulmates<" in nav
    footer = _footer_block(html)
    assert 'href="soulmates.html"' in footer, f"{page} footer is missing Soulmates"


def test_landing_page_discovery_hooks_in_flow(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    for href in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f'<a class="hook-card" href="{href}"' in html, f"missing hook to {href}"
    # each in-flow hook sits after its related section
    assert html.index('class="cand-list"') < html.index('class="hook-card" href="combos.html"')
    assert html.index('class="form-tower"') < html.index('class="hook-card" href="soulmates.html"')
    assert html.index('id="tl-slider"') < html.index('class="hook-card" href="overdue.html"')
    assert 'class="hook-row"' in html  # overdue + unlikeliest side by side


def test_landing_page_explore_grid_is_last_section(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert "Keep exploring" in html
    grid = html[html.index('class="explore-grid"') :]
    for href in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f'href="{href}"' in grid, f"explore grid missing {href}"
    # explore grid comes after the FAQ
    assert html.index("faq-section") < html.index('class="explore-grid"')


def test_landing_faq_deep_links_all_pages(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    faq = html[html.index("faq-section") : html.index('class="explore-grid"')]
    assert "What else is on this site?" in faq
    for href in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f'href="{href}"' in faq, f"FAQ should deep-link {href}"


def test_stylesheet_defines_light_theme(dist):
    css = (dist / "style.css").read_text(encoding="utf-8")
    assert '[data-theme="light"]' in css, "style.css must define a light theme"
    assert ".theme-toggle" in css, "style.css must style the theme toggle"


def test_overdue_has_two_ranked_lists(dist):
    html = (dist / "overdue.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert html.count('class="odcard-list"') == 2  # all-time + current grid
    assert "All-time near-misses" in html
    assert 'class="od-drivers"' in html


def test_404_page_exists_with_chrome_and_home_link(dist):
    f = dist / "404.html"
    assert f.is_file(), "dist/404.html was not generated"
    html = f.read_text(encoding="utf-8")
    assert "404" in html
    assert "DNF" in html
    assert 'href="index.html"' in html
    assert 'class="nav"' in html
    assert "<footer>" in html


def test_404_not_in_sitemap(dist):
    sitemap = (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert "404.html" not in sitemap


def test_sitemap_lastmod_is_last_race_date(dist, data):
    from datetime import date

    today = date.today().isoformat()
    past_dates = [r["date"] for r in data["schedule"]["races"] if r["date"] <= today]
    expected = max(past_dates)
    sitemap = (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<lastmod>{expected}</lastmod>" in sitemap


def test_landing_timeline_has_quickpick_chips(dist, data):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="tl-chips"' in html
    lo = data["podigami"]["seasonRange"][0]
    assert f'data-year="{lo}"' in html
    counts = data["podigami"]["seasonCounts"]
    record = max(counts.items(), key=lambda kv: (kv[1], -int(kv[0])))[0]
    assert f'data-year="{record}"' in html


def test_landing_raw_html_never_hides_content(dist):
    """Scroll-reveal must be JS-applied only: no hiding class in the built HTML,
    so no-JS visitors (and crawlers) always get the full page."""
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="reveal"' not in html
    assert "reveal-in" not in html


def test_podigami_js_motion_is_progressive_enhancement(repo):
    js = (repo / "assets" / "podigami.js").read_text(encoding="utf-8")
    # timeline easing + count-up + scroll-reveal each honour reduced motion
    assert js.count("prefers-reduced-motion") >= 3
    assert js.count("IntersectionObserver") >= 2  # count-up + reveal guard on support


@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_has_mobile_nav_drawer(dist, page):
    """Mobile nav: burger + checkbox toggle + scrim + left drawer with all pages."""
    html = (dist / page).read_text(encoding="utf-8")
    assert 'id="nav-drawer-toggle"' in html, f"{page} missing drawer toggle"
    assert 'class="nav-burger"' in html, f"{page} missing burger"
    assert 'class="nav-scrim"' in html, f"{page} missing scrim"
    drawer = html[html.index('<aside class="nav-drawer"') : html.index("</aside>")]
    for href in ALL_PAGES:
        assert f'href="{href}"' in drawer, f"{page} drawer missing link to {href}"


def _json_ld_blocks(html: str) -> list[dict]:
    """All parsed <script type="application/ld+json"> payloads in a page."""
    return [
        json.loads(m)
        for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    ]


def test_index_canonical_is_site_root(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{SITE_URL}/">' in html
    assert f'<meta property="og:url" content="{SITE_URL}/">' in html
    assert f'href="{SITE_URL}/index.html"' not in html


def test_subpage_canonical_keeps_page_url(dist):
    html = (dist / "combos.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{SITE_URL}/combos.html">' in html


def test_index_json_ld_website(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    websites = [b for b in _json_ld_blocks(html) if b.get("@type") == "WebSite"]
    assert len(websites) == 1, "index.html should carry exactly one WebSite schema"
    site = websites[0]
    assert site["@context"] == "https://schema.org"
    assert site["name"] == "F1 Podigami"
    assert site["url"] == f"{SITE_URL}/"
    assert site["description"]


def test_index_json_ld_next_race_event(dist, data):
    from build.build_podigami_html import pick_next_race

    html = (dist / "index.html").read_text(encoding="utf-8")
    events = [b for b in _json_ld_blocks(html) if b.get("@type") == "SportsEvent"]
    nxt = pick_next_race(data["schedule"], data["podigami"].get("asOf"))
    if nxt is None:
        assert events == [], "no upcoming race -> no SportsEvent schema"
        return
    assert len(events) == 1, "index.html should carry exactly one SportsEvent schema"
    event = events[0]
    assert event["name"] == nxt["raceName"]
    assert event["startDate"].startswith(nxt["date"])
    assert event["location"]["@type"] == "Place"
    assert event["location"]["name"] == nxt["circuitName"]
    assert event["location"]["address"]["addressCountry"] == nxt["country"]


def test_404_is_noindex(dist):
    html = (dist / "404.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex">' in html
    index = (dist / "index.html").read_text(encoding="utf-8")
    assert 'name="robots"' not in index


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_dead_keywords_meta(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    assert 'name="keywords"' not in html, f"{page} still emits the dead keywords meta"


@pytest.mark.parametrize("page", ALL_PAGES)
def test_og_locale_and_image_alt(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    assert '<meta property="og:locale" content="en_US">' in html
    assert '<meta property="og:image:alt" content="' in html


def test_sitemap_homepage_is_root_url(dist):
    sitemap = (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<loc>{SITE_URL}/</loc>" in sitemap
    assert f"<loc>{SITE_URL}/index.html</loc>" not in sitemap
    for page in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f"<loc>{SITE_URL}/{page}</loc>" in sitemap


def test_drawer_marks_active_page(dist):
    html = (dist / "combos.html").read_text(encoding="utf-8")
    drawer = html[html.index('<aside class="nav-drawer"') : html.index("</aside>")]
    assert 'href="combos.html" class="active"' in drawer, "drawer should highlight the current page"
