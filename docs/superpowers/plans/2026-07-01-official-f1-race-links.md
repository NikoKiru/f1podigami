# Official F1 Race Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every Wikipedia race-report link on the site with the official `formula1.com` result page, keeping Wikipedia as a per-race fallback so no link ever dies.

**Architecture:** A new committed dataset `data/f1_race_links.json` (`season → round → {id, slug}`) is built by a new fetcher that parses F1's public per-year results index (robots-allowed). A new pure helper `race_url(links, season, rnd, race_name)` in `_layout.py` builds the F1 URL from that map and falls back to `wiki_url()` when a race is absent. All race-link call sites (combos, unlikeliest, landing next/last/repeat) switch to it; the "scorigami" concept link stays on Wikipedia. The fetcher is wired into `update.py`, exits 0 on any network failure (never blocking the post-race auto-deploy), and produces byte-identical output so it causes no PR churn.

**Tech Stack:** Python 3.11–3.13, `requests`, Pydantic v2 (`src/datalib`), pytest, ruff. String-based HTML builders. Spec: `docs/superpowers/specs/2026-07-01-official-f1-race-links-design.md`.

---

## File Structure

**Create:**
- `src/fetch/fetch_race_links.py` — fetch + parse F1 index pages → `data/f1_race_links.json`. Pure parsing/mapping functions + a network layer + graceful `main()`.
- `data/f1_race_links.json` — the committed map (starts as `{}`, filled by backfill).
- `tests/test_race_links.py` — unit tests for `race_url()` and the fetcher's pure functions, plus a "no dead links" dist check.

**Modify:**
- `src/datalib/schemas.py` — add `RaceLink`.
- `src/datalib/repository.py` — REGISTRY entry + `load_race_links` / `save_race_links`.
- `src/datalib/__init__.py` — export `RaceLink`, `load_race_links`, `save_race_links`.
- `src/build/_layout.py` — add `race_url()`.
- `src/build/build_combos_html.py` — use `race_url` for race pills.
- `src/build/build_unlikeliest.py` — use `race_url` for the race link.
- `src/build/build_podigami_html.py` — use `race_url` for next-race, last-race, repeat link.
- `src/update.py` — add the fetch step; pass `--backfill` under `--full`.
- `tests/test_build_links.py` — flip the combos race-link assertion to F1.
- `tests/test_next_race.py` — update landing link assertions.
- `tests/test_build_unlikeliest.py` — add an F1-URL case.
- `RELEASE_NOTES.md` — changelog entry.

---

## Task 1: New dataset — schema, repository plumbing, committed empty map

**Files:**
- Modify: `src/datalib/schemas.py` (after `RaceRef`, ~line 27)
- Modify: `src/datalib/repository.py` (REGISTRY ~line 34; loaders ~line 137)
- Modify: `src/datalib/__init__.py`
- Create: `data/f1_race_links.json`
- Test: `tests/test_race_links.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_race_links.py`:

```python
"""Tests for the official F1 race-links dataset, the race_url helper, and the
fetch_race_links pure functions."""

import json

from datalib import DATA_DIR, REGISTRY, RaceLink, load_race_links


# --- dataset schema + plumbing ------------------------------------------------


def test_racelink_schema_validates_and_rejects_extra():
    ok = RaceLink.model_validate({"id": "1288", "slug": "austria"})
    assert ok.id == "1288" and ok.slug == "austria"


def test_f1_race_links_registered_and_present():
    assert "f1_race_links.json" in REGISTRY
    assert (DATA_DIR / "f1_race_links.json").exists()


def test_f1_race_links_roundtrips_through_loader():
    # load returns nested RaceLink models keyed by season -> round
    links = load_race_links()
    assert isinstance(links, dict)
    raw = json.loads((DATA_DIR / "f1_race_links.json").read_text(encoding="utf-8"))
    for season, rounds in raw.items():
        for rnd, entry in rounds.items():
            assert links[season][rnd].id == entry["id"]
            assert links[season][rnd].slug == entry["slug"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_race_links.py -q`
Expected: FAIL — `ImportError: cannot import name 'RaceLink'`.

- [ ] **Step 3: Add the `RaceLink` schema**

In `src/datalib/schemas.py`, immediately after the `RaceRef` class (after line 26), add:

```python
class RaceLink(_Base):
    """Official F1 result-page identifiers for one race (see fetch_race_links)."""

    id: str
    slug: str
```

- [ ] **Step 4: Register + add loader/saver**

In `src/datalib/repository.py`:

Add to the schema import block (with the other schema names):

```python
    RaceLink,
```

Add to `REGISTRY` (after the `constructor_standings.json` line):

```python
    "f1_race_links.json": TypeAdapter(dict[str, dict[str, RaceLink]]),
```

Append after `save_model_eval` (~line 137):

```python
def load_race_links() -> dict[str, dict[str, RaceLink]]:
    return _load("f1_race_links.json")


def save_race_links(data: Any) -> None:
    _save("f1_race_links.json", data)
```

- [ ] **Step 5: Export from the package**

In `src/datalib/__init__.py`: add `load_race_links,` and `save_race_links,` to the `from .repository import (...)` block; add `RaceLink,` to the `from .schemas import (...)` block; and add `"RaceLink"`, `"load_race_links"`, `"save_race_links"` to `__all__`.

- [ ] **Step 6: Create the committed empty map**

Create it via the saver so the on-disk bytes exactly match what the round-trip test expects (no trailing newline):

Run: `PYTHONPATH=src python -c "from datalib import save_race_links; save_race_links({})"`
Expected: `data/f1_race_links.json` now contains exactly `{}` (two bytes).

- [ ] **Step 7: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_race_links.py tests/test_datalib.py -q`
Expected: PASS (including `test_dataset_roundtrips_byte_identical[f1_race_links.json]` and `test_registry_covers_every_committed_dataset`).

- [ ] **Step 8: Commit**

```bash
git add src/datalib/schemas.py src/datalib/repository.py src/datalib/__init__.py data/f1_race_links.json tests/test_race_links.py
git commit -m "feat(datalib): add f1_race_links dataset (empty map + schema)"
```

---

## Task 2: `race_url()` helper in `_layout.py`

**Files:**
- Modify: `src/build/_layout.py` (after `wiki_url`, ~line 49)
- Test: `tests/test_race_links.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_race_links.py`:

```python
from build import _layout  # noqa: E402  (RaceLink is already imported at the top of this file)


# --- race_url helper ----------------------------------------------------------

_LINKS = {"2026": {"8": RaceLink(id="1288", slug="austria")}}


def test_race_url_builds_official_f1_url_when_mapped():
    url = _layout.race_url(_LINKS, "2026", "8", "Austrian Grand Prix")
    assert url == "https://www.formula1.com/en/results/2026/races/1288/austria/race-result"


def test_race_url_falls_back_to_wikipedia_when_unmapped():
    url = _layout.race_url(_LINKS, "2026", "9", "British Grand Prix")
    assert url == "https://en.wikipedia.org/wiki/2026_British_Grand_Prix"


def test_race_url_accepts_int_round():
    url = _layout.race_url(_LINKS, "2026", 8, "Austrian Grand Prix")
    assert url.endswith("/races/1288/austria/race-result")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_race_links.py -q -k race_url`
Expected: FAIL — `AttributeError: module 'build._layout' has no attribute 'race_url'`.

- [ ] **Step 3: Implement `race_url`**

In `src/build/_layout.py`, immediately after `wiki_url` (after line 48), add:

```python
def race_url(links: dict, season: str, rnd, race_name: str) -> str:
    """Official F1 result-page URL for a race, falling back to Wikipedia.

    ``links`` is the ``season -> round -> RaceLink`` map from
    ``datalib.load_race_links``. A race absent from the map (data gap, brand-new
    race, or a season F1 and we disagree on) falls back to its Wikipedia report.
    """
    link = links.get(season, {}).get(str(rnd))
    if link is not None:
        return (
            f"https://www.formula1.com/en/results/{season}/races/"
            f"{link.id}/{link.slug}/race-result"
        )
    return wiki_url(season, race_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/test_race_links.py -q -k race_url`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/build/_layout.py tests/test_race_links.py
git commit -m "feat(build): add race_url helper (F1 URL with wiki fallback)"
```

---

## Task 3: The fetcher — `fetch_race_links.py` (pure functions + graceful main)

**Files:**
- Create: `src/fetch/fetch_race_links.py`
- Test: `tests/test_race_links.py`

- [ ] **Step 1: Write the failing tests for the pure functions**

Append to `tests/test_race_links.py`:

```python
from fetch import fetch_race_links as frl  # noqa: E402


# --- fetch_race_links pure logic ----------------------------------------------

_SAMPLE_HTML = """
<a href="/en/results/2026/races/1288/austria/race-result">latest</a>
<ul>
  <a href="/en/results/2026/races/1279/australia/race-result">AUS</a>
  <a href="/en/results/2026/races/1279/australia/race-result">AUS dup</a>
  <a href="/en/results/2026/races/1288/austria/race-result">AUT</a>
  <a href="/en/results/2026/races/1284/miami/race-result">MIA</a>
  <a href="/en/results/2025/races/1200/somewhere/race-result">other year</a>
</ul>
"""


def test_parse_race_links_dedupes_and_sorts_by_id():
    pairs = frl.parse_race_links(_SAMPLE_HTML, 2026)
    assert pairs == [("1279", "australia"), ("1284", "miami"), ("1288", "austria")]


def test_build_season_map_assigns_rounds_when_count_matches():
    pairs = [("1279", "australia"), ("1284", "miami"), ("1288", "austria")]
    m = frl.build_season_map(pairs, expected_count=3)
    assert m == {
        "1": {"id": "1279", "slug": "australia"},
        "2": {"id": "1284", "slug": "miami"},
        "3": {"id": "1288", "slug": "austria"},
    }


def test_build_season_map_empty_on_count_mismatch():
    pairs = [("1279", "australia"), ("1288", "austria")]
    assert frl.build_season_map(pairs, expected_count=3) == {}


def test_season_counts_uses_schedule_for_current_and_podiums_for_history():
    schedule = {"season": "2026", "races": [{"round": "1"}, {"round": "2"}]}
    podiums = [{"season": "1950"}, {"season": "1950"}, {"season": "2026"}]
    counts = frl.season_counts(schedule, podiums)
    assert counts[1950] == 2
    assert counts[2026] == 2  # schedule wins for the current season


def test_compute_targets_modes():
    counts = {1950: 7, 2025: 22, 2026: 24}
    existing = {"1950": {str(i): {} for i in range(1, 8)}}  # 1950 complete
    assert frl.compute_targets("incremental", existing, counts, 2026) == [(2026, 24)]
    # backfill: current + seasons missing/incomplete (1950 complete -> skipped)
    assert frl.compute_targets("backfill", existing, counts, 2026) == [(2026, 24), (2025, 22)]
    assert frl.compute_targets("refetch-all", existing, counts, 2026) == [
        (1950, 7), (2025, 22), (2026, 24)
    ]


def test_update_map_keeps_existing_on_fetch_failure():
    def boom(year):
        raise RuntimeError("network down")

    existing = {"2025": {"1": {"id": "9", "slug": "x"}}}
    out = frl.update_map(existing, [(2026, 22)], boom, sleep=0)
    assert out == existing  # unchanged; no crash


def test_update_map_adds_season_on_success():
    def ok(year):
        return _SAMPLE_HTML

    out = frl.update_map({}, [(2026, 3)], ok, sleep=0)
    assert out["2026"]["1"] == {"id": "1279", "slug": "australia"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_race_links.py -q -k "parse_race or season_map or season_counts or compute_targets or update_map"`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch.fetch_race_links'`.

- [ ] **Step 3: Write the fetcher**

Create `src/fetch/fetch_race_links.py`:

```python
"""Fetch official Formula 1 result-page identifiers for every race.

F1 publishes no API, so we read F1's public per-year results index
(https://www.formula1.com/en/results/{year}/races) — allowed by their
robots.txt — and extract each race's numeric ID + location slug from the
result-page URLs. The IDs are internal, sequential, and not derivable from our
own data, yet are required to build canonical links like
https://www.formula1.com/en/results/2026/races/1288/austria/race-result.

Writes data/f1_race_links.json: {season: {round: {"id","slug"}}}.

Design notes:
- Historic years are immutable: --backfill fetches only seasons missing or
  incomplete in the committed map; the default run refreshes only the current
  season. --refetch-all forces every season (manual, e.g. a URL-scheme change).
- Correctness rests on a count guard, not slug matching: F1 lists a year's races
  with monotonically increasing IDs, so sorting deduped IDs recovers round order.
  A season is trusted only when its race count matches ours; otherwise that whole
  season falls back to Wikipedia at render time. Slugs are NOT matched to our
  race names — they aren't derivable ("great-britain" vs "British Grand Prix").
- Network failures are non-fatal: the script keeps the committed map and exits 0,
  so a transient F1 outage can never block the automated post-race deploy.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from datalib import DATA_DIR, load_podiums, load_schedule, save_race_links  # noqa: E402

INDEX_URL = "https://www.formula1.com/en/results/{year}/races"
RESULT_RE = re.compile(r"/en/results/(\d{4})/races/(\d+)/([a-z0-9-]+)/race-result")
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1podigami/0.2 (https://github.com/NikoKiru/f1podigami)"
LINKS_PATH = DATA_DIR / "f1_race_links.json"


def parse_race_links(html_text: str, year: int) -> list[tuple[str, str]]:
    """(id, slug) pairs for ``year``, deduped and sorted ascending by numeric id.

    The raw index repeats races (a "latest race" selector) and is not in round
    order, but IDs increase with round within a year, so the sort recovers order.
    """
    seen: dict[str, str] = {}
    for y, rid, slug in RESULT_RE.findall(html_text):
        if int(y) == year and rid not in seen:
            seen[rid] = slug
    return sorted(seen.items(), key=lambda t: int(t[0]))


def build_season_map(pairs: list[tuple[str, str]], expected_count: int) -> dict[str, dict[str, str]]:
    """round -> {id, slug}. Empty (→ wiki fallback for the whole season) unless the
    race count matches ours, which is what proves the positional mapping correct."""
    if expected_count <= 0 or len(pairs) != expected_count:
        return {}
    return {str(i): {"id": rid, "slug": slug} for i, (rid, slug) in enumerate(pairs, 1)}


def season_counts(schedule: dict, podiums: list[dict]) -> dict[int, int]:
    """Expected race count per season: the full calendar for the current season
    (schedule), completed races for historic seasons (podiums)."""
    counts: dict[int, int] = {}
    for p in podiums:
        counts[int(p["season"])] = counts.get(int(p["season"]), 0) + 1
    counts[int(schedule["season"])] = len(schedule["races"])
    return counts


def compute_targets(
    mode: str, existing: dict, counts: dict[int, int], current_year: int
) -> list[tuple[int, int]]:
    """Which (year, expected_count) to fetch for the given mode."""
    if mode == "refetch-all":
        years = sorted(counts)
    elif mode == "backfill":
        years = [current_year] + [
            y
            for y in sorted(counts)
            if y != current_year and len(existing.get(str(y), {})) != counts[y]
        ]
        years = list(dict.fromkeys(years))  # dedupe, preserve order
    else:  # incremental
        years = [current_year]
    return [(y, counts[y]) for y in years if y in counts]


def fetch_index(year: int) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    url = INDEX_URL.format(year=year)
    for attempt in range(MAX_BACKOFF_RETRIES):
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.text
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = 2.0**attempt
            print(
                f"  [{resp.status_code}] backoff {wait:.1f}s ({attempt + 1}/{MAX_BACKOFF_RETRIES})",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"giving up on {url}")


def update_map(existing: dict, targets: list[tuple[int, int]], fetch_fn, sleep: float = 1.0) -> dict:
    """Refresh each (year, expected_count) target. A per-year failure or count
    mismatch never discards existing data or aborts — the year is left as-is."""
    result = {k: dict(v) for k, v in existing.items()}
    for i, (year, expected) in enumerate(targets):
        try:
            if i and sleep:
                time.sleep(sleep)
            season_map = build_season_map(parse_race_links(fetch_fn(year), year), expected)
        except Exception as exc:  # noqa: BLE001 - a bad fetch must not abort the run
            print(f"  warn: {year} fetch failed ({exc}); keeping existing", file=sys.stderr)
            continue
        if season_map:
            result[str(year)] = season_map
            print(f"  {year}: mapped {len(season_map)}/{expected}")
        else:
            print(
                f"  warn: {year} race-count mismatch (F1 vs ours); wiki fallback for the season",
                file=sys.stderr,
            )
    return result


def _ordered(m: dict) -> dict:
    """Deterministic key order (seasons + rounds ascending) for byte-stable output."""
    return {
        str(s): {str(r): m[str(s)][str(r)] for r in sorted(int(x) for x in m[str(s)])}
        for s in sorted(int(x) for x in m)
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument(
        "--backfill", action="store_true", help="also fill missing/incomplete historic seasons"
    )
    grp.add_argument(
        "--refetch-all", action="store_true", help="force re-fetch of every season (manual)"
    )
    args = ap.parse_args()
    mode = "refetch-all" if args.refetch_all else "backfill" if args.backfill else "incremental"

    existing: dict = {}
    if LINKS_PATH.exists():
        from datalib import load_race_links

        existing = {
            s: {r: {"id": link.id, "slug": link.slug} for r, link in rounds.items()}
            for s, rounds in load_race_links().items()
        }

    schedule = load_schedule().model_dump()
    podiums = [p.model_dump() for p in load_podiums()]
    counts = season_counts(schedule, podiums)
    current_year = int(schedule["season"])

    targets = compute_targets(mode, existing, counts, current_year)
    print(f"fetch_race_links: mode={mode}, {len(targets)} season(s)")
    new_map = _ordered(update_map(existing, targets, fetch_index))
    save_race_links(new_map)
    print(f"Wrote {LINKS_PATH} ({len(new_map)} seasons)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_race_links.py -q`
Expected: PASS (all fetcher pure-function tests + the earlier ones).

- [ ] **Step 5: Lint + format**

Run: `python -m ruff check src/fetch/fetch_race_links.py tests/test_race_links.py && python -m ruff format src/fetch/fetch_race_links.py tests/test_race_links.py`
Expected: no errors; formatting clean.

- [ ] **Step 6: Commit**

```bash
git add src/fetch/fetch_race_links.py tests/test_race_links.py
git commit -m "feat(fetch): add fetch_race_links (F1 index parser, graceful)"
```

---

## Task 4: Backfill the real map + verify coverage and live URLs

This task hits the network (F1.com). It is a one-time seed committed to git. No new pytest — verification is explicit commands.

**Files:**
- Modify (regenerate): `data/f1_race_links.json`

- [ ] **Step 1: Run the backfill**

Run: `PYTHONPATH=src python src/fetch/fetch_race_links.py --refetch-all`
Expected: prints `mode=refetch-all`, one `YYYY: mapped X/Y` line per season from 1950 to the current year, then `Wrote .../f1_race_links.json (N seasons)`. Watch stderr for any `race-count mismatch` warnings and note which seasons (those will use the Wikipedia fallback — acceptable, but sanity-check them).

- [ ] **Step 2: Validate the dataset**

Run: `PYTHONPATH=src python -m datalib.validate`
Expected: `Validated 12 datasets OK.` (11 existing + f1_race_links.json).

- [ ] **Step 3: Verify byte-identical round-trip + coverage**

Run:
```bash
PYTHONPATH=src python -c "
import json
from datalib import DATA_DIR, load_race_links
links = load_race_links()
seasons = len(links)
races = sum(len(v) for v in links.values())
print(f'seasons={seasons} mapped_races={races}')
# byte-identity guard (same check test_datalib runs)
from datalib.repository import REGISTRY
raw = (DATA_DIR/'f1_race_links.json').read_text(encoding='utf-8')
a = REGISTRY['f1_race_links.json']
red = json.dumps(a.dump_python(a.validate_python(json.loads(raw)), mode='json'), indent=2, ensure_ascii=False)
print('byte-identical:', red == raw)
"
```
Expected: a plausible `seasons=` (≈77) and `mapped_races=` (≈1100) count, and `byte-identical: True`. If `byte-identical` is False, STOP — the fetcher's key ordering is off; fix `_ordered` before continuing.

- [ ] **Step 4: Live spot-check that generated URLs resolve**

Run:
```bash
PYTHONPATH=src python -c "
import requests
from datalib import load_race_links
links = load_race_links()
samples = []
for season in sorted(links, key=int)[:1] + sorted(links, key=int)[-1:]:
    for rnd in sorted(links[season], key=int)[:1]:
        l = links[season][rnd]
        samples.append(f'https://www.formula1.com/en/results/{season}/races/{l.id}/{l.slug}/race-result')
for u in samples:
    r = requests.get(u, headers={'User-Agent':'f1podigami/0.2'}, timeout=30, allow_redirects=True)
    print(r.status_code, r.url == u, u)
"
```
Expected: each line prints `200 True <url>` (HTTP 200, no redirect to a generic/404 page). If any is not 200, note the season/round; it likely indicates a slug/ID issue for that era to investigate.

- [ ] **Step 5: Run the full test + build gate**

Run: `PYTHONPATH=src python -m pytest -q && python src/build_site.py`
Expected: all tests pass; build writes `dist/*.html` with return code 0.

- [ ] **Step 6: Commit the seeded map**

```bash
git add data/f1_race_links.json
git commit -m "data: backfill official F1 race-link map (1950-present)"
```

---

## Task 5: Wire the combos page to `race_url`

**Files:**
- Modify: `src/build/build_combos_html.py` (imports ~line 16; `render_race_pills` ~line 30; `render_combo` ~line 65; `main` ~line 103)
- Test: `tests/test_build_links.py` (`test_race_report_links_are_wikipedia` ~line 75)

- [ ] **Step 1: Update the failing dist test first**

In `tests/test_build_links.py`, replace `test_race_report_links_are_wikipedia` (lines 75-81) with:

```python
def test_race_report_links_are_official_f1(dist):
    html = (dist / "combos.html").read_text(encoding="utf-8")
    links = re.findall(r'<a class="race-pill" href="([^"]+)"', html)
    assert links, "combos page should have race-report links"
    for url in links:
        # every pill links to F1's result page, or (rarely) the wiki fallback
        assert url.startswith(
            "https://www.formula1.com/en/results/"
        ) or url.startswith("https://en.wikipedia.org/wiki/")
        assert " " not in url
    # the whole point of the feature: the vast majority resolve to F1
    f1 = [u for u in links if "formula1.com" in u]
    assert len(f1) > len(links) // 2, "expected most race links to be official F1 URLs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_build_links.py::test_race_report_links_are_official_f1 -q`
Expected: FAIL — pills are still `en.wikipedia.org`, so the `len(f1) > ...` assertion fails.

- [ ] **Step 3: Switch combos to `race_url`**

In `src/build/build_combos_html.py`:

In the `from _layout import (...)` block, **replace** the `wiki_url,` line (line 22) with `race_url,` — `wiki_url` is no longer referenced directly in this file after the switch (leaving it would trip ruff F401), and `race_url` calls it internally for the fallback:

```python
    race_url,
```

Add `load_race_links` to the datalib import (line 25):

```python
from datalib import Combo, RaceRef, load_combos, load_podiums, load_race_links  # noqa: E402
```

Change `render_race_pills` (line 30) signature and the pill href:

```python
def render_race_pills(races: list[RaceRef], links: dict | None = None) -> str:
    """Group races by season; each season gets a row with year + race pills."""
    import html

    links = links or {}
    races_sorted = sorted(races, key=lambda r: (int(r.season), int(r.round)))
    parts: list[str] = []
    for season, group in itertools.groupby(races_sorted, key=lambda r: r.season):
        group_list = list(group)
        pills = "".join(
            f'<a class="race-pill" href="{html.escape(race_url(links, r.season, r.round, r.raceName), quote=True)}"'
            f' target="_blank" rel="noopener"'
            f' title="{html.escape(r.season + " " + r.raceName, quote=True)} &mdash; race report">'
            f'<span class="round">R{html.escape(r.round)}</span>'
            f"{html.escape(short_race_name(r.raceName))}"
            f"</a>"
            for r in group_list
        )
        ct = len(group_list)
        ct_html = f'<span class="ct">x{ct}</span>' if ct > 1 else ""
        parts.append(
            f'<div class="season-row">'
            f'<div class="season-label">{html.escape(season)}{ct_html}</div>'
            f'<div class="race-list">{pills}</div>'
            f"</div>"
        )
    return "".join(parts)
```

Change `render_combo` (line 65) to accept + forward `links`:

```python
def render_combo(rank: int, combo: Combo, links: dict | None = None) -> str:
```

and its detail row (line 97):

```python
        f'<div class="detail-inner">{render_race_pills(combo.races, links)}</div>'
```

In `main` (line 103), load the map and pass it into the row loop (replace line 112):

```python
    links = load_race_links()
    rows_html = "\n".join(render_combo(i, c, links) for i, c in enumerate(combos, 1))
```

Because `build_combos_html` no longer exposes `wiki_url`, repoint its unit tests in `tests/test_units.py` to `_layout`. Add this import near the top (after line 5, `from build import build_combos_html as bc`):

```python
from build import _layout  # noqa: E402
```

Then in the two `wiki_url` tests, change `bc.wiki_url(` to `_layout.wiki_url(` — at line 29 (`assert bc.wiki_url(season, name) == expected` → `assert _layout.wiki_url(season, name) == expected`) and line 33 (`url = bc.wiki_url("2021", "São Paulo Grand Prix")` → `url = _layout.wiki_url("2021", "São Paulo Grand Prix")`). Leave the `short_race_name` tests using `bc`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_build_links.py tests/test_units.py -q`
Expected: PASS (`test_race_report_links_are_official_f1`, the determinism test, and the repointed `wiki_url` unit tests).

- [ ] **Step 5: Lint/format + commit**

```bash
python -m ruff check src/build/build_combos_html.py tests/test_build_links.py tests/test_units.py
python -m ruff format src/build/build_combos_html.py tests/test_build_links.py tests/test_units.py
git add src/build/build_combos_html.py tests/test_build_links.py tests/test_units.py
git commit -m "feat(combos): link race pills to official F1 result pages"
```

---

## Task 6: Wire the unlikeliest page to `race_url`

**Files:**
- Modify: `src/build/build_unlikeliest.py` (imports ~line 26; `_race_link` ~line 76; `render_card` ~line 95; `render_cards` ~line 120; `main` ~line 127)
- Test: `tests/test_build_unlikeliest.py`

- [ ] **Step 1: Write the failing test (F1 URL when links provided)**

In `tests/test_build_unlikeliest.py`, add after `test_render_card_has_every_field_in_place` (after line 83):

```python
def test_render_card_uses_official_f1_url_when_links_present():
    from datalib import RaceLink

    e = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1])
    links = {"2020": {"1": RaceLink(id="1045", slug="austria")}}
    html = bu.render_card(1, e, links=links)
    assert "https://www.formula1.com/en/results/2020/races/1045/austria/race-result" in html
```

Note: the existing `test_render_card_has_every_field_in_place` (line 80) still asserts the Wikipedia URL — that is correct and intended, because it calls `render_card` without `links`, exercising the fallback. Leave it unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_build_unlikeliest.py::test_render_card_uses_official_f1_url_when_links_present -q`
Expected: FAIL — `render_card()` got an unexpected keyword argument `links`.

- [ ] **Step 3: Thread `links` through the render chain**

In `src/build/build_unlikeliest.py`:

Change the `from _layout import` line (line 26) — **replace** `wiki_url` with `race_url` (`wiki_url` is no longer referenced directly here; `race_url` uses it internally):

```python
from _layout import FOOTER, abbr_name, asset, head, nav, race_url  # noqa: E402
```

Change the datalib import (line 28) to add `load_race_links`:

```python
from datalib import UnlikeliestTrio, load_race_links, load_unlikeliest  # noqa: E402
```

Replace `_race_link` (lines 76-83):

```python
def _race_link(e: UnlikeliestTrio, links: dict | None = None) -> str:
    h = e.happened
    url = race_url(links or {}, h.season, h.round, h.raceName)
    label = f"{esc(h.season)} {esc(h.raceName)}"
    return (
        f'<a class="race-link" href="{html.escape(url, quote=True)}" target="_blank" '
        f'rel="noopener" title="{label} &mdash; race report">{label}</a>'
    )
```

Update `render_card` (line 95) signature + the `_race_link` call (line 108):

```python
def render_card(rank: int, e: UnlikeliestTrio, hero: bool = False, links: dict | None = None) -> str:
```
```python
        f'<span class="un-race">{_race_link(e, links)}</span>'
```

Update `render_cards` (line 120) signature + call (line 123):

```python
def render_cards(entries: list[UnlikeliestTrio], links: dict | None = None) -> str:
    if not entries:
        return '<p class="panel-sub">No trios.</p>'
    cards = [render_card(i, e, hero=(i == 1), links=links) for i, e in enumerate(entries, 1)]
    return f'<ol class="uncard-list">{"".join(cards)}</ol>'
```

In `main` (line 130), load + pass links:

```python
    body = render_cards(data.trios, load_race_links())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_build_unlikeliest.py -q`
Expected: PASS (new F1 test + the existing fallback test still green).

- [ ] **Step 5: Lint/format + commit**

```bash
python -m ruff check src/build/build_unlikeliest.py tests/test_build_unlikeliest.py
python -m ruff format src/build/build_unlikeliest.py tests/test_build_unlikeliest.py
git add src/build/build_unlikeliest.py tests/test_build_unlikeliest.py
git commit -m "feat(unlikeliest): link races to official F1 result pages"
```

---

## Task 7: Wire the landing page (next-race, last-race name, repeat link)

**Files:**
- Modify: `src/build/build_podigami_html.py` (imports; `render_next_race` ~line 120; `render_last_race` ~line 188; `main` ~line 503)
- Test: `tests/test_next_race.py`

- [ ] **Step 1: Update the failing landing tests first**

In `tests/test_next_race.py`:

Replace the wiki-link assertion in `test_render_next_race_box_contents` (line 139) — the next-race name now comes from `race_url`; with no links the SCHED fixture's round-2 race ("B GP") falls back to Wikipedia:

```python
    assert 'href="https://en.wikipedia.org/wiki/2026_B_GP"' in html  # race_url wiki fallback
```

Replace `test_render_last_race_name_links_to_schedule_url_when_present` (lines 227-242) with a version that reflects `race_url` (fallback with no links, F1 with links):

```python
def test_render_last_race_name_links_via_race_url_fallback():
    # With no links map, the last-race name falls back to the Wikipedia report.
    podiums = [
        {
            "season": "2026",
            "round": "2",
            "raceName": "B GP",
            "p1": {"driverId": "russell", "name": "George Russell"},
            "p2": {"driverId": "verstappen", "name": "Max Verstappen"},
            "p3": {"driverId": "antonelli", "name": "Andrea Kimi Antonelli"},
        }
    ]
    html = bp.render_last_race(SCHED, podiums, [], {}, [])
    assert '<a class="lr-name" href="https://en.wikipedia.org/wiki/2026_B_GP"' in html


def test_render_last_race_name_links_to_official_f1_when_mapped():
    from datalib import RaceLink

    podiums = [
        {
            "season": "2026",
            "round": "2",
            "raceName": "B GP",
            "p1": {"driverId": "russell", "name": "George Russell"},
            "p2": {"driverId": "verstappen", "name": "Max Verstappen"},
            "p3": {"driverId": "antonelli", "name": "Andrea Kimi Antonelli"},
        }
    ]
    links = {"2026": {"2": RaceLink(id="1280", slug="china")}}
    html = bp.render_last_race(SCHED, podiums, [], {}, [], links=links)
    assert (
        '<a class="lr-name" href="https://www.formula1.com/en/results/2026/races/1280/china/race-result"'
        in html
    )
```

`test_render_last_race_name_links_to_constructed_wiki_url_when_off_schedule` (line 245) needs **no change** — with no links it still falls back to `wiki_url("2025", "Abu Dhabi GP")`, matching its existing assertion.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_next_race.py -q -k "next_race_box or race_url or official_f1"`
Expected: FAIL — `render_last_race()`/`render_next_race()` don't accept `links`, and the next-race box still emits `href="http://x"`.

- [ ] **Step 3: Add `links` to the imports + `render_next_race`**

In `src/build/build_podigami_html.py`, change the `_layout` import (line 20) to add `race_url`:

```python
from _layout import FOOTER, asset, head, nav, race_url  # noqa: E402  (needs the sys.path entry above)
```

Add `load_race_links,` to the `from datalib import (...)` block (lines 24-32), after the `load_podiums,` line:

```python
    load_race_links,
```

Change `render_next_race` (line 120) signature:

```python
def render_next_race(schedule: dict, asof: dict | None = None, links: dict | None = None) -> str:
```

Replace the name-link block (lines 130-135):

```python
    name = esc(nxt["raceName"])
    url = race_url(links or {}, schedule.get("season", ""), nxt["round"], nxt["raceName"])
    name_html = f'<a href="{esc(url)}" target="_blank" rel="noopener">{name}</a>'
```

- [ ] **Step 4: Update `render_last_race` (name link + repeat link)**

Change `render_last_race` (lines 188-194) signature to add `links`:

```python
def render_last_race(
    schedule: dict,
    podiums: list[dict],
    combos: list[dict],
    meta: dict,
    driver_form: list[dict],
    links: dict | None = None,
) -> str:
    links = links or {}
```

Replace the last-race name URL (lines 215-217) — note this also removes the local variable that shadowed the imported `wiki_url`:

```python
    name_url = race_url(links, pod["season"], last["round"], last["raceName"])
```

Update the repeat "last time" link (lines 254-257) to use `race_url`:

```python
        repeat_url = race_url(
            links, second_last["season"], second_last["round"], second_last["raceName"]
        )
```

and change its usage (line 260) from `href="{esc(wiki)}"` to:

```python
            f' &middot; last time <a class="lr-link" href="{esc(repeat_url)}"'
```

Update the last-race `<a class="lr-name" ...>` (line 272) to use the new variable name:

```python
        f'<a class="lr-name" href="{esc(name_url)}" target="_blank" rel="noopener">'
```

- [ ] **Step 5: Load + pass links in `main`**

In `main` (lines 522-532), after the schedule load, add the links load and pass it to both renderers:

```python
    schedule = {}
    if (DATA_DIR / "schedule.json").exists():
        schedule = load_schedule().model_dump()
    links = load_race_links()
    next_race = render_next_race(schedule, data.get("asOf"), links) if schedule else ""
    combos_dicts = [c.model_dump() for c in combos_list]
    podiums_dicts = [p.model_dump() for p in podiums_list]
    last_race = (
        render_last_race(schedule, podiums_dicts, combos_dicts, meta, data["driverForm"], links)
        if schedule
        else ""
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_next_race.py -q`
Expected: PASS.

- [ ] **Step 7: Full suite + build**

Run: `PYTHONPATH=src python -m pytest -q && python src/build_site.py`
Expected: all pass; build returns 0.

- [ ] **Step 8: Lint/format + commit**

```bash
python -m ruff check src/build/build_podigami_html.py tests/test_next_race.py
python -m ruff format src/build/build_podigami_html.py tests/test_next_race.py
git add src/build/build_podigami_html.py tests/test_next_race.py
git commit -m "feat(landing): link next/last/repeat races to official F1 pages"
```

---

## Task 8: Wire the fetcher into the update pipeline

**Files:**
- Modify: `src/update.py` (STEPS ~line 22; loop ~line 45)
- Test: covered by existing `tests/test_build_links.py::test_update_steps_point_to_real_scripts`

- [ ] **Step 1: Add the fetch step after the schedule fetch**

In `src/update.py`, insert into `STEPS` immediately after the `"Fetching race schedule"` entry (line 27):

```python
    ("Fetching official race links", "fetch/fetch_race_links.py"),
```

- [ ] **Step 2: Pass `--backfill` under `--full`**

In `main`, after the existing `fetch_podiums.py` `--full` handling (lines 48-49), add:

```python
        if args.full and script.endswith("fetch_race_links.py"):
            cmd.append("--backfill")
```

- [ ] **Step 3: Verify the step wiring test passes**

Run: `PYTHONPATH=src python -m pytest tests/test_build_links.py::test_update_steps_point_to_real_scripts -q`
Expected: PASS (the referenced script exists).

- [ ] **Step 4: Smoke-test the incremental fetch end-to-end (network)**

Run: `PYTHONPATH=src python src/fetch/fetch_race_links.py`
Expected: `mode=incremental, 1 season(s)`, one `mapped X/Y` line for the current season, `Wrote ...`. Then confirm no churn:

Run: `git diff --stat data/f1_race_links.json`
Expected: **no diff** (the current season was already seeded by the backfill; the incremental run is idempotent). If there is a diff, inspect it — it should only ever reflect a genuine change (e.g. F1 corrected a slug).

- [ ] **Step 5: Commit**

```bash
git add src/update.py
git commit -m "feat(pipeline): fetch official race links in update.py"
```

---

## Task 9: Release notes + final verification + PR

**Files:**
- Modify: `RELEASE_NOTES.md`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Update the changelog and sync user-facing docs**

These are mandated by the repo's "Keeping README.md current" and "Release Notes" rules — this feature changes behavior all three docs describe (they currently say race links go to Wikipedia).

**RELEASE_NOTES.md** — the `## 2026-07-01` heading already exists; add this line under its existing `### Improvements` (repo style: no trailing period):

```markdown
- Race-report links across the site now point to official Formula 1 result pages instead of Wikipedia, with a per-race Wikipedia fallback (#<PR>)
```
(Replace `<PR>` with the PR number once the PR is opened.)

**README.md** — replace the "Cited sources" feature bullet (line ~40):
- Old: `- 🔗 **Cited sources** — every race links to its Wikipedia race report.`
- New: `- 🔗 **Cited sources** — every race links to its official Formula 1 result page, with a Wikipedia fallback.`

**README.md** — replace the data-source sentence (line ~283):
- Old: `endpoint, no API key required. Race reports link to **Wikipedia**, the same source the API cites.`
- New: `endpoint, no API key required. Race reports link to the **official Formula 1** result pages (with a Wikipedia fallback for any race not yet mapped).`

**CLAUDE.md** — update the `index.html` row of the "Four output pages" table (line ~73), changing `+ wiki link` to `+ official F1 result link`:
- Old: `| \`index.html\` | \`build/build_podigami_html.py\` | Landing page: next race, last race result (with podigami/repeat status + wiki link), prediction hero, current form, timeline, FAQ |`
- New: `| \`index.html\` | \`build/build_podigami_html.py\` | Landing page: next race, last race result (with podigami/repeat status + official F1 result link), prediction hero, current form, timeline, FAQ |`

**README.md test counts** — this feature adds tests, so bump the three `277` references. First get the real number:

Run: `PYTHONPATH=src python -m pytest -q 2>&1 | tail -1`
Note the passing count `N`, then set it in all three places: the badge (line ~19, `tests-277%20passing` → `tests-N%20passing`), the file-map line (`pytest suite (277 tests, run in CI)`), and the dev-workflow line (`# 277 tests + coverage gate`).

- [ ] **Step 2: Run the full CI-equivalent gate locally**

Run:
```bash
python -m ruff check .
python -m ruff format --check .
PYTHONPATH=src python -m datalib.validate
PYTHONPATH=src python -m pytest -q
python src/build_site.py
```
Expected: ruff clean, `Validated 12 datasets OK.`, all tests pass, build returns 0.

- [ ] **Step 3: Manually confirm the rendered pages (optional but recommended)**

Serve `dist/` and confirm on `index.html`, `combos.html`, and `unlikeliest.html` that race links go to `formula1.com` (hover to see the URL). The Playwright MCP can drive this against the locally-served `dist/` if desired.

- [ ] **Step 4: Commit docs**

```bash
git add RELEASE_NOTES.md README.md CLAUDE.md
git commit -m "docs: release note + sync README/CLAUDE for official F1 race links"
```

- [ ] **Step 5: Push + open the PR into develop**

```bash
git push -u origin feat/official-f1-race-links
gh pr create --base develop --head feat/official-f1-race-links \
  --title "Official F1 race links (replace Wikipedia)" \
  --body "$(cat <<'EOF'
## Summary
Replace every race-report link across the site with the official formula1.com result page, keeping Wikipedia as a per-race fallback so links never die.

## Changes
- New committed dataset `data/f1_race_links.json` (season → round → {id, slug}) + `RaceLink` schema and `load_/save_race_links`.
- New `src/fetch/fetch_race_links.py`: parses F1's robots-allowed per-year results index; count-guarded positional mapping; graceful (exits 0 on network failure); incremental / `--backfill` / `--refetch-all` modes.
- New `race_url(links, season, rnd, race_name)` helper in `_layout.py` (F1 URL with wiki fallback); all race-link call sites switched (combos, unlikeliest, landing next/last/repeat). Scorigami concept link stays on Wikipedia.
- Wired into `update.py` (so post-race auto-deploys refresh current-season links; `--full` → `--backfill`).

## Testing
- `pytest -q`, `ruff check .`, `ruff format --check .`, `python -m datalib.validate` — all green.
- Backfilled 1950–present; verified byte-identical round-trip + live HTTP 200 spot-checks on sample F1 URLs.

## Checklist
- [x] Lint, format, tests pass
- [x] No security issues introduced
- [x] RELEASE_NOTES.md updated
EOF
)"
```

Then update the RELEASE_NOTES `#<PR>` placeholder with the real number and amend/commit if desired.

---

## Notes for the implementer

- **Why the count guard, not slug matching:** F1 slugs are not derivable from our race names (`great-britain` ≠ "British Grand Prix", `united-states` ≠ "United States Grand Prix"). Correctness comes from: (1) F1 lists a year's races with monotonically increasing IDs → sorting recovers round order, and (2) requiring F1's race count to equal ours before trusting the whole season. A mismatched season falls back to Wikipedia entirely — safe, and rare in practice.
- **Never block the deploy:** `update.py` aborts on any non-zero step, and the automated `update` job fails if `update.py` fails. `fetch_race_links.py` therefore catches all network/parse errors and exits 0, keeping the committed map. Do not "harden" this into raising — that would let an F1.com outage block a race-results deploy.
- **Byte-identical output:** `save_race_links` uses the same `json.dumps(..., indent=2, ensure_ascii=False)` as every dataset; `_ordered()` sorts seasons and rounds numerically and each entry is `{"id", "slug"}` in that field order, so `test_dataset_roundtrips_byte_identical` holds and re-runs produce no diff.
- **`links=None` defaults** on the render helpers mean tests that don't care about URLs keep exercising the Wikipedia fallback unchanged; `build()` always passes the real map.
```
