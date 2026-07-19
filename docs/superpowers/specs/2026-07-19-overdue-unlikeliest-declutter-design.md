# Overdue & Unlikeliest pages: leaderboard de-clutter — Design

**Date:** 2026-07-19
**Status:** Approved

## Problem

`overdue.html` and `unlikeliest.html` render every ranked entry (15+15 and 30
respectively) as a full card: rank, drivers, big accent number, uppercase label,
and three labelled stat cells. The user finds both pages too cluttered on
desktop and mobile — specifically **too much repeated detail per card** and
**visual noise** (the same uppercase labels and big red numbers 30 times over).
Entry counts and page structure are otherwise fine.

## Chosen approach: hero card + leaderboard rows

Of three explored options (leaderboard rows / slim cards with a details toggle /
calm restyle keeping all content visible), the user chose **leaderboard rows**,
previewed and approved via visual mockups.

### Layout (both pages)

- The **#1 hero card keeps today's treatment**: accent border, big number,
  always-visible stat cells. On Overdue, each of the two sections keeps its own
  hero.
- **Every other rank becomes a single-column leaderboard row** (no more card
  grid for ranks #2+): rank, driver names, headline number (`1 in N` /
  `X.Y×`), chevron.
- **Clicking/tapping anywhere on the row expands a stats panel** with the same
  stats the cards show today:
  - Overdue: podium rates, raced together, chance by now.
  - Unlikeliest: podium rates, raced together, times it happened.
- **Unlikeliest race name/link:** muted on the desktop row (right of the
  drivers); on phones it is hidden on the collapsed row and appears in the
  expanded panel instead. The race report link stays clickable in both
  placements.
- **Driver names** reuse the existing `dn-full`/`dn-abbr` swap at the 600px
  breakpoint.

### What does not change

- Entry counts (15 all-time + 15 current-grid; 30 unlikeliest).
- Headline numbers, their computation, and dataset schemas (no `data/` or
  `datalib` changes; build-stage only).
- Hero card content and styling, page headers/taglines, methodology footnote
  (`as-of` line), Overdue's two collapsible `<details>` section panels.

## Implementation

- **Rows are native `<details>`/`<summary>` elements** — `<summary>` is the row
  face, the stats panel is the details body. No JavaScript; accessible for
  free; consistent with the site's existing `<details>` section panels.
- **Delete `assets/overdue.js`** and the `.od-toggle` mobile machinery (button,
  CSS, `od-open` class); the native rows replace them on all viewports. Remove
  the `<script src=".../overdue.js">` tag from the Overdue builder.
- **One shared row style** in `assets/podigami.css` (e.g. `.rankrow` family)
  used by both pages, replacing the duplicated non-hero `.odcard`/`.uncard`
  grid CSS. Hero card CSS stays (per-page or unified — implementer's choice,
  but do not restyle heroes). Red accent stays on rank hash, headline number,
  and open-state chevron; everything else muted per the approved mockups.
- **Builders** (`src/build/build_overdue_html.py`,
  `src/build/build_unlikeliest.py`): `render_card` keeps producing the hero
  (`hero=True` path); a new row renderer produces `<details>` rows for ranks
  #2+. The `uid` disambiguation for Overdue's per-card stats ids is no longer
  needed once `aria-controls` toggles go away.

## Testing

- Update `tests/test_build_output.py` and `tests/test_mobile_css.py` assertions
  to the new structure (hero present, `<details>` rows, no `overdue.js`
  reference, race link present on Unlikeliest rows).
- Full `pytest -q`, `ruff check .`, `ruff format --check .`.
- Playwright verification against a locally served `dist/` at desktop (1280px)
  and phone (390px) widths: rows render, expand/collapse works, race links
  clickable, hero unchanged.

## Ship

Feature branch off `develop`, PR into `develop` per repo workflow, with
`RELEASE_NOTES.md` entry and a README check (page descriptions still accurate).
