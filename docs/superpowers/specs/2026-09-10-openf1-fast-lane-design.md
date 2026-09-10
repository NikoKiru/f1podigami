# OpenF1 Fast Lane — Design

**Date:** 2026-09-10
**Status:** Approved (design); spec under review
**Builds on:** `docs/research/2026-09-08-live-data-latency.md` (flag-to-live measurements, cron collapse)

## Problem

Results reach the site **1.3–7 h after the flag** (2026 rounds 10–13) and qualifying
**2–6.6 h after the session starts**. Two causes, both upstream of our ~15-minute
fetch → deploy path:

1. **Jolpica publishes slowly and unevenly** — batch ingestion per race weekend. At the
   2026 Italian GP its qualifying still had nothing ~2 h after the session ended (the
   16:53Z run saw rounds 1–12 only); the race took until 21:38Z.
2. **GitHub delivers ~6–7 of our 96 daily cron slots** since 2026-08-27, so the next
   attempt after a miss is often hours away.

The user's primary concern is **data discrepancy**. Evidence gathered for this design:

| Finding | Detail |
|---|---|
| Jolpica revises settled races silently | Monaco 2026 R6 P3: Hadjar (Jun 8) → Gasly (Jun 16) → Hadjar (Sep 6). For 82 days the site listed Antonelli / Hamilton / Gasly as a new trio instead of Antonelli / Hamilton / Hadjar. Neither change was flagged. |
| Jolpica publishes incomplete rows first | Monza 2026 R13 arrived with `grid: 0` for every car; the real grid landed ~16 h later (#289). |
| OpenF1 and Jolpica agree on final results | Final podiums identical in **82 of 83** races since 2023; 2026 qualifying order identical in **13 of 13** (R4: OpenF1 omits one car that set no time). The one miss, Monaco 2026, is a post-race time penalty OpenF1 never applied. |
| The at-the-flag result is F1's *provisional* classification | It changed the podium in **4 of 83** races: Austin 2023 (Hamilton DSQ), Spa 2024 (Russell DSQ), Las Vegas 2025 (Norris DSQ), Monaco 2026 (Gasly's unserved 2×5 s). |
| f1api.dev is not independent | Matched Jolpica everywhere, Monaco correction included — a mirror, not a cross-check. |
| OpenF1 rows map exactly onto Jolpica's | For 2026 R1–R13, OpenF1 rows mapped to Jolpica's shape are identical in **every field** — grid (`starting_grid`), position, laps, status, team — except Monaco's five penalty-shifted positions. Team names map 1:1 onto Jolpica constructor IDs (11 teams, no exceptions). |
| OpenF1 `starting_grid` is exact | Matched Monza's official grid for all 22 cars including the 3/30/35/20 penalties (follow-up, see Non-goals). |

## Goals

- The race result on the site **~40 min after the flag** in most races (OpenF1 is free
  from session end + 30 min), qualifying ~30 min after the session.
- **No new class of discrepancy:** OpenF1 rows are byte-identical to Jolpica's whenever the
  sources agree; Jolpica always wins once it has a round; every podium revision — OpenF1
  vs Jolpica, or Jolpica vs itself — is surfaced to a human.
- **Fail closed:** any doubt about the fast data means today's behaviour, unchanged.
- Keep every existing property: static site with no runtime dependency, schema-validated
  data, deterministic compute, no new silent-stall vector.

## Non-goals

- Replacing Jolpica. OpenF1 covers 2023 onward only; the 1950→ history stays Jolpica's.
- A "provisional" label or any special page state (user decision: the early result is
  shown as the result).
- Sprint races (the site tracks Grand Prix podiums only).
- Browser-side updates (rejected: runtime dependency, logic duplicated in JS).
- An external scheduler (rejected: a third-party service holding a GitHub token).
- Replacing the manual `grid_penalties.json` with OpenF1 `starting_grid` — promising
  (exact at Monza) but its publish timing is unknown. Follow-up.

## Decisions (user-approved)

1. **OpenF1 is the fast source**; Jolpica stays canonical and the only historical source.
2. **Publish unless stewards are busy** — a podium-scoped stewards' check (Section 3).
3. **Podium revisions are flagged and still auto-merge** (Section 5). Holding the PR would
   also hold every later race, since all data flows through one `auto/update-data` PR.
4. **In the pipeline, with an earlier watcher** — not in the browser, not an external trigger.
5. **No label.** The early result is the result; a later change is handled by the revision flow.
6. **Fill in everywhere.** OpenF1 writes the newest round into the normal datasets and
   everything downstream (combos, stats, prediction, pages) updates; Jolpica overwrites it
   later. Not a separate provisional overlay.

## Architecture

```
race start - 3h ──► guard arms (today: start + 1h40)
                      │
                      ▼
            watcher polls every 3 min, up to 5 h
            ├─ OpenF1 has the race + stewards clear ─► FAST: OpenF1 fills the newest round
            └─ Jolpica has the race ─────────────────► NORMAL: Jolpica data, as today
                      │
                      ▼
            unchanged pipeline (combos, stats, prediction, build) ─► PR ─► auto-merge ─► deploy
                      │
                      ▼  (round came from OpenF1)
            successor run waits for Jolpica ─► Jolpica overwrites ─► revision check ─► PR
```

| Unit | Status | Responsibility |
|---|---|---|
| `src/fetch/openf1.py` | new | Thin OpenF1 client: session lookup, `session_result`, `drivers`, `race_control`, `starting_grid`. Any non-200 / non-list / `{"detail": …}` body → `None`. |
| `src/fetch/stewards_gate.py` | new | Pure function: result rows + race-control messages → `hold` reasons (empty = clear). No IO. |
| `src/fetch/fetch_openf1.py` | new | Fills the newest current-season round Jolpica lacks, in Jolpica's exact row shape; records it in `unconfirmed.json`. |
| `data/unconfirmed.json` + schema | new | Rounds whose rows came from OpenF1 and which datasets still await Jolpica. |
| `src/check_revisions.py` | new | Diffs every already-published podium against `HEAD`; emits the PR title suffix, label and issue text. |
| `src/check_update_due.py` | changed | Arms 3 h before race/quali start; stays due while a round is unconfirmed. |
| `src/wait_for_results.py` | changed | Polls OpenF1 (through the gate) and Jolpica; 5 h budget; logs first-seen times. |
| Jolpica fetchers (`fetch_podiums`, `fetch_race_results`, `fetch_qualifying`) | small change | After a successful fetch, confirm the rounds they actually received (shared helper). Merge semantics unchanged. |
| `src/update.py` | changed | Runs `fetch_openf1.py` right after the three Jolpica fetchers, before `count_combos`. |
| `.github/workflows/update.yml` | changed | In-flight-PR wait, watcher on relay dispatches, revision step, successor dispatch, longer timeout. |

## Section 1 — The OpenF1 fetcher

`fetch_openf1.py` runs **after** the Jolpica fetchers, so it only ever sees rounds Jolpica
could not provide this run. For the race (and separately the qualifying session) of the
newest scheduled round that is over:

1. **Skip** unless the round is in the current season and the session ended, and the
   datasets it would write lack the round — for the race, **both** `podiums.json` and
   `race_results.json` (all-or-nothing: if Jolpica delivered one but not the other, wait
   for Jolpica to finish rather than mix sources within a round). Never touches an
   earlier round or season.
2. **Match the session**: OpenF1 `sessions?year=Y&session_name=Race|Qualifying`, matched to
   the `schedule.json` round by **UTC start date, start within 6 h of the scheduled start,
   and not cancelled** — exactly one candidate, else no write. Country and circuit names
   are deliberately not used: they differ between the sources ("USA" vs "United States";
   2026 R16 is "Bahrain" in Kuala Lumpur), and exact start times fail when a race is moved
   (Miami 2026 ran at 17:00Z, Jolpica's schedule still says 20:00Z).
3. **Map drivers**: `driver_number` → `current_drivers.json` `number` → `driverId`, and
   the OpenF1 `last_name` must equal the last word of the committed name (accent- and
   case-insensitive, so `ANTONELLI` matches "Andrea Kimi Antonelli" and `HULKENBERG`
   matches "Nico Hülkenberg"). Any unknown number or name mismatch (e.g. a substitute's
   debut) → no write.
4. **Map teams**: `constructorId` comes from OpenF1's `team_name` through a fixed alias
   table, verified 1:1 against every 2026 Jolpica row: Alpine → `alpine`, Aston Martin →
   `aston_martin`, Audi → `audi`, Cadillac → `cadillac`, Ferrari → `ferrari`, Haas F1 Team →
   `haas`, McLaren → `mclaren`, Mercedes → `mercedes`, Racing Bulls → `rb`, Red Bull Racing →
   `red_bull`, Williams → `williams`. OpenF1 reports the car actually driven, so a seat swap
   maps correctly; an unknown team name (a rebrand) → no write.
5. **Race only — stewards' check** (Section 3). Hold → no write this pass.
6. **Build rows in Jolpica's exact shape**, taking race name, date and circuit from
   `schedule.json` and driver names from `current_drivers.json` (both verified identical to
   what Jolpica serves for 2026):
   - `podiums.json`: `{season, round, raceName, p1, p2, p3}`.
   - `race_results.json`: one row per car — `grid` from OpenF1 `starting_grid` (keyed by
     the qualifying session; `0` when absent, as Jolpica's own first publish does);
     `position` for classified cars else `null`; `laps` from `number_of_laps`; `status`
     `Finished` (lead lap) / `Lapped` / `Retired` (`dnf`) / `Did not start` (`dns`) /
     `Disqualified` (`dsq`) — the strings Jolpica uses for 2026.
   - `qualifying.json`: `{season, round, results: [{driverId, constructorId, position}]}`.
7. **Write** through the existing `datalib` `save_*` functions (schema-validated,
   canonical serialization) and add the round to `unconfirmed.json`.

## Section 2 — `unconfirmed.json` and confirmation

```jsonc
[
  { "season": "2026", "round": "14", "kind": "race",
    "pending": ["podiums", "race_results"], "since": "2026-09-13T15:00:00+00:00" }
]
```

- `since` is OpenF1's scheduled session end (deterministic, not wall-clock), so rewriting
  the file never churns it — the compute fixed-point rule holds.
- Each Jolpica fetcher, after a successful API read, removes its dataset from `pending` for
  every round the API actually returned; an entry disappears when `pending` is empty. Per
  dataset on purpose: #239 showed two Jolpica feeds can disagree about the same race, so
  podiums arriving does not confirm race results.
- Jolpica's rows overwrite OpenF1's through the fetchers' existing merge-by-(season, round).
- New `datalib` schema + `load_*/save_*`, included in `datalib.validate`; an empty list is
  the resting state.

## Section 3 — Stewards' check

Runs on each poll once OpenF1 serves the race result.

- **Scope:** only the three cars that crossed the line in the top 3 (order by laps, then
  total time). Only the trio decides the verdict, so order inside the podium is ignored.
- **Holds** if any of them has:
  - an open incident — `UNDER INVESTIGATION`, `WILL BE INVESTIGATED AFTER THE RACE`,
    `SUMMONED`, or `DISQUALIFIED`;
  - an unserved drive-through or stop-go;
  - unserved time penalties that, added to the race times, change the top-3 *set*.
- **Resolution is per incident:** a decision (`… PENALTY FOR CAR …`, `NO FURTHER …`,
  `REPRIMAND`, `WARNING`) closes the incident it refers to — matched on the infringement
  text and the `(HH:MM:SS)` tag — for every car in it. `NOTED` alone does not block.
- While holding, the watcher keeps polling; Jolpica publishing ends the wait (today's path).

**Prototype backtest, all 83 races 2023–2026** (reproduce: OpenF1 `sessions`,
`session_result`, `race_control` for every `Race`):

- Publishes at the first look in **66 (80%)**, holds **17 (20%)** until Jolpica. Post-race
  decisions never appear in OpenF1's feed, so no hold cleared early.
- Holds both real podium changes it can see: **Monaco 2026** and **Jeddah 2023** (Alonso's
  post-race penalty, later overturned — holding avoided two flips).
- Cannot see scrutineering: **Austin 2023** and **Spa 2024** would have shown the
  crossed-the-line trio for a few hours (Las Vegas 2025 was held for another reason).

## Section 4 — Trigger, watcher and successor runs

**Guard** (`check_update_due.py`, still no-network):

- Race trigger: due from **race start − 3 h** (was start + 1h40) while the round is newer
  than `asOf`.
- Qualifying trigger: due from **quali start − 3 h** (was + 1h30) while `postQuali` does not
  cover the next race.
- Confirmation trigger: due while `unconfirmed.json` is non-empty.
- Replaying the last 14 days of real scheduled runs: arming 3 h early with a 5 h watcher
  puts a run **already waiting when OpenF1 publishes in 93% of races and 91% of
  qualifying sessions** (55% for today's arm-at-start / 2 h budget). In the rest, the
  next run publishes on arrival.

**Watcher** (`wait_for_results.py`): polls every 3 min for up to **5 h**. Returns when the
target round is in Jolpica, or in OpenF1 with the stewards' check clear (race) / present
(qualifying). The quali-day short-circuit stays: nothing pending → return immediately.
Logs the first time each source had the round, which measures the real gain from the first
live race onward. Timing out is still not a failure.

**`update.yml`:**

- A first step, before checkout, waits (≤ 15 min) for any open `auto/update-data` PR to
  merge, so a run never computes on a `main` that is about to change.
- The watcher runs on scheduled runs **and** on successor dispatches (new `wait` input);
  a human dispatch still acts immediately.
- `update` job `timeout-minutes`: 180 → **345** (GitHub's cap is 360): ≤ 15 min in-flight
  wait + 5 h watcher + ~20 min pipeline, PR, validate and tests.
- **Successor run:** if a round is still pending (fast result shipped and awaiting Jolpica,
  held by the stewards' check, or not yet published) and it is less than **12 h after the
  session's scheduled start**, the run's last step dispatches `update.yml` with `wait=true`
  using the built-in token (`workflow_dispatch` is exempt from GitHub's no-retrigger
  rule; needs `permissions: actions: write`). This also covers a run that armed early and
  timed out just before publication. The 12 h bound makes a runaway chain impossible.
- A round unconfirmed for **> 48 h** fails the run, reusing the existing
  `auto-update-failure` alert (likely a Jolpica outage or an ID mismatch).

## Section 5 — Revision alert

`check_revisions.py` runs after the pipeline, before the PR step. For every round in both
the working-tree `podiums.json` and `HEAD:data/podiums.json`, any change to `p1/p2/p3`
(noting whether the trio set changed) produces:

- a PR title suffix — `Podium revised: 2026 R6 Monaco (GAS → HAD)`;
- a `podium-revised` label on the data PR;
- a **new issue per revision** (deduplicated by title) with the before/after trio and both
  verdicts, separate from the failure alert, left open for a human to close.

The PR still auto-merges. This makes every race's OpenF1 → Jolpica hand-over a free
cross-check, and catches Jolpica editing old races (the Monaco pattern). Qualifying
revisions are not flagged — they only feed the prediction.

## Error handling (cross-cutting)

Every new path degrades to today's behaviour:

| Condition | Result |
|---|---|
| OpenF1 down, error, `No results found`, paid live window | no write; keep polling; Jolpica path as today |
| Session matches zero or several rounds, or is cancelled | no write |
| Unknown car number / name mismatch / unknown team name | no write for that session |
| Stewards' check holds | no write this pass |
| Jolpica already has the round | OpenF1 step skips; Jolpica wins |
| Jolpica later differs from OpenF1 | Jolpica overwrites; revision alert |
| Round unconfirmed > 48 h | run fails → existing alert issue |
| Successor chain | stops once nothing is pending, or 12 h after the session's scheduled start |

## Testing

All offline; OpenF1 responses recorded into `tests/fixtures/openf1/` (compact: only the
fields and stewards' messages the code reads).

- **Byte-identical rows:** for 2026 R1–R13, the fetcher's rows equal a **frozen snapshot**
  of Jolpica's rows (recorded next to the OpenF1 fixtures — never the live `data/`, which a
  later Jolpica revision could change and turn this test into a stall vector):
  `podiums.json` and `race_results.json` exactly, `qualifying.json` exactly except R4
  (OpenF1 omits a car that set no time). Monaco R6 is the expected mismatch and must be
  held by the gate.
- **Stewards' check:** the 83-race backtest as a fixture test — holds Monaco 2026 and
  Jeddah 2023; publishes ≥ 75%.
- **Fail-closed matrix:** each row of the error-handling table writes nothing.
- **Confirmation:** per-dataset pruning; partial confirmation (podiums yes, race results
  no) keeps the round pending; empty file round-trips byte-identically.
- **Guard / watcher:** arming offsets for race and quali; confirmation trigger; quali-day
  short-circuit; successor bound at 12 h; 48 h escalation.
- **Revision check:** replays the real Monaco history (Hadjar → Gasly → Hadjar) and flags
  both; silent on an identical Jolpica confirmation.
- **Rehearsal:** scratch worktree with pre-Monza data (`46895a3`) and recorded OpenF1
  responses → full fast-mode run → data matches what PR #286 shipped, apart from model
  numbers.

## Rollout

Three PRs, each shippable and useful on its own, in this order:

1. **Revision alert** (Section 5). Small, no behaviour change beyond alerting; would have
   caught both Monaco edits.
2. **Trigger, watcher and successor runs** (Section 4), still Jolpica-only. On its own this
   removes the multi-hour cron gaps: the site gets Jolpica's result within one poll of it
   publishing (Monza 2026 would have gone live soon after Jolpica published, not at the
   next surviving cron slot).
3. **OpenF1 fast lane** (Sections 1–3): fetcher, stewards' check, `unconfirmed.json`,
   Jolpica-fetcher confirmation.

Each goes feature branch → `develop` → promotion to `main` between race weekends. After
PR 3, watch the first live race's two PRs (fast + confirmation) by hand and read the
watcher's first-seen log lines. Docs travel with the PR that changes the behaviour:
README (sources and flow), CLAUDE.md (new failure modes: OpenF1 fetcher,
`unconfirmed.json`, guard timing, successor runs, revision alert), `RELEASE_NOTES.md`.

## Limitations (accepted)

- **Scrutineering disqualifications can't be foreseen.** About 2 in 83 races would show the
  trio that crossed the line for a few hours; Jolpica's data then corrects it with a
  revision alert.
- **~20% of races fall back to today's timing** because the stewards were busy.
- **OpenF1 is free only after the live window** (session end + 30 min) and is itself a
  volunteer service. If it disappears, the fast lane is a silent no-op, not a failure.
- **Runner holds** of up to ~5.5 h per run on race weekends (free on a public repository).
- **The 93% / 91% coverage is measured on 14 days** of GitHub's current scheduler. If
  delivery worsens, the successor chain still only starts once one run has landed.
- **Model numbers shift slightly** when Jolpica confirms a round (standings and status
  details), the same expected churn as today.
