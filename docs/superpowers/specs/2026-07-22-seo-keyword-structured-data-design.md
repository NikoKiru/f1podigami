# SEO keyword + structured-data pass

**Date:** 2026-07-22
**Status:** Approved (design)
**Scope:** Meta and structured-data only. No visible page copy, headings, or layout changes.

## Goal

Maximise organic discoverability of the F1 Podigami site by tuning invisible SEO
signals — page titles, meta descriptions, and JSON-LD structured data — around the
search intents the site can actually rank for. "Podigami" is a coined word with no
search volume, so traffic must come from head terms real users type.

**Primary keyword targets** (chosen by the user):
- **Scorigami niche** — "F1 podium scorigami", "podium scorigami", "F1 firsts".
- **Podium history / statistics** — "F1 podium history", "F1 podium combinations",
  "F1 podium statistics", "every F1 podium".

Secondary (kept where naturally true, not forced): predictions, driver partnerships.

## Constraints

- **Invisible only.** Nothing a visitor reads on the rendered page changes — no H1,
  tagline, intro, or body-copy edits. Only `<head>` content changes.
- **No stale data.** Every schema is generated from data already committed and already
  rendered on the page, so structured data can never drift from visible content
  (a Google structured-data policy requirement).
- **Deterministic build preserved.** Same inputs → same HTML, per project convention.
- **Honesty.** Descriptions must remain truthful; no keyword stuffing.

## Current state (baseline — already good)

`src/build/_layout.py` `head()` already emits: `<title>`, `<meta name="description">`,
canonical, full Open Graph set, Twitter summary-large-image card, `theme-color`,
`google-site-verification`, and an optional `json_ld` list. Only the landing page
passes `json_ld` today: a `WebSite` schema plus a `SportsEvent` for the next race.
`sitemap.xml` already carries `<lastmod>`; `robots.txt` is present. So this pass fills
gaps, it does not build from zero.

## Changes

### 1. Keyword-tuned titles & descriptions

Rewrite the `title` / `description` arguments in each page's `head(...)` call.
Titles ≤ ~60 chars, primary keyword front-loaded, brand implied by wording; descriptions
≤ ~155 chars, truthful, seeded with a primary keyword.

| Page | New title |
|------|-----------|
| `index.html` | `F1 Podium Scorigami — New Trio Tracker & Predictions` |
| `combos.html` | `Every F1 Podium Combination, {min}–{max} — Podium History` |
| `overdue.html` | `F1 Overdue Podiums — Trios That Should Have Happened` |
| `unlikeliest.html` | `F1 Unlikeliest Podiums — Most Improbable Trios Ever` |
| `soulmates.html` | `F1 Podium Partnerships — Drivers Who Shared the Rostrum` |

`404.html` title/description unchanged (noindex).

Descriptions: light rewrite of the existing strings to lead with a target keyword
("F1 podium scorigami …", "Every F1 podium combination in history …", etc.) while
preserving their factual content and dynamic counts. Exact wording finalised during
implementation; the constraint is truthful + keyword-front-loaded + ≤155 chars.

### 2. New structured data (JSON-LD)

`head()` already accepts `json_ld: list[dict]`. Extend usage so **every indexable page**
passes an appropriate list.

- **Organization (sitewide).** Add an `Organization` object (name `F1 Podigami`, `url`,
  `logo` → the site favicon/apple-touch-icon asset) to every page's schema list. Gives
  Google a stable entity + logo.
- **BreadcrumbList (every page).** `Home › <Page>` two-item breadcrumb per page, using
  each page's canonical URL. A small shared helper builds it from `(label, page_path)`.
- **FAQPage (landing page).** The landing page already renders a real FAQ
  (`render_faq`). Refactor so the FAQ Q&A pairs come from a single source that feeds
  **both** the visible HTML and a `FAQPage` schema — guaranteeing parity (policy
  requirement). Rich-result eligible.
- **Dataset (combos page).** Emit a `Dataset` schema: name "Every unique F1 podium
  combination, {min}–{max}", `description`, `creator` (the Organization), `license`
  (link to repo / data licence), `temporalCoverage` `"{min}/{max}"`, `keywords`
  (podium scorigami, F1 podium history, …), `url` (canonical). Eligible for Google
  Dataset Search and reinforces topical authority.
- **SportsEvent enrichment (landing page).** Add `sport: "Formula 1"`, `url` (canonical
  homepage), and `eventStatus: "https://schema.org/EventScheduled"` to the existing
  next-race `SportsEvent`.

Keep the existing `WebSite` schema.

### 3. Small meta touch-ups
- Tune `og:image:alt` and the OG/Twitter description wording to carry a primary keyword,
  consistent with the new `<meta name="description">`.
- **Deliberately NOT added:** `<meta name="keywords">` — ignored by Google, reads as
  spam. Keywords live in title/description/schema instead.
- Sitemap `<lastmod>`: already implemented (`_last_race_date()`), no change.

## Architecture / where changes live

- `src/build/_layout.py` — no signature change to `head()` (already supports everything
  needed). Add small shared JSON-LD helpers here (e.g. `breadcrumb_schema(label,
  page_path)`, `organization_schema()`) so every builder can reuse them and the
  Organization/Breadcrumb shape stays identical across pages.
- `src/build/build_podigami_html.py` — extend `json_ld_schemas()` to add Organization,
  BreadcrumbList, FAQPage, and SportsEvent enrichment; refactor FAQ to a shared source.
- `src/build/build_combos_html.py` — pass Dataset + Organization + BreadcrumbList; new
  title/description.
- `src/build/build_overdue_html.py`, `build_unlikeliest.py`, `build_soulmates_html.py` —
  pass Organization + BreadcrumbList; new title/description.
- `src/build_site.py` — no change (sitemap already fine).

## FAQ single-source refactor (the one non-trivial unit)

Today `render_faq(...)` returns HTML. To keep schema/visible parity without duplicating
copy, introduce a `faq_items(...) -> list[tuple[str, str]]` (question, plain-text answer)
that `render_faq` renders to HTML and `json_ld_schemas` renders to `FAQPage`. Answers in
the schema are plain text (HTML stripped/escaped). One source, two consumers — a unit
with one clear job, testable independently.

## Testing

- `test_build_output.py`: update any assertions pinning exact old titles; add assertions
  that: each page emits an `Organization` + `BreadcrumbList` JSON-LD block; the landing
  page emits a `FAQPage`; combos emits a `Dataset`. Validate each `application/ld+json`
  block parses as JSON and has the expected `@type`.
- New/extended unit test for `faq_items` parity: every visible FAQ question appears in
  the `FAQPage` schema and vice-versa.
- Full gate before shipping: `ruff check .`, `ruff format --check .`,
  `PYTHONPATH=src python -m datalib.validate`, `pytest -q`.
- Optional manual: paste built `index.html` / `combos.html` into Google's Rich Results
  Test to confirm FAQ + Dataset eligibility.

## Out of scope

- Any visible page content, headings, taglines, or layout.
- New pages, new datasets, or data-model changes.
- Twitter `site`/`creator` handles (no account).
- `robots.txt` / sitemap structural changes.

## Success criteria

- All five indexable pages carry Organization + BreadcrumbList structured data; landing
  has FAQPage; combos has Dataset — all valid JSON-LD, all matching visible content.
- Titles/descriptions front-load scorigami + podium-history keywords, truthful, within
  length budgets.
- Zero visible rendered-page change (diff of body content is empty).
- Green CI (lint, format, validate, tests).

## Release notes / README

- `RELEASE_NOTES.md`: add an entry under `### Improvements` (SEO: keyword-tuned metadata
  + FAQPage/Dataset/BreadcrumbList/Organization structured data).
- `README.md`: update if it enumerates structured-data / SEO behaviour (verify during
  implementation).
