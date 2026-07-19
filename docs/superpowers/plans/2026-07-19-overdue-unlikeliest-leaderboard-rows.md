# Overdue & Unlikeliest Leaderboard Rows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De-clutter `overdue.html` and `unlikeliest.html` by keeping only the #1 hero card and rendering every other rank as a compact, expandable leaderboard row.

**Architecture:** Build-stage-only change (no `data/` or `datalib` changes). A new shared renderer `src/build/_rows.py` emits native `<details>`/`<summary>` rows (no JS); both page builders use it for ranks #2+. `assets/overdue.js` and the mobile "Details" toggle machinery are deleted. One shared `.rank-list`/`.rankrow` CSS family replaces the non-hero card grid CSS.

**Tech Stack:** Python 3.11+ string-based HTML generation, pytest, ruff (line-length 100), plain CSS in `assets/podigami.css`, Playwright MCP for visual verification.

**Spec:** `docs/superpowers/specs/2026-07-19-overdue-unlikeliest-declutter-design.md`

**Conventions that apply to every task:** `esc()`/`html.escape()` for interpolated data; no hardcoded absolute paths; run `python -m ruff check .` and `python -m ruff format .` before each commit. The pytest `dist` fixture (in `tests/conftest.py`) builds the site once per session, so HTML-structure tests exercise the real generated output.

---

### Task 0: Branch

- [ ] **Step 0.1:** From a clean `develop`, create the feature branch:

```bash
git checkout develop && git pull && git checkout -b feature/leaderboard-rows
```

---

### Task 1: Shared row renderer `src/build/_rows.py`

**Files:**
- Create: `src/build/_rows.py`
- Create: `tests/test_build_rows.py`

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_build_rows.py`:

```python
"""Unit tests for the shared leaderboard-row renderer."""

from build._rows import render_row


def test_render_row_structure():
    out = render_row(2, "<span>A &middot; B &middot; C</span>", "1 in 440", "<div>stats</div>")
    assert out.startswith('<li class="rankrow">')
    assert out.endswith("</li>")
    assert "<details>" in out
    assert '<summary class="rr-face">' in out
    assert '<span class="rr-rank">2</span>' in out
    assert '<span class="rr-drivers"><span>A &middot; B &middot; C</span></span>' in out
    assert '<span class="rr-num">1 in 440</span>' in out
    assert '<span class="rr-chev" aria-hidden="true">&#9662;</span>' in out
    assert '<div class="rr-stats"><div>stats</div></div>' in out


def test_render_row_race_optional():
    assert 'class="rr-race"' not in render_row(2, "d", "n", "s")
    out = render_row(3, "d", "n", "s", race_html='<a href="x">1990 Japanese GP</a>')
    assert '<span class="rr-race"><a href="x">1990 Japanese GP</a></span>' in out
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_rows.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build._rows'`

- [ ] **Step 1.3: Write the implementation**

Create `src/build/_rows.py`:

```python
"""Shared leaderboard-row renderer for the Overdue and Unlikeliest pages.

Every rank below the #1 hero card is one compact native <details> row: the
<summary> is the always-visible row face (rank, drivers, headline number,
optional race link) and the body holds the stat cells the old cards showed on
their face. Native disclosure means no JavaScript and free keyboard support.

Callers pass pre-escaped HTML fragments (driver spans, stat cells, race link);
this module only assembles structure.
"""

from __future__ import annotations


def render_row(
    rank: int, drivers_html: str, num: str, stats_html: str, race_html: str = ""
) -> str:
    """One expandable row. ``race_html`` (Unlikeliest only) sits on the row face
    on desktop; CSS moves it into the stats panel on phones."""
    race = f'<span class="rr-race">{race_html}</span>' if race_html else ""
    return (
        '<li class="rankrow">'
        "<details>"
        '<summary class="rr-face">'
        f'<span class="rr-rank">{rank}</span>'
        f'<span class="rr-drivers">{drivers_html}</span>'
        f"{race}"
        f'<span class="rr-num">{num}</span>'
        '<span class="rr-chev" aria-hidden="true">&#9662;</span>'
        "</summary>"
        f'<div class="rr-stats">{stats_html}</div>'
        "</details>"
        "</li>"
    )
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_rows.py -v`
Expected: 2 PASS

- [ ] **Step 1.5: Lint, format, commit**

```bash
python -m ruff check . && python -m ruff format .
git add src/build/_rows.py tests/test_build_rows.py
git commit -m "feat: shared leaderboard-row renderer for ranked pages"
```

---

### Task 2: Overdue page — hero + rows, delete `overdue.js`

**Files:**
- Modify: `src/build/build_overdue_html.py`
- Delete: `assets/overdue.js`
- Test: `tests/test_build_overdue.py`, `tests/test_build_output.py`

- [ ] **Step 2.1: Update the unit tests first**

In `tests/test_build_overdue.py`:

**Delete** these two tests (the mobile toggle and its per-section ids are going away): `test_render_card_has_mobile_stats_toggle`, `test_render_cards_stats_ids_unique_per_section`. Also delete the `# ── mobile stats toggle ──…` section comment above them.

**Replace** `test_render_cards_structure` with:

```python
def test_render_cards_hero_then_rows():
    entries = [
        entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 50, 8.0, [0.5, 0.4, 0.3]),
        entry(["A Driver", "B Driver", "D Driver"], ["a", "b", "d"], 30, 4.0, [0.5, 0.4, 0.2]),
        entry(["A Driver", "C Driver", "D Driver"], ["a", "c", "d"], 20, 3.0, [0.5, 0.3, 0.2]),
    ]
    html = bo.render_cards(entries)
    assert 'class="rank-list"' in html
    assert html.count("odcard-hero") == 1  # only the first entry is a card
    assert html.count('class="rankrow"') == 2  # the rest are rows
    assert '<span class="rr-rank">2</span>' in html
    assert '<span class="rr-rank">3</span>' in html
```

**Add** after `test_render_card_probability_stat_present`:

```python
# ── render_row_entry ─────────────────────────────────────────────────────────


def test_render_row_entry_carries_score_and_stats():
    e = entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 10, 2.0, [0.3, 0.2, 0.1])
    html = bo.render_row_entry(2, e)
    assert 'class="rankrow"' in html
    assert "2.0×" in html  # headline number on the row face
    assert "Chance by now" in html and "86%" in html  # stats in the details body
    assert "10&times;" in html  # raced together
    assert 'class="dn-abbr"' in html  # responsive names still emitted
```

- [ ] **Step 2.2: Update the built-output tests**

In `tests/test_build_output.py`:

Line 14 — overdue no longer ships page JS:

```python
    "overdue.html": ["podigami.css", "theme.js"],
```

Lines 18–28 — remove the `"overdue.js",` entry from `ALL_ASSETS`.

In `test_overdue_has_two_ranked_lists` (line ~261):

```python
    assert html.count('class="rank-list"') == 2  # all-time + current grid
```

- [ ] **Step 2.3: Run tests to verify the new ones fail**

Run: `python -m pytest tests/test_build_overdue.py tests/test_build_output.py -v`
Expected: FAIL — `render_row_entry` doesn't exist; built page still references `overdue.js` and `odcard-list`.

- [ ] **Step 2.4: Rewrite the builder**

In `src/build/build_overdue_html.py`:

**Module docstring** (lines 1–10) — replace with:

```python
"""Render data/overdue.json into dist/overdue.html.

Two ranked sections — all-time near-misses and current-grid candidates. In
each, the #1 trio is a full hero card and every other rank is a compact
leaderboard row (shared ``_rows.render_row``) that expands to show its stats.
Every entry leads with the expected number of shared podiums (racesTogether ×
rates) shown as "X.Y×", which makes the overdue-ness concrete: a score of 8
means statistics expected this to happen roughly eight times already. A
"chance by now" stat converts the same number to a probability (Poisson tail:
1 − e^−score) so readers can see just how likely it should have been.
"""
```

**Import** — after the `from _layout import ...` line add:

```python
from _rows import render_row  # noqa: E402
```

**Replace `render_card`** (drop `uid`, drop the toggle button, stats always visible):

```python
def render_card(rank: int, e: OverdueTrio, hero: bool = False) -> str:
    """One full card. ``hero`` makes it the larger, accented #1 variant."""
    cls = "odcard odcard-hero" if hero else "odcard"
    drivers = f'<div class="od-drivers">{render_trio(e.names)}</div>'
    stats = (
        _stat("Podium rates", _rates_cells(e))
        + _stat("Raced together", f"{e.racesTogether}&times;")
        + _stat("Chance by now", format_probability(e.score))
    )
    return (
        f'<li class="{cls}">'
        f'<div class="od-top">'
        f'<span class="od-rank">{rank}</span>'
        f"</div>"
        f"{drivers}"
        f'<div class="od-score">'
        f'<span class="od-score-num">{format_score(e.score)}</span>'
        f'<span class="od-score-label">expected co-podiums</span>'
        f"</div>"
        f'<div class="od-stats">{stats}</div>'
        f"</li>"
    )
```

**Add `render_row_entry`** after `render_card`:

```python
def render_row_entry(rank: int, e: OverdueTrio) -> str:
    """One compact leaderboard row for ranks below the hero."""
    stats = (
        _stat("Podium rates", _rates_cells(e))
        + _stat("Raced together", f"{e.racesTogether}&times;")
        + _stat("Chance by now", format_probability(e.score))
    )
    return render_row(rank, render_trio(e.names), format_score(e.score), stats)
```

**Replace `render_cards`** (drop `uid`):

```python
def render_cards(entries: list[OverdueTrio]) -> str:
    if not entries:
        return '<p class="panel-sub">No candidates.</p>'
    hero = render_card(1, entries[0], hero=True)
    rows = "".join(render_row_entry(i, e) for i, e in enumerate(entries[1:], 2))
    return f'<ol class="rank-list">{hero}{rows}</ol>'
```

**Update `panel`** — remove the `uid` parameter and the `uid=uid` pass-through (docstring: drop the id-disambiguation sentence), calling `render_cards(entries)`.

**Update `main`** — remove `uid="at"` / `uid="cg"` arguments, and delete the line:

```python
<script src="{asset("overdue.js")}"></script>
```

(the `asset` import stays — `theme.js` still uses it).

- [ ] **Step 2.5: Delete the JS asset**

```bash
git rm assets/overdue.js
```

- [ ] **Step 2.6: Run the affected tests**

Run: `python -m pytest tests/test_build_overdue.py tests/test_build_output.py tests/test_build_rows.py -v`
Expected: all PASS (the session-scoped `dist` fixture rebuilds with the new markup).

- [ ] **Step 2.7: Lint, format, commit**

```bash
python -m ruff check . && python -m ruff format .
git add -A
git commit -m "feat: overdue page renders hero + expandable leaderboard rows"
```

---

### Task 3: Unlikeliest page — hero + rows with race-link swap

**Files:**
- Modify: `src/build/build_unlikeliest.py`
- Test: `tests/test_build_unlikeliest.py`

- [ ] **Step 3.1: Update the unit tests first**

In `tests/test_build_unlikeliest.py`:

**Replace** `test_render_cards_lists_all_with_hero_first` with:

```python
def test_render_cards_hero_then_rows():
    entries = [
        trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1]),
        trio(["G H", "I J", "K L"], ["g", "h", "i"], 20, 0.05, 1, [0.2, 0.2, 0.2]),
        trio(["M N", "O P", "Q R"], ["m", "n", "o"], 30, 0.08, 1, [0.2, 0.2, 0.2]),
    ]
    html = bu.render_cards(entries)
    assert html.count("uncard-hero") == 1  # only the first entry is a card
    assert html.count('class="rankrow"') == 2  # the rest are rows
    assert 'class="rank-list"' in html
    assert '<span class="rr-rank">2</span>' in html
    assert '<span class="rr-rank">3</span>' in html
```

**Replace** `test_render_card_shows_repeat_count_when_more_than_one` with (the count now surfaces in the row's details body):

```python
def test_render_row_entry_shows_repeat_count():
    once = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 1, [0.1, 0.1, 0.1])
    twice = trio(["A B", "C D", "E F"], ["a", "b", "c"], 10, 0.01, 2, [0.1, 0.1, 0.1])
    assert ">2<" in bu.render_row_entry(3, twice)  # count cell shows 2
    assert "Times it happened" in bu.render_row_entry(3, once)
```

**Add** after it:

```python
def test_render_row_entry_race_on_face_and_in_stats():
    e = trio(["A B", "C D", "E F"], ["a", "b", "c"], 152, 0.0065, 1, [0.02, 0.13, 0.02])
    html = bu.render_row_entry(2, e)
    assert 'class="rankrow"' in html
    assert "1 in 150" in html  # headline odds on the row face
    # race link appears twice: on the desktop row face and in the stats panel
    assert html.count("https://en.wikipedia.org/wiki/2020_Sakhir_Grand_Prix") == 2
    assert 'class="rr-race"' in html
    assert 'class="un-stat rr-stat-race"' in html
    assert "152&times;" in html  # raced together stat
```

- [ ] **Step 3.2: Run tests to verify the new ones fail**

Run: `python -m pytest tests/test_build_unlikeliest.py -v`
Expected: FAIL — `render_row_entry` doesn't exist.

- [ ] **Step 3.3: Rewrite the builder**

In `src/build/build_unlikeliest.py`:

**Module docstring** — replace the second paragraph's first two sentences (lines 3–8) so the block reads:

```python
"""Render data/unlikeliest.json into dist/unlikeliest.html.

The mirror of the Overdue page: podium trios that *did* happen, ranked by how
statistically unlikely they were. The #1 trio (the single most improbable
podium in F1 history) is a full hero card; every other rank is a compact
leaderboard row (shared ``_rows.render_row``) that expands to show each
driver's career podium rate, how often they raced together, and how many
times it hit.

The headline "1 in N" is the odds the trio would *ever* share a podium, derived
from the expected co-podium count s = racesTogether x rates via the Poisson
tail P(at least once) = 1 - e^-s. More shared races push the odds up (more
chances), so a trio that did it in few shared races is the bigger fluke.
"""
```

**Import** — after the `from _layout import ...` line add:

```python
from _rows import render_row  # noqa: E402
```

**Add `render_row_entry`** after `render_card` (which is unchanged — it still renders the hero):

```python
def render_row_entry(rank: int, e: UnlikeliestTrio, links: dict | None = None) -> str:
    """One compact leaderboard row for ranks below the hero. The race link sits
    on the row face on desktop and repeats in the stats panel, where CSS shows
    it on phones instead."""
    race = _race_link(e, links)
    stats = (
        _stat("Podium rates", _rates_cells(e))
        + _stat("Raced together", f"{e.racesTogether}&times;")
        + _stat("Times it happened", str(e.count))
        + f'<div class="un-stat rr-stat-race">'
        f'<span class="un-stat-label">Race</span>'
        f'<span class="un-stat-val">{race}</span>'
        f"</div>"
    )
    return render_row(rank, render_trio(e.names), format_odds(e.score), stats, race_html=race)
```

**Replace `render_cards`:**

```python
def render_cards(entries: list[UnlikeliestTrio], links: dict | None = None) -> str:
    if not entries:
        return '<p class="panel-sub">No trios.</p>'
    hero = render_card(1, entries[0], hero=True, links=links)
    rows = "".join(render_row_entry(i, e, links) for i, e in enumerate(entries[1:], 2))
    return f'<ol class="rank-list">{hero}{rows}</ol>'
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_unlikeliest.py tests/test_build_output.py -v`
Expected: all PASS

- [ ] **Step 3.5: Lint, format, commit**

```bash
python -m ruff check . && python -m ruff format .
git add src/build/build_unlikeliest.py tests/test_build_unlikeliest.py
git commit -m "feat: unlikeliest page renders hero + expandable leaderboard rows"
```

---

### Task 4: CSS — shared row styles, remove card-grid + toggle machinery

**Files:**
- Modify: `assets/podigami.css`
- Test: `tests/test_mobile_css.py`

Line numbers below refer to `assets/podigami.css` before any edits; apply the edits top-to-bottom and they stay valid (later edits are lower in the file).

- [ ] **Step 4.1: Update the mobile CSS test first**

In `tests/test_mobile_css.py`, **replace** `test_overdue_cards_collapse_stats_on_mobile` with:

```python
def test_rank_rows_swap_race_into_panel_on_mobile():
    """Leaderboard rows: on phones the race name leaves the row face and shows
    as a stat cell inside the expanded panel instead; driver names abbreviate."""
    import re

    s = css("podigami.css")
    assert "od-toggle" not in s, "the old JS Details-toggle CSS must be gone"
    block = re.search(r"@media \(max-width: 600px\)[\s\S]*", s).group(0)
    assert re.search(r"\.rr-race\s*\{[^}]*display:\s*none", block), (
        "mobile must hide the race name on the row face"
    )
    assert re.search(r"\.rr-stat-race\s*\{[^}]*display:\s*flex", block), (
        "mobile must show the race stat cell in the expanded panel"
    )
    assert ".rr-drivers .dn-full" in block and ".rr-drivers .dn-abbr" in block, (
        "row driver names must swap to abbreviated form on mobile"
    )
```

Run: `python -m pytest tests/test_mobile_css.py -v` — expected: the new test FAILS (CSS not written yet), the rest PASS.

- [ ] **Step 4.2: Replace the `.uncard-list` grid with the shared rank-list + row styles**

Replace the block at lines 347–354 (`.uncard-list { ... }`) with:

```css
/* ── Shared ranked list (Overdue + Unlikeliest): hero card + leaderboard rows ─
   The #1 hero keeps its card treatment; every other rank is a compact native
   <details> row — the <summary> is the row face, the body holds the stat
   cells. No JS: native disclosure, free keyboard support. */
.rank-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.rankrow > details {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
}

.rankrow > details[open] {
    border-color: var(--border-strong);
}

.rr-face {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    cursor: pointer;
    list-style: none;
}

.rr-face::-webkit-details-marker {
    display: none;
}

.rr-rank {
    flex: 0 0 auto;
    min-width: 30px;
    font-size: 13px;
    font-weight: 800;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
}

.rr-rank::before {
    content: "#";
    color: var(--accent);
}

.rr-drivers {
    flex: 1;
    min-width: 0;
    font-size: 15px;
    font-weight: 700;
    color: var(--text);
    line-height: 1.35;
}

.rr-drivers .sep {
    color: var(--muted-dim);
    margin: 0 6px;
    font-weight: 400;
}

.rr-drivers .dn-abbr {
    display: none;
}

.rr-race {
    flex: 0 1 auto;
    font-size: 12px;
    text-align: right;
}

.rr-num {
    flex: 0 0 auto;
    font-size: 15px;
    font-weight: 800;
    color: var(--accent-bright);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.rr-chev {
    flex: 0 0 auto;
    color: var(--muted);
    font-size: 11px;
    transition: transform 0.18s ease;
}

.rankrow > details[open] .rr-chev {
    transform: rotate(180deg);
    color: var(--accent-bright);
}

.rr-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 28px;
    margin: 0 14px;
    padding: 10px 0 12px;
    border-top: 1px solid var(--border);
}

/* The race stat cell serves phones only; desktop shows the race on the row
   face. Two-class selector so it beats the later same-specificity
   .un-stat { display: flex } regardless of source order. */
.rr-stats .rr-stat-race {
    display: none;
}
```

- [ ] **Step 4.3: Hero cards no longer live in a grid**

In `.uncard-hero` (was lines 367–373): delete the `grid-column: 1 / -1;` line and the `/* The #1 card spans the full width ... */` comment above the block (the hero is simply the first flex child now).

Same in `.odcard-hero` (was lines 722–728): delete its `grid-column: 1 / -1;` line.

- [ ] **Step 4.4: Drop the stat-label alignment hack (both pages)**

The `min-height: 2.4em` reserved label space so stat values lined up across side-by-side grid cards; with no card grid it only adds dead space.

In `.un-stat-label` (was lines 469–478): delete the `min-height: 2.4em;` line and the two comment lines above it (`/* reserve two lines ... */`). Delete the whole `.uncard-hero .un-stat-label { min-height: 0; }` rule (was lines 480–482).

In `.od-stat-label` (was lines 817–824): delete its `min-height: 2.4em;` line. Delete the whole `.odcard-hero .od-stat-label { min-height: 0; }` rule (was lines 826–828).

- [ ] **Step 4.5: Delete the `.odcard-list` grid block**

Delete the block at (originally) lines 703–710 (`.odcard-list { ... }`) — both pages now share `.rank-list`. Update the section comment above it (lines 699–702) to:

```css
/* ── Overdue page: hero card ─────────────────────────────────────────────────
   Mirrors the Unlikeliest hero. Ranks below it use the shared .rankrow styles. */
```

- [ ] **Step 4.6: Delete the JS toggle machinery**

Delete the whole `/* ── Overdue: per-card stats toggle (mobile only; hidden on desktop) ───────── */` section — the `.od-toggle`, `.od-toggle:hover`, and `.od-toggle .chev` rules (originally lines 876–903).

- [ ] **Step 4.7: Rework the 600px mobile block**

In the `@media (max-width: 600px)` block:

Extend the name-swap selectors (originally lines 1392–1400) to cover rows:

```css
    .un-drivers .dn-full,
    .od-drivers .dn-full,
    .rr-drivers .dn-full {
        display: none;
    }

    .un-drivers .dn-abbr,
    .od-drivers .dn-abbr,
    .rr-drivers .dn-abbr {
        display: inline;
    }
```

Replace the overdue collapse rules (originally lines 1426–1441: `.odcard .od-stats`, `.odcard.od-open .od-stats`, `.od-toggle`, `.odcard.od-open .od-toggle .chev` and the comment above them) with:

```css
    /* Leaderboard rows: tighter type; the race name leaves the row face and
       shows as a stat cell inside the expanded panel instead. */
    .rr-drivers {
        font-size: 13px;
    }

    .rr-num {
        font-size: 14px;
    }

    .rr-race {
        display: none;
    }

    .rr-stats .rr-stat-race {
        display: flex;
    }
```

- [ ] **Step 4.8: Run the full test suite**

Run: `python -m pytest -q`
Expected: all PASS

- [ ] **Step 4.9: Lint, format, commit**

```bash
python -m ruff check . && python -m ruff format .
git add assets/podigami.css tests/test_mobile_css.py
git commit -m "feat: shared leaderboard-row CSS; drop card grid + mobile toggle"
```

---

### Task 5: Full verification (suite + rendered pages)

- [ ] **Step 5.1: Full gates**

```bash
python -m ruff check . && python -m ruff format --check . && python -m pytest -q
```

Expected: 0 lint errors, format clean, all tests pass. Note the final test count for Task 6.

- [ ] **Step 5.2: Build and serve**

```bash
python src/build_site.py
python -m http.server 8123 -d dist   # run in background
```

- [ ] **Step 5.3: Playwright visual verification** (MCP `playwright` tools)

1. Navigate to `http://localhost:8123/overdue.html` at 1280×900. Verify: two sections, each with one hero card followed by 14 compact rows; row face shows `#N`, drivers, `X.Y×`, chevron; no "Details" button anywhere.
2. Click a row → stats panel opens (Podium rates / Raced together / Chance by now); chevron rotates. Click again → closes.
3. Navigate to `http://localhost:8123/unlikeliest.html`. Verify hero + 29 rows; desktop row face shows the race name; clicking the race link opens the race report (href present, `target="_blank"`).
4. Resize to 390×844, reload both pages. Verify: driver names abbreviate (`E. Ocon`), race name gone from row faces, expanding an Unlikeliest row shows the race inside the panel, nothing overflows horizontally.
5. Take screenshots of both pages at both widths for the PR.
6. Stop the server.

- [ ] **Step 5.4: Fix anything found, re-run Step 5.1, commit fixes**

```bash
git add -A && git commit -m "fix: visual polish from rendered-page verification"
```

(Skip the commit if nothing needed fixing.)

---

### Task 6: Docs, PR, merge

**Files:**
- Modify: `RELEASE_NOTES.md`, `README.md`

- [ ] **Step 6.1: RELEASE_NOTES.md** — add under a `## 2026-07-19` heading (create if missing, keep newest-first):

```markdown
### Improvements
- De-cluttered the Overdue and Unlikeliest pages: only the #1 trio keeps its full card; every other rank is a compact leaderboard row that expands to show its stats (no-JS native disclosure) (#PR).
```

(Replace `#PR` with the real PR number after `gh pr create`.)

- [ ] **Step 6.2: README.md** — update the test-count badge (line 19, `tests-NNN%20passing`) and the `tests/` line in the repo map (line ~158, "NNN tests") to the count observed in Step 5.1. The Overdue/Unlikeliest feature descriptions don't mention cards, so no other edits.

- [ ] **Step 6.3: Commit docs**

```bash
git add RELEASE_NOTES.md README.md
git commit -m "docs: release notes + README test count for leaderboard rows"
```

- [ ] **Step 6.4: Push and open the PR into `develop`** (repo default), following `.github/pull_request_template.md`: Summary (de-clutter via hero + leaderboard rows, spec link), Changes (bullet the new `_rows.py`, both builders, CSS rework, `overdue.js` deletion, test updates), Testing (`pytest -q`, `ruff`, Playwright desktop+mobile screenshots), Checklist. Attach the Step 5.3 screenshots.

```bash
git push -u origin feature/leaderboard-rows
gh pr create --fill-first   # then edit body to the template
```

Then update the RELEASE_NOTES entry with the real PR number (amend or follow-up commit) and push.

- [ ] **Step 6.5: Merge once the 7 required checks pass, delete the branch**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout develop && git pull
```

- [ ] **Step 6.6:** Ask the user whether to promote `develop → main` now (deploys to Pages) or batch with other work.
