# Release Notes

## 2026-07-06

### Improvements
- SEO technical quick wins: the homepage now canonicalises on the bare site root (`…/f1podigami/`) in both its `<link rel="canonical">`/`og:url` tags and the sitemap, the landing page carries JSON-LD structured data (`WebSite` plus a `SportsEvent` for the next race while the season runs), the 404 page is marked `noindex`, every page gains `og:locale` + `og:image:alt`, and the dead `meta keywords` tag is gone (#185)

## 2026-07-05

### Fixes
- Auto-update no longer stalls one race behind when the Jolpica round-indexed results endpoint (`/{season}/{round}/results`) lags the aggregate feeds right after a race: `fetch_constructor_standings` now falls back to the last round that returns results (keeping the constructor overlay on), and `datalib._save` writes each dataset's canonical schema form so a payload that omits optional fields still round-trips byte-identically — previously the byte-identical test failed on the empty-constructor case, silently skipping the data PR and looping the guard forever (#178)
- Automated data updates now check out `main` in both `update.yml` jobs: the guard reads `main`'s `asOf` (the only one data PRs advance, preventing an endless re-update loop after the first post-race merge under the develop/main flow) and the data branch is cut from `main` so unpromoted `develop` commits can't ride along into a data PR (#175)

### Improvements
- `update.yml` no longer fails silently: the `auto/update-data` PR now opens **before** the validate/test gate (a bad-data run surfaces as a red PR whose required checks block auto-merge, instead of a silently-skipped step), and a new `notify-failure` job opens/refreshes a single deduplicated issue linking the failed run — so a stall pings a human within one cron tick instead of hiding in a red run (#183)
- Docs: CLAUDE.md now documents the auto-update silent-stall failure mode — a failing test gate in the `update` job skips the data PR, stalling the site one race behind while the guard loops — plus the Jolpica round-indexed endpoint lag that triggered it and a concrete diagnosis path (#182)
- Docs: CLAUDE.md prediction-model section now describes the live v2 rating engine (datasets, acceptance gate, tuned knobs, compact storage) instead of only the v1 Plackett–Luce model (#174)

### Features
- Prediction model v2: a dynamic Bayesian rating engine (driver + car Gaussian ratings filtered over every race classification since 1950 and qualifying since 1994, with DNF-hazard reliability, circuit chaos and Rao-Blackwellised podium simulation) now powers the landing-page prediction. On the frozen 2019–2026 test window it lifts exact-trio top-1 from 12.5% to 18.1%, top-3 from 29.4% to 35.0% and log-loss from 4.078 to 3.916 over the previous Plackett–Luce model, which remains as fallback. New committed datasets `race_results.json` + `qualifying.json` (compact storage), two new fetchers wired into the update pipeline, walk-forward ablation ladder + coordinate-descent tuner in `backtest.py`, and updated FAQ/README copy

## 2026-07-04

### Improvements
- Docs: CLAUDE.md page table now lists all five pages (`unlikeliest.html` was missing) and the new `_hooks.py` helper; stale "four pages" wording fixed there and in the `_layout.py` docstring (#170)
- Mobile nav is now a burger-button drawer that slides in from the left (pure-CSS core so it works without JS, with keyboard/aria/scroll-lock enhancements), replacing the cramped horizontal scroll strip (#168)

### Features
- Landing-page engagement overhaul: live-stat discovery hooks after each section, a "Keep exploring" grid, timeline quick-pick chips (first/record/current season), hero chance count-up and scroll-reveal (both honouring reduced-motion), FAQ deep links, and the previously orphaned Soulmates page added to the site nav and footer (#167)

## 2026-07-03

### Fixes
- Season-rollover proofing for the data pipeline: off-season updates no longer wipe `current_drivers.json` (which emptied the prediction hero, contenders and current-form panels all winter) or `constructor_standings.json` (which dropped team labels and the car overlay) — both now fall back to the latest season that actually has results (#165)
- `fetch_schedule` can no longer write an empty schedule in early January before the new calendar is published (that broke the next-race box and failed the data-integrity CI gate, stalling the automated updates); it falls back to the previous season instead (#165)
- Circuit outline matching now rejects matches beyond ~5 km, so a future circuit missing from the bundled f1-circuits dataset shows no track map instead of silently borrowing the nearest existing track's outline and length (#165)

### Improvements
- Once a season is complete, the schedule looks ahead to the next season's published calendar, so the landing page counts down to the new season opener over the winter instead of showing "season complete" (#165)
- Official F1 race-link matching is now partial per round: a brand-new race name (e.g. a 2027 venue) degrades only its own round to the Wikipedia fallback instead of the whole season, and the hardcoded cancelled-race table is no longer needed (#165)
- Pre-map flags for plausible future host countries (Thailand, Rwanda, Argentina, Vietnam, South Korea) and add a CI check that every mapped country has a committed flag SVG (#165)

## 2026-07-01

### Improvements
- Trim the landing page hero to a short slogan and move the podigami explainer (scorigami etymology, trio/race counts) into a new FAQ entry; also drop the same "only N have happened" framing from the page's meta description
- Show the year in the landing page's "last time" repeat pill (e.g. "last time 2025 R22 · Las Vegas Grand Prix") so a historical round isn't mistaken for the current season
- Raise unit-test coverage for `build_combos_html.py` and `backtest.py` from ~38% to ~98% with render-structure and numeric/shape assertions (#115)
- Enlarge the next-race track map on desktop so it fills the full height of its hero box instead of being capped at 88px, while keeping the box size and mobile layout unchanged
- Sync README.md with the current pipeline (Unlikeliest/Soulmates pages, file map, test count, update.yml cadence) and add a CLAUDE.md rule keeping it current on future PRs
- Race-report links across the site now point to official Formula 1 result pages instead of Wikipedia, with a per-race Wikipedia fallback (#138)
- Extend the official F1 links to the 2023 season by skipping the cancelled, never-held Emilia Romagna GP that had blocked the season's count match (#140)

### Fixes
- Fix official F1 race-report links pointing at the **wrong race**: rounds were mapped to slugs by sorting F1's internal race IDs, which are not assigned in round order, scrambling ~83 links across 7+ seasons (e.g. 2021/2022/2025 and the "last race" box). Rounds are now paired with slugs by race identity (`race_identity.match_season`), a whole-dataset guardrail test blocks any wrong link, and the committed map is corrected (#158)
- Make the "Last race" name on the landing page clickable, linking out to Wikipedia just like the "Next race" name does
- Point the landing-page timeline slider's race links to official F1 pages too — they were still linking to Wikipedia (#140)
- Remove stale `_layout.py` comment describing a Soulmates nav "trailing arrow" that was removed along with the nav link itself (#151)
- Escape dynamic strings in `build_soulmates_html.py` with `esc()`, matching every sibling builder, and neutralize `</script>` in the landing page's embedded JSON blob so it can't prematurely close its `<script>` tag (#150)
- Truncate long team names (e.g. "Cadillac F1 Team") to a single line in the mobile hero driver cards, so one card no longer grows taller than its siblings (#149)
- Fix the prediction model's teammate "halo" blend silently no-oping for a whole constructor when 3 driverIds are tracked for it during a mid-season driver-swap window — it now blends each driver toward the average of their teammates instead of requiring exactly 2 (#148)
- `fetch_driver_races.py`'s driver pool now also includes every driverId that appears in any `combos.json` trio, fixing `compute_unlikeliest.py` silently skipping ~51% of historical podium trios (149 driverIds) whose race history fell outside the top-60-by-podium-count pool (#147). Data regenerates on the next successful automated update.

## 2026-06-29

### Improvements
- Rework the Overdue page into uniform cards matching the Unlikeliest design: each leads with the expected co-podiums score ("8.2×"), driver names abbreviate to `E. Ocon` on narrow screens, and the meaningless bar and raw decimal score are gone

### Features
- Add **Unlikeliest** page: the most statistically improbable podium trios that actually happened, ranked by races-together × career podium rates, with a hero for the single biggest fluke (2020 Sakhir GP) and a per-trio breakdown of why the maths said no
- Add Playwright e2e suite for interactive JS: slider, combos filter/sort, theme, tooltips (#113)

### Fixes
- Fix doubled numbering in "Most likely next combinations" list — `.cand-*` CSS was accidentally removed in #127 (#128)
- Fix hero layout at ~602px: collapse hero to single column at 720px so driver cards are side by side in the nav-wrap dead zone (#116)

### Improvements
- Rework the Unlikeliest page into uniform improbability cards: each leads with the odds the trio would *ever* share a podium (`1 in N`, from the Poisson tail of the expected co-podium count), with every field in a fixed place; driver names abbreviate to `E. Ocon` on narrow screens and the meaningless score bar is gone
- Adopt a `develop` → `main` branching workflow (develop is the default branch; main remains the release/deploy branch) and document it in CLAUDE.md
- Remove redundant stat boxes from combos page header — info already lives on the landing page
- Harden CI: add `datalib.validate` gate to `deploy.yml`, `actionlint` workflow linter, and SHA-pin all action refs (#114)

## 2026-06-28

### Improvements
- Added release notes page with footer link across all pages
- Run Playwright e2e test in CI instead of silently skipping it

### Fixes
- Align timeline slider thumb exactly under the sparkline bars (#110)
- Cache-bust CSS/JS asset URLs with a content hash (#109)
- Collapse combos stat cards into a slim strip on mobile (#107)
- Drive next/last race hero from results, not the calendar (#105)
- Clamp info tooltip within viewport on mobile (#103)
- Clean up sort indicator arrows on combos table header (#102)

### Features
- Link happened-trios to their stats on the combos page (#108)
- Poll for race data every 15 min instead of hourly (#106)
- Abbreviate driver names on mobile combos cards (#101)
- Race-aware hourly data updates via auto-merged PR (#97)
