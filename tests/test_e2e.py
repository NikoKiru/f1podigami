"""Playwright e2e suite for interactive JS: slider, combos filter/sort, theme, tooltips.

Requires Playwright + Chromium. In CI this runs in the dedicated e2e job.
On a dev machine without Playwright installed the tests are skipped gracefully.
"""

import re
from contextlib import contextmanager
from datetime import datetime, timedelta

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


# ── Next-race box (podigami.js) ────────────────────────────────────────────


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


def _race_start(page):
    """The next race's start as baked into the page, or skip when there is none."""
    box = page.locator(".next-race[data-datetime]")
    if not box.count():
        pytest.skip("no next-race box in this build")
    return datetime.fromisoformat(box.get_attribute("data-datetime").replace("Z", "+00:00"))


def test_next_race_shows_no_countdown(dist):
    """Before the race the card says when it is, and nothing ticks."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.clock.set_fixed_time(_race_start(page) - timedelta(days=1, hours=8))
        page.reload()

        assert page.locator(".nr-status").is_hidden()
        card = page.locator(".next-race").inner_text()
        assert "Lights out" not in card
        assert not re.search(r"\d+h \d+m", card), card
        browser.close()


@pytest.mark.parametrize(
    "hours_in, message",
    [(1, "Lights out — race underway"), (5, "Awaiting results")],
)
def test_next_race_says_so_once_the_race_has_started(dist, hours_in, message):
    """The box only rolls over when results land, which can take hours, so the
    date alone would describe a race already run as still to come."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.clock.set_fixed_time(_race_start(page) + timedelta(hours=hours_in))
        page.reload()

        assert page.locator(".nr-status").inner_text() == message
        browser.close()


def test_next_race_status_appears_on_a_page_left_open(dist):
    """Nobody reloads to find out the race has started."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.clock.install(time=_race_start(page) - timedelta(seconds=30))
        page.reload()
        assert page.locator(".nr-status").is_hidden()

        page.clock.run_for(2 * 60 * 1000)

        assert page.locator(".nr-status").inner_text() == "Lights out — race underway"
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


# ── Trio board scrollbar (podigami.css) ────────────────────────────────────


def test_trio_board_scrollbar_clears_the_percentages(dist):
    """The percentages sit flush right, and the native bar beside them touched
    the digits. Scrollbars have to be switched on for this: headless hides them
    by default, which would leave no bar to measure."""
    with sync_playwright() as p:
        browser = p.chromium.launch(ignore_default_args=["--hide-scrollbars"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".cand-prob")

        bar, gap = page.evaluate(
            """() => {
                const board = document.querySelector('.cand-scroll');
                const bar = board.offsetWidth - board.clientWidth;
                const text = document.createRange();
                text.selectNodeContents(document.querySelector('.cand-prob'));
                const barLeft = board.getBoundingClientRect().right - bar;
                return [bar, barLeft - text.getBoundingClientRect().right];
            }"""
        )
        browser.close()
    assert 0 < bar <= 6, f"expected the slim bar, got a {bar}px one"
    assert gap >= 8, f"the percentages sit {gap:.1f}px from the scrollbar"


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


# ── Compact layout ─────────────────────────────────────────────────────────

ALL_PAGES = [
    "index.html",
    "combos.html",
    "overdue.html",
    "unlikeliest.html",
    "soulmates.html",
    "404.html",
]


# Visitors get whichever font their OS has, and Segoe UI (Windows) is narrower than
# what Mac, Android and Linux render, so layouts that only just fit on one machine
# overflow on another. Letter-spacing widens text the same way on any platform.
WIDER_FONT = "* { letter-spacing: 0.05em !important; }"


@pytest.mark.parametrize("wider_font", [False, True], ids=["site-font", "wider-font"])
@pytest.mark.parametrize("width", [320, 390, 721, 768, 1024, 1280])
@pytest.mark.parametrize("page_name", ALL_PAGES)
def test_nothing_leaves_its_card_or_the_page(dist, page_name, width, wider_font):
    """Compact rows put more side by side, and ``overflow-x: hidden`` on the
    page would silently cut off whatever no longer fits, so check the elements
    rather than the scroll width. The viewport alone isn't enough: a row can run
    past its card and over its neighbour while still ending on screen. Off-canvas
    drawers and popovers are meant to sit outside; tables scroll inside themselves."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.goto(_url(dist, page_name))
        page.wait_for_load_state("load")
        if wider_font:
            page.add_style_tag(content=WIDER_FONT)
        cut_off = page.evaluate(
            """() => {
                const skip = '.nav-drawer, .filter-panel, .fp-scrim, .nav-scrim, '
                    + '.info-bubble, .table-wrap';
                const cards = '.panel, .hero, .next-race, .last-race, .hook-card, '
                    + '.rank-wrap, .fact-card';
                const bad = [];
                for (const el of document.querySelectorAll('body *')) {
                    if (el.closest(skip)) continue;
                    const r = el.getBoundingClientRect();
                    if (!r.width) continue;
                    const card = el.parentElement.closest(cards);
                    const edge = card ? card.getBoundingClientRect().right : innerWidth;
                    if (r.right > Math.min(edge, innerWidth) + 0.5) {
                        bad.push(el.tagName + '.' + el.className + ' right=' + r.right);
                    }
                }
                return bad.slice(0, 5);
            }"""
        )
        browser.close()
    assert cut_off == []


@pytest.mark.parametrize("wider_font", [False, True], ids=["site-font", "wider-font"])
@pytest.mark.parametrize("width", [1024, 1280])
def test_combos_rows_stay_on_one_line_on_desktop(dist, width, wider_font):
    """A season range can make any race a trio ran the "Last seen" one, so every
    name has to fit, not only the lifetime ones. The trios are checked too: they
    give up the width the race column takes, which is why it only widens at 1024px."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.goto(_url(dist, "combos.html"))
        page.wait_for_load_state("load")
        if wider_font:
            page.add_style_tag(content=WIDER_FONT)
        result = page.evaluate(
            """() => {
                const rows = [...document.querySelectorAll('tr.combo')];
                const cell = rows[0].querySelector('td.last');
                const name = cell.querySelector('.race-name');
                const range = document.createRange();
                range.selectNodeContents(cell);
                const height = () => range.getBoundingClientRect().height;
                name.textContent = 'Monaco';
                const oneLine = height();
                const races = new Set(rows.flatMap(
                    r => r.dataset.races.split(';').map(race => race.split('|')[2])
                ));
                return {
                    races: races.size,
                    wrappedRaces: [...races].filter(race => {
                        name.textContent = race;
                        return height() > oneLine;
                    }),
                    wrappedTrios: rows.filter(r => new Set(
                        [...r.querySelectorAll('.driver')].map(
                            d => Math.round(d.getBoundingClientRect().top)
                        )
                    ).size > 1).map(r => r.dataset.drivers),
                };
            }"""
        )
        browser.close()
    assert result["races"] > 50
    assert result["wrappedRaces"] == []
    assert result["wrappedTrios"] == []


@pytest.mark.parametrize("width", [390, 1000, 1200, 1280])
def test_every_season_row_stays_inside_its_list(dist, width):
    """Each season has its own longest trio and race name, so one year fitting
    says nothing about the next. A row that outgrows its width must wrap between
    names rather than run over the column beside it."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900}, reduced_motion="reduce")
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".tl-item")
        page.add_style_tag(content=WIDER_FONT)
        result = page.evaluate(
            """async () => {
                const data = JSON.parse(document.getElementById('podigami-data').textContent);
                // The site's own control, whichever one this width shows.
                const select = document.getElementById('tl-select');
                const slider = document.getElementById('tl-slider');
                const pick = year => {
                    const el = select.offsetParent ? select : slider;
                    el.value = year;
                    el.dispatchEvent(new Event(el === select ? 'change' : 'input', {bubbles: true}));
                };
                // Renders are coalesced to one per animation frame.
                const frame = () => new Promise(
                    done => requestAnimationFrame(() => requestAnimationFrame(done))
                );
                let seen = 0;
                const bad = [];
                for (const year of Object.keys(data.bySeason)) {
                    pick(year);
                    await frame();
                    for (const item of document.querySelectorAll('.tl-item')) {
                        seen += 1;
                        const edge = item.getBoundingClientRect().right;
                        for (const cell of item.children) {
                            if (cell.getBoundingClientRect().right > edge + 0.5) {
                                bad.push(year + ': ' + item.textContent.trim().slice(0, 60));
                            }
                        }
                    }
                }
                const total = Object.values(data.bySeason).flat().length;
                return {seen, total, bad: bad.slice(0, 5), count: bad.length};
            }"""
        )
        browser.close()
    assert result["seen"] == result["total"], "the loop didn't reach every season's rows"
    assert result["count"] == 0, result["bad"]


@pytest.mark.parametrize(
    "page_name, row, width, low, high",
    [
        # Desktop: compact, but one line of text still has room around it.
        ("combos.html", "tbody tr.combo", 1280, 34, 40),
        ("overdue.html", ".rr-face", 1280, 34, 40),
        ("unlikeliest.html", ".rr-face", 1280, 34, 40),
        ("soulmates.html", ".rr-face", 1280, 34, 40),
        # Phone: three stacked names, and still a comfortable tap target.
        ("combos.html", "tbody tr.combo", 390, 60, 84),
        ("overdue.html", ".rr-face", 390, 60, 84),
        ("soulmates.html", ".rr-face", 390, 34, 44),
        # Same stack, and nothing between the names: a line box there adds 35px.
        ("index.html", ".tl-item", 390, 60, 84),
    ],
)
def test_table_rows_are_compact_but_not_squished(dist, page_name, row, width, low, high):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.goto(_url(dist, page_name))
        page.wait_for_selector(row)
        height = page.locator(row).first.bounding_box()["height"]
        browser.close()
    assert low <= height <= high, f"{page_name} {row} is {height}px at {width}px wide"


def test_stacked_season_names_keep_their_hairlines(dist):
    """The hairline between stacked names hangs off ``.pdriver + .pdriver``, so
    anything rendered between two names silently removes it, hidden or not."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".tl-item .pdriver")
        rows, lines = page.evaluate(
            """() => [
                document.querySelectorAll('.tl-item').length,
                [...document.querySelectorAll('.tl-item .pdriver + .pdriver')].filter(
                    name => parseFloat(getComputedStyle(name).borderTopWidth) > 0
                ).length,
            ]"""
        )
        browser.close()
    assert lines == rows * 2, f"{lines} hairlines across {rows} trios"


def test_next_race_card_is_a_single_band_on_desktop(dist):
    """Race, session times and circuit plate share one band, so the prediction it
    introduces starts near the top of the page instead of a screen down."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".next-race")
        card = page.locator(".next-race").bounding_box()
        circuit = page.locator(".nr-circuit").bounding_box()
        when = page.locator(".nr-when").bounding_box()
        browser.close()
    assert card["height"] <= 110, f"next-race card is {card['height']}px tall"
    assert abs(when["y"] - circuit["y"]) < 4, "the session times should sit beside the place"


def test_trio_board_window_matches_its_rows(dist):
    """--board-row-h is a hand-kept number: it has to track the real row height,
    or the window stops showing twelve rows and a sliver of the next."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".cand")
        window, row = page.evaluate(
            """() => [
                document.querySelector('.cand-scroll').clientHeight,
                document.querySelector('.cand').getBoundingClientRect().height,
            ]"""
        )
        browser.close()
    assert row <= 36, f"a board row is {row}px tall with its bar inline"
    assert 12 < window / row < 12.8, f"the window shows {window / row:.2f} rows"


def test_faq_and_season_list_use_the_width_on_desktop(dist):
    """A short question and a one-line trio leave half a row empty; two columns
    halve both sections on a wide screen."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".tl-item")
        columns = page.evaluate(
            """() => ['.faq-item', '.tl-item'].map(sel => new Set(
                [...document.querySelectorAll(sel)].map(el => el.getBoundingClientRect().left)
            ).size)"""
        )
        browser.close()
    assert columns == [2, 2]


def test_hero_tooltip_stays_on_screen_on_a_phone(dist):
    """The number sits beside its sentence on phones now, which moves the info
    icon: its bubble must still open fully inside the viewport."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 360, "height": 800}, has_touch=True)
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".hero .info-tip")
        tip = page.locator(".hero .info-tip")
        tip.tap()
        rect = tip.evaluate(
            "el => { const r = el.querySelector('.info-bubble').getBoundingClientRect();"
            " return {left: r.left, right: r.right}; }"
        )
        browser.close()
    assert rect["left"] >= 0 and rect["right"] <= 360, rect


def test_board_rows_stay_on_one_line_with_grid_chips(dist):
    """After qualifying every driver carries a grid chip, the widest state a row
    has. Committed data rarely shows it, so add the chips here: a row that wraps
    pushes its NEW pill under the names and breaks --board-row-h."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(_url(dist, "index.html"))
        page.wait_for_selector(".cand")
        tallest = page.evaluate(
            """() => {
                document.querySelectorAll('.cd:not(:has(.cd-grid))').forEach(driver => {
                    const chip = document.createElement('span');
                    chip.className = 'cd-grid';
                    chip.textContent = 'P22';
                    driver.appendChild(chip);
                });
                return Math.max(...[...document.querySelectorAll('.cand')].map(
                    row => row.getBoundingClientRect().height
                ));
            }"""
        )
        browser.close()
    assert tallest <= 36, f"a board row wrapped to {tallest}px with grid chips"


# ── First-visit card (welcome.js) ──────────────────────────────────────────

CONTENT_PAGES = [name for name in ALL_PAGES if name != "404.html"]
# Long past any reasonable reveal delay, so a later reveal can't pass as "stayed away".
WELL_AFTER_LOAD_MS = 60_000


@contextmanager
def _new_visitor(dist, page_name, *, width=1000, height=800, fragment="", init_script=None):
    """A page opened with empty storage, on a clock the test moves by hand."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        if init_script:
            page.add_init_script(init_script)
        page.clock.install()
        page.goto(_url(dist, page_name, fragment))
        yield page
        browser.close()


def _card_on_screen(page):
    assert page.locator("#welcome").count() == 1
    return page.locator("#welcome").is_visible()


@pytest.mark.new_visitor
@pytest.mark.parametrize("page_name", CONTENT_PAGES)
def test_new_visitor_is_pointed_to_the_faq_on_any_page(dist, page_name):
    """Search sends people straight to the sub-pages, so the card can't rely on
    them coming through the landing page."""
    with _new_visitor(dist, page_name) as page:
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        assert _card_on_screen(page)
        assert "FAQ" in page.locator("#welcome").inner_text()


@pytest.mark.new_visitor
def test_card_waits_for_the_page_to_settle(dist):
    with _new_visitor(dist, "index.html") as page:
        assert not _card_on_screen(page)


@pytest.mark.new_visitor
def test_card_only_ever_shows_once(dist):
    """Even when it's ignored rather than dismissed: a card that returned on each
    page would nag someone who has already decided not to read it."""
    with _new_visitor(dist, "overdue.html") as page:
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        assert _card_on_screen(page)

        page.reload()
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        assert not _card_on_screen(page)


@pytest.mark.new_visitor
def test_card_closes_from_its_button(dist):
    with _new_visitor(dist, "overdue.html") as page:
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        page.locator(".welcome-close").click()
        assert not _card_on_screen(page)


@pytest.mark.new_visitor
def test_card_closes_on_escape(dist):
    with _new_visitor(dist, "overdue.html") as page:
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        page.keyboard.press("Escape")
        assert not _card_on_screen(page)


@pytest.mark.parametrize("width", [390, 1366])
def test_landing_page_is_full_height_once_its_scripts_have_run(dist, width):
    """The browser jumps to #faq early in the load, so if the timeline above it
    then eased open, a phone would land with the FAQ pushed about 900px down and
    off the screen. Whether that shows up depends on load timing, so the test
    checks the cause: nothing above the FAQ may still be growing."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.add_init_script(
            """document.addEventListener('DOMContentLoaded', () => {
                window.heightOnceScriptsRan = document.documentElement.scrollHeight;
            });"""
        )
        page.goto(_url(dist, "index.html"))
        page.wait_for_timeout(600)
        grew_by = page.evaluate(
            "document.documentElement.scrollHeight - window.heightOnceScriptsRan"
        )
        browser.close()
    assert grew_by == 0


# A laptop can't scroll the FAQ to the very top, since it's near the end of the page.
LANDING_SCREENS = [(390, 844), (1366, 768)]


def _assert_landed_on_the_faq(page):
    """The FAQ heading ends up in the top half of the screen, with the first answer
    open. It's read after a pause, because the browser jumps to the anchor early
    and anything growing above it afterwards pushes the FAQ back off the screen."""
    page.wait_for_timeout(600)
    first = page.locator("#faq .faq-item").first
    assert first.get_attribute("open") is not None
    assert "podigami" in first.locator("summary").inner_text()
    heading_top = page.locator("#faq h2").evaluate("h => h.getBoundingClientRect().top")
    assert 0 <= heading_top < page.viewport_size["height"] / 2
    nav_bottom = page.locator("nav.nav").bounding_box()
    assert heading_top >= nav_bottom["y"] + nav_bottom["height"], "the nav covers the heading"


@pytest.mark.parametrize("page_name", CONTENT_PAGES)
@pytest.mark.parametrize("width", [390, 1280])
def test_nav_stays_at_the_top_of_a_scrolled_page(dist, page_name, width):
    """``overflow-x: hidden`` on both html and body makes body a scroll container,
    and a sticky element sticks to that (never scrolling) box, not the screen."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 600})
        page.goto(_url(dist, page_name))
        page.wait_for_load_state("load")
        page.evaluate("window.scrollTo(0, 500)")
        page.wait_for_function("window.scrollY >= 400")
        top = page.locator("nav.nav").evaluate("n => n.getBoundingClientRect().top")
        browser.close()
    assert top == 0


def test_page_still_cannot_scroll_sideways(dist):
    """What the old ``overflow-x: hidden`` was there for."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 800})
        page.goto(_url(dist, "index.html"))
        page.wait_for_load_state("load")
        page.add_style_tag(content="body::after {content: ''; display: block; width: 900px}")
        page.evaluate("window.scrollTo(300, 0)")
        scrolled = page.evaluate("window.scrollX")
        browser.close()
    assert scrolled == 0


@pytest.mark.parametrize("page_name", CONTENT_PAGES)
def test_phone_links_are_big_enough_to_tap(dist, page_name):
    """Anything that stands on its own needs a 32px target. A link inside running
    text is exempt: it takes the line height of the sentence it sits in."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(_url(dist, page_name))
        page.wait_for_load_state("load")
        small = page.evaluate(
            """() => {
                // Links in drawers and FAQ answers are tapped like any other.
                document.querySelectorAll('details').forEach(d => { d.open = true; });
                document.querySelectorAll('tr.detail').forEach(d => d.classList.add('open'));
                const bad = [];
                for (const el of document.querySelectorAll('a, summary, button')) {
                    const r = el.getBoundingClientRect();
                    if (!r.height || r.height >= 31.5 || el.closest('.nav-drawer')) continue;
                    const inSentence = getComputedStyle(el).display === 'inline'
                        && [...el.parentElement.childNodes].some(
                            n => n.nodeType === 3 && n.textContent.trim().length > 2
                        );
                    if (!inSentence) bad.push(el.className + ' ' + r.height + ': '
                        + el.textContent.trim().slice(0, 30));
                }
                return [...new Set(bad)].slice(0, 12);
            }"""
        )
        browser.close()
    assert small == []


@pytest.mark.new_visitor
@pytest.mark.parametrize(("width", "height"), LANDING_SCREENS)
def test_faq_link_from_a_sub_page_lands_on_an_open_answer(dist, width, height):
    with _new_visitor(dist, "overdue.html", width=width, height=height) as page:
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        page.locator(".welcome-link").click()
        page.wait_for_url("**/index.html#faq")
        _assert_landed_on_the_faq(page)


@pytest.mark.new_visitor
@pytest.mark.parametrize(("width", "height"), LANDING_SCREENS)
def test_faq_link_on_the_landing_page_lands_on_an_open_answer(dist, width, height):
    """No page load happens here, only a hash change, so the card has to close
    itself and the answer has to open without a fresh script run."""
    with _new_visitor(dist, "index.html", width=width, height=height) as page:
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        page.locator(".welcome-link").click()
        assert not _card_on_screen(page)
        _assert_landed_on_the_faq(page)


@pytest.mark.new_visitor
@pytest.mark.parametrize(("width", "height"), LANDING_SCREENS)
def test_new_visitor_arriving_at_the_faq_gets_no_card(dist, width, height):
    with _new_visitor(dist, "index.html", width=width, height=height, fragment="#faq") as page:
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        assert not _card_on_screen(page)
        _assert_landed_on_the_faq(page)


@pytest.mark.new_visitor
@pytest.mark.parametrize(
    "block",
    [
        "Object.defineProperty(window, 'localStorage', {get() { throw new Error('denied'); }});",
        "Storage.prototype.setItem = function () { throw new Error('quota'); };",
    ],
    ids=["no-storage", "read-only-storage"],
)
def test_card_stays_away_when_it_could_not_be_remembered(dist, block):
    """Without storage every page load is a "first" visit: better no card than
    the same card on every page."""
    with _new_visitor(dist, "overdue.html", init_script=block) as page:
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        assert not _card_on_screen(page)
    assert errors == []


@pytest.mark.new_visitor
def test_card_fits_a_narrow_phone_in_a_wider_font(dist):
    with _new_visitor(dist, "index.html", width=320, height=640) as page:
        page.add_style_tag(content=WIDER_FONT)
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        card = page.locator("#welcome").bounding_box()
        close = page.locator(".welcome-close").bounding_box()
        text = page.locator(".welcome-text").bounding_box()
    assert card["x"] >= 0 and card["x"] + card["width"] <= 320
    assert card["y"] + card["height"] <= 640
    assert text["x"] + text["width"] <= close["x"], "the close button sits on the text"


@pytest.mark.new_visitor
def test_open_nav_drawer_covers_the_card(dist):
    with _new_visitor(dist, "index.html", width=390, height=800) as page:
        page.clock.run_for(WELL_AFTER_LOAD_MS)
        page.locator(".nav-burger").click()
        on_top = page.locator("#welcome").evaluate(
            """card => {
                const r = card.getBoundingClientRect();
                return card.contains(
                    document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)
                );
            }"""
        )
    assert on_top is False
