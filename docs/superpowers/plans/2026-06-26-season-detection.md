# Season Detection Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `max(season in podiums.json)` with `datetime.date.today().year` in three fetch scripts and fix `render_last_race` to fall back to the most recent available podium when the scheduled last race has no API data yet.

**Architecture:** Four targeted edits, no new files except one new test file. Each fetch helper gets an optional `today_year` parameter so it's testable without patching datetime. The `render_last_race` fallback replaces the early-return with a max-podium lookup plus a schedule-entry probe.

**Tech Stack:** Python 3.11+, pytest, ruff. No new dependencies.

---

## File Map

| Action | File |
|--------|------|
| Modify | `src/fetch/fetch_schedule.py` |
| Modify | `src/fetch/fetch_current_drivers.py` |
| Modify | `src/fetch/fetch_constructor_standings.py` |
| Modify | `src/build/build_podigami_html.py` |
| Create | `tests/test_fetch_season.py` |
| Modify | `tests/test_next_race.py` |

---

### Task 1: Fix `fetch_schedule.py` — remove podiums dependency

**Files:**
- Modify: `src/fetch/fetch_schedule.py:17-21` (imports), `src/fetch/fetch_schedule.py:35-38` (constants), `src/fetch/fetch_schedule.py:59-61` (function), `src/fetch/fetch_schedule.py:93-95` (main)
- Create: `tests/test_fetch_season.py`

- [ ] **Step 1: Write the failing test**

  Create `tests/test_fetch_season.py`:

  ```python
  """Tests for calendar-year season detection in fetch scripts."""

  import json
  from fetch import fetch_schedule as fs
  from fetch import fetch_current_drivers as fcd
  from fetch import fetch_constructor_standings as fcs


  def test_fetch_schedule_has_no_podiums_dependency():
      assert not hasattr(fs, "current_season"), "current_season() must be removed"
      assert not hasattr(fs, "PODIUMS_PATH"), "PODIUMS_PATH must be removed"
  ```

- [ ] **Step 2: Run the test to confirm it fails**

  ```
  pytest tests/test_fetch_season.py::test_fetch_schedule_has_no_podiums_dependency -v
  ```

  Expected: `FAILED` — `fs` still has `current_season` and `PODIUMS_PATH`.

- [ ] **Step 3: Apply the fix to `fetch_schedule.py`**

  Replace the imports block (lines 17–22):

  ```python
  # before
  import json
  import sys
  import time
  from pathlib import Path
  ```

  ```python
  # after
  import datetime
  import json
  import sys
  import time
  from pathlib import Path
  ```

  Remove the `PODIUMS_PATH` constant (line 36):

  ```python
  # before
  DATA_DIR = Path(__file__).resolve().parents[2] / "data"
  PODIUMS_PATH = DATA_DIR / "podiums.json"
  CIRCUITS_PATH = DATA_DIR / "f1-circuits.geojson"
  OUT_PATH = DATA_DIR / "schedule.json"
  ```

  ```python
  # after
  DATA_DIR = Path(__file__).resolve().parents[2] / "data"
  CIRCUITS_PATH = DATA_DIR / "f1-circuits.geojson"
  OUT_PATH = DATA_DIR / "schedule.json"
  ```

  Delete `current_season()` entirely (lines 59–61):

  ```python
  # DELETE this function:
  def current_season() -> int:
      podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
      return max(int(p["season"]) for p in podiums)
  ```

  In `main()`, replace `season = current_season()` (line 95):

  ```python
  # before
  def main() -> int:
      DATA_DIR.mkdir(parents=True, exist_ok=True)
      season = current_season()
  ```

  ```python
  # after
  def main() -> int:
      DATA_DIR.mkdir(parents=True, exist_ok=True)
      season = datetime.date.today().year
  ```

- [ ] **Step 4: Run the test to confirm it passes**

  ```
  pytest tests/test_fetch_season.py::test_fetch_schedule_has_no_podiums_dependency -v
  ```

  Expected: `PASSED`.

- [ ] **Step 5: Commit**

  ```
  git add src/fetch/fetch_schedule.py tests/test_fetch_season.py
  git commit -m "fix: use calendar year in fetch_schedule, remove podiums dependency"
  ```

---

### Task 2: Fix `fetch_current_drivers.py` — calendar-year `season_and_recent_rounds`

**Files:**
- Modify: `src/fetch/fetch_current_drivers.py:17-19` (imports), `src/fetch/fetch_current_drivers.py:56-60` (function)
- Modify: `tests/test_fetch_season.py`

- [ ] **Step 1: Write the failing tests**

  Append to `tests/test_fetch_season.py`:

  ```python

  def test_season_and_recent_rounds_returns_calendar_year_with_rounds(tmp_path, monkeypatch):
      podiums = [
          {"season": "2025", "round": "21", "raceName": "Qatar GP",
           "p1": {}, "p2": {}, "p3": {}},
          {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP",
           "p1": {}, "p2": {}, "p3": {}},
          {"season": "2026", "round": "1", "raceName": "Bahrain GP",
           "p1": {}, "p2": {}, "p3": {}},
      ]
      f = tmp_path / "podiums.json"
      f.write_text(json.dumps(podiums))
      monkeypatch.setattr(fcd, "PODIUMS_PATH", f)

      year, rounds = fcd.season_and_recent_rounds(today_year=2026)

      assert year == 2026
      assert rounds == [1]


  def test_season_and_recent_rounds_empty_when_no_current_year_rounds(tmp_path, monkeypatch):
      podiums = [
          {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP",
           "p1": {}, "p2": {}, "p3": {}},
      ]
      f = tmp_path / "podiums.json"
      f.write_text(json.dumps(podiums))
      monkeypatch.setattr(fcd, "PODIUMS_PATH", f)

      year, rounds = fcd.season_and_recent_rounds(today_year=2026)

      assert year == 2026
      assert rounds == []
  ```

- [ ] **Step 2: Run the tests to confirm they fail**

  ```
  pytest tests/test_fetch_season.py::test_season_and_recent_rounds_returns_calendar_year_with_rounds tests/test_fetch_season.py::test_season_and_recent_rounds_empty_when_no_current_year_rounds -v
  ```

  Expected: both `FAILED` — `season_and_recent_rounds` doesn't accept `today_year` yet.

- [ ] **Step 3: Apply the fix to `fetch_current_drivers.py`**

  Add `import datetime` to the imports block (after `import json`):

  ```python
  # before
  import json
  import sys
  import time
  from pathlib import Path
  ```

  ```python
  # after
  import datetime
  import json
  import sys
  import time
  from pathlib import Path
  ```

  Replace `season_and_recent_rounds()` (lines 56–60):

  ```python
  # before
  def season_and_recent_rounds() -> tuple[int, list[int]]:
      podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
      season = max(int(p["season"]) for p in podiums)
      rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == season})
      return season, rounds[-ROUNDS_BACK:]
  ```

  ```python
  # after
  def season_and_recent_rounds(today_year: int | None = None) -> tuple[int, list[int]]:
      year = today_year if today_year is not None else datetime.date.today().year
      podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
      rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == year})
      return year, rounds[-ROUNDS_BACK:]
  ```

- [ ] **Step 4: Run the tests to confirm they pass**

  ```
  pytest tests/test_fetch_season.py::test_season_and_recent_rounds_returns_calendar_year_with_rounds tests/test_fetch_season.py::test_season_and_recent_rounds_empty_when_no_current_year_rounds -v
  ```

  Expected: both `PASSED`.

- [ ] **Step 5: Commit**

  ```
  git add src/fetch/fetch_current_drivers.py tests/test_fetch_season.py
  git commit -m "fix: use calendar year in season_and_recent_rounds"
  ```

---

### Task 3: Fix `fetch_constructor_standings.py` — calendar-year `season_and_rounds`

**Files:**
- Modify: `src/fetch/fetch_constructor_standings.py:20-22` (imports), `src/fetch/fetch_constructor_standings.py:59-63` (function)
- Modify: `tests/test_fetch_season.py`

- [ ] **Step 1: Write the failing tests**

  Append to `tests/test_fetch_season.py`:

  ```python

  def test_season_and_rounds_returns_calendar_year_with_rounds(tmp_path, monkeypatch):
      podiums = [
          {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP",
           "p1": {}, "p2": {}, "p3": {}},
          {"season": "2026", "round": "1", "raceName": "Bahrain GP",
           "p1": {}, "p2": {}, "p3": {}},
          {"season": "2026", "round": "2", "raceName": "Saudi GP",
           "p1": {}, "p2": {}, "p3": {}},
      ]
      f = tmp_path / "podiums.json"
      f.write_text(json.dumps(podiums))
      monkeypatch.setattr(fcs, "PODIUMS_PATH", f)

      year, rounds = fcs.season_and_rounds(today_year=2026)

      assert year == 2026
      assert rounds == [1, 2]


  def test_season_and_rounds_empty_when_no_current_year_rounds(tmp_path, monkeypatch):
      podiums = [
          {"season": "2025", "round": "22", "raceName": "Abu Dhabi GP",
           "p1": {}, "p2": {}, "p3": {}},
      ]
      f = tmp_path / "podiums.json"
      f.write_text(json.dumps(podiums))
      monkeypatch.setattr(fcs, "PODIUMS_PATH", f)

      year, rounds = fcs.season_and_rounds(today_year=2026)

      assert year == 2026
      assert rounds == []
  ```

- [ ] **Step 2: Run the tests to confirm they fail**

  ```
  pytest tests/test_fetch_season.py::test_season_and_rounds_returns_calendar_year_with_rounds tests/test_fetch_season.py::test_season_and_rounds_empty_when_no_current_year_rounds -v
  ```

  Expected: both `FAILED` — `season_and_rounds` doesn't accept `today_year` yet.

- [ ] **Step 3: Apply the fix to `fetch_constructor_standings.py`**

  Add `import datetime` to the imports block (after `import json`):

  ```python
  # before
  import json
  import sys
  import time
  from pathlib import Path
  ```

  ```python
  # after
  import datetime
  import json
  import sys
  import time
  from pathlib import Path
  ```

  Replace `season_and_rounds()` (lines 59–63):

  ```python
  # before
  def season_and_rounds() -> tuple[int, list[int]]:
      podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
      season = max(int(p["season"]) for p in podiums)
      rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == season})
      return season, rounds
  ```

  ```python
  # after
  def season_and_rounds(today_year: int | None = None) -> tuple[int, list[int]]:
      year = today_year if today_year is not None else datetime.date.today().year
      podiums = json.loads(PODIUMS_PATH.read_text(encoding="utf-8"))
      rounds = sorted({int(p["round"]) for p in podiums if int(p["season"]) == year})
      return year, rounds
  ```

- [ ] **Step 4: Run the tests to confirm they pass**

  ```
  pytest tests/test_fetch_season.py::test_season_and_rounds_returns_calendar_year_with_rounds tests/test_fetch_season.py::test_season_and_rounds_empty_when_no_current_year_rounds -v
  ```

  Expected: both `PASSED`.

- [ ] **Step 5: Commit**

  ```
  git add src/fetch/fetch_constructor_standings.py tests/test_fetch_season.py
  git commit -m "fix: use calendar year in season_and_rounds"
  ```

---

### Task 4: Fix `render_last_race` — fall back to most recent podium on API lag

**Files:**
- Modify: `src/build/build_podigami_html.py:177-183`
- Modify: `tests/test_next_race.py`

- [ ] **Step 1: Write the failing tests**

  Append to `tests/test_next_race.py`:

  ```python


  # --- render_last_race fallback -----------------------------------------------

  _SCHED_LAG = {
      "season": "2026",
      "totalRounds": 2,
      "races": [
          {
              "round": "1",
              "raceName": "Bahrain GP",
              "date": "2026-03-01",
              "country": "Bahrain",
              "circuitName": "Bahrain International Circuit",
              "locality": "Sakhir",
              "url": "",
              "time": "15:00:00Z",
              "trackPath": "",
              "trackViewBox": "0 0 120 72",
              "lengthKm": None,
          },
          {
              "round": "2",
              "raceName": "Saudi GP",
              "date": "2026-12-01",
              "country": "Saudi Arabia",
              "circuitName": "Jeddah Corniche Circuit",
              "locality": "Jeddah",
              "url": "",
              "time": "",
              "trackPath": "",
              "trackViewBox": "0 0 120 72",
              "lengthKm": None,
          },
      ],
  }

  _PODIUMS_LAG = [
      {
          "season": "2025",
          "round": "22",
          "raceName": "Abu Dhabi GP",
          "p1": {"driverId": "norris", "name": "Lando Norris"},
          "p2": {"driverId": "russell", "name": "George Russell"},
          "p3": {"driverId": "antonelli", "name": "Andrea Kimi Antonelli"},
      }
  ]


  def test_render_last_race_falls_back_when_scheduled_round_has_no_podium():
      # Round 1 is in the past (today=2026-04-01) but has no podium yet.
      # Should fall back to the most recent podium in the dataset (2025 R22).
      html = bp.render_last_race(
          _SCHED_LAG, _PODIUMS_LAG, [], {}, [], today="2026-04-01"
      )
      assert html != "", "should render a section, not return empty"
      assert "Abu Dhabi GP" in html
      assert 'class="last-race"' in html


  def test_render_last_race_returns_empty_when_no_podiums_at_all():
      html = bp.render_last_race(
          _SCHED_LAG, [], [], {}, [], today="2026-04-01"
      )
      assert html == ""
  ```

- [ ] **Step 2: Run the tests to confirm they fail**

  ```
  pytest tests/test_next_race.py::test_render_last_race_falls_back_when_scheduled_round_has_no_podium tests/test_next_race.py::test_render_last_race_returns_empty_when_no_podiums_at_all -v
  ```

  Expected: `test_render_last_race_falls_back_when_scheduled_round_has_no_podium` FAILED (returns `""`), `test_render_last_race_returns_empty_when_no_podiums_at_all` PASSED (already works).

- [ ] **Step 3: Apply the fix to `build_podigami_html.py`**

  In `render_last_race`, replace lines 177–183:

  ```python
  # before
      pod = None
      for p in reversed(podiums):
          if p["season"] == season and p["round"] == rnd:
              pod = p
              break
      if not pod:
          return ""
  ```

  ```python
  # after
      pod = None
      for p in reversed(podiums):
          if p["season"] == season and p["round"] == rnd:
              pod = p
              break
      if not pod:
          if not podiums:
              return ""
          pod = max(podiums, key=lambda p: (int(p["season"]), int(p["round"])))
          rnd = pod["round"]
          last = next(
              (r for r in schedule.get("races", []) if r["round"] == rnd),
              {"country": "", "raceName": pod["raceName"], "round": rnd},
          )
  ```

- [ ] **Step 4: Run the tests to confirm they pass**

  ```
  pytest tests/test_next_race.py::test_render_last_race_falls_back_when_scheduled_round_has_no_podium tests/test_next_race.py::test_render_last_race_returns_empty_when_no_podiums_at_all -v
  ```

  Expected: both `PASSED`.

- [ ] **Step 5: Commit**

  ```
  git add src/build/build_podigami_html.py tests/test_next_race.py
  git commit -m "fix: render_last_race falls back to most recent podium on API lag"
  ```

---

### Task 5: Full verification, PR, and merge

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

  ```
  python -m pytest -q
  ```

  Expected: all tests pass, 0 failures.

- [ ] **Step 2: Run lint and format check**

  ```
  python -m ruff check .
  python -m ruff format --check .
  ```

  Expected: no output (clean). If `ruff format --check` reports diffs, run `python -m ruff format .` and commit the result.

- [ ] **Step 3: Push the branch**

  ```
  git push -u origin fix/issue-83-halflife-text
  ```

- [ ] **Step 4: Create the PR**

  ```
  gh pr create \
    --title "fix: use calendar year for season detection, fix render_last_race API lag (#84)" \
    --body "$(cat <<'EOF'
  ## Summary
  Fixes #84 — site showed previous season and \"Season complete\" during the off-season gap.

  ## Changes
  - `fetch_schedule.py`: remove `current_season()` (read from podiums); use `datetime.date.today().year` directly in `main()`
  - `fetch_current_drivers.py`: rewrite `season_and_recent_rounds()` to use calendar year; returns empty rounds list if no races completed yet for the current year
  - `fetch_constructor_standings.py`: same calendar-year fix for `season_and_rounds()`
  - `build_podigami_html.py`: `render_last_race` falls back to the most recent podium in the dataset instead of returning empty when the scheduled last race has no API data yet
  - New test file `tests/test_fetch_season.py` with unit tests for the three updated helpers
  - Extended `tests/test_next_race.py` with two `render_last_race` fallback tests

  ## Testing
  - `pytest -q` — all tests pass
  - `ruff check . && ruff format --check .` — clean

  ## Checklist
  - [x] Lint passes (`ruff check .`)
  - [x] Format passes (`ruff format --check .`)
  - [x] Tests pass (`pytest -q`)
  - [x] No new security issues introduced
  EOF
  )"
  ```

- [ ] **Step 5: Wait for CI to pass, then merge**

  ```
  gh pr checks --watch
  ```

  Once all checks are green:

  ```
  gh pr merge --squash --delete-branch
  ```

- [ ] **Step 6: Delete the local branch**

  ```
  git checkout main
  git pull
  git branch -d fix/issue-83-halflife-text
  ```
