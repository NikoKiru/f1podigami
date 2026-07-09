# Overdue page: collapsible sections + mobile-friendlier cards

**Date:** 2026-07-09
**Status:** Approved (pending spec review)
**Scope:** `overdue.html` only — render helpers, CSS, one new page script, tests.

## Problem

On mobile the Overdue page is cluttered. Each trio card is tall: rank, three
driver names (wrapping to two lines), a large `X.Y×` score with an
"expected co-podiums" caption, and a heavy three-column stat block
(podium rates · raced together · chance by now). Two long grids —
"All-time near-misses" and "Current grid — still possible" — stack one below
the other, so reaching the second means scrolling past all of the first.

## Goals

1. **Reduce mobile clutter** on the trio cards without losing any data.
2. Let the reader **collapse either whole section** so the two grids don't
   force each other off-screen — view/navigate one at a time.

## Non-goals (YAGNI)

- Persisting collapse/expand state across visits (no localStorage).
- Collapsing the per-card stats on desktop (desktop has room — stays as-is).
- Any change to the data pipeline, model, or `data/overdue.json`.

## Current state (what we're changing)

- `src/build/build_overdue_html.py`
  - `panel(title, sub, entries)` emits `<section class="panel"> <h2> <p.panel-sub>
    {cards} </section>`.
  - `render_card(rank, e, hero)` emits `<li class="odcard…">` containing
    `.od-top` (rank), `.od-drivers`, `.od-score`, and `.od-stats` (three
    `.od-stat` cells). `#1` in each section is the enlarged `.odcard-hero`.
  - The page loads only `theme.js`.
- `assets/podigami.css`
  - `.panel*`, `.odcard*`, `.od-*` styles; the `@media (max-width:600px)` block
    already abbreviates driver names and shrinks the hero, but does not trim the
    stat block or offer any collapse.
- Combinations page precedent (the pattern the user asked to mirror):
  `build_combos_html.py` renders each row with an expand chevron and a hidden
  `.detail` sibling; `assets/index.js` toggles `.open`/`.expanded` on click and
  the chevron rotates via CSS. This is JS-driven and applies on all screen sizes.

## Design

### Part 1 — Collapsible sections (native `<details>`, all screens, open by default)

`panel()` emits a **native `<details class="panel od-panel" open>`** instead of a
`<section>`:

```html
<details class="panel od-panel" open>
  <summary class="panel-head">
    <h2>All-time near-misses</h2>
    <span class="panel-chev" aria-hidden="true">&#9662;</span>
  </summary>
  <p class="panel-sub">…</p>
  <ol class="odcard-list">…</ol>
</details>
```

- `open` by default → identical first paint for non-interacting users; all
  content stays in the DOM (SEO-safe, crawlers see everything).
- Clicking the summary collapses/expands the entire section, so "All-time" can be
  hidden to land on "Current grid" (and vice-versa).
- **No JavaScript.** `<details>` is keyboard-operable and exposes expanded state
  to assistive tech for free.

**CSS (scoped to `.od-panel` so the shared `.panel` on other pages is untouched):**

- `.od-panel > summary` → `cursor:pointer; list-style:none; display:flex;
  align-items:center; justify-content:space-between;` and
  `.od-panel > summary::-webkit-details-marker { display:none }` to drop the
  native disclosure triangle.
- Keep the current heading rhythm: the `<h2>` sits in the summary; `.panel-sub`
  stays directly beneath it (tune margins so spacing matches today).
- `.panel-chev` rotates when open: `.od-panel[open] .panel-chev { transform:
  rotate(180deg) }` with a short `transform` transition, mirroring the combos
  chevron.
- Reuse the existing `.panel` box (background/border/radius/padding).

`panel()` is defined **locally** in `build_overdue_html.py`, so this changes only
the Overdue page.

### Part 2 — Mobile card clutter (per-card "Details" expand, mobile only)

`render_card()` keeps the **main info always visible** — rank · trio · `X.Y×`
score + "expected co-podiums" — and puts the three stats behind a per-card
toggle:

```html
<li class="odcard…">
  <div class="od-top"><span class="od-rank">2</span></div>
  <div class="od-drivers">…</div>
  <div class="od-score">…</div>
  <button type="button" class="od-toggle" aria-expanded="false"
          aria-controls="odstats-{uid}">
    <span class="od-toggle-label">Details</span>
    <span class="chev" aria-hidden="true">&#9662;</span>
  </button>
  <div class="od-stats" id="odstats-{uid}">…three .od-stat cells…</div>
</li>
```

- **Desktop unchanged:** `.od-toggle { display:none }`, `.od-stats` visible as
  today.
- **Mobile (≤600px):** `.od-stats` is CSS-hidden and the `Details ▾` button is
  shown; clicking toggles `.od-open` on the `.odcard`, which reveals the stats
  and rotates the chevron. Applies to every card including the `#1` hero.
- **JS:** a new `assets/overdue.js` wires the toggles — exactly the shape of the
  combos handler in `index.js`:

  ```js
  document.querySelectorAll('.od-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.odcard');
      const open = card.classList.toggle('od-open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  });
  ```

  Loaded via `asset("overdue.js")` (content-hash cache-busting) immediately
  before `theme.js`.

- **Unique ids:** `render_card` takes a short section prefix (e.g. `at` for
  all-time, `cg` for current-grid) so `id="odstats-{prefix}{rank}"` /
  `aria-controls` never collide across the two grids. `render_cards()` /
  `panel()` thread the prefix through.

**CSS:**

```css
.od-toggle { display: none; }            /* desktop default */

@media (max-width: 600px) {
  .odcard .od-stats { display: none; }
  .odcard.od-open .od-stats { display: grid; }
  .od-toggle { display: flex; }          /* align-items:center; the Details row */
  .odcard.od-open .od-toggle .chev { transform: rotate(180deg); }
}
```

**Progressive-enhancement trade-off (matches combos):** on mobile the stats are
CSS-hidden by default and revealed by the `.od-open` class the script adds, so a
no-JS phone would see the `Details` button but the stats stay collapsed — the
same behavior combos already ships. The content remains in the DOM for crawlers.
(If we later want "always shown without JS" we can gate the mobile hide behind a
`html.js` class the script sets; not doing that now for parity with combos and to
avoid a first-paint flash.)

## Files touched

- `src/build/build_overdue_html.py` — `panel()` → `<details>`; `render_card()`
  gains the toggle + stats `id`; thread a section prefix; load `overdue.js`.
- `assets/podigami.css` — section summary/chevron styles (scoped `.od-panel`) +
  mobile card-collapse rules + `.od-toggle` styling.
- `assets/overdue.js` — **new** toggle wiring.
- Tests:
  - `tests/test_build_output.py` — overdue asset list (line ~14) gains
    `"overdue.js"`.
  - `tests/test_build_overdue.py` — update `test_panel_wraps_title_and_sub`
    for the `<details>`/`<summary>` shape; add a card-toggle assertion
    (`.od-toggle`, `aria-expanded`, stats `id`).
  - `tests/test_mobile_css.py` — add a regression asserting the mobile block
    hides `.od-stats` and shows `.od-toggle`.
- `RELEASE_NOTES.md` — one entry under today's date.

## Testing / verification

- `python -m ruff check .` and `python -m ruff format --check .`
- `python -m pytest -q`
- `python src/build_site.py`, serve `dist/`, and use the Playwright MCP to confirm
  on a phone viewport: each section header collapses/expands; cards show the
  `Details` toggle and reveal stats on tap; desktop viewport shows the full cards
  unchanged with no toggle.

## Decisions (resolved during brainstorming)

1. **Default state:** both sections **expanded** on load; collapse is opt-in.
2. **Card expand scope:** **mobile only** — desktop keeps all stats visible.
3. **Mechanism:** native `<details>` for sections (no JS); small JS toggle for the
   mobile card stats, mirroring the combinations page.
