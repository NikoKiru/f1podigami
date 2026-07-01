# Landing Hero Slogan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trim the landing page hero to a short slogan, move the moved-out explanation into a rewritten FAQ entry, and drop the "only N have happened" framing from the meta description.

**Architecture:** Pure copy/string edit inside `src/build/build_podigami_html.py` (three spots: hero `<header>` paragraph, `render_faq`'s scarcity entry, and the `head()` meta description). No data, schema, or test-fixture changes — confirmed no test in `tests/` pins this copy (see spec's Out of Scope section).

**Tech Stack:** Python string templating (no template engine), pytest for the `dist` fixture, ruff for lint/format.

---

### Task 1: Rewrite the hero tagline

**Files:**
- Modify: `src/build/build_podigami_html.py:588-594`

- [ ] **Step 1: Replace the tagline paragraph**

Current (lines 587-596, inside `<header><div class="container">`):

```python
        <h1><span class="accent">F1</span> Podigami</h1>
        <p class="tagline">Podigami &mdash; a blend of &ldquo;podium&rdquo; and
        &ldquo;<a href="https://en.wikipedia.org/wiki/Scorigami" target="_blank" rel="noopener">scorigami</a>&rdquo;
        &mdash; tracks F1 podium trios that have never happened before. Only <strong>{
        total_combos:,}</strong> unique combinations have appeared across <strong>{
        total_races:,}</strong> races since {lo}, yet today&rsquo;s {grid_size}-driver grid
        produces <strong>{possible_trios:,}</strong> possible trios per race. A statistical model
        predicts which brand-new trio is most likely next in the {season} season.</p>
```

Replace with:

```python
        <h1><span class="accent">F1</span> Podigami</h1>
        <p class="tagline">Spotting the podium trio F1 has never seen &mdash;
        and predicting who&rsquo;s about to make it happen.</p>
```

- [ ] **Step 2: Check for now-unused locals**

`total_combos`, `total_races`, `possible_trios`, `grid_size`, `lo` were used in the
old tagline. `render_faq`'s rewritten entry (Task 2) will consume `total_combos`,
`total_races`, `possible_trios`, `grid_size`, `lo`, so pass them through to
`render_faq` there rather than deleting them. Don't remove any of these locals in
this step — just confirm they're still referenced somewhere after Task 2, so ruff
doesn't flag them as unused.

- [ ] **Step 3: Commit**

```bash
git add src/build/build_podigami_html.py
git commit -m "Trim landing hero to a slogan"
```

---

### Task 2: Rewrite the FAQ scarcity entry into a factual explainer

**Files:**
- Modify: `src/build/build_podigami_html.py` (`render_faq` signature + its "Why haven't most trios happened yet?" entry, ~line 452-488)
- Modify: `src/build/build_podigami_html.py` (the `render_faq(data, model_eval)` call site, ~line 557)

- [ ] **Step 1: Extend `render_faq`'s signature to accept the stats it now needs**

Current signature:

```python
def render_faq(data: dict, ev: dict) -> str:
```

Change to:

```python
def render_faq(
    data: dict,
    ev: dict,
    total_combos: int,
    total_races: int,
    possible_trios: int,
    grid_size: int,
    lo: int,
) -> str:
```

- [ ] **Step 2: Replace the scarcity FAQ entry**

Current entry (in the `items` list):

```python
        (
            "Why haven&rsquo;t most trios happened yet?",
            "Even with decades of racing, the number of possible three-driver combinations from "
            "a 20-driver grid is enormous. Most trios are still podigamis waiting to happen.",
        ),
```

Replace with (keep it in the same list position):

```python
        (
            "What does &ldquo;podigami&rdquo; mean?",
            f"Podigami blends &ldquo;podium&rdquo; and &ldquo;"
            f'<a href="https://en.wikipedia.org/wiki/Scorigami" target="_blank" rel="noopener">scorigami</a>'
            f"&rdquo; &mdash; it&rsquo;s the practice of tracking F1 podium trios that have never "
            f"happened before. Since {lo}, <strong>{total_combos:,}</strong> unique trios have "
            f"appeared across <strong>{total_races:,}</strong> races. Today&rsquo;s {grid_size}-driver "
            f"grid can produce <strong>{possible_trios:,}</strong> different trios per race, so most "
            f"combinations simply haven&rsquo;t come up yet.",
        ),
```

- [ ] **Step 3: Update the call site to pass the new arguments**

Current (~line 557):

```python
    faq = render_faq(data, model_eval)
```

This line comes after `possible_trios`, `grid_size`, `total_combos`, `total_races`,
and `lo` are already computed earlier in `main()` (lines 511, 517-520). Change to:

```python
    faq = render_faq(data, model_eval, total_combos, total_races, possible_trios, grid_size, lo)
```

- [ ] **Step 4: Commit**

```bash
git add src/build/build_podigami_html.py
git commit -m "Move podigami explanation from hero into a rewritten FAQ entry"
```

---

### Task 3: Trim the meta description

**Files:**
- Modify: `src/build/build_podigami_html.py:574-578`

- [ ] **Step 1: Replace the description text**

Current:

```python
            description=(
                f"Podigami is the art of spotting F1 podium trios that have never happened before. "
                f"Only {total_combos:,} unique trios have appeared in {total_races:,} races since {lo}. "
                f"A statistical model predicts which brand-new trio is most likely next in the {season} season."
            ),
```

Replace with:

```python
            description=(
                f"Podigami is the art of spotting F1 podium trios that have never happened before. "
                f"A statistical model predicts which brand-new trio is most likely next in the {season} season."
            ),
```

- [ ] **Step 2: Commit**

```bash
git add src/build/build_podigami_html.py
git commit -m "Drop trio-count framing from the landing page meta description"
```

---

### Task 4: Verify

**Files:** none (verification only)

- [ ] **Step 1: Lint and format**

Run: `python -m ruff check .` then `python -m ruff format --check .`
Expected: both report no issues (no unused-variable warnings for `total_combos` etc., since Task 2 wires them into `render_faq`).

- [ ] **Step 2: Run the test suite**

Run: `python -m pytest -q`
Expected: all tests pass (the `dist` fixture rebuilds the site from the new builder code; no test currently asserts on this copy, per the spec's Out of Scope note, so no test edits are expected here).

- [ ] **Step 3: Rebuild and visually check**

Run: `python src/build_site.py`
Then open `dist/index.html` in a browser (or use the `playwright` MCP against the local file) and confirm:
- The header now shows only the short slogan, no stats.
- The FAQ has a "What does 'podigami' mean?" entry with the etymology + counts.
- No leftover references to the old "Why haven't most trios happened yet?" question.

- [ ] **Step 4: Update README and RELEASE_NOTES per CLAUDE.md**

- `RELEASE_NOTES.md`: add a line under today's date heading, `### Improvements`, e.g.
  `- Simplified the landing page hero to a slogan and moved the podigami explainer into the FAQ (#<PR>).`
- `README.md`: only touch it if it quotes the old hero copy or FAQ question text (check with a search for "podigami" blend text or "Why haven't most trios"); otherwise no change needed.

- [ ] **Step 5: Commit any docs updates**

```bash
git add RELEASE_NOTES.md README.md
git commit -m "Update release notes for landing hero slogan change"
```
