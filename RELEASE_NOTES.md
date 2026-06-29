# Release Notes

## 2026-06-29

### Features
- Add Playwright e2e suite for interactive JS: slider, combos filter/sort, theme, tooltips (#113)

### Improvements
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
