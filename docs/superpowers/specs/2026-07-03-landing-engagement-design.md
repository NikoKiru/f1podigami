# Landing-Page Engagement Overhaul — Design

**Date:** 2026-07-03
**Status:** Approved
**Goal:** Keep visitors on the landing page longer and route them onward to the
other four pages (Combinations, Overdue, Unlikeliest, Soulmates), applying
established web-engagement behaviour patterns. No new backend features, no
analytics — build-time HTML/CSS/JS enhancements only.

## Background: behaviour analysis applied to this page

| Established pattern | Landing page today |
|---|---|
| ~50% of visitors never reach the bottom of a page; attention concentrates above the fold | Strong top (next race / last race / hero), but everything that drives onward navigation sits in the thin top nav |
| Sessions end at dead ends — pages need a "next thing to do" | Page ends at the FAQ with no onward path except the footer |
| Curiosity-gap CTAs with live stats outperform generic nav labels | All cross-links today are bare labels ("Overdue") |
| Interactive elements are the strongest dwell-time driver | The timeline slider is good but sits near the bottom |
| Subtle motion and count-up numbers pull users down the page | Hero % is static; sections all render at once |
| In-content links outperform chrome/nav links | Almost no inline deep links (only last-race trio + timeline items) |
| Orphan pages get zero traffic | `soulmates.html` is built but absent from top nav AND footer nav |

## Scope

Five workstreams, one feature branch, one PR into `develop`.

### 1. Fix the orphan page + nav

- Add `("soulmates.html", "Soulmates")` to `NAV_LINKS` in `src/build/_layout.py`
  and to the footer nav. Appears on all five pages.
- Verify the 5-item nav fits at the 600px mobile breakpoint (adjust CSS if not).

### 2. Woven-in discovery hooks

New shared renderer `src/build/_hooks.py` exposing a hook-card component:
kicker label + one live stat line (computed at build time from committed
`data/*.json` via datalib loaders) + arrow CTA link.

Placement in `build_podigami_html.py` (contextual, adjacent to the related
section):

| After section | Links to | Live stat source |
|---|---|---|
| Candidates panel | `combos.html` | `len(load_combos())` — "N unique trios since 1950 — every one, sortable" |
| Current form panel | `soulmates.html` | `soulmates.topPairs[0]` + `soulmates.max` — top shared-podium pair |
| Timeline panel | `overdue.html` | `overdue.allTime[0]` — names + racesTogether, never all three on the podium |
| Timeline panel | `unlikeliest.html` | `unlikeliest.trios[0]` — names + `happened` race/season |

Error handling: if a dataset is missing or empty, render the card **without**
the stat line (kicker + CTA only). The build must never fail because a hook
stat is unavailable. All interpolated data goes through `esc()`.

### 3. "Keep exploring" grid

After the FAQ: a responsive card grid (2×2 desktop, 1-col mobile) with all four
other pages, reusing the hook component, so visitors who reach the bottom
always have a next step.

### 4. Motion that rewards scrolling

All progressive enhancement. No-JS users see a fully static, complete page.
`prefers-reduced-motion: reduce` disables all of it.

- **Hero count-up:** the headline chance % counts up from 0 on first view
  (IntersectionObserver). The server-rendered number stays in the HTML
  (SEO/no-JS); JS reads it, animates, and restores the exact original text.
- **Scroll-reveal:** panels fade-up (opacity + 12px translateY). JS adds the
  hiding class only when IntersectionObserver is available — raw HTML never
  hides content.
- **Timeline quick-picks:** chips above the slider — "1950 · first season",
  "<record year> · most new trios", "<current season>" — one-tap jumps that
  drive the existing slider. Record year computed at build time from
  `seasonCounts` (earliest year wins ties).

### 5. Inline deep links

- FAQ podigami answer: link the unique-trios count to `combos.html`.
- New FAQ item "What else is on this site?" linking all four other pages with
  one-line descriptions.

## Non-goals

- No new interactive widgets (trio builder, quizzes) — explicitly declined.
- No analytics/measurement — explicitly declined.
- No changes to fetch/compute pipeline or data schemas.

## Architecture

- `src/build/_hooks.py` — pure functions: `hook_card(kicker, stat_html, href,
  cta) -> str` and per-page stat builders that accept already-loaded data
  objects (no I/O inside — callers load via datalib). Unit-testable in
  isolation.
- `build_podigami_html.py` — loads overdue/unlikeliest/soulmates via datalib
  (tolerating absent files like it already does for schedule/model_eval),
  composes hooks + explore grid + quick-picks into the page.
- `assets/podigami.js` — new IIFEs for count-up, scroll-reveal, quick-picks
  (same style as existing modules; each bails out silently if its DOM hooks are
  absent).
- `assets/podigami.css` / `assets/style.css` — hook card, explore grid, reveal
  transitions, chips. Nav CSS touched only if 5 items overflow at 600px.

## Testing

TDD throughout (test first, then implement):

- `tests/test_hooks.py` — unit tests for `_hooks.py`: stat formatting,
  missing/empty-data fallback (card without stat line), HTML escaping of
  driver names.
- `tests/test_build_output.py` — generated-HTML assertions: Soulmates link in
  nav + footer on all five pages; hook cards present with correct hrefs and
  placement order; explore grid present with four links; count-up/reveal
  attributes present; panels NOT hidden in raw HTML (no inline hiding class);
  quick-pick chips present with correct years.
- `tests/test_mobile_css.py` — nav fits five items at 600px; explore grid
  collapses to one column.
- Existing tests updated where HTML structure changes.
- Manual gate: Playwright pass on locally served `dist/` (count-up animates,
  reveals fire, chips drive the slider, reduced-motion honoured) before user
  approval.

## Ship path

1. Feature branch off `develop` → PR into `develop` (RELEASE_NOTES entry;
   README updates for nav/page discovery changes).
2. Merge on green CI → local `python src/build_site.py` + serve `dist/` for
   user approval.
3. Promotion PR `develop` → `main` (full 9 checks) → Pages deploy.
