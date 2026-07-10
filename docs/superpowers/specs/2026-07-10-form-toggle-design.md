# Collapse "Current form" into the candidates panel

**Date:** 2026-07-10
**Status:** Approved

## Goal

Shorten the landing page by removing the standalone "Current form" panel and
tucking the driver-form tower behind a "Show current form" toggle inside the
"Most likely next combinations" (candidates) panel, where it explains the
ranking it sits next to.

## Approach

Native `<details>`/`<summary>` — zero JavaScript, keyboard/screen-reader
accessible for free, and consistent with the site's existing collapsible
pattern (overdue panels, FAQ items). Collapsed by default.

## Changes

### `src/build/build_podigami_html.py`

- **`render_form()`** returns a `<details class="form-details">` block instead
  of a standalone `<section class="panel">`:
  - `<summary>` styled as a centered pill button. Pure-CSS label swap: two
    spans — "Show current form ▾" and "Hide current form ▴" — toggled by
    `details[open]`.
  - Expanded content: the model explanation (the text currently in the
    panel-heading info-tip) rendered as a small muted caption above the tower,
    then the existing form tower unchanged (number chip, TLA, surname, team,
    bar, weight). A hover info-tip inside a `<summary>` would fight the toggle
    click, hence the caption.
- **`render_candidates()`** accepts the form block and appends it after the
  `</ol>`, inside the same panel.
- **`main()`** no longer places `{form}` between the combos hook and the
  soulmates hook; the section order becomes: hero, candidates (with embedded
  form details), combos hook, soulmates hook, timeline, …

### `assets/podigami.css`

- New `.form-details` styles: default disclosure marker hidden, summary as a
  centered pill button (consistent with existing chip styling), open/closed
  label spans switched via `details[open]`.
- Existing `.form-tower` / `.tower-row` styles reused as-is, including the
  600px mobile rules.

### Tests

- `test_build_output.py` / `test_build_podigami.py`: assertions on the
  standalone "Current form" panel move to — the candidates panel contains the
  `<details>` + form tower; no standalone form section exists.

### Docs

- README landing-page description updated if it names the form section.
- RELEASE_NOTES entry under `## 2026-07-10`.

## Unchanged

- The FAQ item "What is 'current form' based on?" stays — the section still
  exists, just collapsed.
- `podigami.json` data flow and `render_form`'s inputs (driver form list,
  v1/v2 explanation variants) are untouched.
