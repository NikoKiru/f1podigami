"""Browser test: the timeline slider thumb tracks the sparkline bar centers.

A native range thumb travels inset by half its own width, while the flex
sparkline's first/last bar centers sit only half a (much smaller) bar-width
from the edges. Left uncorrected the thumb drifts inward of the bars at both
ends. We size the thumb to a known width and offset the slider so the thumb's
center travels exactly from the first bar center to the last bar center.

Requires Playwright + Chromium. In CI this runs in the dedicated e2e job.
On a dev machine without Playwright installed the test is skipped gracefully.
"""

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

# Subpixel slop: layout rounds to device pixels, so allow well under 1px.
TOL = 0.75


def _geometry(dist):
    url = (dist / "index.html").resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Desktop width: the sparkline + slider are hidden below 600px.
        page = browser.new_page(viewport={"width": 1000, "height": 1600})
        page.goto(url)
        page.wait_for_selector("#tl-slider")
        geom = page.evaluate(
            """() => {
                const bars = Array.from(document.querySelectorAll('.tl-bar'));
                const slider = document.getElementById('tl-slider');
                const f = bars[0].getBoundingClientRect();
                const l = bars[bars.length - 1].getBoundingClientRect();
                const s = slider.getBoundingClientRect();
                const cs = getComputedStyle(slider);
                return {
                    nbars: bars.length,
                    c0: f.left + f.width / 2,
                    c1: l.left + l.width / 2,
                    sLeft: s.left,
                    sRight: s.right,
                    thumb: parseFloat(cs.getPropertyValue('--tl-thumb')),
                    padL: parseFloat(cs.paddingLeft) || 0,
                    padR: parseFloat(cs.paddingRight) || 0,
                    borderL: parseFloat(cs.borderLeftWidth) || 0,
                    borderR: parseFloat(cs.borderRightWidth) || 0,
                };
            }"""
        )
        browser.close()
    return geom


def test_timeline_slider_aligns_with_bars(dist):
    g = _geometry(dist)

    assert g["nbars"] > 1, "expected a multi-year sparkline"
    assert g["thumb"] and g["thumb"] > 0, "slider must expose a fixed --tl-thumb width"

    # The runnable track fills the slider's content box; the thumb stays within
    # it, so its center travels from (trackLeft + thumb/2) to (trackRight - thumb/2).
    track_left = g["sLeft"] + g["borderL"] + g["padL"]
    track_right = g["sRight"] - g["borderR"] - g["padR"]
    thumb_min_center = track_left + g["thumb"] / 2
    thumb_max_center = track_right - g["thumb"] / 2

    assert abs(thumb_min_center - g["c0"]) < TOL, (
        f"slider start off by {thumb_min_center - g['c0']:.2f}px from first bar"
    )
    assert abs(thumb_max_center - g["c1"]) < TOL, (
        f"slider end off by {thumb_max_center - g['c1']:.2f}px from last bar"
    )
