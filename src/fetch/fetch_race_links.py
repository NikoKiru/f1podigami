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
- Correctness rests on SLUG IDENTITY, not ID or page order (issue #158). F1's
  internal race IDs are NOT assigned in round order (rescheduled/late-added races
  get out-of-order IDs), and the index's DOM order pins the "latest race" first
  for the current season — so neither recovers the round. Instead we pair each of
  our rounds with the slug whose identity matches its race name
  (``race_identity.match_season``, backed by ``ACCEPTABLE_SLUGS``). A season is
  trusted only when every round matches exactly one slug with none left over;
  otherwise that whole season falls back to Wikipedia at render time.
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
from fetch.race_identity import match_season  # noqa: E402

INDEX_URL = "https://www.formula1.com/en/results/{year}/races"
RESULT_RE = re.compile(r"/en/results/(\d{4})/races/(\d+)/([a-z0-9-]+)/race-result")
MAX_BACKOFF_RETRIES = 6
USER_AGENT = "f1podigami/0.2 (https://github.com/NikoKiru/f1podigami)"
LINKS_PATH = DATA_DIR / "f1_race_links.json"

# Races F1's results archive lists but that were never actually held (cancelled),
# so they have no result and no round in our podium data. Dropping them before the
# count guard lets the season align 1:1 with our rounds instead of falling back to
# Wikipedia. Keyed by year -> slugs.
CANCELLED_RACES: dict[int, frozenset[str]] = {
    2023: frozenset({"emilia-romagna"}),  # Imola — cancelled due to flooding, never held
}


def parse_race_links(html_text: str, year: int) -> list[tuple[str, str]]:
    """(id, slug) pairs for ``year``, deduped in first-seen order.

    Order is intentionally NOT relied upon: the raw index repeats races (a "latest
    race" selector) and neither its DOM order nor the numeric IDs track round
    order. Rounds are assigned later by slug identity (see module docstring)."""
    seen: dict[str, str] = {}
    for y, rid, slug in RESULT_RE.findall(html_text):
        if int(y) == year and rid not in seen:
            seen[rid] = slug
    return list(seen.items())


def season_round_names(schedule: dict, podiums: list[dict]) -> dict[int, dict[str, str]]:
    """season -> {round: raceName}: the full calendar for the current season
    (schedule), completed races for historic seasons (podiums)."""
    names: dict[int, dict[str, str]] = {}
    for p in podiums:
        names.setdefault(int(p["season"]), {})[str(p["round"])] = p["raceName"]
    names.setdefault(int(schedule["season"]), {}).update(
        {str(r["round"]): r["raceName"] for r in schedule["races"]}
    )
    return names


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


def update_map(
    existing: dict,
    targets: list[tuple[int, int]],
    fetch_fn,
    round_names: dict[int, dict[str, str]],
    sleep: float = 1.0,
) -> dict:
    """Refresh each (year, expected_count) target. A per-year failure or an
    identity mismatch never discards existing data or aborts — the year is left
    as-is. Rounds are assigned by slug identity, not ID/page order."""
    result = {k: dict(v) for k, v in existing.items()}
    for i, (year, expected) in enumerate(targets):
        try:
            if i and sleep:
                time.sleep(sleep)
            skip = CANCELLED_RACES.get(year, frozenset())
            pairs = [
                (rid, slug)
                for rid, slug in parse_race_links(fetch_fn(year), year)
                if slug not in skip
            ]
            season_map = match_season(round_names.get(year, {}), pairs)
        except Exception as exc:  # noqa: BLE001 - a bad fetch must not abort the run
            print(f"  warn: {year} fetch failed ({exc}); keeping existing", file=sys.stderr)
            continue
        if season_map:
            result[str(year)] = {str(r): season_map[str(r)] for r in sorted(season_map, key=int)}
            print(f"  {year}: mapped {len(season_map)}/{expected}")
        else:
            print(
                f"  warn: {year} slugs don't match our races (F1 vs ours);"
                " wiki fallback for the season",
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
    round_names = season_round_names(schedule, podiums)
    current_year = int(schedule["season"])

    targets = compute_targets(mode, existing, counts, current_year)
    print(f"fetch_race_links: mode={mode}, {len(targets)} season(s)")
    new_map = _ordered(update_map(existing, targets, fetch_index, round_names))
    save_race_links(new_map)
    print(f"Wrote {LINKS_PATH} ({len(new_map)} seasons)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
