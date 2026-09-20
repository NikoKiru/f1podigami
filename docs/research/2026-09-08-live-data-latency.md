# Flag to deploy: where the post-race latency actually goes

**Date:** 2026-09-08 · **Status:** research only, nothing implemented
**Question:** is there a faster / more reliable way to get live race data onto the deployed site?

Readable version: <https://claude.ai/code/artifact/dc95b746-96db-4a43-9337-6a522c77379b>

## Summary

The deploy pipeline is not the bottleneck. Everything from fetch through to the Pages
edge cache costs about **15 minutes**; the rest of the 1.3–7 h gap is upstream publish
lag plus GitHub's scheduled-cron losses. Two things make this worth revisiting now:

1. **GitHub's cron delivery collapsed on 2026-08-27** and has not recovered — from
   ~36 runs/day to ~7. `CLAUDE.md` still documents the old ~17% figure.
2. **A materially faster source exists** (OpenF1, ~40 min after the flag) and it maps
   onto data the repo already holds.

## Measured: flag to live, 2026 season

Flag taken as start + 1h40, the same `RESULTS_BUFFER` the guard uses. Measured from the
merge history of `data/podigami.json` on `main` (first commit where `asOf` advances).

| R | Race | Lag | Note |
|--:|------|----:|------|
| 7 | Barcelona | 123.0 h | documented silent stall |
| 8 | Austrian | 3.0 h | |
| 9 | British | 267.7 h | documented silent stall |
| 10 | Belgian | 1.7 h | mature pipeline |
| 11 | Hungarian | 1.4 h | mature pipeline |
| 12 | Dutch | 1.3 h | mature pipeline |
| 13 | Italian | 7.0 h | tail |

### The 15 minutes we control

| Stage | Evidence | Time |
|-------|----------|-----:|
| Watcher notices publication | 3-min poll, `wait_for_results.py` | ≤ 3 min |
| Fetch + compute + build | run 34061478518, 21:34:45 → 21:37:44 | 3 min |
| PR opened → auto-merged | PR #286, 21:37:44 → 21:38:50 | 70 s |
| `deploy.yml` → Pages | 12 recent deploys, 38–75 s | 40 s |
| Pages edge cache | live site sends `Cache-Control: max-age=600` | ≤ 10 min |

Typical race ≈ 84 min total, of which ~69 min is Jolpica publish lag.
Round 13 ≈ 408 min total, of which ~5h45 is Jolpica and ~48 min is waiting for a cron slot.

## Finding 1 — GitHub cron delivery collapsed on 2026-08-27

296 scheduled `update.yml` runs over 17.9 days (2026-08-21 → 2026-09-08) against 96/day
requested. Whole-window average 16.5/day (17.2%), but that hides a step change:

```
2026-08-23   18/96
2026-08-24   37/96
2026-08-25   36/96
2026-08-26   24/96
2026-08-27    2/96   <- step change
2026-08-28    3/96
2026-08-29    6/96
2026-08-30    6/96
2026-08-31    6/96
2026-09-01    6/96
2026-09-02    8/96
2026-09-03    7/96
2026-09-04    7/96
2026-09-05    9/96
2026-09-06    9/96
2026-09-07    7/96
2026-09-08    5/96   (partial, measured 19:20 UTC)
```

Gaps between consecutive delivered runs (n=295):

| min | p25 | median | p75 | p90 | max |
|----:|----:|-------:|----:|----:|----:|
| 9 m | 25 m | 39 m | 1.9 h | 4.2 h | 11.9 h |

The current regime is ~7% delivery, roughly one run every 3–4 h. This lines up with a
GitHub Actions incident reported around 2026-08-26 (community discussion #201738); the
community workaround is an external `workflow_dispatch` trigger.

**Consequence:** the watcher's 2 h budget plus a p90 4.2 h retry gap explains round 13's
seven hours exactly. That outcome is now structural, not bad luck.

Reproduce:

```bash
gh run list --workflow=update.yml --limit 300 \
  --json createdAt,event --jq '.[] | select(.event=="schedule") | .createdAt'
```

## Finding 2 — faster sources exist and fit the current ID scheme

### OpenF1 (<https://openf1.org>) — recommended fast lane

- Derived from the official F1 timing feed. `session_result` documented as available
  *"a few minutes after the official results are published on the official Formula 1 website."*
- Free/paid split is a **time window, not a delay**: *"Data is considered live from
  30 minutes before a session starts until 30 minutes after it ends. Outside of this
  window, data is classified as historical and is free to access."* For Monza that means
  free from **15:30 UTC** — about 40 min after the flag, versus 21:38 UTC actual.
- `session_result` keys on `driver_number`, which maps straight onto the `number` field
  **already in `data/current_drivers.json`**. No new mapping infrastructure.
- `sessions.date_start` matches `schedule.json` date+time exactly → clean round mapping.
- Returns `{"detail":"No results found."}` for an unpublished session → clean watcher sentinel.
- No auth, ~3 req/s, sends `access-control-allow-origin: *`.
- **2023 onward only.** A fast lane, never a replacement for the 1950→ history.

### f1api.dev — cross-check only

Returns **identical Ergast IDs** (`antonelli`, `russell`, `max_verstappen`, `mercedes`,
`red_bull`), CORS `*`, no auth, Vercel-cached 600 s. Zero mapping work — but provenance
and update cadence are entirely undocumented. Treat as a cross-check, not a primary.

### Jolpica — why it is slow

Slow by design: their stated model is batch ingestion per race weekend, not live timing
(jolpica-f1 discussion #95). Also the only source for the 1950→ history, and a single
point of failure — volunteer-run, as Ergast was before deprecation.

## Options

`combos.json` holds only **754 unique trios** (27 KB raw, **4.5 KB gzipped** as a bare
index), and the podigami verdict is a set-membership test on three driver IDs. That makes
a fast lane much cheaper than it first looks.

### 1. Fix the trigger — smallest change, targets reliability

Extend the watcher budget 2 h → ~5 h so one landed cron slot spans the whole realistic
publish window (free on a public repo; jobs cap at 6 h). Optionally add an external
`workflow_dispatch` trigger so the pipeline stops depending on a platform feature that is
currently ~93% lossy. Touches `update.yml` and `wait_for_results.py`; no data-model change.

### 2. Build-time provisional fast lane — targets speed

Poll OpenF1 alongside Jolpica. Publish a clearly-labelled provisional podium + podigami
verdict as its own small dataset with its own `datalib` schema; the renderer prefers
canonical over provisional, and the normal pipeline overwrites it when Jolpica lands.
Stays fully pre-rendered — no runtime dependency. Verdict live ≈40 min after the flag.

### 3. Client-side hydration — fastest, but a runtime dependency

Ship the 4.5 KB trio index; JS checks OpenF1 at page load and swaps in the last-race block
when it finds a round newer than the baked-in `asOf`. Deploy latency drops to zero and the
site keeps updating through an Actions outage — at the cost of the site's first runtime
third-party dependency, and verdict logic living in two places.

## Caveats for either fast lane

- **Podiums change.** A stewards' decision hours after the flag can reshuffle the top
  three. The fast path must be able to *retract* a claimed PODIGAMI, not only add one.
- **A provisional trio is not yet in `combos.json`,** so `_lookup_combo` returns nothing
  and `render_last_race`'s `else` branch calls it a podigami by default. Correct for a
  genuine first-time trio, wrong for a repeat — the provisional path needs its own *n+1*
  handling.
- **Two sources that must agree** is the exact failure class `CLAUDE.md` documents at
  #239. The overlay must fail closed: garbage or unreachable upstream renders nothing and
  leaves today's behaviour intact.
- **Extending the watcher hold** blocks the `update-data` concurrency group for its
  duration. Pending runs cancel each other (already the observed behaviour), but a 5 h
  hold makes that window much longer.

## Sources

- <https://openf1.org/> — tier boundary, live-window definition, rate limits
- <https://openf1.org/docs/> — `session_result` availability wording
- <https://f1api.dev/> — probed live for round 13 shape, IDs and CORS
- <https://github.com/jolpica/jolpica-f1/discussions/95> — stated update cadence
- <https://github.com/orgs/community/discussions/201738> — scheduled-workflow degradation, late Aug 2026
- Local: `gh run list --workflow=update.yml`, `git log origin/main -- data/podigami.json`,
  live response headers from <https://nikokiru.github.io/f1podigami/>
