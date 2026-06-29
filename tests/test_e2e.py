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
