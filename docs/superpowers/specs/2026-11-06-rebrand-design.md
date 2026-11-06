# Rebrand: plate logo, plate badges, a calmer phone landing page

Date: 2026-11-06 · Status: agreed in brainstorming, ready to plan

## Why

The owner finds the current logo and badges ugly. The logo is three silver, gold and bronze bars on a red line, which reads as a stock bar-chart icon. The badges are an assortment of round pills, red text labels and red status text. The logo and badges set the tone for the rest of the site, so they come first.

Separately, the landing page on a phone "bombards you with text." The owner opens it on a phone to see **the most likely trio, new or not, at the top of "Most likely trios."** Today that list starts at the very bottom of the first phone screen, under a repeated title, a five-line race card and a long 19% box. The full page runs about 4½ phone screens.

## Goals

1. A new mark and wordmark that look like a sports brand rather than a chart, used everywhere the old mark appears.
2. One badge family (set A, "plates") replacing every pill, chip and red text label across the site.
3. A last-race verdict in scorigami style ("NO PODIGAMI (3)") instead of the race history sentence.
4. On a phone, the landing page shows "Most likely trios" in the first screen, and the whole page is about 2 phone screens instead of 4½.

## Non-goals

- The other five pages (Combinations, Overdue, Unlikeliest, Soulmates, Scorecard) get **no content or layout trimming**. The owner's view: "if the user goes there that means they have decided to stay." They get only the new logo, wordmark and badges.
- Desktop landing page content and layout stay as they are. Desktop gets the new logo, wordmark and badges, and the new last-race verdict.
- No new web fonts, no change to the colour tokens beyond what badges need, and no change to the data, the model or the pipeline.
- Nothing is deleted from the site. Anything hidden on a phone stays available on desktop, one tap away, or on its own page.

## Anti-goals (fails even if it technically works)

- **A site-wide restyle beyond what's agreed here.** On 2026-08-24 a broad "v2 look" restyle (Barlow fonts, skewed red tick headings, timing-tower tables, darker tokens) was built and rejected twice ("this looks shit"), then fully reverted. Do not touch fonts, section headings, panel styling, table layouts or tokens beyond the badges and brand. Do not add skewed red "tick" decorations.
- Any origami reference in the brand. The owner doesn't want the origami half of the name to be prominent.
- Within the badge family, red marking anything other than "new" (the NEW marker and the PODIGAMI verdict). This rule governs badges and labels only. Every other red on the site stays as it is today: the nav gradient line and active-tab underline, the next-race card's left rail, the red "F1" in page `<h1>`s, link colours (`--accent-link`), hover and focus states, the big hero %, the selected timeline bar, and the ranked pages' rails. Removing them would be the wide restyle the first anti-goal forbids. If they clash with the plate, the owner will say so at the checkpoint.
- Three-letter codes or team-colour dots for historical drivers. Old seasons have no colour data, and codes like "FAR / FAG / PAR" are unrecognisable.

## Decisions (made by the owner from mockups)

All approved mockups are in `.superpowers/brainstorm/1139-1793977655/content/` (gitignored; local to the owner's main PC). Each file is named below. Open it in a browser to see the approved look.

**Binding vs sketch.** Only what this document states is binding. The mockups were drawn to decide the items below, and anything else in them is a sketch shortcut, not a decision. Everything not named here keeps today's styling, including:
- the trio board's dimmed repeat rows (NEW rows must still stand out)
- 6px board bars and two-decimal percentages
- panel gradients and the race card's rails
- full year-chip labels ("first season"), unless they no longer fit on a phone

### 1. The mark: "D3 · Plate" (`logo-d-refine.html`, `logo-d3-in-context.html`)

A white, slanted "P" on a red rounded square, like a race-number board. The P stands for P1/P2/P3. Two horizontal cuts through the bottom of the stem give it speed. The plate doesn't change between light and dark themes. Approved SVG (64×64):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <mask id="p-cuts" maskUnits="userSpaceOnUse" x="-20" y="-20" width="120" height="120">
      <rect x="-20" y="-20" width="120" height="120" fill="#fff"/>
      <rect x="9" y="44" width="21" height="3" fill="#000"/>
      <rect x="9" y="51" width="21" height="3" fill="#000"/>
    </mask>
  </defs>
  <rect width="64" height="64" rx="14" fill="#e10600"/>
  <g transform="translate(5 7) scale(.78)">
    <g transform="translate(8 0) skewX(-10)">
      <path fill-rule="evenodd" fill="#fff" mask="url(#p-cuts)"
        d="M13 58V6H36C46.5 6 54 13.2 54 22.5C54 31.8 46.5 39 36 39H27V58Z
           M27 17.5H35.5C39 17.5 41.5 19.7 41.5 22.5C41.5 25.3 39 27.5 35.5 27.5H27Z"/>
    </g>
  </g>
</svg>
```

The bowl is a real hole (even-odd), so the red shows through it. The red is the site's existing `--accent` `#e10600`.

Where it goes:
- `_layout._BRAND_MARK` (header brand and the mobile drawer head)
- `assets/favicon.svg`
- `assets/apple-touch-icon.png`
- `assets/og-image.png`

The mask id must be unique wherever the inline SVG appears more than once on a page (header and drawer).

### 2. The wordmark: "W3 · Stacked" (`wordmark.html`)

Two lines to the right of the plate:
- **Top line:** "FORMULA 1", about 9px, weight 700, letter-spacing 0.32em, uppercase, muted colour (`--muted-dim`).
- **Bottom line:** "PODIGAMI", about 17px, weight 900, *italic*, letter-spacing 0.02em, uppercase, text colour.

It replaces the current `<span class="brand-name"><span class="accent">F1</span> Podigami</span>` in the header and the drawer. The site's name, `<title>`s and schema.org name stay "F1 Podigami."

### 3. Badges: "set A · Plates" (`badges.html`)

Every badge is a small square-cornered plate echoing the logo: 4px corners, heavy uppercase spaced-out type. The approved dark-theme values:

| Role | Look (dark theme) | Today's classes it replaces (non-exhaustive) |
|---|---|---|
| Primary section label ("NEXT RACE") | solid plate, bg `#e6edf3` (≈`--text`), ink `#0b0d12`, 9.5–10px, weight 800, letter-spacing .16em, padding 3px 7px | `.nr-tag` |
| Secondary label ("LAST RACE", discovery kickers) | solid plate, bg `#2a313c` (`--border`), ink `#c9d1d9` (`--text-dim`) | `.lr-tag`, `.hook-kicker`, `.sc-tag` |
| **NEW** marker | solid red plate `--accent`, white, 9.5px, weight 900, *italic*, letter-spacing .08–.1em, padding 2px 7px 2px 6px | `.cand-pill` (NEW), and any other "new" marker |
| Status ("Awaiting results", live states, "grid-aware") | outlined plate, 1px `--border-strong`, text colour, caps 9.5px weight 800 .14em, with a 6px dot (gold `#f4c430` for awaiting) | `.nr-status`, `.panel-badge` |
| Chips (timeline year chips) | bg `#1f2530`, 1px `--border`, 6px corners, year in bold text colour, label muted; the selected one has a red border | `.tl-chip` |
| Round info ("R19 / 23") | plain muted caps, no plate | `.nr-round` |

These are dark-theme values. Light-theme equivalents must be derived through the existing tokens and pass contrast (see Constraints).

The site's other small markers move to the same family. Here is how each maps:
- **Scorecard "New trio" tag:** the red NEW plate, because it marks a new trio.
- **Scorecard "Called it" tag** (solid red today) and its other outcome tags: the builder proposes a treatment within the family. The primary white plate is the likely fit, since red is reserved for "new". The owner settles it at checkpoint 2.
- **Combos race pills** (`.race-pill`): these are mixed-case race-name links, many per row. They take the **plate shape only** (4px corners, plate background and border) and keep their current case, size and spacing, so expanded rows wrap as they do today.
- **Shared-car marker** (`.shared-badge`, `.race-pill-shared`): keeps its ⇄ glyph and takes the plate shape. No word is added.
- **Grid-position chips** (`.cd-grid`, "P3"): the secondary plate.

### 4. Last-race verdict (`last-race.html`, layout "I" in `last-race-v2.html`)

"3rd time · last 2026 R17 · Singapore Grand Prix" is replaced by one plate, inspired by scorigami's "No Scorigami (16)":
- **Repeat trio:** `NO PODIGAMI (3)`, a secondary plate (grey) with the count in bold, brighter ink.
- **New trio:** `PODIGAMI`, a red slanted plate (same as NEW).

The trio itself stays a link to its filtered Combinations view (`combos_link`), which is where the history now lives. The link to the previous occurrence's race report goes away.

**Layout "I":** the verdict sits straight after the trio, left-aligned. It is not pushed to the far edge (the owner found the pushed version "off balance" on a phone). This applies on desktop too, where it's one line: `LAST RACE · flag · R18 · United States Grand Prix · trio · verdict`.

### 5. Landing page on a phone, first screen: "O · Same order, less text" (`phone-first-screen.html`)

At the mobile breakpoint (`max-width: 600px`), top to bottom:

1. **Header:** burger, plate, stacked wordmark, theme toggle. The page's own title and tagline block (`<header><h1>…<p class="tagline">`) is **not shown**. After checkpoint 1 the owner extended this to **desktop and phone**: the landing page's banner is visually hidden at every width, and the `<h1>` stays in the DOM. The other five pages keep their banners.
2. **One race card:**
   - Next race: a `NEXT RACE` plate, flag, `R19 / 23`, the race start in the visitor's local time on the right (e.g. `SUN 21:00`), then the race name.
   - A divider, then the last race: a `LAST RACE` plate, flag, `R18 · United States GP`, and on the next line the trio followed by its verdict (layout I).
   - Hidden on phones: the locality line ("Mexico City, Mexico"), the qualifying time and the circuit art plate.
3. **The new-trio chance box, two lines:**
   - Line 1: the big % and a short sentence, "chance the podium is a trio F1 has never seen."
   - Line 2: "Likeliest new:", the trio in codes with team dots, and a red `NEW` plate.
   - Hidden on phones: the full-name/team driver cards and the model-accuracy sentence, which the Scorecard page already covers.
4. **Most likely trios:** keeps today's heading. The top 5 rows, **all the same size** (the owner rejected an enlarged first row). Each row has the trio, its %, and a thin bar.

The "Most likely trios" list must start above the fold on a 390×844 phone.

### 6. Landing page on a phone, below the first screen (`phone-whole-page.html`)

- **Most likely trios:** after the top 5, two buttons side by side, "All 15 ▾" (the count is the board's length) and "Current form ▾" (today's form toggle).
- **New podiums through the years:**
  - The heading, the year and count readout ("2026 · 11 new trios"), the bar chart and the year chips stay.
  - The season list shows the **latest 3** new trios of the selected season, then "All 11 this season ▾".
  - Each trio takes two lines: names on line 1, then a small caps race line ("R15 · AZERBAIJAN") on line 2.
  - The trio stays a link to Combinations.
  - It must still be possible to reach every season on a phone (today: bars, chips and the `tl-select` dropdown).
- **Names in that list: "N2 · Surname only"** (`timeline-names.html`):
  - Surnames only, no team colours, no codes, e.g. "Frentzen / Häkkinen / Schumacher". Long trios wrap only at a slash, never mid-name.
  - An initial is added only when another driver with the same surname is among **that season's podium finishers, from every podium in `podiums.json`, not only the new trios** ("G. Hill" and "P. Hill" in 1962, "M. Schumacher" and "R. Schumacher" in 1999). This overrides the rule written on the N2 mockup card, which only checked within the same trio and so left "Bandini / McLaren / Hill" ambiguous. The owner picked N2 after that ambiguity was pointed out and was told this season-wide fix in chat. Compute the display surnames at build time and embed them in the season data, so `podigami.js` needs no surname logic.
  - Surnames must handle particles and suffixes: "de Cesaris", "de Angelis", "de la Rosa", "von Trips", "Piquet Jr.". Today's last-word split gets these wrong.
  - Display names go through `driver_name()` / `displayName` (e.g. "Kimi Antonelli" → "Antonelli").
- **Explore:**
  - On phones, one panel replaces both hook rows (`hook_row_board` and `hook_row_timeline`) and the "Keep exploring" grid.
  - Five one-line rows, each with a secondary plate, one stat and a chevron, linking to the page:
    - COMBINATIONS: **755** trios since 1950
    - OVERDUE: **top overdue trio surnames** · N races
    - UNLIKELIEST: **top trio surnames** · year
    - SOULMATES: **pair** · N together
    - SCORECARD: Every prediction, graded
  - The stats are the ones the hook cards already compute.
- **FAQ:** on phones, one collapsed row, "Questions & answers  8 ▾", that opens today's FAQ list. The FAQ's JSON-LD is unaffected.
- **Footer:** unchanged.

### 7. Everything else

Desktop landing page and the other five pages get items 1–4: the mark, wordmark, badges and verdict. Nothing else changes.

## Constraints

- Static site: string-built HTML, `esc()` on all data, build reads only `data/`. All CSS and JS go through `_layout.asset()` (content-hash cache-busting). Don't add bare asset URLs.
- Mobile breakpoint is `max-width: 600px`. Check phone layouts with `WIDER_FONT` from `tests/test_e2e.py` too. Segoe UI here is narrower than most visitors' fonts.
- **Light theme:** every badge, the wordmark and the verdict need light-theme values via tokens, with readable contrast in both themes. Use the `optimal-color-contrast` skill when writing the badge CSS.
- Trio-name markup convention (#319): the "/" lives inside the preceding name's nowrap span. The phone timeline list is now inline-wrapping surnames rather than one-driver-per-line stacked names, so update the CSS and JS that stack it (`displayName`'s `narrow` branch, `.pdriver` rules).
- The `#faq` anchor and any in-page links to the FAQ must open the collapsed FAQ on phones. A known phone-only FAQ jump bug only reproduced over HTTP, not `file://`.
- The hero's post-qualifying state ("Updated after qualifying · was X%", grid "P3" chips) must still render sensibly in the compact phone box.
- Tests assert generated HTML. Update `test_build_output.py`, `test_build_podigami.py`, `test_mobile_css.py` and the e2e tests where markup changes.
- Ship per `CLAUDE.md`: a `RELEASE_NOTES.md` entry, and `README.md` where it shows or describes the logo or landing page.

## Process requirement: visual sign-off before going wide

The owner judges visually and fast, and a wide restyle was reverted before. The plan has two checkpoints, each with real screenshots of the built site (desktop and 390px phone, dark and light themes).

1. **Checkpoint 1: the core look.** Build the header (mark and wordmark), the landing page's race card with the verdict, and the badge family on the landing page. Get the owner's OK before going further.
2. **Checkpoint 2: everything else.** Apply the badges to the other five pages, including the scorecard tags, combos race pills and shared-car marker, and do the phone landing-page restructure. Show screenshots of every changed page before opening the PR.

## Calls made in brainstorming (owner hasn't explicitly confirmed; check these)

- Set A plate styling applies to **every** badge-like element on every page, not only the ones in the mockups.
- The verdict count includes the race just run, as scorigami does: a trio's second podium together reads "(2)".
- The verdict has a plain tooltip, e.g. "This trio's 3rd podium together" / "First time this trio has shared a podium".
- The wordmark is live text in the site's existing system font stack, with no new web font. It will look slightly different on iPhone/Android than on Windows, where it was approved.
- The favicon, apple-touch icon and link-preview image are redrawn with the plate. The link preview uses the stacked wordmark and the existing tagline "Every F1 podium combination since 1950."
- Phone trimming is CSS/markup at the `600px` breakpoint. Desktop markup and content stay as they are.
- On phones, when the next race has a status (live, awaiting results), the start time on the right of the race strip hides. The status plate shows on its own line under the race name, where `.nr-status` already sits.
- The round label reads "R19 / 23" at every width, replacing "Round 19 / 23".
- The page `<h1>` stays in the DOM on phones (visually hidden) for SEO and screen readers.
- The "red is for new" rule covers badges only. Every non-badge red stays: the nav line, the card rail, the red "F1" in page titles, links.
- Mockup details the document doesn't name are sketches. Today's styling stays, including the dimmed repeat rows on the trio board.
- Combos race pills and the shared-car marker take the plate shape only, with no new typography and no added word.
- The surname-initial rule is season-wide across all of that season's podium finishers.

## Left to the builder

- How phone and desktop variants are produced (shared markup with CSS, or a second phone-only fragment), as long as there's no duplicated visible content and no layout shift.
- Exact light-theme badge colours, within the tokens and contrast rules.
- How the PNG icons are generated: a reproducible script is preferred to hand-made files, for example rendering the SVG with Playwright.
- The short race label format in the timeline list ("R15 · Azerbaijan" vs "R15 · Azerbaijan GP").
- The expand/collapse mechanics for "All 15", "All 11 this season" and the FAQ row (`<details>` or the existing toggle pattern).
- The apple-touch icon's corner treatment. iOS rounds icons itself, so a full-bleed square plate is probably right there.
