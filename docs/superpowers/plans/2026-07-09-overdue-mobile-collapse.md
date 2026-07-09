# Overdue Mobile Collapse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `overdue.html` less cluttered on phones (each trio card's three stats collapse behind a per-card "Details" toggle, mobile only) and let either grid section collapse (native `<details>`, both open by default).

**Architecture:** Two independent collapse layers. Section-level uses a native `<details class="panel od-panel" open>` per grid — no JS, keyboard/AT-friendly, open by default. Card-level uses a `<button class="od-toggle">` that a tiny new `assets/overdue.js` toggles (adds `.od-open`), with CSS hiding `.od-stats` only inside the `max-width:600px` breakpoint so desktop is untouched. Mirrors the combinations page's expand pattern (`index.js` + `.detail`).

**Tech Stack:** Python string-templated HTML (`src/build/build_overdue_html.py`), CSS (`assets/podigami.css`), vanilla JS (`assets/overdue.js`), pytest.

---

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `src/build/build_overdue_html.py` | Renders overdue.html | `panel()` → `<details>`; `render_card()`/`render_cards()`/`panel()` thread a section `uid` + emit the toggle; `main()` passes uids and loads `overdue.js` |
| `assets/podigami.css` | Overdue styles | Section summary/chevron chrome (`.od-panel`), `.od-toggle` base (hidden on desktop), mobile card-collapse rules |
| `assets/overdue.js` | **New.** Per-card Details toggle | Toggles `.od-open` + `aria-expanded` on click |
| `tests/test_build_overdue.py` | Render-helper unit tests | Update `panel` test; add toggle/uid tests |
| `tests/test_build_output.py` | Built-site assertions | Add `overdue.js` to `PAGES["overdue.html"]` and `ALL_ASSETS` |
| `tests/test_mobile_css.py` | Mobile-CSS regression | Add overdue card-collapse guard |
| `RELEASE_NOTES.md` | Changelog | One entry under today's date |

**Conventions to follow:** HTML is string-built — escape interpolated data with the existing `esc()` helper (the fixed markup here needs none). Path resolution via `Path(__file__).resolve().parents[N]`. Run `ruff check` + `ruff format --check` before committing. The `dist` pytest fixture builds `dist/` once per session, so a RED asset test must be run in its own `pytest` invocation before implementing, then GREEN in a fresh invocation after.

---

## Task 1: Collapsible section headers (native `<details>`)

Turn each grid's `<section class="panel">` into a `<details class="panel od-panel" open>` whose `<summary>` holds the `<h2>` and a rotating chevron. All screens; open by default.

**Files:**
- Modify: `src/build/build_overdue_html.py` (`panel()`, around lines 103-110)
- Modify: `assets/podigami.css` (add a block after the `.od-stat-val` rule, ~line 836)
- Test: `tests/test_build_overdue.py` (`test_panel_wraps_title_and_sub`, lines 120-124)

- [ ] **Step 1: Update the failing panel test**

Replace `test_panel_wraps_title_and_sub` (currently lines 120-124) in `tests/test_build_overdue.py` with:

```python
def test_panel_wraps_title_and_sub():
    out = bo.panel("My Title", "the subtitle", [])
    assert "<h2>My Title</h2>" in out
    assert "the subtitle" in out
    # section is now a collapsible <details>, open by default
    assert '<details class="panel od-panel" open>' in out
    assert '<summary class="panel-head">' in out
    assert 'class="panel-chev"' in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_build_overdue.py::test_panel_wraps_title_and_sub -v`
Expected: FAIL — output still contains `<section class="panel">`, so the `<details ...>` assertion fails.

- [ ] **Step 3: Rewrite `panel()` to emit `<details>`**

In `src/build/build_overdue_html.py`, replace the whole `panel()` function (lines 103-110):

```python
def panel(title: str, sub: str, entries: list[OverdueTrio], uid: str = "") -> str:
    """One collapsible grid section.

    A native ``<details open>`` so the header toggles the whole section with no
    JS; ``uid`` disambiguates each card's stats id across the two sections.
    """
    return (
        f'<details class="panel od-panel" open>'
        f'<summary class="panel-head">'
        f"<h2>{title}</h2>"
        f'<span class="panel-chev" aria-hidden="true">&#9662;</span>'
        f"</summary>"
        f'<p class="panel-sub">{sub}</p>'
        f"{render_cards(entries, uid=uid)}"
        f"</details>"
    )
```

Note: this adds the `uid` parameter now and forwards it to `render_cards(entries, uid=uid)`. `render_cards` still has to accept `uid` — that lands in Task 2. To keep Task 1 self-contained and green, **also** apply the one-line signature default in Step 3b before running tests.

- [ ] **Step 3b: Let `render_cards`/`render_card` accept `uid` (no behaviour change yet)**

In `src/build/build_overdue_html.py`, change the `render_cards` signature (line 96) and its call (line 99):

```python
def render_cards(entries: list[OverdueTrio], uid: str = "") -> str:
    if not entries:
        return '<p class="panel-sub">No candidates.</p>'
    cards = [render_card(i, e, hero=(i == 1), uid=uid) for i, e in enumerate(entries, 1)]
    return f'<ol class="odcard-list">{"".join(cards)}</ol>'
```

And change the `render_card` signature (line 72) to accept the same default (body unchanged for now):

```python
def render_card(rank: int, e: OverdueTrio, hero: bool = False, uid: str = "") -> str:
```

- [ ] **Step 4: Run the panel test to verify it passes**

Run: `python -m pytest tests/test_build_overdue.py::test_panel_wraps_title_and_sub -v`
Expected: PASS.

- [ ] **Step 5: Add the section-collapse CSS**

In `assets/podigami.css`, immediately after the `.od-stat-val { … }` rule (ends ~line 836, just before the `/* current form — broadcast timing tower */` comment), insert:

```css
/* ── Overdue: collapsible section headers (native <details>) ──────────────── */
.od-panel > summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    cursor: pointer;
    list-style: none;
}

.od-panel > summary::-webkit-details-marker {
    display: none;
}

.od-panel > summary h2 {
    margin: 0;
}

.od-panel > summary:hover h2 {
    color: var(--text);
}

.od-panel > .panel-sub {
    margin-top: 6px;
}

.panel-chev {
    flex: 0 0 auto;
    color: var(--muted);
    font-size: 12px;
    transition: transform 0.18s ease, color 0.15s;
}

.od-panel[open] > summary .panel-chev {
    transform: rotate(180deg);
    color: var(--accent-bright);
}
```

- [ ] **Step 6: Build and eyeball the output**

Run: `python src/build_site.py`
Then confirm the two sections are collapsible details:

Run: `python -c "import pathlib; h=pathlib.Path('dist/overdue.html').read_text(encoding='utf-8'); print(h.count('<details class=\"panel od-panel\" open>'))"`
Expected: `2`

- [ ] **Step 7: Run the full overdue + output suites**

Run: `python -m pytest tests/test_build_overdue.py tests/test_build_output.py -q`
Expected: PASS (no asset changes yet; `test_overdue_has_two_ranked_lists` still sees two `odcard-list`s).

- [ ] **Step 8: Commit**

```bash
git add src/build/build_overdue_html.py assets/podigami.css tests/test_build_overdue.py
git commit -m "feat: collapsible sections on the overdue page (native <details>)"
```

---

## Task 2: Per-card "Details" toggle markup

Give each card the toggle button + a unique stats `id`, and pass section uids from `main()`. The button does nothing yet (no JS/CSS) — that's Task 3 — but the markup is testable now.

**Files:**
- Modify: `src/build/build_overdue_html.py` (`render_card()` body ~lines 72-93; `main()` panel calls ~lines 117-128)
- Test: `tests/test_build_overdue.py` (add two tests)

- [ ] **Step 1: Write the failing markup tests**

Append to `tests/test_build_overdue.py`:

```python
def test_render_card_has_mobile_stats_toggle():
    e = entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 10, 2.0, [0.3, 0.2, 0.1])
    html = bo.render_card(2, e, uid="at")
    assert 'class="od-toggle"' in html
    assert 'aria-expanded="false"' in html
    assert 'id="odstats-at2"' in html
    assert 'aria-controls="odstats-at2"' in html


def test_render_cards_stats_ids_unique_per_section():
    entries = [entry(["A Driver", "B Driver", "C Driver"], ["a", "b", "c"], 10, 2.0, [0.3, 0.2, 0.1])]
    assert 'id="odstats-at1"' in bo.render_cards(entries, uid="at")
    assert 'id="odstats-cg1"' in bo.render_cards(entries, uid="cg")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_build_overdue.py::test_render_card_has_mobile_stats_toggle tests/test_build_overdue.py::test_render_cards_stats_ids_unique_per_section -v`
Expected: FAIL — no `od-toggle` / `odstats-…` in the current card markup.

- [ ] **Step 3: Add the toggle + stats id to `render_card()`**

In `src/build/build_overdue_html.py`, replace the `render_card` body (lines 72-93) with (signature already took `uid` in Task 1):

```python
def render_card(rank: int, e: OverdueTrio, hero: bool = False, uid: str = "") -> str:
    """One uniform card. ``hero`` makes it the larger, accented #1 variant.

    On mobile the three stat cells collapse behind a per-card "Details" toggle
    (see assets/overdue.js); ``uid`` keeps each card's stats id unique across the
    two sections.
    """
    cls = "odcard odcard-hero" if hero else "odcard"
    drivers = f'<div class="od-drivers">{render_trio(e.names)}</div>'
    stats = (
        _stat("Podium rates", _rates_cells(e))
        + _stat("Raced together", f"{e.racesTogether}&times;")
        + _stat("Chance by now", format_probability(e.score))
    )
    stats_id = f"odstats-{uid}{rank}"
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
        f'<button type="button" class="od-toggle" aria-expanded="false" aria-controls="{stats_id}">'
        f'<span class="od-toggle-label">Details</span>'
        f'<span class="chev" aria-hidden="true">&#9662;</span>'
        f"</button>"
        f'<div class="od-stats" id="{stats_id}">{stats}</div>'
        f"</li>"
    )
```

- [ ] **Step 4: Pass section uids from `main()`**

In `src/build/build_overdue_html.py`, add `uid="at"` / `uid="cg"` to the two `panel(...)` calls (lines 117-128):

```python
    all_time = panel(
        "All-time near-misses",
        "Trios from across F1 history that raced together often and each podiumed often "
        "&mdash; yet never all three on the same podium. Expected co-podiums = races together "
        "&times; each driver&rsquo;s career podium rate.",
        data.allTime,
        uid="at",
    )
    grid = panel(
        "Current grid &mdash; still possible",
        "The most overdue trios among this season&rsquo;s drivers. These could still happen.",
        data.currentGrid,
        uid="cg",
    )
```

- [ ] **Step 5: Run the overdue suite to verify green**

Run: `python -m pytest tests/test_build_overdue.py -q`
Expected: PASS — new toggle/uid tests pass; existing `test_render_card_fields_present`, `test_render_card_hero_variant`, `test_render_card_probability_stat_present`, `test_render_cards_structure` still pass (defaults `uid=""` → ids like `odstats-1`).

- [ ] **Step 6: Commit**

```bash
git add src/build/build_overdue_html.py tests/test_build_overdue.py
git commit -m "feat: add per-card Details toggle markup to overdue cards"
```

---

## Task 3: Wire the toggle — `overdue.js` + CSS

Add the script that makes the button work, the CSS that hides stats only on mobile, and the asset/mobile-CSS test updates.

**Files:**
- Create: `assets/overdue.js`
- Modify: `src/build/build_overdue_html.py` (script tags in the page template, ~lines 155-157)
- Modify: `assets/podigami.css` (`.od-toggle` base after the Task 1 block; mobile rules inside the `@media (max-width: 600px)` block)
- Test: `tests/test_build_output.py` (`PAGES`, `ALL_ASSETS`), `tests/test_mobile_css.py` (new test)

- [ ] **Step 1: Update the asset-list tests (RED)**

In `tests/test_build_output.py`, change the overdue entry (line 14) and `ALL_ASSETS` (lines 18-27):

```python
    "overdue.html": ["podigami.css", "overdue.js", "theme.js"],
```

```python
ALL_ASSETS = [
    "style.css",
    "index.css",
    "soulmates.css",
    "podigami.css",
    "index.js",
    "podigami.js",
    "overdue.js",
    "theme.js",
    "favicon.svg",
]
```

- [ ] **Step 2: Add the mobile-CSS regression test (RED)**

Append to `tests/test_mobile_css.py`:

```python
def test_overdue_cards_collapse_stats_on_mobile():
    """On phones the three stat cells hide behind a per-card Details toggle."""
    import re

    s = css("podigami.css")
    block = re.search(r"@media \(max-width: 600px\)[\s\S]*", s).group(0)
    assert re.search(r"\.odcard\s+\.od-stats\s*\{[^}]*display:\s*none", block), (
        "mobile must hide the overdue stat block by default"
    )
    assert re.search(r"\.od-toggle\s*\{[^}]*display:\s*flex", block), (
        "the Details toggle must appear on mobile"
    )
```

- [ ] **Step 3: Run both to verify they fail**

Run: `python -m pytest tests/test_build_output.py::test_page_assets_referenced_and_copied tests/test_build_output.py::test_all_assets_copied tests/test_mobile_css.py::test_overdue_cards_collapse_stats_on_mobile -q`
Expected: FAIL — `overdue.js` is neither referenced nor copied, and the mobile CSS rules don't exist yet.

- [ ] **Step 4: Create `assets/overdue.js`**

```js
// Overdue page: reveal a card's stat cells on mobile via the "Details" toggle.
// Desktop keeps the stats visible (CSS hides the button), so this is a no-op there.
document.querySelectorAll('.od-toggle').forEach(btn => {
    const card = btn.closest('.odcard');
    if (!card) return;
    btn.addEventListener('click', () => {
        const open = card.classList.toggle('od-open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
});
```

- [ ] **Step 5: Load the script on the overdue page**

In `src/build/build_overdue_html.py`, in the page template (currently lines 155-157), add the `overdue.js` tag before `theme.js`:

```python
{FOOTER}
<script src="{asset("overdue.js")}"></script>
<script src="{asset("theme.js")}"></script>
</body>
</html>
```

- [ ] **Step 6: Add the `.od-toggle` base + mobile CSS**

In `assets/podigami.css`, right after the Task 1 section-collapse block you added (after `.od-panel[open] > summary .panel-chev { … }`), add the desktop-hidden base:

```css
/* ── Overdue: per-card stats toggle (mobile only; hidden on desktop) ───────── */
.od-toggle {
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    width: 100%;
    margin-top: 4px;
    padding: 10px 0 0;
    border: none;
    border-top: 1px solid var(--border);
    background: none;
    color: var(--muted);
    font: inherit;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    cursor: pointer;
}

.od-toggle:hover {
    color: var(--text);
}

.od-toggle .chev {
    font-size: 11px;
    transition: transform 0.18s ease;
}
```

Then, inside the existing `@media (max-width: 600px)` block, immediately after the `.odcard-hero .od-score-num { … }` rule (~line 1307), add:

```css
    /* Overdue cards: collapse the three stat cells behind the Details toggle */
    .odcard .od-stats {
        display: none;
    }

    .odcard.od-open .od-stats {
        display: grid;
    }

    .od-toggle {
        display: flex;
    }

    .odcard.od-open .od-toggle .chev {
        transform: rotate(180deg);
    }
```

- [ ] **Step 7: Rebuild and run the previously-red tests (GREEN)**

Run: `python src/build_site.py && python -m pytest tests/test_build_output.py::test_page_assets_referenced_and_copied tests/test_build_output.py::test_all_assets_copied tests/test_mobile_css.py::test_overdue_cards_collapse_stats_on_mobile -q`
Expected: PASS — `dist/overdue.js` now exists and is referenced; mobile rules present.

- [ ] **Step 8: Commit**

```bash
git add assets/overdue.js src/build/build_overdue_html.py assets/podigami.css tests/test_build_output.py tests/test_mobile_css.py
git commit -m "feat: wire overdue Details toggle (overdue.js + mobile collapse CSS)"
```

---

## Task 4: Docs + full verification

**Files:**
- Modify: `RELEASE_NOTES.md`

- [ ] **Step 1: Add a RELEASE_NOTES entry**

Under a `## 2026-07-09` heading (create it if absent) add, under `### Improvements`:

```markdown
- Overdue page: collapsible All-time / Current-grid sections and per-card "Details" expand to declutter cards on mobile (#<PR>).
```

(Replace `<PR>` with the PR number once opened, or drop the token if unknown at commit time.)

- [ ] **Step 2: Lint + format**

Run: `python -m ruff check . && python -m ruff format --check .`
Expected: both pass (no changes needed).

- [ ] **Step 3: Full test suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 4: Browser verification (Playwright MCP)**

Build and serve, then verify in a real browser (per CLAUDE.md's Playwright guidance):

```bash
python src/build_site.py
# serve dist/ (e.g. python -m http.server 8000 --directory dist) and drive with the playwright MCP
```

Confirm:
- **Desktop viewport (e.g. 1200px):** cards show all three stats; no `Details` button visible; clicking a section header collapses/expands that whole section (chevron rotates).
- **Phone viewport (375px):** each card shows rank + trio + score + `Details ▾`; the stats are hidden until the button is tapped, then appear (chevron rotates); both sections still collapse from their headers.

- [ ] **Step 5: Commit any doc change**

```bash
git add RELEASE_NOTES.md
git commit -m "docs: release note for overdue mobile collapse"
```

---

## Self-review

**Spec coverage:**
- Goal 1 (reduce mobile clutter) → Tasks 2-3 (per-card Details toggle, mobile-only CSS). ✓
- Goal 2 (collapse either section) → Task 1 (native `<details open>`). ✓
- Decision "both expanded by default" → `open` attribute in Task 1. ✓
- Decision "card expand mobile only" → `.od-toggle{display:none}` desktop base + reveal inside `max-width:600px` (Task 3). ✓
- Decision "combos-parity JS technique" → `overdue.js` toggling `.od-open` (Task 3), matching `index.js`. ✓
- Files listed in spec (build_overdue_html.py, podigami.css, overdue.js, three test files, RELEASE_NOTES) all have tasks. ✓

**Placeholder scan:** No TBD/TODO except the intentional `<PR>` token in the release note (guidance given for both cases). All code steps show full code.

**Type/name consistency:** `uid` param added to `panel`/`render_cards`/`render_card` in Task 1's signatures and used in Task 2's bodies; stats id format `odstats-{uid}{rank}` is identical in the `render_card` body, the `aria-controls`, and the Task 2 tests (`odstats-at2`, `odstats-at1`, `odstats-cg1`). Class names `od-panel`, `panel-chev`, `od-toggle`, `od-open`, `od-stats` match across HTML, CSS, JS, and tests.
