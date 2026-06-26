# Custom 404 Page — Design Spec

**Date:** 2026-06-26
**Issue:** [#88](https://github.com/NikoKiru/f1podigami/issues/88)

## Goal

Ship a branded `404.html` so mistyped or stale URLs don't dump users on GitHub Pages' generic error screen. The page must be consistent with the existing site chrome (favicon, nav, footer, theme toggle) and carry an F1-flavoured tone.

## Architecture

### New file

`src/build/build_404_html.py` — a standalone page builder following the same pattern as `build_overdue_html.py` and siblings:

- Sets up `ROOT` via `Path(__file__).resolve().parents[2]`
- Inserts `src/build/` and `src/` into `sys.path`
- Imports `head`, `nav`, `FOOTER` from `_layout`
- Writes to `ROOT / "dist" / "404.html"`

No data files are read — this page has no dynamic content.

### Changes to `src/build_site.py`

- `"build_404_html.py"` added to `PAGE_BUILDERS` (runs during every build)
- `PAGES` list **unchanged** — 404 stays out of the sitemap

### No new CSS file

Page-specific styles are inlined in a `<style>` block inside the HTML. The 404 page is a one-off that most users never see; adding `assets/404.css` to the asset copy loop is not worth it.

## Page Content

```
[nav — active page: none / no link highlighted]

  404
  DNF — this page retired from the race.
  [Back to the grid →]   → index.html

[footer]
```

The `404` heading is displayed large and centred. Below it: one line of F1-flavoured copy. Below that: a single CTA link styled as a button, linking to `index.html`.

### `head()` call

```python
head(
    "404 — Page Not Found | F1 Podigami",
    description="This page doesn't exist. Head back to F1 Podigami.",
    page_path="404.html",
)
```

No page-specific CSS file argument (only `style.css` is linked).

### `nav()` call

`nav("")` — passing an empty string so no nav link is marked active (the 404 page isn't in the nav).

## GitHub Pages behaviour

GitHub Pages automatically serves the top-level `404.html` for any unmatched path under the repository's Pages site. No additional config needed.

## Testing

- Existing `test_build_output.py` suite builds `dist/` via `build_site.py`; add an assertion that `dist/404.html` exists and contains the expected heading text and home link.
- `ruff check` + `ruff format --check` must pass on the new builder.
- Manual: run `python src/build_site.py` and open `dist/404.html` in a browser to verify chrome and link.
