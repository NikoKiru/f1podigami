# Release Notes

## 2026-07-01

### Improvements
- Sync README.md with the current pipeline (Unlikeliest/Soulmates pages, file map, test count, update.yml cadence) and add a CLAUDE.md rule keeping it current on future PRs
- Race-report links across the site now point to official Formula 1 result pages instead of Wikipedia, with a per-race Wikipedia fallback (#138)
- Extend the official F1 links to the 2023 season by skipping the cancelled, never-held Emilia Romagna GP that had blocked the season's count match (#140)

### Fixes
- Make the "Last race" name on the landing page clickable, linking out to Wikipedia just like the "Next race" name does
- Point the landing-page timeline slider's race links to official F1 pages too — they were still linking to Wikipedia (#140)

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
