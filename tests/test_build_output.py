"""Output / HTML validation: the built site is complete and well-formed."""

import html as _html
import json
import re

import pytest

SITE_URL = "https://nikokiru.github.io/f1podigami"

# page -> assets it must reference (and which must end up in dist/)
PAGES = {
    "index.html": ["podigami.css", "podigami.js", "theme.js"],
    "combos.html": ["index.css", "index.js", "theme.js"],
    "overdue.html": ["podigami.css", "theme.js"],
    "soulmates.html": ["podigami.css", "theme.js"],
}

ALL_ASSETS = [
    "style.css",
    "index.css",
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
    # style.css is linked with a cache-busting ?v= token
    assert '<link rel="stylesheet" href="style.css?v=' in html


# page -> a keyword phrase its <title> must front-load
TITLE_KEYWORDS = {
    "index.html": "F1 Podium Scorigami",
    "combos.html": "F1 Podium Combination",
    "overdue.html": "F1 Overdue Podiums",
    "unlikeliest.html": "F1 Unlikeliest Podiums",
    "soulmates.html": "F1 Podium Partnerships",
}


@pytest.mark.parametrize("page,keyword", TITLE_KEYWORDS.items())
def test_title_front_loads_keyword(dist, page, keyword):
    html = (dist / page).read_text(encoding="utf-8")
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    assert m, f"{page} has no <title>"
    title = m.group(1)
    assert keyword in title, f"{page} title missing keyword {keyword!r}: {title!r}"
    assert len(title) <= 65, f"{page} title too long ({len(title)}): {title!r}"


@pytest.mark.parametrize("page", ["index.html", "combos.html"])
def test_description_within_budget(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    m = re.search(r'<meta name="description" content="(.*?)">', html, re.DOTALL)
    assert m, f"{page} has no meta description"
    assert len(m.group(1)) <= 160, f"{page} description too long: {len(m.group(1))}"


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


def test_combos_season_filter_controls(dist):
    """Both season controls ship: the widescreen dual-handle slider and the
    mobile From/To selects, over the real span of seasons on the page."""
    html = (dist / "combos.html").read_text(encoding="utf-8")
    assert 'class="season-range" data-min="1950"' in html
    assert 'id="season-from"' in html and 'id="season-to"' in html
    assert 'id="season-from-sel"' in html and 'id="season-to-sel"' in html
    assert 'id="season-readout"' in html
    assert 'id="range-note"' in html


def test_combos_filters_live_in_a_toggleable_panel(dist):
    """On mobile the filters sit in a slide-out panel; the markup that makes
    that possible (checkbox core, scrim, trigger, panel wrapping .filters)
    must ship on every build."""
    html = (dist / "combos.html").read_text(encoding="utf-8")
    assert '<input type="checkbox" id="filter-toggle" class="fp-toggle">' in html
    assert 'class="fp-scrim"' in html
    assert 'class="filter-toggle"' in html and 'aria-controls="filter-panel"' in html
    assert 'id="filter-count"' in html and 'id="filter-done"' in html

    panel = html.index('<div class="filter-panel"')
    controls_bar = html.index('<div class="controls-bar">')
    assert panel < html.index('<div class="filters">') < controls_bar, (
        "the filters must be inside the panel, which precedes the trigger bar"
    )


def test_combos_rows_carry_race_seasons(dist):
    """Every combo row exposes its races to the season filter, and those
    seasons match the season rows rendered in its expanded detail."""
    import re

    html = (dist / "combos.html").read_text(encoding="utf-8")
    rows = re.findall(r'<tr class="combo"[^>]*data-races="([^"]*)"[^>]*>', html)
    assert len(rows) > 700, "every combo row should carry data-races"

    # data-races entries are season|round|raceName, and their count matches
    # the row's data-count.
    counts = re.findall(r'<tr class="combo" data-count="(\d+)"', html)
    assert len(counts) == len(rows)
    for races, count in zip(rows[:50], counts[:50], strict=True):
        entries = races.split(";")
        assert len(entries) == int(count)
        for entry in entries:
            season, rnd, _name = entry.split("|", 2)
            assert season.isdigit() and rnd.isdigit()


def test_combos_shared_drive_marker_counts(dist):
    """Locks the shared-drive badge/pill counts so a regression in the shared
    map or trio expansion is caught in CI rather than a manual grep."""
    html = (dist / "combos.html").read_text(encoding="utf-8")
    assert html.count("shared-badge") == 40
    assert html.count("race-pill-shared") == 42


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
    assert 'class="cd-code"' in html  # candidate-row TLA codes
    assert 'class="tr-num"' in html  # car-number chips


def test_landing_page_has_faq_section(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert "faq-section" in html  # dedicated FAQ section
    assert "Frequently asked questions" in html
    assert 'class="faq-item"' in html  # expandable items
    assert "top three" in html  # backtest hit rate, stated in the hero's footing line


def test_landing_page_has_info_tooltips(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="info-tip"' in html  # "i" info affordance
    assert 'class="info-bubble"' in html  # hover/focus explanation


def test_landing_page_has_next_race_box(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="next-race"' in html
    assert "data-datetime=" in html  # countdown/local-time hook
    assert 'class="nr-track"' in html  # circuit outline SVG


def test_post_quali_hero_state_matches_data(dist, data):
    """The rendered hero must mirror the committed postQuali state exactly —
    conditional on the data so the update job's pytest run stays green whether
    the block is live or null (the #178 stall-class guardrail).

    Keyed on ``live_post_quali``, not the raw key: a block whose race has already
    run is deliberately not rendered."""
    from build.build_podigami_html import live_post_quali

    html_text = (dist / "index.html").read_text(encoding="utf-8")
    if live_post_quali(data["podigami"]):
        assert "hc-updated" in html_text
        assert "cd-grid" in html_text
    else:
        assert "hc-updated" not in html_text
        assert "cd-grid" not in html_text


def test_display_name_uppercases_surname_only():
    from build.build_podigami_html import display_name

    assert display_name("Max Verstappen") == "Max VERSTAPPEN"
    assert display_name("Juan Pablo Montoya") == "Juan Pablo MONTOYA"
    assert display_name("Kimi Räikkönen") == "Kimi RÄIKKÖNEN"  # unicode-safe
    assert display_name("") == ""


def test_antonelli_is_kimi_antonelli_on_every_page(dist):
    """F1 and Mercedes call him Kimi Antonelli; the API still says "Andrea Kimi".

    data/ keeps the API's spelling, so every page has to render names through
    ``driver_name``. This catches any path that skips it — including the
    lowercased search keys, the ``?d=`` filter links and the timeline's JSON.
    """
    api_form = re.compile(r"andrea[\s+]kimi|\bA\. Antonelli", re.IGNORECASE)
    for page in sorted(dist.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        assert not api_form.search(text), f"{page.name} still shows 'Andrea Kimi Antonelli'"
    # He has podiums, so the combinations table always lists him.
    assert "Kimi Antonelli" in (dist / "combos.html").read_text(encoding="utf-8")


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
    assert html.index('class="form-tower"') < html.index('class="hook-card" href="combos.html"')
    assert html.index('id="tl-slider"') < html.index('class="hook-card" href="overdue.html"')
    assert 'class="hook-row"' in html  # overdue + unlikeliest side by side


def test_landing_page_form_is_collapsed_in_candidates_panel(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    # no standalone "Current form" panel heading anymore
    assert "<h2>Current form" not in html
    # the tower sits in a collapsed <details> inside the candidates panel
    assert '<details class="form-details">' in html
    assert '<details class="form-details" open' not in html
    assert "Show current form" in html
    details = html[html.index('<details class="form-details">') :]
    assert details.index('class="form-tower"') < details.index("</details>")
    panel_start = html.index("Most likely trios")
    assert panel_start < html.index('<details class="form-details">')


def test_landing_trio_board_marks_happened_and_new(dist):
    """The board's whole point: a visitor can tell an already-happened trio from
    one the model simply rates too low to list."""
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert "Most likely trios" in html
    assert 'class="cand cand-done"' in html
    assert 'class="cand cand-new"' in html
    assert "cand-pill" in html
    # done rows carry their history behind a hover/tap bubble
    assert 'class="trio-tip"' in html
    assert "trio-bubble" in html
    assert "Happened" in html
    # the list scrolls inside a fixed window rather than running the page long
    assert 'class="cand-scroll"' in html


def test_landing_trio_board_bubbles_link_to_combos(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    board = html[html.index('class="cand-scroll"') : html.index("form-details")]
    assert "combos.html?d=" in board


def test_landing_trio_board_new_rows_have_no_bubble(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    board = html[html.index('class="cand-scroll"') : html.index("form-details")]
    for row in board.split('<li class="cand')[1:]:
        if "cand-new" in row[:20]:
            assert "trio-tip" not in row, "a never-happened row has nothing to reveal"


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


def test_overdue_has_two_ranked_tables(dist):
    html = (dist / "overdue.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert html.count('class="rank-wrap"') == 2  # all-time + current grid
    assert html.count('<span class="rh-num">Expected co-podiums</span>') == 2
    assert "All-time near-misses" in html
    assert 'class="oddriver"' in html


def test_unlikeliest_has_ranked_table(dist):
    html = (dist / "unlikeliest.html").read_text(encoding="utf-8")
    assert html.count('class="rank-wrap"') == 1
    assert html.count("rankrow-hero") == 1  # the #1 trio, marked by an accent rail
    assert "<details open>" not in html  # every row starts closed, #1 included
    assert 'class="rankrow"' in html
    assert 'class="rr-stat rr-stat-race"' in html  # race repeats in the row drawer


def test_ranked_pages_share_one_table_component(dist):
    """The three ranked pages must render through the same component as each
    other (and read like the combinations table) — no per-page hero cards."""
    for name in ("overdue.html", "unlikeliest.html", "soulmates.html"):
        html = (dist / name).read_text(encoding="utf-8")
        assert 'class="rank-wrap"' in html, name
        assert 'class="rank-head"' in html, name
        assert 'class="rank-list"' in html, name
        # the retired bespoke hero cards must not come back
        for dead in ("odcard", "uncard", "smcard", "od-stat", "un-stat", "sm-stat"):
            assert dead not in html, f"{name} still emits .{dead}"


def test_soulmates_uses_shared_ranked_layout(dist):
    """Soulmates must share the site's ranked-table chrome rather than its old
    bespoke bar-chart list."""
    html = (dist / "soulmates.html").read_text(encoding="utf-8")
    assert 'class="nav"' in html
    assert 'class="rank-section"' in html  # naked heading, no panel box
    assert html.count('class="rank-wrap"') == 1
    assert '<span class="rh-num">Shared podiums</span>' in html
    assert html.count("rankrow-hero") == 1  # the #1 duo, marked by an accent rail
    assert 'class="rankrow"' in html  # the rest are shared leaderboard rows
    assert 'class="fact-card"' in html  # did-you-know cards retained
    # the old bespoke layout is gone
    assert 'class="sm-page"' not in html
    assert 'class="pl-list"' not in html
    assert 'class="fact-stack"' not in html


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


@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_has_organization_schema(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    orgs = [b for b in _json_ld_blocks(html) if b.get("@type") == "Organization"]
    assert len(orgs) == 1, f"{page} should carry exactly one Organization schema"
    assert orgs[0]["name"] == "F1 Podigami"
    assert orgs[0]["logo"].endswith("apple-touch-icon.png")


SUBPAGE_BREADCRUMB = {
    "combos.html": "Podium Combinations",
    "overdue.html": "Overdue Podiums",
    "unlikeliest.html": "Unlikeliest Podiums",
    "soulmates.html": "Podium Partnerships",
}


@pytest.mark.parametrize("page,label", SUBPAGE_BREADCRUMB.items())
def test_subpages_have_breadcrumb(dist, page, label):
    html = (dist / page).read_text(encoding="utf-8")
    crumbs = [b for b in _json_ld_blocks(html) if b.get("@type") == "BreadcrumbList"]
    assert len(crumbs) == 1, f"{page} should carry one BreadcrumbList"
    items = crumbs[0]["itemListElement"]
    assert items[0]["name"] == "Home"
    assert items[-1]["name"] == label
    assert items[-1]["item"] == f"{SITE_URL}/{page}"


def test_index_faqpage_schema_matches_visible_faq(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    faqs = [b for b in _json_ld_blocks(html) if b.get("@type") == "FAQPage"]
    assert len(faqs) == 1, "index.html should carry exactly one FAQPage schema"
    q_entities = faqs[0]["mainEntity"]
    assert len(q_entities) >= 5
    for qe in q_entities:
        assert qe["@type"] == "Question"
        assert qe["name"]  # question text
        assert qe["acceptedAnswer"]["@type"] == "Answer"
        assert qe["acceptedAnswer"]["text"]
        # schema answer is plain text (no HTML tags leaked in)
        assert "<" not in qe["acceptedAnswer"]["text"]
    # Parity: each schema question is a visible FAQ <summary> on the page. The
    # schema name is plain text (entities unescaped), so compare against the
    # unescaped page rather than the raw &ldquo;-carrying HTML.
    page_plain = _html.unescape(html)
    for qe in q_entities:
        assert f'<summary class="faq-q">{qe["name"]}</summary>' in page_plain


def test_combos_dataset_schema(dist):
    html = (dist / "combos.html").read_text(encoding="utf-8")
    datasets = [b for b in _json_ld_blocks(html) if b.get("@type") == "Dataset"]
    assert len(datasets) == 1, "combos.html should carry exactly one Dataset schema"
    ds = datasets[0]
    assert "podium combination" in ds["name"].lower()
    assert ds["url"] == f"{SITE_URL}/combos.html"
    assert ds["creator"]["@type"] == "Organization"
    assert ds["license"]
    assert "/" in ds["temporalCoverage"]  # e.g. "1950/2026"
    assert isinstance(ds["keywords"], list) and ds["keywords"]


def test_index_sportsevent_enriched(dist, data):
    from build.build_podigami_html import pick_next_race

    html = (dist / "index.html").read_text(encoding="utf-8")
    nxt = pick_next_race(data["schedule"], data["podigami"].get("asOf"))
    events = [b for b in _json_ld_blocks(html) if b.get("@type") == "SportsEvent"]
    if nxt is None:
        assert events == []
        return
    ev = events[0]
    assert ev["sport"] == "Formula 1"
    assert ev["eventStatus"] == "https://schema.org/EventScheduled"
    assert ev["url"] == f"{SITE_URL}/"


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
