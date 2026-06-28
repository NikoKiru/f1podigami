# Link existing-combo trios to the combos page

**Date:** 2026-06-28
**Status:** Approved

## Goal

Whenever the site shows a podium trio that **has actually happened** (an existing
entry in `combos.json`), make that trio a clickable link that takes the user to
the combo's stats on the combos page.

## Scope

Existing (happened) combos are shown in exactly two places outside the combos
page itself, both on the landing page:

1. **Last-race box** (`src/build/build_podigami_html.py` → `render_last_race`) —
   the just-happened podium trio, rendered as TLA codes (`VER / NOR / LEC`).
2. **Timeline rows** (`assets/podigami.js` → `applyContent`) — the trios that
   debuted on a podium in the selected season, rendered as full/abbreviated names.

Out of scope (never-happened trios or non-trios, so not link targets):
- Hero "most likely next podigami" and the "most likely next combinations"
  candidates list (brand-new trios).
- The entire **overdue** page (trios that have never happened).
- The **soulmates** page (driver *pairs*, not trios).
- The **combos page** itself stays as-is (rows already expand on click).

## Link shape

The **whole trio** is wrapped in a single `<a>` (not one link per name). It
points at the combos page with the three driver **full names** as repeated `d`
query params:

```
combos.html?d=Max+Verstappen&d=Lando+Norris&d=Charles+Leclerc
```

Full names are used (not surnames or codes) because the combos-page filter does
distinct-substring matching against each driver's full name. Three full names
resolve to exactly that one trio with no surname-collision risk.

## Arrival behaviour on the combos page

`assets/index.js`: on load, read `new URLSearchParams(location.search).getAll('d')`,
drop the values into the three existing filter inputs in order, then let the
existing `applyFilter()` run. The table filters down to that trio and the Clear
button auto-enables. No new anchor/scroll machinery — pure reuse of the current
filter.

## Implementation pieces

- **Python** (`build_podigami_html.py`): add a small `combos_link(names)` helper
  (`"combos.html?" + urlencode([("d", n) for n in names])`) and use it to wrap
  the `lr-trio` content in `render_last_race`. Only emit a link when the combo is
  found in `combos.json` (always true for a real last-race result).
- **JS** (`assets/podigami.js`): wrap each timeline trio's names in an
  `<a class="combo-link">` built with `URLSearchParams`.
- **JS** (`assets/index.js`): the param-prefill block described above (~4 lines).
- **CSS** (`assets/podigami.css`): a `.combo-link` class that **inherits text
  color** (so contrast is preserved in light and dark themes) with a hover/focus
  underline and a focus ring for affordance. Add a `title`/`aria-label`
  ("See this trio on the combos page") so the affordance is discoverable since
  the trio at rest looks unchanged.

## Testing

- Update last-race assertions in the build tests for the new `<a>` wrapper.
- Add a test asserting the last-race trio is an `<a>` whose `href` is
  `combos.html?d=…` with the three driver names.
- Timeline links are client-rendered (no JS test runner in this repo), so they
  are covered by manual verification plus the Python URL-shape being mirrored in
  JS.
