# Landing-Page Engagement Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep landing-page visitors engaged longer and route them to the other four pages via live-stat hook cards, an explore grid, motion, and deep links — per `docs/superpowers/specs/2026-07-03-landing-engagement-design.md`.

**Architecture:** A new pure-render module `src/build/_hooks.py` produces "hook cards" (kicker + build-time stat + CTA) composed into `build_podigami_html.py` at contextual positions plus a final "Keep exploring" grid. Client-side motion (count-up, scroll-reveal, timeline quick-picks) is progressive enhancement in `assets/podigami.js` — raw HTML never hides content; `prefers-reduced-motion` disables everything. `soulmates.html` joins the shared nav/footer.

**Tech Stack:** Python 3.11+ string-based HTML builders, Pydantic datalib loaders, vanilla JS IIFEs, plain CSS with existing tokens, pytest.

**Working branch:** `feat/landing-engagement` (already exists, spec committed). All commands run from repo root. Tests: `python -m pytest -q` (the `dist` fixture rebuilds the site once per session). Lint: `python -m ruff check .` and `python -m ruff format .`.

**Repo conventions that matter here:**
- HTML built via f-strings; every interpolated value goes through `esc()` (=`html.escape`).
- Builders import siblings directly (`from _hooks import ...`) because each builder puts its own dir on `sys.path`; tests import as `from build import _hooks`.
- CSS tokens: `--surface`, `--border`, `--radius`, `--accent`, `--accent-bright`, `--text`, `--text-dim`, `--muted`, `--surface-2`, `--border-strong`. Mobile breakpoint `@media (max-width: 600px)`.
- datalib models use attribute access: `soulmates.topPairs[0].a`, `overdue.allTime[0].racesTogether`, `unlikeliest.trios[0].happened.raceName` (RaceRef: `season`, `round`, `raceName`).

---

### Task 1: Soulmates page into shared nav + footer

**Files:**
- Modify: `src/build/_layout.py:25-30` (NAV_LINKS) and `:181-198` (FOOTER)
- Test: `tests/test_build_output.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_build_output.py` (after `test_footer_has_universal_details`):

```python
# All five generated pages must carry identical chrome with all five links.
ALL_PAGES = ["index.html", "combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"]


@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_links_soulmates_in_nav_and_footer(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    nav = html[html.index('<nav class="nav">') : html.index("</nav>")]
    assert 'href="soulmates.html"' in nav, f"{page} nav is missing Soulmates"
    assert ">Soulmates<" in nav
    footer = _footer_block(html)
    assert 'href="soulmates.html"' in footer, f"{page} footer is missing Soulmates"
```

Also extend the existing footer-links loop in `test_footer_has_universal_details` from:

```python
    for link in ("index.html", "combos.html", "overdue.html"):
```

to:

```python
    for link in ("index.html", "combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_output.py -q -k "soulmates_in_nav or universal_details"`
Expected: the 5 new nav tests FAIL (`'href="soulmates.html"' in nav` assert), `universal_details` FAILS on `soulmates.html`.

- [ ] **Step 3: Implement in `src/build/_layout.py`**

NAV_LINKS becomes:

```python
NAV_LINKS = [
    ("index.html", "Podigami"),
    ("combos.html", "Combinations"),
    ("overdue.html", "Overdue"),
    ("unlikeliest.html", "Unlikeliest"),
    ("soulmates.html", "Soulmates"),
]
```

In `FOOTER`, after the Unlikeliest anchor add:

```html
            <a href="soulmates.html">Soulmates</a>
```

- [ ] **Step 4: Run the full output tests**

Run: `python -m pytest tests/test_build_output.py -q`
Expected: all PASS (footer stays byte-identical across pages, so `test_footer_is_identical_across_pages` still passes).

- [ ] **Step 5: Commit**

```bash
git add src/build/_layout.py tests/test_build_output.py
git commit -m "feat: add orphaned Soulmates page to shared nav and footer"
```

---

### Task 2: `_hooks.py` — hook card renderer + stat builders (pure, no I/O)

**Files:**
- Create: `src/build/_hooks.py`
- Create: `tests/test_hooks.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_hooks.py`:

```python
"""Unit tests for the discovery hook cards (src/build/_hooks.py)."""

from types import SimpleNamespace as NS

from build import _hooks


def test_hook_card_structure_and_escaping():
    out = _hooks.hook_card("Kick & er", "<b>stat</b>", "combos.html?a=1&b=2", "Go <now>")
    assert out.startswith('<a class="hook-card" href="combos.html?a=1&amp;b=2">')
    assert '<span class="hook-kicker">Kick &amp; er</span>' in out
    assert '<span class="hook-stat"><b>stat</b></span>' in out  # stat_html is trusted HTML
    assert "Go &lt;now&gt;" in out  # CTA text is escaped
    assert "hook-arrow" in out


def test_hook_card_without_stat_omits_stat_line():
    out = _hooks.hook_card("Overdue trios", "", "overdue.html", "Who is due")
    assert "hook-stat" not in out
    assert 'href="overdue.html"' in out


def test_combos_hook_formats_total():
    out = _hooks.combos_hook(1234, 1950)
    assert "1,234" in out
    assert "1950" in out
    assert 'href="combos.html"' in out


def test_combos_hook_zero_total_falls_back_statless():
    assert "hook-stat" not in _hooks.combos_hook(0, 1950)


def test_soulmates_hook_top_pair_and_escaping():
    sm = NS(topPairs=[NS(a="Lewis & Hamilton", b="Sebastian Vettel", count=61)])
    out = _hooks.soulmates_hook(sm)
    assert "Lewis &amp; Hamilton" in out
    assert "61" in out
    assert 'href="soulmates.html"' in out


def test_soulmates_hook_missing_data():
    assert "hook-stat" not in _hooks.soulmates_hook(None)
    assert "hook-stat" not in _hooks.soulmates_hook(NS(topPairs=[]))
    assert 'href="soulmates.html"' in _hooks.soulmates_hook(None)


def test_overdue_hook_surnames_and_races():
    od = NS(
        allTime=[
            NS(
                names=["Lewis Hamilton", "Max Verstappen", "Oscar Piastri"],
                racesTogether=78,
            )
        ]
    )
    out = _hooks.overdue_hook(od)
    assert "Hamilton / Verstappen / Piastri" in out
    assert "78" in out
    assert 'href="overdue.html"' in out


def test_overdue_hook_missing_data():
    assert "hook-stat" not in _hooks.overdue_hook(None)
    assert "hook-stat" not in _hooks.overdue_hook(NS(allTime=[]))


def test_unlikeliest_hook_race_and_season():
    ul = NS(
        trios=[
            NS(
                names=["Esteban Ocon", "Sergio Pérez", "Lance Stroll"],
                happened=NS(season="2020", round="16", raceName="Sakhir Grand Prix"),
            )
        ]
    )
    out = _hooks.unlikeliest_hook(ul)
    assert "Ocon / Pérez / Stroll" in out
    assert "Sakhir Grand Prix" in out
    assert "2020" in out
    assert 'href="unlikeliest.html"' in out


def test_unlikeliest_hook_missing_data():
    assert "hook-stat" not in _hooks.unlikeliest_hook(None)
    assert "hook-stat" not in _hooks.unlikeliest_hook(NS(trios=[]))


def test_explore_grid_links_all_four_pages():
    out = _hooks.explore_grid()
    for href in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f'href="{href}"' in out
    assert "Keep exploring" in out
    assert out.count("hook-card") >= 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hooks.py -q`
Expected: FAIL with `ImportError: cannot import name '_hooks'`.

- [ ] **Step 3: Create `src/build/_hooks.py`**

```python
"""Discovery hook cards: cross-page teasers with a live build-time stat.

A hook card is a whole-card link: kicker label, one stat line computed from
committed data, and an arrow CTA. Stat builders are pure functions over
already-loaded datalib models (callers do the I/O); every builder tolerates
``None`` or empty data by dropping the stat line, so a data gap can never
break the build.
"""

from __future__ import annotations

import html


def esc(s) -> str:
    return html.escape(str(s))


def _surname(name: str) -> str:
    parts = str(name).split()
    return parts[-1] if parts else str(name)


def _surnames(names) -> str:
    """Escaped "A / B / C" surname line for a trio."""
    return " / ".join(esc(_surname(n)) for n in names)


def hook_card(kicker: str, stat_html: str, href: str, cta: str) -> str:
    """One teaser card. ``stat_html`` is pre-escaped/trusted HTML; "" omits it."""
    stat = f'<span class="hook-stat">{stat_html}</span>' if stat_html else ""
    return (
        f'<a class="hook-card" href="{esc(href)}">'
        f'<span class="hook-kicker">{esc(kicker)}</span>'
        f"{stat}"
        f'<span class="hook-cta">{esc(cta)}'
        f' <span class="hook-arrow" aria-hidden="true">&rarr;</span></span>'
        f"</a>"
    )


def combos_hook(total_combos: int, since_year) -> str:
    stat = ""
    if total_combos:
        stat = (
            f"<b>{total_combos:,}</b> unique podium trios since {esc(since_year)}"
            f" &mdash; every single one, sortable"
        )
    return hook_card("All the combinations", stat, "combos.html", "Browse them all")


def soulmates_hook(soulmates) -> str:
    stat = ""
    if soulmates is not None and soulmates.topPairs:
        p = soulmates.topPairs[0]
        stat = (
            f"<b>{esc(p.a)} &amp; {esc(p.b)}</b> shared the podium"
            f" <b>{p.count}</b> times &mdash; F1&rsquo;s tightest duo"
        )
    return hook_card("Podium soulmates", stat, "soulmates.html", "See every partnership")


def overdue_hook(overdue) -> str:
    stat = ""
    if overdue is not None and overdue.allTime:
        t = overdue.allTime[0]
        stat = (
            f"<b>{_surnames(t.names)}</b>: {t.racesTogether} races together,"
            f" never all three on the podium"
        )
    return hook_card("Overdue trios", stat, "overdue.html", "Who's due next")


def unlikeliest_hook(unlikeliest) -> str:
    stat = ""
    if unlikeliest is not None and unlikeliest.trios:
        t = unlikeliest.trios[0]
        stat = (
            f"The most improbable podium ever: <b>{_surnames(t.names)}</b>,"
            f" {esc(t.happened.raceName)} {esc(t.happened.season)}"
        )
    return hook_card("Unlikeliest podiums", stat, "unlikeliest.html", "See the longest shots")


def explore_grid() -> str:
    """End-of-page hub: every other page, one line each (no stats — the in-flow
    hooks carry those; repeating them here would read as a glitch)."""
    cards = [
        hook_card(
            "Combinations",
            "Every unique podium trio in F1 history &mdash; sortable, searchable.",
            "combos.html",
            "Browse them all",
        ),
        hook_card(
            "Overdue",
            "Trios that keep almost happening &mdash; who&rsquo;s been waiting longest.",
            "overdue.html",
            "Who's due next",
        ),
        hook_card(
            "Unlikeliest",
            "The podiums that defied the odds the hardest.",
            "unlikeliest.html",
            "See the longest shots",
        ),
        hook_card(
            "Soulmates",
            "Which drivers keep meeting on the podium.",
            "soulmates.html",
            "See every partnership",
        ),
    ]
    return (
        '<section class="panel explore"><h2>Keep exploring</h2>'
        f'<div class="explore-grid">{"".join(cards)}</div></section>'
    )
```

Note the escaping contract: `hook_card` escapes `kicker`/`href`/`cta` (so CTA strings use plain apostrophes), while `stat_html` (including the explore-grid one-liners) is trusted HTML that may carry entities — every dynamic value inside it must go through `esc()`/`_surnames()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hooks.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/build/_hooks.py tests/test_hooks.py
git commit -m "feat: discovery hook-card renderer with live stats and safe fallbacks"
```

---

### Task 3: Wire hooks + explore grid into the landing page, with CSS

**Files:**
- Modify: `src/build/build_podigami_html.py` (imports, `main()`, page f-string)
- Modify: `assets/podigami.css` (hook card + grids)
- Test: `tests/test_build_output.py`, `tests/test_mobile_css.py`

- [ ] **Step 1: Write the failing output tests**

Add to `tests/test_build_output.py`:

```python
def test_landing_page_discovery_hooks_in_flow(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    for href in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f'<a class="hook-card" href="{href}"' in html, f"missing hook to {href}"
    # each in-flow hook sits after its related section
    assert html.index('class="cand-list"') < html.index('class="hook-card" href="combos.html"')
    assert html.index('class="form-tower"') < html.index('class="hook-card" href="soulmates.html"')
    assert html.index('id="tl-slider"') < html.index('class="hook-card" href="overdue.html"')
    assert 'class="hook-row"' in html  # overdue + unlikeliest side by side


def test_landing_page_explore_grid_is_last_section(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert "Keep exploring" in html
    grid = html[html.index('class="explore-grid"') :]
    for href in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f'href="{href}"' in grid, f"explore grid missing {href}"
    # explore grid comes after the FAQ
    assert html.index("faq-section") < html.index('class="explore-grid"')
```

And to `tests/test_mobile_css.py`:

```python
def test_hook_grids_collapse_on_mobile():
    """The 2-up hook row and 2x2 explore grid must stack to one column on phones."""
    import re

    s = css("podigami.css")
    assert ".hook-card" in s and ".explore-grid" in s
    assert re.search(
        r"@media \(max-width: 600px\).*?\.hook-row[\s\S]*?grid-template-columns:\s*1fr",
        s,
        re.DOTALL,
    ), "hook-row/explore-grid must collapse to 1 column inside the 600px breakpoint"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_output.py tests/test_mobile_css.py -q -k "hook or explore"`
Expected: 3 FAILs (no hook-card markup, no CSS yet).

- [ ] **Step 3: Wire into `build_podigami_html.py`**

Add to the sibling imports (after `from flags import flag_svg`):

```python
from _hooks import (  # noqa: E402
    combos_hook,
    explore_grid,
    overdue_hook,
    soulmates_hook,
    unlikeliest_hook,
)
```

Extend the datalib import list with `load_overdue`, `load_soulmates`, `load_unlikeliest`.

In `main()` after `model_eval` loading, add (tolerant loads mirror the existing schedule/model_eval pattern):

```python
    soulmates_data = load_soulmates() if (DATA_DIR / "soulmates.json").exists() else None
    overdue_data = load_overdue() if (DATA_DIR / "overdue.json").exists() else None
    unlikeliest_data = load_unlikeliest() if (DATA_DIR / "unlikeliest.json").exists() else None

    hook_combos = combos_hook(total_combos, lo)
    hook_soulmates = soulmates_hook(soulmates_data)
    hook_row = (
        f'<div class="hook-row">{overdue_hook(overdue_data)}'
        f"{unlikeliest_hook(unlikeliest_data)}</div>"
    )
    explore = explore_grid()
```

Change the page composition block from:

```
        {next_race}
        {last_race}
        {hero}
        {candidates}
        {form}
        {timeline}
        {faq}
```

to:

```
        {next_race}
        {last_race}
        {hero}
        {candidates}
        {hook_combos}
        {form}
        {hook_soulmates}
        {timeline}
        {hook_row}
        {faq}
        {explore}
```

- [ ] **Step 4: Add CSS to `assets/podigami.css`** (append at end of file, before any trailing mobile block — or as its own section with its own media query):

```css
/* ---- Discovery hooks & explore grid ------------------------------------ */

.hook-card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 14px;
    padding: 14px 18px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    text-decoration: none;
    color: var(--text);
    transition: border-color 0.15s ease, transform 0.15s ease;
}

.hook-card:hover {
    border-color: var(--accent);
    transform: translateY(-1px);
}

.hook-kicker {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    color: var(--accent-bright);
}

.hook-stat {
    color: var(--text-dim);
    font-size: 14px;
    line-height: 1.45;
}

.hook-stat b {
    color: var(--text);
}

.hook-cta {
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
}

.hook-card:hover .hook-cta {
    color: var(--text);
}

.hook-arrow {
    display: inline-block;
    transition: transform 0.15s ease;
}

.hook-card:hover .hook-arrow {
    transform: translateX(3px);
}

.hook-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}

.explore-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-top: 12px;
}

.explore-grid .hook-card {
    margin-top: 0;
}

@media (max-width: 600px) {
    .hook-row,
    .explore-grid {
        grid-template-columns: 1fr;
    }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_output.py tests/test_mobile_css.py tests/test_build_podigami.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/build/build_podigami_html.py assets/podigami.css tests/test_build_output.py tests/test_mobile_css.py
git commit -m "feat: weave discovery hooks and keep-exploring grid into landing page"
```

---

### Task 4: FAQ deep links + "What else is on this site?" item

**Files:**
- Modify: `src/build/build_podigami_html.py` (`render_faq`)
- Test: `tests/test_build_output.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_build_output.py`:

```python
def test_landing_faq_deep_links_all_pages(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    faq = html[html.index("faq-section") : html.index('class="explore-grid"')]
    assert "What else is on this site?" in faq
    for href in ("combos.html", "overdue.html", "unlikeliest.html", "soulmates.html"):
        assert f'href="{href}"' in faq, f"FAQ should deep-link {href}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_output.py::test_landing_faq_deep_links_all_pages -q`
Expected: FAIL ("What else is on this site?" not found).

- [ ] **Step 3: Implement in `render_faq`**

In the podigami-definition item, change

```python
f"happened before. Since {lo}, <strong>{total_combos:,}</strong> unique trios have "
```

to

```python
f'happened before. Since {lo}, <a href="combos.html"><strong>{total_combos:,}</strong></a> unique trios have '
```

Append a new item to the `items` list:

```python
        (
            "What else is on this site?",
            'Four deeper dives: <a href="combos.html">Combinations</a> lists every unique '
            'podium trio in history; <a href="overdue.html">Overdue</a> ranks the trios that '
            'keep almost happening; <a href="unlikeliest.html">Unlikeliest</a> celebrates the '
            'podiums that defied the odds; and <a href="soulmates.html">Soulmates</a> maps '
            "which drivers keep meeting on the podium.",
        ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_output.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/build/build_podigami_html.py tests/test_build_output.py
git commit -m "feat: FAQ deep links plus what-else-is-here item"
```

---

### Task 5: Timeline quick-pick chips

**Files:**
- Modify: `src/build/build_podigami_html.py` (`_quickpicks` helper + `render_timeline`)
- Modify: `assets/podigami.js` (chip → slider IIFE)
- Modify: `assets/podigami.css` (chip styles)
- Test: `tests/test_build_podigami.py`, `tests/test_build_output.py`

- [ ] **Step 1: Write the failing unit tests**

Add to `tests/test_build_podigami.py`:

```python
def test_quickpicks_first_record_current():
    out = bp._quickpicks(1950, 2026, {"1950": 3, "1982": 17, "2026": 5})
    assert 'data-year="1950"' in out and "first season" in out
    assert 'data-year="1982"' in out and "17 new" in out
    assert 'data-year="2026"' in out and "this season" in out


def test_quickpicks_record_tie_prefers_earliest_and_dedupes():
    # tie between 1950 and 1982 -> earliest (1950) wins; 1950 is already the
    # "first season" chip, so no separate record chip is emitted
    out = bp._quickpicks(1950, 2026, {"1950": 17, "1982": 17})
    assert out.count('data-year="1950"') == 1
    assert 'data-year="1982"' not in out


def test_quickpicks_empty_counts_and_single_season():
    out = bp._quickpicks(2026, 2026, {})
    assert out.count("tl-chip") == 1  # just the first-season chip
```

And to `tests/test_build_output.py`:

```python
def test_landing_timeline_has_quickpick_chips(dist, data):
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="tl-chips"' in html
    lo = data["podigami"]["seasonRange"][0]
    assert f'data-year="{lo}"' in html
    counts = data["podigami"]["seasonCounts"]
    record = max(counts.items(), key=lambda kv: (kv[1], -int(kv[0])))[0]
    assert f'data-year="{record}"' in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_podigami.py tests/test_build_output.py -q -k quickpick`
Expected: FAIL with `AttributeError: ... has no attribute '_quickpicks'` / missing `tl-chips`.

- [ ] **Step 3: Implement `_quickpicks` and wire into `render_timeline`**

Add to `build_podigami_html.py` (above `render_timeline`):

```python
def _quickpicks(lo: int, current: int, counts: dict) -> str:
    """One-tap year chips for the timeline: first season, record season
    (earliest wins ties), and the current season. Duplicates collapse."""
    picks: list[tuple[int, str]] = [(lo, "first season")]
    if counts:
        rec_year_s, rec_n = max(counts.items(), key=lambda kv: (kv[1], -int(kv[0])))
        rec_year = int(rec_year_s)
        if rec_year not in {lo, current}:
            picks.append((rec_year, f"record: {rec_n} new"))
    if current != lo:
        picks.append((current, "this season"))
    chips = "".join(
        f'<button type="button" class="tl-chip" data-year="{y}">'
        f"{y} &middot; {esc(label)}</button>"
        for y, label in picks
    )
    return f'<div class="tl-chips">{chips}</div>'
```

In `render_timeline`, after the `</div>` closing `tl-header` (i.e. between the header block and `tl-spark`), insert:

```python
        f"  {_quickpicks(lo, current, counts)}"
```

- [ ] **Step 4: Add the JS module** (append to `assets/podigami.js`):

```js
// Timeline quick-picks: chips that jump the year slider to notable seasons
// (first ever, record year, current). They just drive the existing slider.
(function () {
    const chips = Array.from(document.querySelectorAll('.tl-chip'));
    const slider = document.getElementById('tl-slider');
    if (!chips.length || !slider) return;
    chips.forEach(chip => chip.addEventListener('click', () => {
        slider.value = chip.dataset.year;
        slider.dispatchEvent(new Event('input', { bubbles: true }));
    }));
})();
```

- [ ] **Step 5: Add chip CSS** (append to the hooks section of `assets/podigami.css`, above its 600px block):

```css
.tl-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 10px 0 2px;
}

.tl-chip {
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 12px;
    border-radius: 999px;
    border: 1px solid var(--border-strong);
    background: var(--surface-2);
    color: var(--text-dim);
    cursor: pointer;
    transition: border-color 0.15s ease, color 0.15s ease;
}

.tl-chip:hover {
    border-color: var(--accent);
    color: var(--text);
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_podigami.py tests/test_build_output.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/build/build_podigami_html.py assets/podigami.js assets/podigami.css tests/test_build_podigami.py tests/test_build_output.py
git commit -m "feat: timeline quick-pick chips for notable seasons"
```

---

### Task 6: Hero count-up + scroll-reveal (progressive enhancement)

**Files:**
- Modify: `assets/podigami.js` (two IIFEs)
- Modify: `assets/podigami.css` (reveal transitions)
- Test: `tests/test_build_output.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_build_output.py`:

```python
def test_landing_raw_html_never_hides_content(dist):
    """Scroll-reveal must be JS-applied only: no hiding class in the built HTML,
    so no-JS visitors (and crawlers) always get the full page."""
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert 'class="reveal"' not in html
    assert "reveal-in" not in html


def test_podigami_js_motion_is_progressive_enhancement(repo):
    js = (repo / "assets" / "podigami.js").read_text(encoding="utf-8")
    # timeline easing + count-up + scroll-reveal each honour reduced motion
    assert js.count("prefers-reduced-motion") >= 3
    assert js.count("IntersectionObserver") >= 2  # count-up + reveal guard on support
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_output.py -q -k "hides_content or progressive"`
Expected: `test_podigami_js_motion_is_progressive_enhancement` FAILS (only 1 reduced-motion reference today); the raw-HTML test PASSES already (guard test — keep it).

- [ ] **Step 3: Append the two IIFEs to `assets/podigami.js`**

```js
// Hero count-up: the headline chance % climbs from 0 on first view. The
// server-rendered number stays in the HTML for SEO/no-JS and is restored
// verbatim when the animation lands.
(function () {
    const el = document.querySelector('.hc-num');
    if (!el || !('IntersectionObserver' in window)) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const finalText = el.textContent;
    const target = parseFloat(finalText);
    if (isNaN(target)) return;
    const DURATION = 900;
    const io = new IntersectionObserver(entries => {
        if (!entries.some(e => e.isIntersecting)) return;
        io.disconnect();
        const t0 = performance.now();
        (function frame(now) {
            const p = Math.min((now - t0) / DURATION, 1);
            const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
            if (p < 1) {
                el.textContent = Math.round(target * eased) + '%';
                requestAnimationFrame(frame);
            } else {
                el.textContent = finalText;
            }
        })(t0);
    }, { threshold: 0.4 });
    io.observe(el);
})();

// Scroll-reveal: sections fade up as they enter the viewport. The hiding
// class is added HERE, never in the HTML, so content is never hidden without
// JS; above-the-fold elements are left untouched to avoid a first-paint flash.
(function () {
    if (!('IntersectionObserver' in window)) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const els = document.querySelectorAll(
        'main .panel, main .hook-row, main .container > .hook-card');
    const io = new IntersectionObserver(entries => {
        entries.forEach(e => {
            if (!e.isIntersecting) return;
            e.target.classList.add('reveal-in');
            io.unobserve(e.target);
        });
    }, { threshold: 0.08 });
    els.forEach(el => {
        if (el.getBoundingClientRect().top > window.innerHeight * 0.9) {
            el.classList.add('reveal');
            io.observe(el);
        }
    });
})();
```

- [ ] **Step 4: Add reveal CSS** (append to `assets/podigami.css`):

```css
/* Scroll-reveal (class applied by JS only — raw HTML never hides content). */
.reveal {
    opacity: 0;
    transform: translateY(12px);
}

.reveal.reveal-in {
    opacity: 1;
    transform: none;
    transition: opacity 0.5s ease, transform 0.5s ease;
}

@media (prefers-reduced-motion: reduce) {
    .reveal {
        opacity: 1;
        transform: none;
    }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_output.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add assets/podigami.js assets/podigami.css tests/test_build_output.py
git commit -m "feat: hero count-up and scroll-reveal as progressive enhancement"
```

---

### Task 7: Docs, full verification, release notes

**Files:**
- Modify: `README.md` (Pages table / feature bullets)
- Modify: `RELEASE_NOTES.md`

- [ ] **Step 1: Update `README.md`**

In the `## 🏎️ Pages` table row for `index.html`, mention the discovery layer (adjust to current wording), e.g. append: "… plus discovery hooks and a Keep-exploring grid routing to every other page". No structural README changes otherwise (page list, file map, workflows are unchanged).

- [ ] **Step 2: Update `RELEASE_NOTES.md`**

Under a `## 2026-07-04` heading (create if absent), `### Features`:

```markdown
- Landing-page engagement overhaul: live-stat discovery hooks, "Keep exploring" grid, timeline quick-pick chips, hero count-up and scroll-reveal, FAQ deep links; Soulmates added to site nav (#PR)
```

(Replace `#PR` with the real PR number after `gh pr create`.)

- [ ] **Step 3: Full verification**

Run: `python -m ruff format . && python -m ruff check . && python -m pytest -q && PYTHONPATH=src python -m datalib.validate`
Expected: format clean, 0 lint errors, all tests pass, all schemas valid.

- [ ] **Step 4: Rebuild + browser check (Playwright MCP against locally served dist/)**

```bash
python src/build_site.py
python -m http.server 8123 --directory dist   # background
```

Verify with Playwright: hooks + explore grid render and navigate; chips drive the slider; count-up animates once; reveals fire on scroll; mobile viewport (390×844) stacks grids; no console errors. Screenshot for the user.

- [ ] **Step 5: Commit docs**

```bash
git add README.md RELEASE_NOTES.md
git commit -m "docs: release notes + README for landing engagement overhaul"
```

---

### Task 8: PR into develop → merge → local approval preview

- [ ] **Step 1: Push and open PR** (template structure: Summary / Changes / Testing / Checklist; RELEASE_NOTES PR number backfilled):

```bash
git push -u origin feat/landing-engagement
gh pr create --base develop --title "Landing-page engagement overhaul" --body "..."
```

Then update RELEASE_NOTES with the PR number, amend nothing — add a small commit if needed.

- [ ] **Step 2: Wait for the 7 required checks, merge (squash), delete branch**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout develop && git pull
```

- [ ] **Step 3: Serve locally for user approval**

```bash
python src/build_site.py
python -m http.server 8123 --directory dist
```

Hand the URL (http://localhost:8123) to the user. **STOP — user approval gate.** Only after approval: promotion PR `develop → main` (`gh pr create --base main --head develop`), wait for all 9 checks, merge, confirm Pages deploy.

---

## Self-review notes

- Spec coverage: nav fix (T1), hooks (T2–T3), explore grid (T2–T3), count-up/reveal (T6), quick-picks (T5), FAQ links (T4), tests woven through, README/RELEASE_NOTES (T7), ship path (T8). ✓
- `hook_card` escapes `kicker`/`href`/`cta`; `stat_html` is trusted-HTML by contract and all builders escape interpolated data via `esc()`/`_surnames()`. ✓
- Types consistent: stat builders take datalib model objects (attribute access) or `None`; tests use `SimpleNamespace` duck-typing. ✓
