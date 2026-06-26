# Design: Content-based `lastmod` in sitemap.xml

**Date:** 2026-06-26
**Issue:** [#85](https://github.com/NikoKiru/f1podigami/issues/85)

## Problem

`_write_sitemap_xml()` in `src/build_site.py` stamps every URL with `datetime.now(UTC)` on every build. Since the site rebuilds on every push and weekly via the data refresh, `lastmod` advances even when page content did not change — making the signal meaningless to crawlers.

## Decision

All four pages share one `lastmod`: the ISO date of the most recent completed race, derived from `schedule.json`. All pages update at the same cadence (after each race), so per-page granularity adds complexity for no real benefit.

The git-log approach was ruled out because the deploy workflow uses a shallow clone (`fetch-depth: 1`), which would return no output for files not touched in the most recent commit.

## Solution

Add a `_last_race_date()` helper to `src/build_site.py`:

```python
def _last_race_date() -> str:
    from datalib import load_schedule
    today = datetime.now(UTC).date().isoformat()
    races = load_schedule().races
    past = [r.date for r in races if r.date <= today]
    return max(past) if past else today
```

Replace the `today = datetime.now(UTC).strftime(...)` line in `_write_sitemap_xml()` with a call to `_last_race_date()`.

**Fallback:** If `schedule.json` contains no races with a past date (very start of a new season before Round 1), falls back to today's date — same behaviour as before.

## Scope

- **Changed:** `src/build_site.py` — one helper added, one line changed in `_write_sitemap_xml`.
- **Updated:** Any test in `tests/test_build_output.py` asserting on `sitemap.xml` content (currently expects today's date; must expect the last race date instead).
- **Not changed:** Page builders, datalib, data files, CI workflows.

## Testing

- `pytest -q` — existing sitemap tests updated to match the real race date.
- `python src/build_site.py` locally — verify `dist/sitemap.xml` contains the last race date, not today's date.
- `ruff check . && ruff format --check .` — lint clean.
