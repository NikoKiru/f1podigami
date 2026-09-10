# OpenF1 Fast Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a race result on the site about 40 minutes after the flag, and qualifying about 30 minutes after the session, by letting OpenF1 fill the newest round until Jolpica publishes it. The site must never show a result that disagrees with Jolpica without an alert.

**Architecture:** `src/fetch/fetch_openf1.py` runs right after the three Jolpica fetchers. For the newest race and qualifying session Jolpica does not have yet, it writes OpenF1's classification into `podiums.json` / `race_results.json` / `qualifying.json` in Jolpica's exact row shape, provided a podium-scoped stewards' check (`src/fetch/stewards_gate.py`) is clear. It records each round in `data/unconfirmed.json`. The Jolpica fetchers confirm rounds as the API returns them. The guard stays armed while anything is unconfirmed, and the watcher accepts OpenF1 as a ready source. Everything downstream is unchanged. PR 3 of 3 from `docs/superpowers/specs/2026-09-10-openf1-fast-lane-design.md` (Sections 1–3). It depends on PR 1 (revision alert) and PR 2 (race-day watcher) being merged.

**Tech Stack:** Python 3.11+, `requests`, Pydantic v2 (`datalib`), pytest, GitHub Actions.

## Global Constraints

- Python `>=3.11`; ruff `>=0.15.22,<0.16`, line length 100, rules `E,W,F,I,UP,B,C4` (no lambda assignment; `zip(..., strict=)`). `python -m ruff check .` / `python -m ruff format --check .` must pass.
- No new dependencies. OpenF1 is `https://api.openf1.org/v1`, no auth, ~3 req/s: sleep 0.4 s between requests.
- **Fail closed everywhere:** any OpenF1 error, non-list body, `{"detail": …}`, unmatched or cancelled session, unknown car number, surname mismatch, unknown team name, incomplete podium, or held stewards' check → **write nothing**. An unexpected exception inside the fetcher is caught in `main()` and also writes nothing. The Jolpica path must behave exactly as before.
- **Jolpica always wins:** OpenF1 only fills a current-season round absent from the datasets it would write (for a race, absent from **both** `podiums.json` and `race_results.json`). It never touches an earlier round.
- **Values fixed by the spec / verified evidence:**
  - Session match: same UTC date, start within **6 h** of the scheduled start, not `is_cancelled`, exactly one candidate (Miami 2026 ran at 17:00Z vs the schedule's 20:00Z).
  - OpenF1 data only after **session end + 30 min** (its live window).
  - Teams (verified 1:1 against every 2026 Jolpica row): `Alpine→alpine, Aston Martin→aston_martin, Audi→audi, Cadillac→cadillac, Ferrari→ferrari, Haas F1 Team→haas, McLaren→mclaren, Mercedes→mercedes, Racing Bulls→rb, Red Bull Racing→red_bull, Williams→williams`.
  - Status vocabulary: `Disqualified` (dsq) / `Did not start` (dns) / `Retired` (dnf) / `Lapped` (fewer laps than the leader) / `Finished`.
  - Row order: classified by position, then the rest by laps completed (descending) — Jolpica's order.
  - Round unconfirmed > **48 h** after its session ended → the run fails (existing `auto-update-failure` alert).
- **Verified expectations** (scratchpad run against real OpenF1 data, 2026-09-10): rounds 1–5, 7, 8, 10–13 produce podium and race-results entries *identical* to Jolpica's. Round 6 (Monaco, unserved penalties) and round 9 (Silverstone, post-race investigation of Hamilton) are **held**. Qualifying matches by position for all 13, except round 4 (OpenF1 omits Hadjar, who set no time). Jolpica's stored qualifying *order* is not always by position (rounds 5 and 10), so tests compare by position. The gate backtest over 83 races publishes **65 (78%)** and holds Monaco 2026 and Jeddah 2023.
- Tests are offline, replaying **frozen fixtures** (never live `data/`: a Jolpica revision would turn a byte-identical test into a stall vector).
- Branch `feat/openf1-fast-lane` from `develop` after PRs 1 and 2 merged; PR into `develop`; promote only when no qualifying or race is within 48 h.
- Every PR updates `RELEASE_NOTES.md`, README and CLAUDE.md where they describe behaviour.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD
  ```

---

## File Structure

| File | Responsibility |
|---|---|
| `src/datalib/schemas.py`, `repository.py`, `__init__.py` (modify) | `UnconfirmedRound` schema, `unconfirmed.json` registry + `load_/save_unconfirmed` |
| `data/unconfirmed.json` (create) | `[]` at rest |
| `src/fetch/unconfirmed.py` (create) | `confirm()` / `confirm_on_disk()` bookkeeping |
| `src/fetch/fetch_podiums.py`, `fetch_race_results.py`, `fetch_qualifying.py` (modify) | Confirm the rounds the API returned |
| `src/fetch/openf1.py` (create) | Thin fail-closed OpenF1 client |
| `src/fetch/stewards_gate.py` (create) | Pure stewards' check |
| `src/fetch/fetch_openf1.py` (create) | Match, map, build rows, fill the newest round; CLI (`--now` for rehearsals) |
| `src/update.py` (modify) | Run `fetch_openf1.py` after the Jolpica fetchers |
| `src/check_update_due.py` (modify) | Confirmation trigger, stale check, successor includes unconfirmed |
| `src/wait_for_results.py` (modify) | OpenF1 as a ready source; confirmation targets; `published=fast` |
| `.github/workflows/update.yml` (modify) | Stale-unconfirmed step |
| `tests/fixtures/openf1/record_fixtures.py` + 3 `.json.gz` (create) | Frozen OpenF1 + Jolpica fixtures |
| `tests/test_unconfirmed.py`, `test_stewards_gate.py`, `test_fetch_openf1.py` (create); `test_datalib.py`, `test_check_update_due.py`, `test_wait_for_results.py` (extend) | Tests |
| `CLAUDE.md`, `README.md`, `RELEASE_NOTES.md` | Docs |

---

### Task 0: Branch

- [ ] **Step 1:**

```bash
git switch develop && git pull
git switch -c feat/openf1-fast-lane
grep -n "ARM_BEFORE\|def report" src/check_update_due.py src/wait_for_results.py
```
Expected: PR 2's `ARM_BEFORE` and `report(published: str)` are present. If not, stop: PR 2 must be merged first.

---

### Task 1: The `unconfirmed.json` dataset

**Files:**
- Modify: `src/datalib/schemas.py`, `src/datalib/repository.py`, `src/datalib/__init__.py`
- Create: `data/unconfirmed.json`
- Test: `tests/test_datalib.py` (append)

**Interfaces:**
- Produces: `UnconfirmedRound` (`season: str, round: str, kind: Literal["race","qualifying"], pending: list[Literal["podiums","race_results","qualifying"]], since: str`); `load_unconfirmed() -> list[UnconfirmedRound]`; `save_unconfirmed(data) -> None`; registry key `"unconfirmed.json"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_datalib.py`:

```python
# --- unconfirmed.json (OpenF1 rounds awaiting Jolpica) -----------------------------

_UNCONFIRMED = {
    "season": "2026",
    "round": "14",
    "kind": "race",
    "pending": ["podiums", "race_results"],
    "since": "2026-09-13T15:00:00+00:00",
}


def test_save_unconfirmed_roundtrips(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_unconfirmed([_UNCONFIRMED])
    raw = (tmp_path / "unconfirmed.json").read_text(encoding="utf-8")
    adapter = REGISTRY["unconfirmed.json"]
    dumped = adapter.dump_python(adapter.validate_python(json.loads(raw)), mode="json")
    assert json.dumps(dumped, indent=2, ensure_ascii=False) == raw
    assert repository.load_unconfirmed()[0].pending == ["podiums", "race_results"]


def test_unconfirmed_at_rest_is_an_empty_list(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_unconfirmed([])
    assert (tmp_path / "unconfirmed.json").read_text(encoding="utf-8") == "[]"


def test_unconfirmed_rejects_an_unknown_dataset_or_kind():
    adapter = REGISTRY["unconfirmed.json"]
    with pytest.raises(ValidationError):
        adapter.validate_python([{**_UNCONFIRMED, "pending": ["combos"]}])
    with pytest.raises(ValidationError):
        adapter.validate_python([{**_UNCONFIRMED, "kind": "sprint"}])
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_datalib.py -q -k unconfirmed`
Expected: FAIL with `KeyError: 'unconfirmed.json'` / `AttributeError: … save_unconfirmed`.

- [ ] **Step 3: Implement**

`src/datalib/schemas.py`: add `from typing import Literal` below `from __future__ import annotations` (before the pydantic import, isort order), and append:

```python
# --- unconfirmed.json ---------------------------------------------------------


class UnconfirmedRound(_Base):
    """A round whose rows came from OpenF1 and still await Jolpica, per dataset.

    Written by ``fetch/fetch_openf1.py`` when it fills the newest round ahead of
    Jolpica. Each Jolpica fetcher removes its dataset from ``pending`` once the
    API returns that round, and the entry disappears when nothing is pending.
    ``since`` is OpenF1's scheduled session end — deterministic, so rewriting the
    file never churns it. The update guard stays armed while any entry exists.
    """

    season: str
    round: str
    kind: Literal["race", "qualifying"]
    pending: list[Literal["podiums", "race_results", "qualifying"]]
    since: str
```

`src/datalib/repository.py`: add `UnconfirmedRound` to the `from .schemas import (...)` list (alphabetical, after `Soulmates` and before `Unlikeliest`), add to `REGISTRY` after `"retirements.json"`:

```python
    "unconfirmed.json": TypeAdapter(list[UnconfirmedRound]),
```

and append:

```python
def load_unconfirmed() -> list[UnconfirmedRound]:
    return _load("unconfirmed.json")


def save_unconfirmed(data: Any) -> None:
    _save("unconfirmed.json", data)
```

`src/datalib/__init__.py`: add `load_unconfirmed` and `save_unconfirmed` to the repository import list (alphabetical), `UnconfirmedRound` to the schemas import list (after `TrioBoardEntry`, before `Unlikeliest`), and to `__all__` add `"load_unconfirmed"`, `"save_unconfirmed"` (after `"save_retirements"`) and `"UnconfirmedRound"` (after `"RetirementRace"`).

Create the committed file with the canonical writer (it must be exactly `[]`, no newline):

```bash
PYTHONPATH=src python -c "from datalib import save_unconfirmed; save_unconfirmed([])"
```
(PowerShell: `$env:PYTHONPATH="src"; python -c "from datalib import save_unconfirmed; save_unconfirmed([])"`)

- [ ] **Step 4: Run the datalib + integrity suites**

Run: `python -m pytest tests/test_datalib.py tests/test_data_integrity.py -q`
Expected: all pass. The parametrized round-trip and "registry covers every dataset" tests now include `unconfirmed.json`.

- [ ] **Step 5: Commit**

```bash
python -m ruff check src/datalib tests/test_datalib.py && python -m ruff format src/datalib tests/test_datalib.py
git add src/datalib data/unconfirmed.json tests/test_datalib.py
git commit -m "Add the unconfirmed.json dataset for OpenF1 rounds awaiting Jolpica" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 2: Confirmation bookkeeping + Jolpica fetcher hooks

**Files:**
- Create: `src/fetch/unconfirmed.py`
- Modify: `src/fetch/fetch_podiums.py`, `src/fetch/fetch_race_results.py`, `src/fetch/fetch_qualifying.py`
- Test: `tests/test_unconfirmed.py`

**Interfaces:**
- Consumes: `load_unconfirmed`, `save_unconfirmed`, `repository.DATA_DIR` (Task 1).
- Produces: `confirm(entries: list[dict], dataset: str, rounds: set[tuple[str, str]]) -> list[dict]`; `confirm_on_disk(dataset: str, rounds: Iterable[tuple[str, str]]) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_unconfirmed.py`:

```python
"""Bookkeeping for rounds OpenF1 filled ahead of Jolpica (src/fetch/unconfirmed.py).

Confirmation is per dataset on purpose: two Jolpica feeds can disagree about the
same race for an hour (#239), so podiums arriving must not confirm race results.
"""

from fetch.unconfirmed import confirm, confirm_on_disk

RACE = {
    "season": "2026",
    "round": "14",
    "kind": "race",
    "pending": ["podiums", "race_results"],
    "since": "2026-09-13T15:00:00+00:00",
}
QUALI = {
    "season": "2026",
    "round": "15",
    "kind": "qualifying",
    "pending": ["qualifying"],
    "since": "2026-09-25T13:00:00+00:00",
}


def test_confirming_one_dataset_keeps_the_round_pending():
    assert confirm([RACE], "podiums", {("2026", "14")}) == [{**RACE, "pending": ["race_results"]}]


def test_confirming_the_last_dataset_drops_the_round():
    once = confirm([RACE], "podiums", {("2026", "14")})
    assert confirm(once, "race_results", {("2026", "14")}) == []


def test_other_rounds_and_datasets_are_untouched():
    assert confirm([RACE, QUALI], "qualifying", {("2026", "14")}) == [RACE, QUALI]
    assert confirm([RACE, QUALI], "qualifying", {("2026", "15")}) == [RACE]


def test_confirm_does_not_mutate_its_input():
    entries = [{**RACE, "pending": list(RACE["pending"])}]
    confirm(entries, "podiums", {("2026", "14")})
    assert entries[0]["pending"] == ["podiums", "race_results"]


def test_confirm_on_disk_updates_the_file(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_unconfirmed([RACE])
    confirm_on_disk("race_results", [("2026", "14")])
    assert [u.model_dump() for u in repository.load_unconfirmed()] == [
        {**RACE, "pending": ["podiums"]}
    ]


def test_confirm_on_disk_without_the_file_is_a_no_op(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    confirm_on_disk("podiums", [("2026", "14")])
    assert not (tmp_path / "unconfirmed.json").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_unconfirmed.py -q`
Expected: `ModuleNotFoundError: No module named 'fetch.unconfirmed'`.

- [ ] **Step 3: Implement the helper**

Create `src/fetch/unconfirmed.py`:

```python
"""Bookkeeping for rounds OpenF1 filled ahead of Jolpica (data/unconfirmed.json).

fetch_openf1.py records each round it writes together with the datasets it
wrote (``pending``). Each Jolpica fetcher calls :func:`confirm_on_disk` with the
rounds the API actually returned this run: its dataset leaves ``pending`` for
those rounds, and an entry with nothing left pending is dropped. Per dataset on
purpose — two Jolpica feeds can disagree about the same race for an hour (#239),
so podiums arriving does not confirm race results.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from datalib import repository  # noqa: E402


def confirm(entries: list[dict], dataset: str, rounds: set[tuple[str, str]]) -> list[dict]:
    """``entries`` with ``dataset`` confirmed for ``rounds``; emptied entries dropped."""
    kept = []
    for e in entries:
        pending = list(e["pending"])
        if (e["season"], e["round"]) in rounds and dataset in pending:
            pending.remove(dataset)
        if pending:
            kept.append({**e, "pending": pending})
    return kept


def confirm_on_disk(dataset: str, rounds: Iterable[tuple[str, str]]) -> None:
    """Apply :func:`confirm` to data/unconfirmed.json; a no-op when nothing changes."""
    if not (repository.DATA_DIR / "unconfirmed.json").exists():
        return
    entries = [u.model_dump() for u in repository.load_unconfirmed()]
    updated = confirm(entries, dataset, set(rounds))
    if updated == entries:
        return
    repository.save_unconfirmed(updated)
    confirmed = sorted(
        f"{e['season']} R{e['round']}"
        for e in entries
        if dataset in e["pending"] and (e["season"], e["round"]) in set(rounds)
    )
    print(f"Jolpica confirmed {dataset} for {', '.join(confirmed)}")
```

- [ ] **Step 4: Hook the three Jolpica fetchers**

`src/fetch/fetch_podiums.py`: add `from fetch.unconfirmed import confirm_on_disk  # noqa: E402` after the `fetch.api_cache` import. In `main()`, declare `received: dict[tuple[str, str], set[int]] = {}` just before `for season in seasons_to_fetch:`, and right after `entry[f"p{position}"] = driver_record(results[0])` add:

```python
                received.setdefault(key, set()).add(position)
```

After `save_podiums(complete)` add:

```python
    # A round OpenF1 filled is confirmed once the API returned all three steps.
    confirm_on_disk("podiums", {k for k, got in received.items() if got == {1, 2, 3}})
```

`src/fetch/fetch_race_results.py`: add the same import after the `fetch.api_cache` import; after `save_race_results(combined)` add:

```python
    confirm_on_disk("race_results", {(r["season"], r["round"]) for r in fetched if r["results"]})
```

`src/fetch/fetch_qualifying.py`: add the same import; after `save_qualifying(combined)` add:

```python
    confirm_on_disk("qualifying", {(e["season"], e["round"]) for e in fetched})
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_unconfirmed.py tests/test_fetch_race_results.py tests/test_fetch_qualifying.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
python -m ruff check src/fetch tests/test_unconfirmed.py && python -m ruff format src/fetch tests/test_unconfirmed.py
git add src/fetch/unconfirmed.py src/fetch/fetch_podiums.py src/fetch/fetch_race_results.py src/fetch/fetch_qualifying.py tests/test_unconfirmed.py
git commit -m "Confirm OpenF1-filled rounds as the Jolpica fetchers receive them" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 3: OpenF1 client and frozen fixtures

**Files:**
- Create: `src/fetch/openf1.py`
- Create: `tests/fixtures/openf1/record_fixtures.py`
- Create (by running the recorder): `tests/fixtures/openf1/openf1_2026.json.gz`, `jolpica_2026.json.gz`, `gate_backtest.json.gz`

**Interfaces:**
- Produces: `openf1.get(endpoint, **params) -> list[dict] | None`, `sessions(year: int, name: str)`, `session_result(session_key)`, `drivers(session_key)`, `race_control(session_key)`, `starting_grid(quali_session_key)` — each `list[dict] | None`. Fixture JSON shapes, as used by later tasks:
  - `openf1_2026.json.gz`: `{"sessions": {"Race": [...], "Qualifying": [...]}, "session_result": {"<key>": [...]}, "drivers": {"<key>": [...]}, "race_control": {"<race key>": [...]}, "starting_grid": {"<quali key>": [...]}}`
  - `jolpica_2026.json.gz`: `{"schedule": {...}, "current_drivers": {...}, "podiums": [...], "race_results": [...], "qualifying": [...]}` (2026 rounds 1–13)
  - `gate_backtest.json.gz`: `[{"label": "2026 Monte Carlo", "result": [...], "messages": [...]}, ...]`

- [ ] **Step 1: Write the client**

Create `src/fetch/openf1.py`:

```python
"""Minimal, fail-closed OpenF1 client (https://openf1.org) for the fast lane.

Every call returns the parsed list on success and ``None`` otherwise: an HTTP
error or timeout, a body that is not a list of objects, or OpenF1's
``{"detail": "No results found."}`` sentinel (served with a 404). Callers treat
``None`` as "no fast data", never as an error — OpenF1 is an optional
accelerator and the Jolpica path must keep working without it.

Free-tier data for a session opens 30 min after it ends; earlier requests hit the
paid live window and come back as errors, i.e. ``None``.
"""

from __future__ import annotations

import time

import requests

API_ROOT = "https://api.openf1.org/v1"
USER_AGENT = "f1podigami/0.1 (https://github.com/NikoKiru/f1podigami)"
SLEEP_BETWEEN = 0.4  # OpenF1's free tier allows ~3 requests/s


def get(endpoint: str, **params) -> list[dict] | None:
    try:
        resp = requests.get(
            f"{API_ROOT}/{endpoint}",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"  OpenF1 {endpoint}: {exc}")
        return None
    finally:
        time.sleep(SLEEP_BETWEEN)
    if resp.status_code != 200:
        print(f"  OpenF1 {endpoint}: HTTP {resp.status_code}")
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    if not isinstance(body, list) or not all(isinstance(row, dict) for row in body):
        return None
    return body


def sessions(year: int, name: str) -> list[dict] | None:
    return get("sessions", year=year, session_name=name)


def session_result(session_key: int) -> list[dict] | None:
    return get("session_result", session_key=session_key)


def drivers(session_key: int) -> list[dict] | None:
    return get("drivers", session_key=session_key)


def race_control(session_key: int) -> list[dict] | None:
    return get("race_control", session_key=session_key)


def starting_grid(quali_session_key: int) -> list[dict] | None:
    """The official starting grid, keyed by the *qualifying* session."""
    return get("starting_grid", session_key=quali_session_key)
```

- [ ] **Step 2: Write the recorder**

Create `tests/fixtures/openf1/record_fixtures.py`:

```python
"""Record the frozen fixtures the fast-lane tests replay (network; run by hand).

    python tests/fixtures/openf1/record_fixtures.py

Writes three gzipped JSON files next to this script:

- openf1_2026.json.gz — every OpenF1 response fetch_openf1 reads for 2026 rounds
  1-13 (race + qualifying sessions, results, drivers, stewards' messages,
  starting grids), trimmed to the fields the code uses.
- jolpica_2026.json.gz — a FROZEN snapshot of origin/main's schedule, current
  drivers, and 2026 rounds 1-13 of podiums / race_results / qualifying: the rows
  the fetcher must reproduce. Never compare against live data/ instead — a later
  Jolpica revision would turn the test into a stall vector.
- gate_backtest.json.gz — result rows + stewards' messages (up to session end +
  30 min) for every Race 2023 onward, for the stewards' check backtest.

Re-recording changes the expectations; commit new files deliberately.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
from fetch import openf1  # noqa: E402

LAST_ROUND = 13
RESULT_KEYS = ("driver_number", "position", "number_of_laps", "duration", "dnf", "dns", "dsq")
DRIVER_KEYS = ("driver_number", "last_name", "team_name")
SESSION_KEYS = ("session_key", "session_name", "date_start", "date_end", "is_cancelled", "location")
SCHEDULE_KEYS = ("round", "raceName", "date", "time", "qualifyingDate", "qualifyingTime", "circuitId")
STEWARDS_WORDS = (
    "STEWARDS", "INCIDENT", "PENALTY", "DISQUALIF", "INVESTIGAT",
    "SUMMON", "REPRIMAND", "WARNING", "NO FURTHER", "NOTED",
)


def trim(rows: list[dict] | None, keys: tuple[str, ...]) -> list[dict]:
    return [{k: row.get(k) for k in keys} for row in rows or []]


def stewards(messages: list[dict] | None) -> list[dict]:
    """Only the messages the stewards' check can react to."""
    kept = []
    for m in messages or []:
        text = (m.get("message") or "").upper()
        if "CAR" in text and any(word in text for word in STEWARDS_WORDS):
            kept.append({"date": m.get("date"), "message": m.get("message")})
    return kept


def git_json(path: str):
    out = subprocess.run(
        ["git", "show", f"origin/main:{path}"],
        capture_output=True, text=True, encoding="utf-8", cwd=REPO, check=True,
    )
    return json.loads(out.stdout)


def write(name: str, payload) -> None:
    with gzip.open(HERE / name, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), sort_keys=True)
    print(f"wrote {name} ({(HERE / name).stat().st_size // 1024} KB)")


def record_2026(schedule: dict) -> None:
    races = openf1.sessions(2026, "Race") or []
    qualis = openf1.sessions(2026, "Qualifying") or []
    out = {
        "sessions": {"Race": trim(races, SESSION_KEYS), "Qualifying": trim(qualis, SESSION_KEYS)},
        "session_result": {},
        "drivers": {},
        "race_control": {},
        "starting_grid": {},
    }
    for race in schedule["races"]:
        if int(race["round"]) > LAST_ROUND:
            continue
        days = {race["date"], race.get("qualifyingDate")}
        for s in races + qualis:
            if s["date_start"][:10] not in days:
                continue
            key = str(s["session_key"])
            out["session_result"][key] = trim(openf1.session_result(s["session_key"]), RESULT_KEYS)
            out["drivers"][key] = trim(openf1.drivers(s["session_key"]), DRIVER_KEYS)
            if s["session_name"] == "Race":
                out["race_control"][key] = stewards(openf1.race_control(s["session_key"]))
            else:
                grid = openf1.starting_grid(s["session_key"])
                out["starting_grid"][key] = trim(grid, ("driver_number", "position"))
    write("openf1_2026.json.gz", out)


def record_jolpica(schedule: dict) -> None:
    rounds = {str(r) for r in range(1, LAST_ROUND + 1)}

    def pick(rows: list[dict]) -> list[dict]:
        return [r for r in rows if r["season"] == "2026" and r["round"] in rounds]

    write(
        "jolpica_2026.json.gz",
        {
            "schedule": {
                "season": schedule["season"],
                "races": [{k: r.get(k) for k in SCHEDULE_KEYS} for r in schedule["races"]],
            },
            "current_drivers": git_json("data/current_drivers.json"),
            "podiums": pick(git_json("data/podiums.json")),
            "race_results": pick(git_json("data/race_results.json")),
            "qualifying": pick(git_json("data/qualifying.json")),
        },
    )


def record_backtest() -> None:
    now = datetime.now(UTC)
    races = []
    for year in range(2023, now.year + 1):
        for s in openf1.sessions(year, "Race") or []:
            end = datetime.fromisoformat(s["date_end"])
            if s.get("is_cancelled") or end > now:
                continue
            result = openf1.session_result(s["session_key"])
            messages = openf1.race_control(s["session_key"])
            if not result or messages is None:
                continue
            first_look = end + timedelta(minutes=30)
            races.append(
                {
                    "label": f"{year} {s['location']}",
                    "result": trim(result, RESULT_KEYS),
                    "messages": [
                        m for m in stewards(messages)
                        if datetime.fromisoformat(m["date"]) <= first_look
                    ],
                }
            )
    write("gate_backtest.json.gz", races)


if __name__ == "__main__":
    schedule = git_json("data/schedule.json")
    record_2026(schedule)
    record_jolpica(schedule)
    record_backtest()
```

- [ ] **Step 3: Record the fixtures (network, ~3–5 min)**

```bash
git fetch origin main
python tests/fixtures/openf1/record_fixtures.py
```
Expected: three `wrote …json.gz (N KB)` lines. `openf1_2026` and `jolpica_2026` are tens of KB. `gate_backtest` is under ~150 KB.

- [ ] **Step 4: Sanity-check the fixtures**

```bash
python -c "import gzip,json; d=json.load(gzip.open('tests/fixtures/openf1/gate_backtest.json.gz','rt',encoding='utf-8')); print(len(d), [r['label'] for r in d if r['label'] in ('2026 Monte Carlo','2023 Jeddah')])"
```
Expected: `83` (or more if later 2026 races have run) and both labels listed.

- [ ] **Step 5: Commit**

```bash
python -m ruff check src/fetch/openf1.py tests/fixtures/openf1/record_fixtures.py
python -m ruff format src/fetch/openf1.py tests/fixtures/openf1/record_fixtures.py
git add src/fetch/openf1.py tests/fixtures/openf1
git commit -m "Add a fail-closed OpenF1 client and frozen fast-lane fixtures" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 4: The stewards' check

**Files:**
- Create: `src/fetch/stewards_gate.py`
- Test: `tests/test_stewards_gate.py`

**Interfaces:**
- Produces: `hold_reasons(rows: list[dict], messages: list[dict]) -> list[str]` (empty = publish); `crossing_order(rows) -> list[dict]`; `stewards_state(messages) -> tuple[dict[int, str], dict[int, list[int]], dict[int, int]]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stewards_gate.py`:

```python
"""The stewards' check (src/fetch/stewards_gate.py).

OpenF1 serves a race's classification ~30 min after it ends, before the FIA's
final classification. This check holds the fast lane while the stewards could
still change the podium *trio*.
"""

import gzip
import json
from pathlib import Path

from fetch.stewards_gate import crossing_order, hold_reasons

BACKTEST = Path(__file__).parent / "fixtures" / "openf1" / "gate_backtest.json.gz"


def row(number, position, laps=50, time=5000.0, **flags):
    return {"driver_number": number, "position": position, "number_of_laps": laps,
            "duration": time, **flags}


# 1 wins, 4 second, 16 third; 44 is 3 s behind 16; 63 well back.
FINISH = [
    row(1, 1, time=5000.0),
    row(4, 2, time=5010.0),
    row(16, 3, time=5020.0),
    row(44, 4, time=5023.0),
    row(63, 5, time=5040.0),
]


def msg(text, t="2026-09-13T14:00:00+00:00"):
    return {"date": t, "message": text}


def test_a_clean_race_publishes():
    assert hold_reasons(FINISH, []) == []


def test_an_open_incident_on_a_podium_car_holds():
    reasons = hold_reasons(FINISH, [msg(
        "FIA STEWARDS: INCIDENT INVOLVING CAR 16 (LEC) WILL BE INVESTIGATED AFTER THE RACE - IMPEDING"
    )])
    assert len(reasons) == 1 and reasons[0].startswith("#16 open")


def test_an_open_incident_off_the_podium_is_ignored():
    assert hold_reasons(FINISH, [msg(
        "FIA STEWARDS: INCIDENT INVOLVING CAR 63 (RUS) UNDER INVESTIGATION - UNSAFE RELEASE"
    )]) == []


def test_a_decision_closes_the_whole_incident():
    """Austin 2024: Norris was penalised; the same incident no longer holds Verstappen."""
    msgs = [
        msg("FIA STEWARDS: TURN 12 INCIDENT INVOLVING CARS 4 (NOR) AND 1 (VER) UNDER "
            "INVESTIGATION - LEAVING THE TRACK AND GAINING AN ADVANTAGE", "2026-09-13T14:00:00+00:00"),
        msg("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 4 (NOR) - LEAVING THE TRACK AND "
            "GAINING AN ADVANTAGE", "2026-09-13T14:05:00+00:00"),
    ]
    # 5 s puts car 4 on 5015, still ahead of car 16 (5020): the trio stands.
    assert hold_reasons(FINISH, msgs) == []


def test_noted_alone_does_not_block():
    assert hold_reasons(FINISH, [msg(
        "TURN 10 INCIDENT INVOLVING CARS 16 (LEC) AND 44 (HAM) NOTED - CAUSING A COLLISION"
    )]) == []


def test_unserved_penalties_that_change_the_trio_hold():
    """Monaco 2026: Gasly's two unserved 5 s penalties dropped him from 3rd to 7th."""
    msgs = [
        msg("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - SPEEDING IN THE PIT LANE (14:02:16)",
            "2026-09-13T14:10:00+00:00"),
        msg("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - SPEEDING IN THE PIT LANE (14:22:57)",
            "2026-09-13T14:36:00+00:00"),
    ]
    assert hold_reasons(FINISH, msgs) == ["unserved time penalties change the trio"]


def test_a_served_penalty_is_not_counted():
    msgs = [
        msg("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - TRACK LIMITS",
            "2026-09-13T14:10:00+00:00"),
        msg("FIA STEWARDS: PENALTY SERVED - 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - TRACK LIMITS",
            "2026-09-13T14:30:00+00:00"),
    ]
    # Unserved, 5 s would put car 16 (5025) behind car 44 (5023).
    assert hold_reasons(FINISH, msgs) == []


def test_an_unserved_drive_through_holds():
    assert hold_reasons(FINISH, [msg("FIA STEWARDS: DRIVE THROUGH PENALTY FOR CAR 4 (NOR) - FALSE START")]) == [
        "#4 has an unserved drive-through or stop-go"
    ]


def test_positions_that_disagree_with_race_times_hold():
    """Austin 2023 as OpenF1 has it now: Hamilton unclassified but timed in 2nd."""
    rows = [*FINISH[:3], row(44, None, time=5005.0)]
    assert hold_reasons(rows, []) == ["OpenF1's positions disagree with its own race times"]


def test_a_disqualified_car_is_out_of_the_crossing_order():
    assert hold_reasons([*FINISH, row(81, None, time=4990.0, dsq=True)], []) == []


def test_crossing_order_is_laps_then_time():
    rows = [row(1, 2, laps=49, time=4900.0), row(4, 1, laps=50, time=5000.0)]
    assert [r["driver_number"] for r in crossing_order(rows)] == [4, 1]


def test_backtest_holds_what_it_can_see_and_publishes_most_races():
    races = json.load(gzip.open(BACKTEST, "rt", encoding="utf-8"))
    held = {r["label"] for r in races if hold_reasons(r["result"], r["messages"])}
    assert "2026 Monte Carlo" in held  # Gasly's unserved penalties
    assert "2023 Jeddah" in held  # Alonso's post-race penalty (later overturned)
    assert len(races) >= 80
    assert (len(races) - len(held)) / len(races) >= 0.75
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_stewards_gate.py -q`
Expected: `ModuleNotFoundError: No module named 'fetch.stewards_gate'`.

- [ ] **Step 3: Implement (verified code — do not "simplify" the matching rules)**

Create `src/fetch/stewards_gate.py`:

```python
"""Would a stewards' decision still change this race's podium trio?

OpenF1 serves a race's classification ~30 min after it ends — before the FIA's
final classification. Across the 83 races of 2023-2026 the trio that crossed the
line first was not the final one four times: three post-race scrutineering
disqualifications (Austin 2023, Spa 2024, Las Vegas 2025), which nothing in the
feed announces, and Monaco 2026, where Gasly's two unserved 5 s penalties dropped
him from 3rd to 7th — which the feed does show.

This check holds the fast lane while the stewards could still change the trio:
a car that crossed the line in the top 3 with an open incident, an unserved
drive-through or stop-go, or unserved time penalties big enough to push it out
of the top 3. Order inside the podium doesn't matter — the verdict is about the
trio. A decision closes the incident it refers to (matched on the infringement
text and its ``(HH:MM:SS)`` tag) for every car in it; ``NOTED`` alone does not
block. Backtested on those 83 races it publishes 78% at the first look and holds
Monaco 2026 and Jeddah 2023 (Alonso's post-race penalty, later overturned).

Pure: OpenF1 ``session_result`` rows and ``race_control`` messages in, reasons out.
"""

from __future__ import annotations

import re

CARS = re.compile(r"(\d+) \([A-Z]{3}\)")
TAG = re.compile(r"\((\d{2}:\d{2}:\d{2})\)")
SECONDS = re.compile(r"(\d+) SECOND TIME PENALTY")
OPENS = ("UNDER INVESTIGATION", "WILL BE INVESTIGATED", "SUMMONED", "DISQUALIF")
DECIDES = ("PENALTY", "NO FURTHER", "REPRIMAND", "WARNING", "NO ACTION")
STOPS = ("DRIVE THROUGH", "STOP AND GO", "STOP/GO")


def _race_time(row: dict) -> float | None:
    value = row.get("duration")
    if isinstance(value, list):
        value = value[-1] if value else None
    return float(value) if isinstance(value, (int, float)) else None


def crossing_order(rows: list[dict]) -> list[dict]:
    """Cars in the order they took the flag: most laps, then least time.

    A car OpenF1 already marks disqualified is out of the classification, so it
    is left out here too.
    """
    timed = [r for r in rows if not r.get("dsq") and _race_time(r) is not None]
    return sorted(timed, key=lambda r: (-(r.get("number_of_laps") or 0), _race_time(r)))


def _infringement(text: str) -> str:
    """The infringement after the last ' - ', without its '(HH:MM:SS)' tag."""
    if " - " not in text:
        return ""
    return TAG.sub("", text.rsplit(" - ", 1)[1]).strip()


def stewards_state(
    messages: list[dict],
) -> tuple[dict[int, str], dict[int, list[int]], dict[int, int]]:
    """Per car number: open incidents, unserved time penalties (s), unserved stop penalties."""
    incidents: list[dict] = []
    seconds: dict[int, list[int]] = {}
    stops: dict[int, int] = {}
    for m in sorted(messages, key=lambda m: m.get("date") or ""):
        text = (m.get("message") or "").upper()
        if "FIA STEWARDS" not in text and "INCIDENT" not in text:
            continue
        cars = {int(c) for c in CARS.findall(text)}
        if not cars:
            continue
        tag_match = TAG.search(text)
        tag = tag_match.group(1) if tag_match else None
        infr = _infringement(text)
        timed = SECONDS.search(text)
        stop = any(word in text for word in STOPS)
        if "PENALTY SERVED" in text:
            for c in cars:
                if timed and int(timed.group(1)) in seconds.get(c, []):
                    seconds[c].remove(int(timed.group(1)))
                elif stop:
                    stops[c] = stops.get(c, 0) - 1
            continue
        if any(word in text for word in DECIDES):
            for c in cars:
                if timed:
                    seconds.setdefault(c, []).append(int(timed.group(1)))
                elif stop:
                    stops[c] = stops.get(c, 0) + 1
            for inc in incidents:
                if inc["open"] and (
                    (tag is not None and inc["tag"] == tag)
                    or (infr and inc["infr"] == infr and inc["cars"] & cars)
                    or (not infr and inc["cars"] & cars)
                ):
                    inc["open"] = False
            continue
        if any(word in text for word in OPENS):
            incidents.append(
                {"cars": cars, "infr": infr, "tag": tag, "open": True,
                 "text": (m.get("message") or "")[:100]}
            )
    open_by_car: dict[int, str] = {}
    for inc in incidents:
        if inc["open"]:
            for c in inc["cars"]:
                open_by_car[c] = inc["text"]
    return open_by_car, seconds, stops


def hold_reasons(rows: list[dict], messages: list[dict]) -> list[str]:
    """Why the stewards could still change the podium trio; empty means publish."""
    order = crossing_order(rows)
    if len(order) < 3:
        return ["fewer than three timed finishers"]
    top3 = [r["driver_number"] for r in order[:3]]
    listed = {r.get("driver_number") for r in rows if r.get("position") in (1, 2, 3)}
    if listed != set(top3):
        return ["OpenF1's positions disagree with its own race times"]
    open_by_car, seconds, stops = stewards_state(messages)
    reasons = []
    for car in top3:
        if car in open_by_car:
            reasons.append(f"#{car} open: {open_by_car[car]}")
        if stops.get(car, 0) > 0:
            reasons.append(f"#{car} has an unserved drive-through or stop-go")
    adjusted = sorted(
        order,
        key=lambda r: (
            -(r.get("number_of_laps") or 0),
            _race_time(r) + sum(seconds.get(r["driver_number"], [])),
        ),
    )
    if {r["driver_number"] for r in adjusted[:3]} != set(top3):
        reasons.append("unserved time penalties change the trio")
    return reasons
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_stewards_gate.py -q`
Expected: `12 passed`.

- [ ] **Step 5: Commit**

```bash
python -m ruff check src/fetch/stewards_gate.py tests/test_stewards_gate.py
python -m ruff format src/fetch/stewards_gate.py tests/test_stewards_gate.py
git add src/fetch/stewards_gate.py tests/test_stewards_gate.py
git commit -m "Hold the fast lane while the stewards could still change the trio" -m "Backtested on 83 races: publishes 78% at the first look, holds Monaco 2026
and Jeddah 2023.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 5: The OpenF1 fetcher

**Files:**
- Create: `src/fetch/fetch_openf1.py`
- Test: `tests/test_fetch_openf1.py`

**Interfaces:**
- Consumes: `fetch.openf1` (Task 3), `hold_reasons` (Task 4), datalib load/save incl. `load_unconfirmed`/`save_unconfirmed` (Task 1).
- Produces (Task 6's watcher calls these):
  - `build_race(race: dict, season: str, current: list[dict], now: datetime, client=openf1) -> dict | None` → `{"podium": dict, "race": dict, "sessionEnd": str}`
  - `build_qualifying(race: dict, season: str, current: list[dict], now: datetime, client=openf1) -> dict | None` → `{"entry": dict, "sessionEnd": str}`
  - `fill(schedule, current, podiums, race_results, qualifying, unconfirmed, now, client=openf1) -> set[str]` (mutates the lists; returns `{"race","qualifying"}` subset)
  - `match_session(sessions, date, time) -> dict | None`, `map_drivers(entrants, current) -> dict[int, dict] | None`, `TEAM_TO_CONSTRUCTOR`
  - CLI: `python src/fetch/fetch_openf1.py [--now ISO8601]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetch_openf1.py`:

```python
"""The OpenF1 fast lane (src/fetch/fetch_openf1.py), replayed from frozen fixtures.

The byte-identical tests are the concrete "no discrepancy" guarantee: for every
2026 round the stewards' check lets through, the rows OpenF1 produces must equal
the rows Jolpica published — so Jolpica's later confirmation changes nothing.
"""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fetch.fetch_openf1 import build_qualifying, build_race, fill, map_drivers, match_session

FIX = Path(__file__).parent / "fixtures" / "openf1"


def _load(name):
    with gzip.open(FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


OPENF1 = _load("openf1_2026.json.gz")
JOLPICA = _load("jolpica_2026.json.gz")
NOW = datetime(2026, 9, 10, tzinfo=UTC)
CURRENT = JOLPICA["current_drivers"]["drivers"]
SCHEDULE = JOLPICA["schedule"]
RACES = {r["round"]: r for r in SCHEDULE["races"]}
HELD = {"6", "9"}  # Monaco: unserved penalties; Silverstone: post-race investigation


class FakeClient:
    """Replays openf1_2026.json.gz through fetch.openf1's interface."""

    def __init__(self, data, broken=()):
        self.data = data
        self.broken = set(broken)

    def sessions(self, year, name):
        return None if "sessions" in self.broken else self.data["sessions"].get(name, [])

    def session_result(self, key):
        return self.data["session_result"].get(str(key))

    def drivers(self, key):
        return self.data["drivers"].get(str(key))

    def race_control(self, key):
        return None if "race_control" in self.broken else self.data["race_control"].get(str(key), [])

    def starting_grid(self, key):
        return self.data["starting_grid"].get(str(key))


def jolpica(dataset, rnd):
    return next(r for r in JOLPICA[dataset] if r["round"] == rnd)


@pytest.mark.parametrize("rnd", [str(r) for r in range(1, 14) if str(r) not in HELD])
def test_race_rows_are_identical_to_jolpicas(rnd):
    built = build_race(RACES[rnd], "2026", CURRENT, NOW, FakeClient(OPENF1))
    assert built is not None
    assert built["podium"] == jolpica("podiums", rnd)
    assert built["race"] == jolpica("race_results", rnd)


@pytest.mark.parametrize("rnd", sorted(HELD))
def test_the_stewards_check_holds_monaco_and_silverstone(rnd):
    assert build_race(RACES[rnd], "2026", CURRENT, NOW, FakeClient(OPENF1)) is None


@pytest.mark.parametrize("rnd", [str(r) for r in range(1, 14)])
def test_qualifying_rows_match_jolpicas_by_position(rnd):
    built = build_qualifying(RACES[rnd], "2026", CURRENT, NOW, FakeClient(OPENF1))
    theirs = sorted(jolpica("qualifying", rnd)["results"], key=lambda r: r["position"])
    if rnd == "4":  # OpenF1 omits Hadjar, who set no time; Jolpica lists him P22
        theirs = [r for r in theirs if r["driverId"] != "hadjar"]
    assert built["entry"]["results"] == theirs


def test_match_session_tolerates_a_moved_start_but_not_another_day():
    moved = [{"session_key": 1, "date_start": "2026-05-03T17:00:00+00:00", "is_cancelled": False}]
    assert match_session(moved, "2026-05-03", "20:00:00Z")["session_key"] == 1  # Miami 2026
    assert match_session(moved, "2026-05-04", "17:00:00Z") is None


def test_match_session_skips_cancelled_and_ambiguous_sessions():
    cancelled = [{"session_key": 1, "date_start": "2026-04-12T15:00:00+00:00", "is_cancelled": True}]
    assert match_session(cancelled, "2026-04-12", "15:00:00Z") is None
    two = [
        {"session_key": 1, "date_start": "2026-04-12T15:00:00+00:00"},
        {"session_key": 2, "date_start": "2026-04-12T16:00:00+00:00"},
    ]
    assert match_session(two, "2026-04-12", "15:00:00Z") is None


def test_map_drivers_fails_closed():
    current = [{"driverId": "hulkenberg", "name": "Nico Hülkenberg", "number": "27"}]
    car = {"driver_number": 27, "last_name": "Hulkenberg", "team_name": "Audi"}
    assert map_drivers([car], current) == {
        27: {"driverId": "hulkenberg", "name": "Nico Hülkenberg", "constructorId": "audi"}
    }
    assert map_drivers([{**car, "driver_number": 99}], current) is None  # unknown car
    assert map_drivers([{**car, "last_name": "Bortoleto"}], current) is None  # someone else
    assert map_drivers([{**car, "team_name": "Sauber"}], current) is None  # unknown team


def test_nothing_is_written_while_openf1_is_down():
    client = FakeClient(OPENF1, broken={"sessions"})
    assert build_race(RACES["13"], "2026", CURRENT, NOW, client) is None
    assert build_qualifying(RACES["13"], "2026", CURRENT, NOW, client) is None


def test_nothing_is_written_without_race_control():
    assert build_race(RACES["13"], "2026", CURRENT, NOW, FakeClient(OPENF1, broken={"race_control"})) is None


def test_nothing_is_written_inside_the_live_window():
    # Monza's race session ends 15:00Z; OpenF1's free data opens at 15:30Z.
    early = datetime(2026, 9, 6, 15, 20, tzinfo=UTC)
    assert build_race(RACES["13"], "2026", CURRENT, early, FakeClient(OPENF1)) is None


def test_an_unknown_car_writes_nothing():
    current = [d for d in CURRENT if d["driverId"] != "hadjar"]
    assert build_race(RACES["13"], "2026", current, NOW, FakeClient(OPENF1)) is None


def _datasets(drop_race=None, drop_quali=None):
    def keep(rows, rnd):
        return [dict(r) for r in rows if r["round"] != rnd]

    return (
        keep(JOLPICA["podiums"], drop_race),
        keep(JOLPICA["race_results"], drop_race),
        keep(JOLPICA["qualifying"], drop_quali),
    )


def test_fill_writes_the_newest_race_and_records_it():
    podiums, race_results, qualifying = _datasets(drop_race="13")
    unconfirmed = []
    written = fill(SCHEDULE, CURRENT, podiums, race_results, qualifying, unconfirmed, NOW, FakeClient(OPENF1))
    assert written == {"race"}
    assert podiums[-1] == jolpica("podiums", "13")
    assert race_results[-1] == jolpica("race_results", "13")
    assert unconfirmed == [
        {"season": "2026", "round": "13", "kind": "race",
         "pending": ["podiums", "race_results"], "since": "2026-09-06T15:00:00+00:00"}
    ]


def test_fill_writes_the_newest_qualifying_and_records_it():
    podiums, race_results, qualifying = _datasets(drop_quali="13")
    unconfirmed = []
    written = fill(SCHEDULE, CURRENT, podiums, race_results, qualifying, unconfirmed, NOW, FakeClient(OPENF1))
    assert written == {"qualifying"}
    assert qualifying[-1]["round"] == "13"
    assert unconfirmed[0]["kind"] == "qualifying" and unconfirmed[0]["pending"] == ["qualifying"]


def test_fill_leaves_rounds_jolpica_already_has():
    podiums, race_results, qualifying = _datasets()
    assert fill(SCHEDULE, CURRENT, podiums, race_results, qualifying, [], NOW, FakeClient(OPENF1)) == set()


def test_fill_never_mixes_sources_within_a_round():
    """Jolpica delivered the podium but not the classification: wait for Jolpica."""
    podiums, race_results, qualifying = _datasets()
    race_results = [r for r in race_results if r["round"] != "13"]
    assert fill(SCHEDULE, CURRENT, podiums, race_results, qualifying, [], NOW, FakeClient(OPENF1)) == set()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_fetch_openf1.py -q`
Expected: `ModuleNotFoundError: No module named 'fetch.fetch_openf1'`.

- [ ] **Step 3: Implement (the pure core is the version verified against real OpenF1 data)**

Create `src/fetch/fetch_openf1.py`:

```python
"""Fill the newest round from OpenF1 before Jolpica publishes it.

Jolpica — the only source for the 1950-onwards history — publishes a race 1-7h
after the flag (batch ingestion). OpenF1 (https://openf1.org), derived from the
official timing feed, serves the same classification ~30 min after the session
ends. This runs after the Jolpica fetchers in update.py and, for the newest race
and qualifying session Jolpica does not have yet, writes OpenF1's result into the
same datasets in Jolpica's exact row shape. Everything downstream (combos, stats,
prediction, pages) then rolls forward straight away; when Jolpica publishes the
round its fetchers overwrite these rows — byte-identical when the sources agree
(verified for every 2026 round the stewards' check lets through), and a changed
podium raises the revision alert.

Fail closed, always. Any doubt — OpenF1 unreachable or still inside its live
window, a session that doesn't match exactly one scheduled round, a car number,
surname or team we can't map, a stewards' decision still pending on the podium —
writes nothing, leaving the Jolpica path exactly as before. Every written round
is recorded in data/unconfirmed.json until Jolpica confirms it.
"""

from __future__ import annotations

import argparse
import sys
import traceback
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from check_update_due import session_start  # noqa: E402
from datalib import (  # noqa: E402
    load_current_drivers,
    load_podiums,
    load_qualifying,
    load_race_results,
    load_schedule,
    load_unconfirmed,
    repository,
    save_podiums,
    save_qualifying,
    save_race_results,
    save_unconfirmed,
)
from fetch import openf1  # noqa: E402
from fetch.stewards_gate import hold_reasons  # noqa: E402

# OpenF1 team_name -> Jolpica constructorId, verified 1:1 against every 2026
# Jolpica row. A name not listed (a rebrand, a new team) fails closed until added.
TEAM_TO_CONSTRUCTOR = {
    "Alpine": "alpine",
    "Aston Martin": "aston_martin",
    "Audi": "audi",
    "Cadillac": "cadillac",
    "Ferrari": "ferrari",
    "Haas F1 Team": "haas",
    "McLaren": "mclaren",
    "Mercedes": "mercedes",
    "Racing Bulls": "rb",
    "Red Bull Racing": "red_bull",
    "Williams": "williams",
}

# A session is the scheduled one if it starts on the same UTC date and within this
# window. Not exact on purpose: Miami 2026 ran at 17:00Z while Jolpica's schedule
# still says 20:00Z. Country and circuit names are not used — they differ between
# the sources ("USA" / "United States"; 2026 R16 is "Bahrain" in Kuala Lumpur).
MATCH_WINDOW = timedelta(hours=6)

# OpenF1's free tier opens a session's data 30 min after it ends.
FREE_AFTER = timedelta(minutes=30)


def _instant(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _surname_key(name: str) -> str:
    words = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().split()
    return words[-1] if words else ""


def match_session(sessions: list[dict], date: str, time: str | None) -> dict | None:
    """The one non-cancelled session on the scheduled UTC date within MATCH_WINDOW."""
    scheduled = session_start(date, time or "")
    if scheduled is None:
        return None
    found = []
    for s in sessions:
        begins = _instant(s.get("date_start"))
        if (
            begins is not None
            and not s.get("is_cancelled")
            and begins.date() == scheduled.date()
            and abs(begins - scheduled) <= MATCH_WINDOW
        ):
            found.append(s)
    return found[0] if len(found) == 1 else None


def map_drivers(entrants: list[dict], current: list[dict]) -> dict[int, dict] | None:
    """OpenF1 car number -> our driver and team, or None if any car won't map exactly.

    ``current`` is current_drivers.json's ``drivers``. The number must be known,
    OpenF1's last name must equal the last word of the committed name (accent- and
    case-insensitive), and the team must be in TEAM_TO_CONSTRUCTOR.
    """
    by_number = {str(d["number"]): d for d in current if d.get("number")}
    mapped: dict[int, dict] = {}
    for e in entrants:
        number = e.get("driver_number")
        ours = by_number.get(str(number))
        if ours is None:
            print(f"  OpenF1: car #{number} is not in current_drivers.json")
            return None
        if _surname_key(e.get("last_name") or "") != _surname_key(ours["name"]):
            print(f"  OpenF1: car #{number} is {e.get('last_name')!r}; we have {ours['name']!r}")
            return None
        team = TEAM_TO_CONSTRUCTOR.get(e.get("team_name") or "")
        if team is None:
            print(f"  OpenF1: unknown team {e.get('team_name')!r} for car #{number}")
            return None
        mapped[number] = {"driverId": ours["driverId"], "name": ours["name"], "constructorId": team}
    return mapped


def _status(row: dict, lead_laps: int) -> str:
    """Jolpica's status vocabulary (verified row-for-row for 2026 rounds 1-13)."""
    if row.get("dsq"):
        return "Disqualified"
    if row.get("dns"):
        return "Did not start"
    if row.get("dnf"):
        return "Retired"
    if (row.get("number_of_laps") or 0) < lead_laps:
        return "Lapped"
    return "Finished"


def _row_order(row: dict) -> tuple[bool, int, int]:
    """Classified cars by position, then the rest by laps completed: Jolpica's order."""
    position = row.get("position")
    classified = isinstance(position, int)
    return (not classified, position if classified else 0, -(row.get("number_of_laps") or 0))


def race_rows(
    result: list[dict], drivers: dict[int, dict], grid: dict[int, int]
) -> list[dict] | None:
    lead_laps = max((r.get("number_of_laps") or 0) for r in result)
    rows = []
    for r in sorted(result, key=_row_order):
        d = drivers.get(r.get("driver_number"))
        if d is None:
            print(f"  OpenF1: a result for unmapped car #{r.get('driver_number')}")
            return None
        position = r.get("position")
        rows.append(
            {
                "driverId": d["driverId"],
                "constructorId": d["constructorId"],
                "grid": grid.get(r["driver_number"], 0),
                "position": position if isinstance(position, int) else None,
                "laps": r.get("number_of_laps") or 0,
                "status": _status(r, lead_laps),
            }
        )
    return rows


def _session(client, season: str, name: str, date: str, time: str | None, now: datetime):
    """The matched session if its free data should be available, else None."""
    session = match_session(client.sessions(int(season), name) or [], date, time)
    if session is None:
        print(f"  OpenF1: no single {name} session matches {date}")
        return None
    ended = _instant(session.get("date_end"))
    if ended is None or now < ended + FREE_AFTER:
        print(f"  OpenF1: the {date} {name} is still inside OpenF1's live window")
        return None
    return session


def build_race(
    race: dict, season: str, current: list[dict], now: datetime, client=openf1
) -> dict | None:
    """``{"podium", "race", "sessionEnd"}`` for a scheduled race, or None to write nothing."""
    session = _session(client, season, "Race", race.get("date", ""), race.get("time"), now)
    if session is None:
        return None
    key = session["session_key"]
    result = client.session_result(key)
    if not result:
        print(f"  OpenF1: no result yet for round {race['round']}")
        return None
    drivers = map_drivers(client.drivers(key) or [], current)
    if drivers is None:
        return None
    messages = client.race_control(key)
    if messages is None:
        print("  OpenF1: race control unavailable, so the stewards' check can't clear")
        return None
    reasons = hold_reasons(result, messages)
    if reasons:
        print(f"  OpenF1: holding round {race['round']}: " + "; ".join(reasons))
        return None
    grid: dict[int, int] = {}
    quali = match_session(
        client.sessions(int(season), "Qualifying") or [],
        race.get("qualifyingDate") or "",
        race.get("qualifyingTime"),
    )
    if quali is not None:
        for g in client.starting_grid(quali["session_key"]) or []:
            if isinstance(g.get("position"), int):
                grid[g["driver_number"]] = g["position"]
    rows = race_rows(result, drivers, grid)
    if rows is None:
        return None
    by_position = {r["position"]: r for r in rows if r["position"] in (1, 2, 3)}
    if sorted(by_position) != [1, 2, 3]:
        print(f"  OpenF1: no complete podium for round {race['round']}")
        return None
    names = {d["driverId"]: d["name"] for d in drivers.values()}
    podium: dict = {"season": season, "round": race["round"], "raceName": race["raceName"]}
    for p in (1, 2, 3):
        driver_id = by_position[p]["driverId"]
        podium[f"p{p}"] = {"driverId": driver_id, "name": names[driver_id]}
    return {
        "podium": podium,
        "race": {
            "season": season,
            "round": race["round"],
            "raceName": race["raceName"],
            "date": race["date"],
            "circuitId": race["circuitId"],
            "results": rows,
        },
        "sessionEnd": session["date_end"],
    }


def build_qualifying(
    race: dict, season: str, current: list[dict], now: datetime, client=openf1
) -> dict | None:
    """``{"entry", "sessionEnd"}`` for a race's qualifying, or None to write nothing."""
    session = _session(
        client, season, "Qualifying", race.get("qualifyingDate") or "", race.get("qualifyingTime"), now
    )
    if session is None:
        return None
    key = session["session_key"]
    result = client.session_result(key)
    if not result:
        print(f"  OpenF1: no qualifying result yet for round {race['round']}")
        return None
    drivers = map_drivers(client.drivers(key) or [], current)
    if drivers is None:
        return None
    rows = []
    classified = (r for r in result if isinstance(r.get("position"), int))
    for r in sorted(classified, key=lambda r: r["position"]):
        d = drivers.get(r.get("driver_number"))
        if d is None:
            print(f"  OpenF1: a qualifying result for unmapped car #{r.get('driver_number')}")
            return None
        rows.append({"driverId": d["driverId"], "constructorId": d["constructorId"], "position": r["position"]})
    if len(rows) < 3:
        return None
    return {"entry": {"season": season, "round": race["round"], "results": rows}, "sessionEnd": session["date_end"]}


def newest_started(schedule: dict, now: datetime, date_key: str, time_key: str) -> dict | None:
    """The newest scheduled race whose race (or qualifying) session has started by now."""
    newest = None
    for race in schedule.get("races", []):
        start = session_start(race.get(date_key) or "", race.get(time_key) or "")
        if start is None or start > now:
            continue
        if newest is None or int(race["round"]) > int(newest["round"]):
            newest = race
    return newest


def _rounds(rows: list[dict]) -> set[tuple[str, str]]:
    return {(r["season"], r["round"]) for r in rows}


def fill(
    schedule: dict,
    current: list[dict],
    podiums: list[dict],
    race_results: list[dict],
    qualifying: list[dict],
    unconfirmed: list[dict],
    now: datetime,
    client=openf1,
) -> set[str]:
    """Write the newest race and qualifying Jolpica lacks into the lists, in place.

    Returns the kinds written ({"race", "qualifying"}); each written round is
    appended to ``unconfirmed``. A race is only written when *both* podiums and
    race_results lack it, so a round never mixes sources.
    """
    season = str(schedule["season"])
    written: set[str] = set()

    race = newest_started(schedule, now, "date", "time")
    if race is not None:
        key = (season, race["round"])
        if key not in _rounds(podiums) and key not in _rounds(race_results):
            built = build_race(race, season, current, now, client)
            if built is not None:
                podiums.append(built["podium"])
                race_results.append(built["race"])
                unconfirmed.append(
                    {"season": season, "round": race["round"], "kind": "race",
                     "pending": ["podiums", "race_results"], "since": built["sessionEnd"]}
                )
                written.add("race")

    quali = newest_started(schedule, now, "qualifyingDate", "qualifyingTime")
    if quali is not None and (season, quali["round"]) not in _rounds(qualifying):
        built = build_qualifying(quali, season, current, now, client)
        if built is not None:
            qualifying.append(built["entry"])
            unconfirmed.append(
                {"season": season, "round": quali["round"], "kind": "qualifying",
                 "pending": ["qualifying"], "since": built["sessionEnd"]}
            )
            written.add("qualifying")

    for rows in (podiums, race_results, qualifying):
        rows.sort(key=lambda r: (int(r["season"]), int(r["round"])))
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--now", help="ISO-8601 instant to act as 'now' (rehearsals)")
    args = ap.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)

    schedule = load_schedule().model_dump()
    current = [d.model_dump() for d in load_current_drivers().drivers]
    podiums = [p.model_dump() for p in load_podiums()]
    race_results = [r.model_dump() for r in load_race_results()]
    qualifying = [q.model_dump() for q in load_qualifying()]
    has_file = (repository.DATA_DIR / "unconfirmed.json").exists()
    unconfirmed = [u.model_dump() for u in load_unconfirmed()] if has_file else []

    try:
        written = fill(schedule, current, podiums, race_results, qualifying, unconfirmed, now)
    except Exception:  # noqa: BLE001 - the fast lane must never break the Jolpica path
        traceback.print_exc()
        print("OpenF1 fast lane failed; leaving the round to Jolpica.")
        return 0

    if "race" in written:
        save_podiums(podiums)
        save_race_results(race_results)
    if "qualifying" in written:
        save_qualifying(qualifying)
    if written:
        save_unconfirmed(unconfirmed)
        print(f"OpenF1 filled: {', '.join(sorted(written))} (awaiting Jolpica)")
    else:
        print("OpenF1 fast lane: nothing to fill.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_fetch_openf1.py -q`
Expected: all pass: 11 identical races, 2 held, 13 qualifying, plus the matcher, mapper, fail-closed and `fill` tests. If a byte-identical test fails, **do not loosen it**. Print both dicts, find the differing field, and fix the mapping. The scratchpad run showed these rows identical, so a diff means the code drifted from the verified version.

- [ ] **Step 5: Commit**

```bash
python -m ruff check src/fetch/fetch_openf1.py tests/test_fetch_openf1.py
python -m ruff format src/fetch/fetch_openf1.py tests/test_fetch_openf1.py
git add src/fetch/fetch_openf1.py tests/test_fetch_openf1.py
git commit -m "Fill the newest round from OpenF1 in Jolpica's exact row shape" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 6: Pipeline, guard, watcher and workflow integration

**Files:**
- Modify: `src/update.py`, `src/check_update_due.py`, `src/wait_for_results.py`, `.github/workflows/update.yml`
- Test: `tests/test_check_update_due.py`, `tests/test_wait_for_results.py` (append)

**Interfaces:**
- Consumes: `build_race`, `build_qualifying` (Task 5); PR 2's `wait_target`, `report(published: str)`, `pending_session_starts`, `is_successor_due`.
- Produces: `check_update_due.STALE_UNCONFIRMED` (48 h), `is_confirmation_due(unconfirmed) -> bool`, `stale_unconfirmed(unconfirmed, now) -> list[str]`, `read_unconfirmed(data_dir: Path = DATA_DIR) -> list[dict]`; `pending_session_starts`/`is_successor_due` gain `unconfirmed: Sequence[dict] = ()`; CLI `--fail-on-stale`. `wait_for_results.wait_target(..., unconfirmed=())` can return `("confirm-race"|"confirm-qualifying", season, round)`; `wait_until(ready, *, timeout_s, interval_s, sleep, now) -> str | None`; `report("fast")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_update_due.py`:

```python
# --- OpenF1 rounds awaiting Jolpica ---------------------------------------------

from check_update_due import is_confirmation_due, stale_unconfirmed  # noqa: E402

UNCONFIRMED_R10 = {
    "season": "2026",
    "round": "10",
    "kind": "race",
    "pending": ["race_results"],
    "since": "2026-07-19T15:00:00+00:00",
}


def test_an_unconfirmed_round_keeps_the_guard_armed():
    assert is_confirmation_due([]) is False
    assert is_confirmation_due([UNCONFIRMED_R10]) is True


def test_a_round_unconfirmed_for_over_48h_is_stale():
    assert stale_unconfirmed([UNCONFIRMED_R10], at("2026-07-21 15:00")) == []
    assert len(stale_unconfirmed([UNCONFIRMED_R10], at("2026-07-21 15:01"))) == 1


def test_the_successor_waits_for_confirmation_inside_the_window():
    s = qsched(R10)
    # Jolpica hasn't confirmed; the chain may run until 12h after the session ended.
    assert is_successor_due(s, ASOF_R10, None, at("2026-07-20 02:59"), [UNCONFIRMED_R10]) is True
    assert is_successor_due(s, ASOF_R10, None, at("2026-07-20 03:00"), [UNCONFIRMED_R10]) is False
```

Append to `tests/test_wait_for_results.py`:

```python
# --- OpenF1 fast lane: confirmation targets, first-ready source, "fast" ------------

from wait_for_results import report, wait_until  # noqa: E402

UNCONFIRMED_13 = [
    {"season": "2026", "round": "13", "kind": "race", "pending": ["race_results"],
     "since": "2026-09-06T15:00:00+00:00"}
]


def test_wait_target_waits_for_jolpica_to_confirm_an_openf1_round():
    podigami = {"asOf": {"season": "2026", "round": "13"}, "postQuali": None}
    target = wait_target(SCHEDULE, podigami, at("2026-09-06 16:00"), UNCONFIRMED_13)
    assert target == ("confirm-race", 2026, 13)


def test_a_pending_session_outranks_a_confirmation():
    podigami = {"asOf": {"season": "2026", "round": "12"}, "postQuali": None}
    assert wait_target(SCHEDULE, podigami, at("2026-09-06 16:00"), UNCONFIRMED_13) == ("race", 2026, 13)


def test_wait_until_returns_the_first_ready_source():
    clock = Clock()
    feed = [None, None, "openf1"]
    assert wait_until(lambda: feed.pop(0), timeout_s=3600, interval_s=180, sleep=clock.sleep, now=clock) == "openf1"
    assert clock.slept == [180, 180]


def test_wait_until_gives_up_with_none():
    clock = Clock()
    assert wait_until(lambda: None, timeout_s=600, interval_s=180, sleep=clock.sleep, now=clock) is None


def test_report_fast(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    report("fast")
    assert out.read_text(encoding="utf-8") == "published=fast\n"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_check_update_due.py tests/test_wait_for_results.py -q`
Expected: `ImportError` for `is_confirmation_due` / `wait_until`.

- [ ] **Step 3: Guard changes (`src/check_update_due.py`)**

Add `from collections.abc import Sequence` to the imports. Below `SUCCESSOR_WINDOW`, add:

```python
# A round OpenF1 filled must be confirmed by Jolpica within this long of its
# session ending, or the run fails loudly (reusing the auto-update-failure
# alert): Jolpica is down, or the two sources disagree about the round.
STALE_UNCONFIRMED = timedelta(hours=48)
```

Add these functions after `is_post_quali_update_due`:

```python
def read_unconfirmed(data_dir: Path = DATA_DIR) -> list[dict]:
    """data/unconfirmed.json as plain dicts; [] when absent or unreadable."""
    path = data_dir / "unconfirmed.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def is_confirmation_due(unconfirmed: Sequence[dict]) -> bool:
    """True while any round's rows still await Jolpica."""
    return bool(unconfirmed)


def stale_unconfirmed(unconfirmed: Sequence[dict], now: datetime) -> list[str]:
    """Rounds still unconfirmed more than STALE_UNCONFIRMED after their session ended."""
    stale = []
    for e in unconfirmed:
        try:
            since = datetime.fromisoformat(e["since"])
        except (KeyError, TypeError, ValueError):
            stale.append(f"{e.get('season')} R{e.get('round')} (unreadable 'since')")
            continue
        if now - since > STALE_UNCONFIRMED:
            stale.append(
                f"{e['season']} R{e['round']} {e['kind']}: "
                f"{', '.join(e['pending'])} pending since {e['since']}"
            )
    return stale
```

Change `pending_session_starts` and `is_successor_due` to take unconfirmed rounds (their windows run from the session end):

```python
def pending_session_starts(
    schedule: dict,
    asof: dict,
    post_quali: dict | None,
    now: datetime,
    unconfirmed: Sequence[dict] = (),
) -> list[datetime]:
    """Starts of the sessions the data still lacks, plus the session end of each
    round still awaiting Jolpica's confirmation."""
    starts: list[datetime] = []
    race = latest_armed_round(schedule, now)
    if race is not None and race > _have(asof):
        entry = _race_by_round(schedule, race[1])
        start = entry and session_start(entry.get("date", ""), entry.get("time", ""))
        if start:
            starts.append(start)
    quali = next_quali_target(schedule, asof, post_quali, now)
    if quali is not None:
        entry = _race_by_round(schedule, quali[1])
        start = entry and session_start(
            entry.get("qualifyingDate") or "", entry.get("qualifyingTime") or ""
        )
        if start:
            starts.append(start)
    for e in unconfirmed:
        try:
            starts.append(datetime.fromisoformat(e["since"]))
        except (KeyError, TypeError, ValueError):
            continue
    return starts


def is_successor_due(
    schedule: dict,
    asof: dict,
    post_quali: dict | None,
    now: datetime,
    unconfirmed: Sequence[dict] = (),
) -> bool:
    """True while a session is pending and ``now`` is inside its SUCCESSOR_WINDOW."""
    return any(
        now < start + SUCCESSOR_WINDOW
        for start in pending_session_starts(schedule, asof, post_quali, now, unconfirmed)
    )
```

Replace `main` with:

```python
def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI glue
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--successor",
        action="store_true",
        help="report successor=true|false (a session still pending) instead of due",
    )
    ap.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="exit 1 when a round stays unconfirmed past STALE_UNCONFIRMED",
    )
    args = ap.parse_args(argv)

    schedule = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    podigami = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))
    asof = podigami.get("asOf", {})
    post = podigami.get("postQuali")
    unconfirmed = read_unconfirmed()
    now = datetime.now(UTC)

    if args.fail_on_stale:
        stale = stale_unconfirmed(unconfirmed, now)
        for line in stale:
            print(f"::error::Jolpica has not confirmed {line}")
        return 1 if stale else 0

    if args.successor:
        key = "successor"
        value = is_successor_due(schedule, asof, post, now, unconfirmed)
        print(f"successor due: {value} (asOf season={asof.get('season')} round={asof.get('round')})")
    else:
        key = "due"
        race_due = is_update_due(schedule, asof, now)
        quali_due = is_post_quali_update_due(schedule, asof, post, now)
        confirm_due = is_confirmation_due(unconfirmed)
        value = race_due or quali_due or confirm_due
        print(
            f"update due: {value} (race={race_due} quali={quali_due} confirm={confirm_due} "
            f"asOf season={asof.get('season')} round={asof.get('round')})"
        )

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={'true' if value else 'false'}\n")
    return 0
```

- [ ] **Step 4: Watcher changes (`src/wait_for_results.py`)**

Change the guard import to `from check_update_due import is_update_due, latest_armed_round, next_quali_target, read_unconfirmed`, and add `from fetch import fetch_openf1` after the `fetch.api_cache` import.

Replace `wait_for_round` with a generic `wait_until` plus a thin `wait_for_round` (same behaviour as before, so its existing tests keep passing):

```python
def wait_until(
    ready: Callable[[], str | None],
    *,
    timeout_s: float = POLL_TIMEOUT_S,
    interval_s: float = POLL_INTERVAL_S,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> str | None:
    """Poll ``ready`` until it names a source, or None once the budget runs out.

    Never sleeps when the data is already there, and stops before a sleep that
    would overrun ``timeout_s`` rather than spinning past it.
    """
    deadline = now() + timeout_s
    while True:
        source = ready()
        if source is not None:
            return source
        if now() + interval_s > deadline:
            return None
        sleep(interval_s)


def wait_for_round(
    target: int,
    fetch: Callable[[], object | None],
    *,
    timeout_s: float = POLL_TIMEOUT_S,
    interval_s: float = POLL_INTERVAL_S,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> bool:
    """Poll ``fetch`` until the feed reports round >= ``target``."""

    def ready() -> str | None:
        published = latest_published_round(fetch())
        return "published" if published is not None and published >= target else None

    return wait_until(ready, timeout_s=timeout_s, interval_s=interval_s, sleep=sleep, now=now) is not None
```

Extend `wait_target` with an `unconfirmed` parameter. Add `unconfirmed: Sequence[dict] = ()` to its signature (import `Sequence` from `collections.abc` next to `Callable`) and, just before its final `return None`, add:

```python
    for e in unconfirmed:
        try:
            return (f"confirm-{e['kind']}", int(e["season"]), int(e["round"]))
        except (KeyError, TypeError, ValueError):
            continue
```

Add the OpenF1 readiness check (the same code path the fetcher uses, so the two can't disagree):

```python
def _openf1_ready(kind: str, schedule: dict, season: int, rnd: int) -> bool:
    """Would fetch_openf1 write this session right now?"""
    race = next((r for r in schedule.get("races", []) if str(r.get("round")) == str(rnd)), None)
    if race is None:
        return False
    try:
        current = json.loads((DATA_DIR / "current_drivers.json").read_text(encoding="utf-8"))
        build = fetch_openf1.build_race if kind == "race" else fetch_openf1.build_qualifying
        return build(race, str(season), current.get("drivers", []), datetime.now(UTC)) is not None
    except Exception as exc:  # noqa: BLE001 - an OpenF1 surprise must never break the watch
        # Logged, not swallowed: the watch carries on waiting for Jolpica.
        print(f"  OpenF1 readiness check failed ({exc!r}); treating it as not ready")
        return False
```

Replace `main` with:

```python
def main() -> int:  # pragma: no cover - thin CLI glue exercised in CI, not unit tests
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeout", type=float, default=POLL_TIMEOUT_S, help="seconds")
    ap.add_argument("--interval", type=float, default=POLL_INTERVAL_S, help="seconds")
    args = ap.parse_args()

    schedule = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    podigami = json.loads((DATA_DIR / "podigami.json").read_text(encoding="utf-8"))
    unconfirmed = read_unconfirmed(DATA_DIR)

    target = wait_target(schedule, podigami, datetime.now(UTC), unconfirmed)
    if target is None:
        print("Nothing pending upstream; nothing to wait for.")
        report("true")
        return 0

    kind, season, rnd = target
    races_feed = kind in ("race", "confirm-race")

    def ready() -> str | None:
        feed = _fetch_last_results(season) if races_feed else _fetch_last_qualifying(season)
        published = latest_published_round(feed)
        if published is not None and published >= rnd:
            return "jolpica"
        if kind in ("race", "qualifying") and _openf1_ready(kind, schedule, season, rnd):
            return "openf1"
        return None

    print(f"Waiting for {season} round {rnd} ({kind}) upstream...")
    source = wait_until(ready, timeout_s=args.timeout, interval_s=args.interval)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")
    if source == "jolpica":
        print(f"Jolpica has round {rnd} ({kind}) at {stamp}; running the pipeline.")
        report("true")
    elif source == "openf1":
        print(f"OpenF1 has round {rnd} ({kind}), stewards clear, at {stamp}; fast lane.")
        report("fast")  # the successor run then waits for Jolpica to confirm
    else:
        print(f"Round {rnd} ({kind}) still unpublished after the budget; running anyway.")
        report("false")
    return 0
```

- [ ] **Step 5: Pipeline step (`src/update.py`)**

In `STEPS`, directly after `("Fetching qualifying", "fetch/fetch_qualifying.py"),` insert:

```python
    # After the Jolpica fetchers, so Jolpica always wins a round it already has.
    ("Filling the newest round from OpenF1", "fetch/fetch_openf1.py"),
```

- [ ] **Step 6: Workflow stale check (`.github/workflows/update.yml`)**

Insert after the `Run tests` step (before `Check whether a session is still pending`):

```yaml
      # A round OpenF1 filled must be confirmed by Jolpica within 48h of its
      # session. Failing here (after the PR step, like validate/tests) trips
      # notify-failure's alert issue: Jolpica is down, or the sources disagree.
      # Guarded: scheduled runs take this workflow from develop but main's
      # scripts, and main's guard only learns --fail-on-stale when the fast lane
      # (fetch_openf1.py) is promoted with it.
      - name: Fail if a round stays unconfirmed for over 48h
        run: |
          if [ -f src/fetch/fetch_openf1.py ]; then
            python src/check_update_due.py --fail-on-stale
          else
            echo "The OpenF1 fast lane is not on main yet; nothing can be unconfirmed."
          fi
```

(The successor condition `published != 'true'` already covers `published=fast`: after a fast-lane run, the successor waits for Jolpica's confirmation.)

- [ ] **Step 7: Run everything touched**

Run: `python -m pytest tests/test_check_update_due.py tests/test_wait_for_results.py tests/test_fetch_openf1.py tests/test_unconfirmed.py -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
python -m ruff check . && python -m ruff format .
git add src/update.py src/check_update_due.py src/wait_for_results.py .github/workflows/update.yml tests/test_check_update_due.py tests/test_wait_for_results.py
git commit -m "Run the OpenF1 fast lane in the pipeline and keep watching until Jolpica confirms" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 7: Live rehearsal: replay Monza race day

Proves the whole path on real OpenF1 data: fill → compute → build. The replay rolls the local data back to before Monza's result and pretends it is 16:00Z on race day.

- [ ] **Step 1: Scratch worktree with pre-Monza data**

```bash
git worktree add --detach ../f1p-rehearsal HEAD
cd ../f1p-rehearsal
git checkout 46895a3 -- data/
PYTHONPATH=src python -c "from datalib import save_unconfirmed; save_unconfirmed([])"
```
(`46895a3` is main's data just before Monza's result landed: `asOf` round 12, with the round 13 qualifying and `postQuali` present.)

- [ ] **Step 2: Fill from OpenF1 as of 16:00Z on race day**

```bash
python src/fetch/fetch_openf1.py --now 2026-09-06T16:00:00+00:00
```
Expected: `OpenF1 filled: race (awaiting Jolpica)`. `data/unconfirmed.json` holds round 13 with `"since": "2026-09-06T15:00:00+00:00"`.

- [ ] **Step 3: The rows equal what Jolpica published**

```bash
python - <<'EOF'
import json, subprocess
def main(p): return json.loads(subprocess.run(["git","show",f"origin/main:{p}"],capture_output=True,text=True,encoding="utf-8").stdout)
def here(p): return json.load(open(p, encoding="utf-8"))
for name in ("podiums", "race_results"):
    ours = next(r for r in here(f"data/{name}.json") if r["season"] == "2026" and r["round"] == "13")
    theirs = next(r for r in main(f"data/{name}.json") if r["season"] == "2026" and r["round"] == "13")
    print(name, "IDENTICAL" if ours == theirs else "DIFFERENT")
EOF
```
Expected: `podiums IDENTICAL`, `race_results IDENTICAL`.

- [ ] **Step 4: Compute and build like the pipeline would**

```bash
python src/compute/count_combos.py && python src/compute/compute_soulmates.py && python src/compute/compute_podigami.py && python src/build_site.py
python -c "import re;h=open('dist/index.html',encoding='utf-8').read();i=h.find('class=\"last-race\"');print(re.sub('<[^>]+>',' ',h[i:i+1500])[:300])"
```
Expected: the last-race strip reads `R13 · Italian Grand Prix  ANT / RUS / VER  4th time · last 2026 R8 · Austrian Grand Prix`, and the next-race card is the Spanish Grand Prix. Optionally screenshot `dist/index.html` with Playwright.

- [ ] **Step 5: Clean up**

```bash
cd -
git worktree remove --force ../f1p-rehearsal
```

---

### Task 8: Docs, verification, PR, first live race

**Files:** `CLAUDE.md`, `README.md`, `RELEASE_NOTES.md`

- [ ] **Step 1: CLAUDE.md**

1. In "### Three-stage pipeline" / the `src/fetch/` line, change `→ API calls to the Jolpica F1 API (api.jolpi.ca/ergast/f1) → data/*.json` to `→ API calls to the Jolpica F1 API (api.jolpi.ca/ergast/f1), plus OpenF1 for the newest round only → data/*.json`.
2. Add a new subsection before "#### ⚠️ When a finished race doesn't appear":

```markdown
#### OpenF1 fast lane (#<PR>)

`src/fetch/fetch_openf1.py` runs right after the Jolpica fetchers. For the newest race and qualifying session Jolpica does not have yet, it writes OpenF1's classification (api.openf1.org, ~30 min after the session) into `podiums.json` / `race_results.json` / `qualifying.json` in Jolpica's exact row shape, so the whole site rolls forward ~40 min after the flag. For every 2026 round it lets through, its rows were identical to Jolpica's.
- **Fail closed.** No write on any OpenF1 error, an unmatched/cancelled session (matched by UTC date + 6 h window), an unknown car number, a surname mismatch, an unknown team name (`TEAM_TO_CONSTRUCTOR` — a rebrand needs a new alias), or a held **stewards' check** (`src/fetch/stewards_gate.py`: open incident, unserved drive-through or time penalties that would change the podium *trio*). Holds ~22% of races; those keep the Jolpica timing.
- **Jolpica always wins.** A race is only filled when both `podiums.json` and `race_results.json` lack it. Each written round is listed in `data/unconfirmed.json` (per dataset); each Jolpica fetcher confirms the rounds its API returned (`fetch/unconfirmed.py`). The guard stays armed while anything is unconfirmed; after a fast-lane run (`published=fast`) the successor run waits for Jolpica.
- **Discrepancies are loud.** Jolpica's confirmation overwrites OpenF1's rows; a changed podium triggers the podium revision alert. A round unconfirmed > 48 h after its session fails the run (`--fail-on-stale`) → `auto-update-failure` issue.
- **Can't be foreseen:** post-race scrutineering disqualifications (Austin 2023, Spa 2024, Las Vegas 2025). The site shows the crossed-the-line trio for a few hours, then corrects itself with a revision alert.
- Rehearse with `python src/fetch/fetch_openf1.py --now <ISO>` in a scratch worktree (see the plan's Task 7).
```

- [ ] **Step 2: README.md**

In the architecture mermaid, add `OF(("OpenF1 API"))` under `API(("Jolpica F1 API"))`, add `FO["fetch_openf1"]:::fetch` inside the `FETCH` subgraph, and add `OF -.-> FO` under `API -.-> FETCH`. In "## 📡 Data source", after the Jolpica paragraph add:

```markdown
The **newest** race and qualifying session come first from **[OpenF1](https://openf1.org)**, about 30 minutes after the session, so a result reaches the site roughly 40 minutes after the chequered flag instead of hours later. OpenF1's rows are written in Jolpica's exact format, held back while the stewards could still change the podium, and replaced by Jolpica's as soon as it publishes (a changed podium raises an alert). All history comes from Jolpica.
```

- [ ] **Step 3: RELEASE_NOTES.md**

Under the current date heading, `### Features`:

```markdown
- **Race results now reach the site about 40 minutes after the chequered flag in most races.** The newest race and qualifying session come from OpenF1, which publishes the official classification about half an hour after a session, instead of waiting 1–7 hours for Jolpica. OpenF1's rows are written in exactly Jolpica's format. For every 2026 race the check lets through, they were identical row for row, so when Jolpica publishes, nothing changes. The fast lane holds back whenever the stewards could still change the podium trio (an open investigation, an unserved penalty) — about one race in five, which then follows the old timing — and a result Jolpica later changes (a post-race disqualification) is corrected automatically and flagged (#<PR>)
```

- [ ] **Step 4: Full verification (mirrors CI)**

```bash
python -m ruff check .
python -m ruff format --check .
PYTHONPATH=src python -m datalib.validate
python -m pytest -q
python src/update.py
git status --short
```
Expected: all green. `update.py` runs end to end, and the fast-lane step prints `nothing to fill` (Jolpica has every finished round). `git status` shows only the data churn a normal refresh produces. Discard that churn with `git checkout -- data/` before committing.

- [ ] **Step 5: Commit, PR, number, merge, promote**

```bash
git add CLAUDE.md README.md RELEASE_NOTES.md
git commit -m "Document the OpenF1 fast lane" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
git push -u origin feat/openf1-fast-lane
gh pr create --base develop --title "Fill the newest round from OpenF1 until Jolpica publishes it" --body-file - <<'EOF'
## Summary
PR 3 of 3 from `docs/superpowers/specs/2026-09-10-openf1-fast-lane-design.md`. OpenF1 fills the newest race and qualifying session ~30 min after the session, in Jolpica's exact row shape, unless the stewards could still change the podium trio. Jolpica overwrites it on arrival and any podium change raises the revision alert. Everything before the current round stays Jolpica-only.

## Changes
- `fetch/openf1.py` (fail-closed client), `fetch/stewards_gate.py` (podium-scoped stewards' check), `fetch/fetch_openf1.py` (match, map, build rows, fill; `--now` for rehearsals)
- `data/unconfirmed.json` + schema; Jolpica fetchers confirm rounds per dataset (`fetch/unconfirmed.py`)
- Guard: confirmation trigger, `--fail-on-stale` (48 h), successor waits for confirmation; watcher: OpenF1 as a ready source, `published=fast`
- `update.py` runs the fast lane after the Jolpica fetchers; `update.yml` stale step
- Frozen fixtures + recorder under `tests/fixtures/openf1/`; docs

## Testing
- `python -m pytest -q`: byte-identical rows vs a frozen Jolpica snapshot for 2026 R1–R13 (R6 and R9 held), qualifying by position, 83-race stewards' backtest (≥75% published, Monaco 2026 + Jeddah 2023 held), fail-closed matrix, confirmation bookkeeping
- Live rehearsal: pre-Monza data + OpenF1 at 16:00Z race day → rows identical to what Jolpica published; site shows R13 "4th time"
- `python -m ruff check .` / `ruff format --check .` / `datalib.validate` / `python src/update.py`

## Checklist
- [x] Lint and format pass
- [x] Tests pass
- [x] No security issues introduced (no new secrets; OpenF1 is public and read-only; fail-closed on every error)
- [x] RELEASE_NOTES.md updated

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD
EOF
```

Then:

1. Replace `#<PR>` in `CLAUDE.md` and `RELEASE_NOTES.md` with the printed number; `git commit -am "Reference #<number> in the release note"` (with the trailer) and `git push`.
2. `gh pr checks <number> --watch` (7 checks), then `gh pr merge <number> --squash --delete-branch`.
   Prove the merged workflow still runs against `main`, which doesn't have the fast lane yet (the stale step must print its skip line):
   ```bash
   gh workflow run update.yml -f mode=auto -f force=true
   sleep 20; run=$(gh run list --workflow=update.yml --limit 1 --json databaseId --jq '.[0].databaseId')
   gh run watch "$run" --exit-status
   gh run view "$run" --log | grep "fast lane is not on main yet"
   ```
   Expected: green, with the skip line. If it fails, revert the merge on `develop` immediately.
3. Promote only when no qualifying or race is within the next 48 h. The only data file this adds is the new `data/unconfirmed.json`; `main` has no copy, so the promotion's three-way merge cannot conflict on it:
   ```bash
   gh pr create --base main --head develop --title "Promote develop to main: OpenF1 fast lane" \
     --body "Promotes #<number>: OpenF1 fills the newest race and qualifying session ~30 min after the session unless the stewards could still change the podium; Jolpica overwrites it on arrival and a changed podium raises the revision alert. Adds data/unconfirmed.json ([] at rest)."
   gh pr checks <promotion number> --watch   # all 9 required checks
   gh pr merge <promotion number> --merge
   ```
4. `git switch develop && git pull && git branch -d feat/openf1-fast-lane`.

- [ ] **Step 6: Watch the first live weekend**

After the first qualifying and race with the fast lane live:
- `gh run list --workflow=update.yml --limit 10` shows a run that logged `OpenF1 has round N … fast lane`, then a successor that logged `Jolpica has round N`.
- There are two data PRs: the fast one, and the confirmation (podium usually unchanged; small model churn is expected).
- Compute the actual flag-to-live time from the fast PR's merge time and compare it with the spec's 40 min target. If a race was held, note the stewards' reason from the log.
- Any `podium-revised` issue: verify against formula1.com.
