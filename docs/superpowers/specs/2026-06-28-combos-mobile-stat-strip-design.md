# Combos page: collapse stat cards into a slim strip on mobile

## Problem

On `combos.html` at the ≤600px breakpoint, the three `.stats` cards (Races /
Unique Combos / Seasons) collapse into full-width stacked blocks
(`style.css` `@media (max-width: 600px)` → `.stats { grid-template-columns: 1fr }`).
They look tappable but do nothing — a false affordance — and they push the
combinations table below the fold. A first-time mobile tester instinctively
tapped them expecting navigation/filtering.

## Goal

Make the combinations list the first thing a mobile visitor sees, and remove the
"these look like buttons" signal, without losing the headline numbers.

## Change

A single CSS-only edit in `assets/index.css`, inside its existing
`@media (max-width: 600px)` block. Restyle the stat cards into one compact,
wrapping inline strip:

- Strip card chrome on `.stat`: `background`, `padding`, `border-radius`, and the
  `::before` accent bar (`content: none`).
- `display: inline` for `.stat`, `.num`, `.label`; insert `·` separators via a
  clean `.stat:not(:last-child)::after` pseudo (no conflict with the existing
  `.stat::before` accent rule).
- Net header height drops from ~180px (three stacked cards) to ~40px (one wrapped
  line: *"1,124 Races · 487 Unique Combos · 1950–2026 Seasons"*), so the filters
  and table greet the user immediately.

## Scope / blast radius

- The rule lives in `index.css`, which **only `combos.html` loads**. The soulmates
  page uses `soulmates.css`; the landing page uses `podigami.css`. Both are
  untouched.
- Entirely inside the 600px media query → **desktop is unchanged** (cards remain).
- **No Python/HTML change** — same markup, CSS reflows it. Generated page body is
  byte-identical.

## Testing

- Add a regression guard in `tests/test_mobile_css.py` asserting the strip rule
  exists in `index.css` (the `.stat:not(:last-child)::after` separator + accent
  removal), matching the existing substring-assertion style.
- `pytest -q`, `ruff check .`, `ruff format --check .`.
- Manual eyeball of `combos.html` at 375px width.

## Out of scope

- No changes to the soulmates or landing-page stat cards.
- No new interactivity on the stat numbers (considered and rejected — the goal is
  to *remove* the false affordance, not build a real one).
