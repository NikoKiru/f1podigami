"""Playwright e2e suite for interactive JS: slider, combos filter/sort, theme, tooltips.

Requires Playwright + Chromium. In CI this runs in the dedicated e2e job.
On a dev machine without Playwright installed the tests are skipped gracefully.
"""

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402


def _url(dist, filename, query=""):
    return (dist / filename).resolve().as_uri() + query


# ── Timeline slider + sparkline bars (podigami.js) ─────────────────────────


def test_sparkline_click_updates_year(dist):
    """Clicking a sparkline bar updates #tl-year and marks the bar .on."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 1600})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector("#tl-slider")

        page.locator(".tl-bar[data-season='1980']").click()

        assert page.text_content("#tl-year") == "1980"
        assert page.locator(".tl-bar.on").get_attribute("data-season") == "1980"
        browser.close()


def test_slider_input_updates_year_and_count(dist):
    """Setting the slider to 1950 via input event updates the year readout."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 1600})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector("#tl-slider")

        page.locator("#tl-slider").evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('input')); }",
            "1950",
        )
        page.wait_for_function("document.getElementById('tl-year').textContent === '1950'")

        assert page.text_content("#tl-year") == "1950"
        count = page.text_content("#tl-count")
        assert count and len(count) > 0
        browser.close()


# ── Trio names on phones (index.css, podigami.css, podigami.js) ────────────


@pytest.mark.parametrize(
    ("page_name", "group", "driver"),
    [
        ("combos.html", "tbody tr.combo td.drivers", ".driver"),
        ("overdue.html", ".rr-drivers", ".oddriver"),
        ("unlikeliest.html", ".rr-drivers", ".undriver"),
        ("index.html", ".tl-item .trio", ".pdriver"),
    ],
)
def test_trios_stack_one_whole_name_per_line_on_phones(dist, page_name, group, driver):
    """On a phone every trio is three lines, one name apiece: a name never
    splits ("M." above "Verstappen") and never shares a line with another."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 360, "height": 800})
        page.goto(_url(dist, page_name))
        page.wait_for_selector(f"{group} {driver}")
        bad = page.evaluate(
            """([group, driver]) => {
                const bad = [];
                for (const g of document.querySelectorAll(group)) {
                    const tops = [];
                    for (const d of g.querySelectorAll(driver)) {
                        const name = d.querySelector('.dn-abbr') || d;
                        const r = document.createRange();
                        r.selectNodeContents(name.firstChild);
                        const lines = r.getClientRects();
                        if (lines.length !== 1) bad.push('split: ' + name.textContent);
                        else tops.push(lines[0].top);
                    }
                    if (tops.some((t, i) => i && t <= tops[i - 1])) {
                        bad.push('shared line: ' + g.textContent);
                    }
                }
                return bad.slice(0, 5);
            }""",
            [group, driver],
        )
        browser.close()
    assert bad == []


# ── Info-tip tooltips (podigami.js) ────────────────────────────────────────


def test_info_tip_tap_toggles(dist):
    """Tapping an info-tip opens it; a second tap closes it."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 400, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".info-tip")

        tip = page.locator(".info-tip").first
        assert not tip.evaluate("el => el.classList.contains('open')")

        tip.click()
        assert tip.evaluate("el => el.classList.contains('open')")
        assert tip.get_attribute("aria-expanded") == "true"

        tip.click()
        assert not tip.evaluate("el => el.classList.contains('open')")
        assert tip.get_attribute("aria-expanded") == "false"
        browser.close()


def test_info_tip_outside_tap_dismisses(dist):
    """A document-level click outside the tip removes .open from it."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 400, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".info-tip")

        tip = page.locator(".info-tip").first
        tip.click()
        assert tip.evaluate("el => el.classList.contains('open')")

        # Dispatch directly on document — bubbles past any stopPropagation on the tip.
        page.evaluate(
            "document.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}))"
        )
        assert not tip.evaluate("el => el.classList.contains('open')")
        browser.close()


def test_info_tip_escape_dismisses(dist):
    """Pressing Escape closes an open tooltip."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 400, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".info-tip")

        tip = page.locator(".info-tip").first
        tip.click()
        assert tip.evaluate("el => el.classList.contains('open')")

        page.keyboard.press("Escape")
        assert not tip.evaluate("el => el.classList.contains('open')")
        browser.close()


# ── Next-race countdown (podigami.js) ──────────────────────────────────────


def test_next_race_shows_local_time(dist):
    """The .nr-date element contains '(your time)' after the JS rewrites it."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.goto(_url(dist, "index.html"))

        if not page.locator(".next-race[data-datetime]").count():
            pytest.skip("no next-race box in this build")
        if not page.locator(".nr-date").count():
            pytest.skip("no .nr-date element")

        assert "your time" in (page.locator(".nr-date").text_content() or "")
        browser.close()


def test_next_race_localises_qualifying_too(dist):
    """Qualifying joins the race on one line and is converted out of UTC.

    The race time was always localised; qualifying used to ship as a separate
    UTC-only line, leaving two different clocks in one card.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.goto(_url(dist, "index.html"))

        if not page.locator(".next-race[data-quali-datetime]").count():
            pytest.skip("next race has no qualifying entry in this build")

        when = page.locator(".nr-date").text_content() or ""
        assert "Quali" in when
        assert "your time" in when
        assert "UTC" not in when
        browser.close()


def test_next_race_countdown_ticks(dist):
    """The countdown value changes after ~1 s when the race is upcoming."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.goto(_url(dist, "index.html"))

        if not page.locator(".nr-countdown").count():
            pytest.skip("no .nr-countdown element")

        first = page.locator(".nr-countdown").text_content() or ""
        # The ticking format always contains 'h ' and 'm ' (e.g. "6d 12h 34m 56s").
        # Static messages ("Lights out — race underway", "Awaiting results") do not.
        if "h " not in first or "m " not in first:
            pytest.skip("race not upcoming — countdown shows a static message")

        page.wait_for_timeout(1200)
        second = page.locator(".nr-countdown").text_content() or ""
        assert first != second
        browser.close()


# ── Combos filter (index.js) ───────────────────────────────────────────────


def test_combos_filter_hides_non_matching_rows(dist):
    """Typing a driver name hides rows that don't include that driver."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        total = int(page.text_content("#total-count") or "0")
        page.locator(".filters input[data-filter]").first.fill("hamilton")

        visible = int(page.text_content("#visible-count") or "0")
        assert 0 < visible < total

        all_match = page.evaluate(
            """() =>
            Array.from(document.querySelectorAll('tr.combo'))
                .filter(r => r.style.display !== 'none')
                .every(r => r.dataset.drivers.includes('hamilton'))
            """
        )
        assert all_match
        browser.close()


def test_combos_filter_two_distinct_drivers(dist):
    """Two filter inputs with distinct names narrows results to their shared rows."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        inputs = page.locator(".filters input[data-filter]")
        inputs.nth(0).fill("hamilton")
        inputs.nth(1).fill("verstappen")

        visible = int(page.text_content("#visible-count") or "0")
        assert visible > 0

        all_match = page.evaluate(
            """() =>
            Array.from(document.querySelectorAll('tr.combo'))
                .filter(r => r.style.display !== 'none')
                .every(r =>
                    r.dataset.drivers.includes('hamilton') &&
                    r.dataset.drivers.includes('verstappen')
                )
            """
        )
        assert all_match
        browser.close()


def test_combos_deep_link_prefills_filters(dist):
    """?d=Name query params pre-fill the filter inputs and narrow the table."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html", "?d=Hamilton&d=Verstappen"))
        page.wait_for_selector("tr.combo")

        inputs = page.locator(".filters input[data-filter]")
        assert inputs.nth(0).input_value() == "Hamilton"
        assert inputs.nth(1).input_value() == "Verstappen"

        visible = int(page.text_content("#visible-count") or "0")
        assert visible > 0
        browser.close()


# ── Combos filter panel (index.js) ─────────────────────────────────────────


def test_combos_filter_panel_opens_and_closes_on_mobile(dist):
    """On a phone the filters are off-canvas until the trigger is tapped, and
    the "Show N trios" button puts them away again."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 400, "height": 800})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        panel = page.locator("#filter-panel")
        toggle = page.locator(".filter-toggle")
        assert toggle.is_visible()
        assert panel.bounding_box()["x"] >= 400, "panel should start off-canvas"

        toggle.click()
        page.wait_for_function(
            "document.querySelector('#filter-panel').getBoundingClientRect().right <= 400"
        )
        assert toggle.get_attribute("aria-expanded") == "true"
        assert page.evaluate("document.documentElement.classList.contains('drawer-open')")

        page.locator(".fp-done").click()
        page.wait_for_function(
            "document.querySelector('#filter-panel').getBoundingClientRect().x >= 400"
        )
        assert toggle.get_attribute("aria-expanded") == "false"
        assert not page.evaluate("document.documentElement.classList.contains('drawer-open')")
        browser.close()


def test_combos_filter_panel_reports_active_filters(dist):
    """The trigger badge counts the filters in force, and the panel's button
    counts the rows they leave — both while the panel is shut."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 400, "height": 800})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        toggle = page.locator(".filter-toggle")
        assert not toggle.evaluate("el => el.classList.contains('has-active')")

        page.locator(".filter-toggle").click()
        page.locator(".filters input[data-filter]").first.fill("hamilton")
        page.locator("#season-from-sel").select_option("2015")

        # one driver box + a narrowed season range
        assert page.text_content("#filter-count") == "2"
        assert toggle.evaluate("el => el.classList.contains('has-active')")
        visible = page.text_content("#visible-count")
        assert page.text_content(".fp-done") == f"Show {visible} trios"
        browser.close()


def test_combos_filter_panel_is_inline_on_desktop(dist):
    """Widescreen keeps the filters in the flow above the table — no trigger,
    no drawer."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        assert not page.locator(".filter-toggle").is_visible()
        assert page.locator(".filters").is_visible()
        assert page.eval_on_selector("#filter-panel", "el => getComputedStyle(el).position") == (
            "static"
        )
        browser.close()


# ── Combos season range (index.js) ─────────────────────────────────────────


def _set_range(page, lo, hi):
    """Drive the widescreen slider the way a drag would."""
    page.evaluate(
        """([lo, hi]) => {
            const to = document.getElementById('season-to');
            const from = document.getElementById('season-from');
            to.value = hi; to.dispatchEvent(new Event('input'));
            from.value = lo; from.dispatchEvent(new Event('input'));
        }""",
        [str(lo), str(hi)],
    )


def test_season_range_keeps_only_trios_that_raced_in_it(dist):
    """A narrowed window hides every trio without a podium inside it."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        total = int(page.text_content("#visible-count") or "0")
        _set_range(page, 2001, 2003)
        visible = int(page.text_content("#visible-count") or "0")
        assert 0 < visible < total

        every_row_raced_in_window = page.evaluate(
            """() =>
            Array.from(document.querySelectorAll('tr.combo'))
                .filter(r => r.style.display !== 'none')
                .every(r => r.dataset.races.split(';').some(e => {
                    const y = Number(e.split('|')[0]);
                    return y >= 2001 && y <= 2003;
                }))
            """
        )
        assert every_row_raced_in_window
        assert page.text_content("#season-readout") == "2001 – 2003"
        browser.close()


def test_season_range_recomputes_count_and_last_seen(dist):
    """Count and Last seen describe the window, not the trio's whole life."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        _set_range(page, 2001, 2003)

        agrees = page.evaluate(
            """() =>
            Array.from(document.querySelectorAll('tr.combo'))
                .filter(r => r.style.display !== 'none')
                .every(r => {
                    const inRange = r.dataset.races.split(';')
                        .map(e => e.split('|'))
                        .filter(e => Number(e[0]) >= 2001 && Number(e[0]) <= 2003);
                    const shownCount = Number(r.querySelector('.count').textContent);
                    const shownYear = r.querySelector('.last .year').textContent;
                    const latest = inRange.reduce((a, b) =>
                        Number(a[0]) * 1000 + Number(a[1]) >= Number(b[0]) * 1000 + Number(b[1]) ? a : b);
                    return shownCount === inRange.length && shownYear === latest[0];
                })
            """
        )
        assert agrees
        browser.close()


def test_season_range_restores_lifetime_figures(dist):
    """Widening back to the full span puts the all-time numbers back."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        def counts():
            return page.evaluate(
                "() => Array.from(document.querySelectorAll('tr.combo'))"
                ".map(r => r.dataset.drivers + ':' + r.querySelector('.count').textContent)"
                ".sort().join()"
            )

        before = counts()
        _set_range(page, 2001, 2003)
        _set_range(page, 1950, 2026)

        assert counts() == before
        assert page.text_content("#season-readout") == "All seasons"
        browser.close()


def test_season_range_hides_out_of_window_pills(dist):
    """The expanded detail shows only the seasons the window covers, so the
    pills add up to the Count beside them."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        _set_range(page, 2001, 2003)
        consistent = page.evaluate(
            """() => {
                const row = Array.from(document.querySelectorAll('tr.combo'))
                    .find(r => r.style.display !== 'none');
                const detail = row.nextElementSibling;
                const shown = Array.from(detail.querySelectorAll('.season-row'))
                    .filter(sr => sr.style.display !== 'none');
                const seasons = shown.map(sr => Number(sr.dataset.season));
                const pills = shown.reduce(
                    (n, sr) => n + sr.querySelectorAll('.race-pill').length, 0);
                return seasons.every(y => y >= 2001 && y <= 2003)
                    && pills === Number(row.querySelector('.count').textContent);
            }"""
        )
        assert consistent
        browser.close()


def test_season_range_handles_do_not_cross(dist):
    """Dragging "from" past "to" stops it at "to" rather than inverting."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        _set_range(page, 1990, 2000)
        page.evaluate(
            """() => {
                const from = document.getElementById('season-from');
                from.value = '2020'; from.dispatchEvent(new Event('input'));
            }"""
        )
        assert page.input_value("#season-from") == "2000"
        assert page.input_value("#season-to") == "2000"
        browser.close()


def test_season_selects_mirror_the_slider(dist):
    """On mobile the From/To selects drive the same state, and push past each
    other rather than clamping."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        assert page.locator("#season-from-sel").is_visible()
        assert not page.locator("#season-from").is_visible()

        page.select_option("#season-from-sel", "2010")
        page.select_option("#season-to-sel", "2012")
        assert page.input_value("#season-from") == "2010"
        assert page.input_value("#season-to") == "2012"

        # picking a From beyond the current To pushes To along
        page.select_option("#season-from-sel", "2015")
        assert page.input_value("#season-to-sel") == "2015"
        browser.close()


def test_season_range_deep_link(dist):
    """?from=&to= pre-sets the window on load."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html", "?from=2001&to=2003"))
        page.wait_for_selector("tr.combo")

        assert page.input_value("#season-from") == "2001"
        assert page.input_value("#season-to") == "2003"
        assert page.text_content("#season-readout") == "2001 – 2003"
        assert "from 2001–2003" in (page.text_content("#range-note") or "")

        total = int(page.text_content("#total-count") or "0")
        visible = int(page.text_content("#visible-count") or "0")
        assert 0 < visible < total
        browser.close()


def test_season_range_deep_link_swaps_reversed_bounds(dist):
    """A reversed ?from/?to is read as the window it describes."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html", "?from=2003&to=2001"))
        page.wait_for_selector("tr.combo")

        assert page.input_value("#season-from") == "2001"
        assert page.input_value("#season-to") == "2003"
        browser.close()


def test_clear_button_resets_the_season_range(dist):
    """Clear is enabled by a narrowed window alone, and resets it."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        total = int(page.text_content("#total-count") or "0")
        assert page.locator("#clear-filters").is_disabled()
        _set_range(page, 2001, 2003)
        assert page.locator("#clear-filters").is_enabled()

        page.locator("#clear-filters").click()
        assert page.input_value("#season-from") == "1950"
        assert page.input_value("#season-to") == "2026"
        assert page.text_content("#season-readout") == "All seasons"
        assert int(page.text_content("#visible-count") or "0") == total
        browser.close()


def test_season_range_combines_with_driver_filter(dist):
    """The two filters intersect rather than replacing one another."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        page.locator(".filters input[data-filter]").first.fill("schumacher")
        with_driver = int(page.text_content("#visible-count") or "0")
        _set_range(page, 2001, 2003)
        both = int(page.text_content("#visible-count") or "0")
        assert 0 < both < with_driver

        all_match = page.evaluate(
            """() =>
            Array.from(document.querySelectorAll('tr.combo'))
                .filter(r => r.style.display !== 'none')
                .every(r => r.dataset.drivers.includes('schumacher')
                    && r.dataset.races.split(';').some(e => {
                        const y = Number(e.split('|')[0]);
                        return y >= 2001 && y <= 2003;
                    }))
            """
        )
        assert all_match
        browser.close()


def test_clear_button_drops_the_driver_deep_link(dist):
    """Clear empties the URL too, so a reload can't put the filter back.

    A visitor arriving from a trio link elsewhere on the site lands with ?d=
    names in the URL. Clearing has to retract those as well as the inputs —
    otherwise the table shows everything while the address bar still says it is
    filtered, and the next reload silently re-applies it.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html", "?d=Max+Verstappen&d=George+Russell"))
        # attached, not visible: the deep link hides the first row on arrival.
        page.wait_for_selector("tr.combo", state="attached")

        total = int(page.text_content("#total-count") or "0")
        assert page.input_value(".filters input[data-filter] >> nth=0") == "Max Verstappen"
        filtered = int(page.text_content("#visible-count") or "0")
        assert 0 < filtered < total

        page.locator("#clear-filters").click()

        assert page.evaluate("() => location.search") == ""
        assert int(page.text_content("#visible-count") or "0") == total
        browser.close()


def test_driver_filter_is_reflected_in_the_url(dist):
    """Typing a driver name makes the view shareable, the way ?from/?to already are."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        assert page.evaluate("() => location.search") == ""
        page.locator(".filters input[data-filter]").first.fill("hamilton")

        assert page.evaluate("() => new URLSearchParams(location.search).getAll('d')") == [
            "hamilton"
        ]
        browser.close()


# ── Combos sort (index.js) ─────────────────────────────────────────────────


def test_combos_active_column_click_toggles_direction(dist):
    """Clicking the already-active column header toggles its sort direction."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        th = page.locator("th[data-sort='count']")
        assert th.evaluate(
            "el => el.classList.contains('active') && el.classList.contains('dir-desc')"
        )

        th.click()
        assert th.evaluate(
            "el => el.classList.contains('active') && el.classList.contains('dir-asc')"
        )

        th.click()
        assert th.evaluate(
            "el => el.classList.contains('active') && el.classList.contains('dir-desc')"
        )
        browser.close()


def test_combos_clicking_new_column_makes_it_active(dist):
    """Clicking a non-active column sets it as the active sort and deactivates others."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_selector("tr.combo")

        page.locator("th[data-sort='drivers']").click()

        assert page.locator("th[data-sort='drivers']").evaluate(
            "el => el.classList.contains('active')"
        )
        assert not page.locator("th[data-sort='count']").evaluate(
            "el => el.classList.contains('active')"
        )
        browser.close()


# ── Theme toggle (theme.js) ────────────────────────────────────────────────


def test_theme_toggle_flips_data_theme(dist):
    """Clicking the theme button switches data-theme between 'dark' and 'light'."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector("#theme-toggle")

        initial = page.locator("html").get_attribute("data-theme")
        page.locator("#theme-toggle").click()
        after = page.locator("html").get_attribute("data-theme")
        assert after in ("light", "dark") and after != initial
        browser.close()


def test_theme_toggle_updates_theme_color_meta(dist):
    """Toggling the theme changes the theme-color <meta> content value."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector("#theme-toggle")

        before = page.locator("meta[name='theme-color']").get_attribute("content")
        page.locator("#theme-toggle").click()
        after = page.locator("meta[name='theme-color']").get_attribute("content")
        assert after != before
        browser.close()


def test_theme_persists_across_reload(dist):
    """Theme choice is stored in localStorage and survives a page reload."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1000, "height": 800})
        page = ctx.new_page()
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector("#theme-toggle")

        page.locator("#theme-toggle").click()
        toggled = page.locator("html").get_attribute("data-theme")

        page.reload()
        page.wait_for_selector("#theme-toggle")
        assert page.locator("html").get_attribute("data-theme") == toggled

        ctx.close()
        browser.close()


# ── Trio board history bubbles (podigami.js) ───────────────────────────────
# A hover-dismissed popover containing a link is fragile: the pointer has to
# travel to reach the link, and whatever hides the bubble races the click.


def _open_first_board_bubble(page):
    tip = page.locator(".trio-tip").first
    tip.scroll_into_view_if_needed()
    tip.hover()
    return tip


def test_trio_bubble_opens_on_hover(dist):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".trio-tip")

        tip = _open_first_board_bubble(page)
        assert tip.evaluate("el => el.classList.contains('open')")
        browser.close()


def test_trio_bubble_survives_pointer_travel_to_its_link(dist):
    """Regression: the bubble sat in a gap below the row that belonged to
    neither element, so moving the mouse toward "See all" fired mouseleave and
    closed it before the link could be reached."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".trio-tip")

        tip = _open_first_board_bubble(page)
        link = tip.locator(".trio-bubble a")
        box = link.bounding_box()
        # Walk the pointer down to the link the way a hand would, crossing the gap.
        start = tip.bounding_box()
        steps = 8
        for i in range(1, steps + 1):
            page.mouse.move(
                start["x"]
                + start["width"] / 2
                + (box["x"] + box["width"] / 2 - start["x"] - start["width"] / 2) * i / steps,
                start["y"]
                + start["height"] / 2
                + (box["y"] + box["height"] / 2 - start["y"] - start["height"] / 2) * i / steps,
            )
        assert tip.evaluate("el => el.classList.contains('open')"), (
            "bubble closed while the pointer travelled to its own link"
        )
        browser.close()


def test_trio_bubble_stays_flush_under_a_transformed_ancestor(dist):
    """The bubble is position:fixed, so any transformed ancestor becomes its
    containing block and its viewport coordinates land relative to that instead.

    The scroll-reveal transition (`.reveal.reveal-in` animates transform for
    0.5s) puts a transform on the enclosing panel, so hovering a row while its
    panel is still animating in used to drop the bubble hundreds of pixels below
    its row. Same trap as a mask-image or filter on any ancestor.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".trio-tip")

        # Hold the panel in the state the reveal transition passes through.
        page.evaluate(
            "() => { const t = document.querySelector('.trio-tip');"
            " t.closest('.panel').style.transform = 'translateY(12px)'; }"
        )
        tip = page.locator(".trio-tip").first
        tip.scroll_into_view_if_needed()
        tip.hover()

        gap = page.evaluate(
            """() => {
                const t = document.querySelector('.trio-tip.open');
                const b = t.querySelector('.trio-bubble').getBoundingClientRect();
                const a = t.getBoundingClientRect();
                // Flush below the row, or flush above it when flipped.
                return Math.min(Math.abs(b.top - a.bottom), Math.abs(b.bottom - a.top));
            }"""
        )
        assert gap < 2, f"bubble sits {gap:.0f}px from its row instead of flush against it"
        browser.close()


def test_trio_bubble_link_navigates_to_combos(dist):
    """Regression: the document-level close ran during the same click dispatch
    and hid the anchor, cancelling its navigation."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".trio-tip")

        tip = _open_first_board_bubble(page)
        tip.locator(".trio-bubble a").click()
        page.wait_for_url("**/combos.html*")
        assert "combos.html" in page.url
        assert "d=" in page.url
        browser.close()


def test_trio_bubble_opens_on_touch_tap(dist):
    """Regression: a tap synthesises mouseenter (which opened the bubble) before
    click (which toggled it shut), so the first tap appeared to do nothing."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".trio-tip")

        tip = page.locator(".trio-tip").first
        tip.scroll_into_view_if_needed()
        tip.tap()
        assert tip.evaluate("el => el.classList.contains('open')"), (
            "first tap left the bubble closed"
        )
        browser.close()


def test_trio_bubble_stays_tooltip_sized_on_a_phone(dist):
    """It read as a band across the list rather than a tooltip: 366px of a
    390px viewport."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".trio-tip")

        tip = page.locator(".trio-tip").first
        tip.scroll_into_view_if_needed()
        tip.tap()
        width = tip.evaluate("el => el.querySelector('.trio-bubble').getBoundingClientRect().width")
        assert width <= 320, f"bubble is {width}px wide on a 390px screen"
        # ...but still fully on screen
        rect = tip.evaluate(
            "el => { const r = el.querySelector('.trio-bubble').getBoundingClientRect();"
            " return {left: r.left, right: r.right}; }"
        )
        assert rect["left"] >= 0 and rect["right"] <= 390
        browser.close()
