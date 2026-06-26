# Sitemap Content-Based `lastmod` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the build-date `lastmod` in `dist/sitemap.xml` with the date of the most recently completed F1 race, derived from `data/schedule.json`.

**Architecture:** Add a `_last_race_date()` helper to `src/build_site.py` that loads `schedule.json` via `datalib.load_schedule()` and returns `max(r.date for r in races if r.date <= today)`. Wire it into `_write_sitemap_xml()` in place of `datetime.now()`. Add a test asserting the sitemap contains the expected date.

**Tech Stack:** Python 3.11+, Pydantic v2 (`datalib`), pytest, ruff

---

## File Map

| File | Change |
|------|--------|
| `src/build_site.py` | Add `_last_race_date()` helper; update `_write_sitemap_xml()` to call it |
| `tests/test_build_output.py` | Add `test_sitemap_lastmod_is_last_race_date` |

---

### Task 1: Create feature branch and write the failing test

**Files:**
- Modify: `tests/test_build_output.py`

- [ ] **Step 1: Create the feature branch**

```powershell
git checkout -b fix/sitemap-lastmod
```

- [ ] **Step 2: Add the failing test**

Append to the bottom of `tests/test_build_output.py`:

```python
def test_sitemap_lastmod_is_last_race_date(dist, data):
    from datetime import date

    today = date.today().isoformat()
    past_dates = [r["date"] for r in data["schedule"]["races"] if r["date"] <= today]
    expected = max(past_dates)
    sitemap = (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<lastmod>{expected}</lastmod>" in sitemap
```

> `data["schedule"]["races"]` works because conftest's `data` fixture loads every `data/*.json` keyed by stem. Each race dict has a `"date"` key in ISO format (`"2026-03-08"`).

- [ ] **Step 3: Run the new test to confirm it fails**

```powershell
python -m pytest tests/test_build_output.py::test_sitemap_lastmod_is_last_race_date -v
```

Expected: **FAILED** — the sitemap currently contains today's build date, not the last race date.

- [ ] **Step 4: Commit the failing test**

```powershell
git add tests/test_build_output.py
git commit -m "test: add failing test for content-based sitemap lastmod"
```

---

### Task 2: Implement `_last_race_date()` and wire it up

**Files:**
- Modify: `src/build_site.py:43–55`

- [ ] **Step 1: Add the `_last_race_date()` helper**

In `src/build_site.py`, add this function **before** `_write_sitemap_xml()` (i.e. after the `_write_robots_txt` function, around line 41):

```python
def _last_race_date() -> str:
    from datalib import load_schedule

    today = datetime.now(UTC).date().isoformat()
    races = load_schedule().races
    past = [r.date for r in races if r.date <= today]
    return max(past) if past else today
```

> `datetime` and `UTC` are already imported at the top of `build_site.py`. `build_site.py` lives in `src/`, so Python automatically adds `src/` to `sys.path` when the script is run — no extra path manipulation needed. The lazy `import` inside the function keeps `build_site.py`'s module-level imports unchanged.

- [ ] **Step 2: Update `_write_sitemap_xml()` to use the helper**

Replace the existing `_write_sitemap_xml()` function (currently lines 43–55) with:

```python
def _write_sitemap_xml() -> None:
    lastmod = _last_race_date()
    urls = "\n".join(
        f"  <url>\n    <loc>{SITE_URL}/{page}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>"
        for page in PAGES
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )
    (DIST / "sitemap.xml").write_text(content, encoding="utf-8")
```

- [ ] **Step 3: Run the new test to confirm it passes**

```powershell
python -m pytest tests/test_build_output.py::test_sitemap_lastmod_is_last_race_date -v
```

Expected: **PASSED**

- [ ] **Step 4: Run the full test suite**

```powershell
python -m pytest -q
```

Expected: all tests pass, no failures or errors.

- [ ] **Step 5: Lint and format check**

```powershell
python -m ruff check .
python -m ruff format --check .
```

Expected: no output (clean). If `ruff format --check` reports a diff, run `python -m ruff format .` to fix, then re-check.

- [ ] **Step 6: Commit the implementation**

```powershell
git add src/build_site.py
git commit -m "fix: derive sitemap lastmod from last completed race date (closes #85)"
```

---

### Task 3: PR, merge, and close issue

- [ ] **Step 1: Push the branch**

```powershell
git push -u origin fix/sitemap-lastmod
```

- [ ] **Step 2: Create the PR**

```powershell
gh pr create --title "fix: derive sitemap lastmod from last completed race date" --body "$(cat <<'EOF'
## Summary
Fixes #85. `sitemap.xml` was stamping every URL with the build date on every deploy, making `<lastmod>` meaningless to crawlers.

## Changes
- Added `_last_race_date()` to `src/build_site.py`: loads `schedule.json` via `datalib`, returns `max(r.date for r in races if r.date <= today)`, falling back to today if no past races exist.
- `_write_sitemap_xml()` now calls `_last_race_date()` instead of `datetime.now()`.
- Added `test_sitemap_lastmod_is_last_race_date` in `tests/test_build_output.py` to assert the sitemap contains the last completed race date.

## Testing
- `pytest -q` — all tests pass
- `ruff check . && ruff format --check .` — clean
- `python src/build_site.py` + manual inspection of `dist/sitemap.xml` confirms the last race date appears instead of today

## Checklist
- [x] Lint passes (`ruff check .`)
- [x] Format passes (`ruff format --check .`)
- [x] Tests pass (`pytest -q`)
- [x] No security issues introduced
EOF
)"
```

- [ ] **Step 3: Wait for CI to pass, then merge**

```powershell
gh pr checks --watch
gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Clean up local branch and sync**

```powershell
git checkout main
git pull
git branch -d fix/sitemap-lastmod
```

- [ ] **Step 5: Confirm issue #85 is closed**

```powershell
gh issue view 85 --repo NikoKiru/f1podigami
```

Expected: `state: CLOSED`
