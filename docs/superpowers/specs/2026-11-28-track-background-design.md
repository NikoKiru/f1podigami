# Next-race track as the band's background drawing

**Date:** 2026-11-28
**Status:** approved in conversation (the owner picked every visual choice in the
visual companion, then asked for it to go straight to deploy)
**Scope:** landing page only: the `.next-race` + `.last-race` band

## Intent

The circuit plate (a small framed outline captioned "LUSAIL INTERNATIONAL CIRCUIT ·
5.38 KM") reads as an info box. The owner wants the track to be something nice to
look at: a large drawing that has the whole right side of the band, across both the
next-race and last-race rows, with no data attached.

## Goals

- The outline of the next race's circuit, drawn large on the right side of the band,
  spanning both rows.
- Today's colour and weight: `--accent-bright` stroke at ~2.4px, not a faded
  watermark (owner's call after seeing watermark, glow and animated-lap variants).
- Each circuit is rotated to whatever angle makes it biggest in the space, and
  recomputed whenever the next race changes.
- Circuits the owner knows better the other way up are turned 180°. Turning by 180°
  doesn't change the size.

## Non-goals and anti-goals

- No circuit name, no length, anywhere on the card (owner: "intet navn"). The
  locality line keeps "Lusail, Qatar" only. The JSON-LD event keeps
  `location.name`, because it's invisible structured data and not part of the card.
- No mirroring: it would reverse the direction of the lap.
- No change to the phone layout: the landing page already hides the track at ≤600px.
- Don't let the full-strength red line run under text. That would hurt legibility,
  which is the reason the track only shows where there's room for it.

## Approaches considered

1. **Rotate at build time from the stored `trackPath` (chosen).** It's pure geometry
   over data we already commit. It runs on every build, so on every data update, and
   the flip list lives next to the drawing code.
2. Rotate at fetch time and store the rotated path in `schedule.json`. Rejected:
   rotation depends on the box's shape, which is presentation, so tweaking it or
   the flip list would need a network refetch.

For the layering: wrap both sections in one `.race-band` that holds the SVG (chosen).
The alternative was an SVG overflowing from `.next-race` into `.last-race`, which is
fragile: `.next-race` clips with `overflow:hidden`, and `.last-race` paints its
background over anything from a sibling.

## Design

- **`src/build/track_art.py`** (pure, no IO):
  - parses the stored path (`M x y L x y ... Z`) into points;
  - `best_angle(points)`: integer degrees in [-90, 90) maximising the fit scale in
    a **2.8:1** box. Ties go to the smallest |angle|. The result is **0** unless
    the gain is at least **10%**, so tracks that already fit stay north-up.
  - `FLIPPED`: circuitIds turned a further 180°, as the owner picked them:
    `suzuka, shanghai, miami, villeneuve, monza, madring, rodriguez, vegas,
    yas_marina`. A circuit not in the list (a new venue) uses the computed angle.
  - `track_svg(path, circuit_id)` returns the rotated path, with 1-decimal
    coordinates and a tight `viewBox` (2-unit margin) so the drawing fills its box.
    The output is deterministic.
- **Markup:** `render_race_band(next_html, last_html, nxt)` wraps the two sections in
  `<div class="race-band has-track">` and appends
  `<svg class="band-track" aria-hidden="true">` after them, or omits it when the race
  has no `trackPath`, there is no next race, or the season is complete.
  `render_next_race` loses the plate (`.nr-art`, `.nr-plate-cap`) and the
  `nr-noplate` modifier, and its circuit line is just locality and country.
- **CSS:** the band carries the section gap. The SVG is absolutely positioned on
  the right, takes ~30% of the band's width and nearly all of its height, and is
  aligned right (`xMaxYMid meet`). It sits above the sections' backgrounds and below
  their content. The sections reserve that width as right padding, so text wraps
  before it reaches the drawing. The drawing is hidden below the width where the band
  gets too cramped, and the builder picks that breakpoint from measurements.
- Remove the dead plate CSS (desktop and the ≤720px/≤600px rules) and the tests
  that asserted it.

## Left to the builder

- The exact show/hide breakpoint and the reserved width. Check them with
  `WIDER_FONT` from `tests/test_e2e.py`, in both themes.
- Test shape: unit tests for `track_art` (angle choice, 10% rule, flip, tight
  viewBox, determinism), render tests for the band and the bare circuit line, and an
  e2e check that the drawn path's box doesn't intersect any text box in the band.
