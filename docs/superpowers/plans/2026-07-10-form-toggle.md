# Form Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the standalone "Current form" panel from the landing page and embed the driver-form tower behind a native `<details>` "Show current form" toggle inside the "Most likely next combinations" (candidates) panel.

**Architecture:** `render_form()` in `src/build/build_podigami_html.py` changes from returning a standalone `<section class="panel">` to returning a `<details class="form-details">` block; `render_candidates()` gains a `form_html` parameter and appends it after its `<ol>`; `main()` wires them together and drops the standalone `{form}` placement. Pure-CSS open/closed label swap (two spans toggled by `details[open]`), no JS. Spec: `docs/superpowers/specs/2026-07-10-form-toggle-design.md`.

**Tech Stack:** Python string-based HTML generation, pytest, plain CSS (`assets/podigami.css`).

---

### Task 1: `render_form()` returns a `<details>` block

**Files:**
- Modify: `src/build/build_podigami_html.py:370-413` (`render_form`)
- Test: `tests/test_build_podigami.py:159-172` (`test_render_form_builds_timing_tower`)

- [ ] **Step 1: Extend the failing test**

In `tests/test_build_podigami.py`, replace `test_render_form_builds_timing_tower` with:

```python
def test_render_form_builds_timing_tower():
    form = [
        {**pd("antonelli", "Andrea Kimi Antonelli", "mercedes"), "weight": 12.2},
        {**pd("norris", "Lando Norris", "mclaren"), "weight": 8.6},
        # zero-weight driver is filtered out of the tower
        {**pd("zzz", "Zed Zero", ""), "weight": 0.0},
    ]
    out = bp.render_form(form, True, META, half_life=6.0)
    assert out.count('class="tower-row"') == 2
    assert "tr-num" in out and "tr-bar" in out
    assert 'class="tr-code">ANT' in out
    assert "constructor strength" in out  # using_constructors=True extends the sub
    assert "~6 races" in out
    assert "~8 races" not in out
    # collapsed <details> block, not a standalone panel
    assert out.startswith('<details class="form-details">')
    assert "<section" not in out
    assert "Show current form" in out and "Hide current form" in out
    assert " open>" not in out  # collapsed by default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_podigami.py::test_render_form_builds_timing_tower -q`
Expected: FAIL on `out.startswith('<details class="form-details">')` (current output starts with `<section class="panel">`).

- [ ] **Step 3: Rewrite `render_form`'s return block**

In `src/build/build_podigami_html.py`, keep the row-building and `sub` logic of `render_form` unchanged, and replace the final `return (...)` (the `<section class="panel">…Current form…</section>` block) with:

```python
    return (
        f'<details class="form-details">'
        f'<summary>'
        f'<span class="fd-closed">Show current form &#9662;</span>'
        f'<span class="fd-open">Hide current form &#9652;</span>'
        f"</summary>"
        f'<p class="form-caption">{sub}</p>'
        f'<div class="form-tower">{"".join(rows)}</div>'
        f"</details>"
    )
```

Also update the docstring-less function by adding a short docstring:

```python
    """Driver-form tower collapsed behind a <details> toggle.

    The returned block is embedded inside the candidates panel by
    render_candidates(), not emitted as a standalone section.
    """
```

- [ ] **Step 4: Run form tests to verify they pass**

Run: `python -m pytest tests/test_build_podigami.py -q -k render_form`
Expected: 3 passed (`test_render_form_builds_timing_tower`, `test_render_form_half_life_default_is_six`, `test_render_form_v2_caption_describes_ratings` — the latter two only assert on caption text, which is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/build/build_podigami_html.py tests/test_build_podigami.py
git commit -m "feat: render_form returns a collapsed <details> block"
```

---

### Task 2: `render_candidates()` embeds the form block; `main()` wiring

**Files:**
- Modify: `src/build/build_podigami_html.py:331-367` (`render_candidates`), `src/build/build_podigami_html.py:674-733` (`main`: call order + page layout)
- Test: `tests/test_build_podigami.py` (new test after `test_render_candidates_empty_is_blank`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_build_podigami.py` after `test_render_candidates_empty_is_blank`:

```python
def test_render_candidates_embeds_form_block_after_list():
    cands = [
        {
            "prob": 3.0,
            "names": ["Andrea Kimi Antonelli", "Lando Norris", "George Russell"],
            "perDriver": [
                pd("antonelli", "Andrea Kimi Antonelli", "mercedes"),
                pd("norris", "Lando Norris", "mclaren"),
                pd("russell", "George Russell", "mercedes"),
            ],
        }
    ]
    form_html = '<details class="form-details">FORM</details>'
    out = bp.render_candidates(cands, META, form_html)
    assert form_html in out
    assert out.index('class="cand-list"') < out.index(form_html)  # after the ranked list
    assert out.rstrip().endswith("</section>")  # inside the panel
    # default keeps the old signature working
    assert "form-details" not in bp.render_candidates(cands, META)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_podigami.py::test_render_candidates_embeds_form_block_after_list -q`
Expected: FAIL with `TypeError: render_candidates() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: Add the `form_html` parameter**

In `render_candidates`, change the signature and the returned block's tail:

```python
def render_candidates(cands: list[dict], meta: dict, form_html: str = "") -> str:
```

and change the `return` block's last lines from:

```python
        f'  <ol class="cand-list">{"".join(rows)}</ol>'
        f"</section>"
```

to:

```python
        f'  <ol class="cand-list">{"".join(rows)}</ol>'
        f"  {form_html}"
        f"</section>"
```

- [ ] **Step 4: Rewire `main()`**

In `main()`, the current lines:

```python
    acc_badge = render_accuracy_badge(model_eval)
    hero = render_hero(cands[0], chance, meta, acc_badge) if cands else ""
    candidates = render_candidates(cands, meta)
    form = render_form(
        data["driverForm"],
        using_constructors,
        meta,
        data["params"].get("halfLife", 6.0),
        is_v2=data["params"].get("model") == "dbpl-v2",
    )
```

become:

```python
    acc_badge = render_accuracy_badge(model_eval)
    hero = render_hero(cands[0], chance, meta, acc_badge) if cands else ""
    form = render_form(
        data["driverForm"],
        using_constructors,
        meta,
        data["params"].get("halfLife", 6.0),
        is_v2=data["params"].get("model") == "dbpl-v2",
    )
    candidates = render_candidates(cands, meta, form)
```

and in the page f-string, the section sequence:

```python
        {hero}
        {candidates}
        {hook_combos}
        {form}
        {hook_soulmates}
```

becomes:

```python
        {hero}
        {candidates}
        {hook_combos}
        {hook_soulmates}
```

Also update the module docstring's line 4 from
`a ranked list of contenders, the current-form grid, and a year-slider timeline`
to
`a ranked list of contenders (with a collapsible current-form tower), and a`
(next line continues `year-slider timeline of every trio that debuted in each season.`).

- [ ] **Step 5: Run the unit tests**

Run: `python -m pytest tests/test_build_podigami.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/build/build_podigami_html.py tests/test_build_podigami.py
git commit -m "feat: embed collapsed form tower inside the candidates panel"
```

---

### Task 3: Integration assertions on the built page

**Files:**
- Modify: `tests/test_build_output.py:196-204` (`test_landing_page_discovery_hooks_in_flow`)
- Test: same file (new `test_landing_page_form_is_collapsed_in_candidates_panel`)

- [ ] **Step 1: Update the ordering assertion and add the new test**

In `test_landing_page_discovery_hooks_in_flow`, replace:

```python
    assert html.index('class="form-tower"') < html.index('class="hook-card" href="soulmates.html"')
```

with:

```python
    assert html.index('class="form-tower"') < html.index('class="hook-card" href="combos.html"')
```

(the form tower now lives inside the candidates panel, which precedes the combos hook).

Then add after `test_landing_page_discovery_hooks_in_flow`:

```python
def test_landing_page_form_is_collapsed_in_candidates_panel(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    # no standalone "Current form" panel heading anymore
    assert "<h2>Current form" not in html
    # the tower sits in a collapsed <details> inside the candidates panel
    assert '<details class="form-details">' in html
    assert '<details class="form-details" open' not in html
    assert "Show current form" in html
    details = html[html.index('<details class="form-details">') :]
    assert details.index('class="form-tower"') < details.index("</details>")
    panel_start = html.index("Most likely next combinations")
    assert panel_start < html.index('<details class="form-details">')
```

- [ ] **Step 2: Run the build-output tests**

Run: `python -m pytest tests/test_build_output.py -q`
Expected: all pass (the session-scoped `dist` fixture rebuilds with the new layout).

- [ ] **Step 3: Commit**

```bash
git add tests/test_build_output.py
git commit -m "test: assert form tower is collapsed inside candidates panel"
```

---

### Task 4: CSS for the toggle

**Files:**
- Modify: `assets/podigami.css` (insert immediately before the `/* current form — broadcast timing tower */` comment at line ~905)

- [ ] **Step 1: Add the styles**

Insert before `/* current form — broadcast timing tower */`:

```css
/* current form — collapsed <details> inside the candidates panel */
.form-details {
    margin-top: 14px;
}

.form-details > summary {
    list-style: none;
    display: block;
    width: fit-content;
    margin: 0 auto;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 16px;
    border-radius: 999px;
    border: 1px solid var(--border-strong);
    background: var(--surface-2);
    color: var(--text-dim);
    cursor: pointer;
    user-select: none;
    transition: border-color 0.15s ease, color 0.15s ease;
}

.form-details > summary:hover {
    border-color: var(--accent);
    color: var(--text);
}

.form-details > summary::-webkit-details-marker {
    display: none;
}

.form-details .fd-open {
    display: none;
}

.form-details[open] .fd-open {
    display: inline;
}

.form-details[open] .fd-closed {
    display: none;
}

.form-caption {
    margin: 12px 0 10px;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--muted);
}
```

(All variables — `--border-strong`, `--surface-2`, `--text-dim`, `--accent`, `--text`, `--muted` — already exist in `assets/style.css` for both themes; the pill styling mirrors `.tl-chip`.)

- [ ] **Step 2: Rebuild and eyeball**

Run: `python src/build_site.py`
Then serve and check both states + mobile width:

```bash
python -m http.server 8000 -d dist
```

Verify at http://localhost:8000/: candidates panel shows the centered "Show current form ▾" pill; clicking it reveals the caption + tower and the label flips to "Hide current form ▴"; tower rows still render correctly at 600px width. (Playwright MCP against localhost is fine here.)

- [ ] **Step 3: Commit**

```bash
git add assets/podigami.css
git commit -m "style: pill summary + caption for the collapsed form tower"
```

---

### Task 5: Docs, full verification, ship

**Files:**
- Modify: `README.md:51`, `RELEASE_NOTES.md` (top)

- [ ] **Step 1: Update README page table**

In `README.md` line 51, change
`candidate rankings, current form tower, season debut timeline`
to
`candidate rankings (with a collapsible current-form tower), season debut timeline`.

- [ ] **Step 2: Add release note**

At the top of `RELEASE_NOTES.md`, under a `## 2026-07-10` heading (create if absent):

```markdown
### Improvements
- Landing page: the "Current form" tower now lives behind a "Show current form" toggle inside the "Most likely next combinations" panel, shortening the page (#PR)
```

(Replace `#PR` with the real PR number once known.)

- [ ] **Step 3: Full local gate (mirrors CI)**

```bash
python -m ruff check . && python -m ruff format --check . && python -m pytest -q
```

Expected: no lint/format violations, full suite passes.

- [ ] **Step 4: Commit and open the PR into `develop`**

```bash
git add README.md RELEASE_NOTES.md
git commit -m "docs: README + release notes for the form toggle"
git push -u origin feature/form-toggle
gh pr create --base develop --title "feat: collapse current-form tower into the candidates panel" --body "<PR-template body>"
```

PR body follows `.github/pull_request_template.md` (Summary / Changes / Testing / Checklist). After required checks pass, squash-merge and delete the branch.
