# SEO keyword + structured-data pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add keyword-tuned page metadata and rich JSON-LD structured data (Organization, BreadcrumbList, FAQPage, Dataset, enriched SportsEvent) to the F1 Podigami static site, changing nothing a visitor sees.

**Architecture:** All changes live in the build stage (`src/build/`). Two small reusable JSON-LD helpers go in `_layout.py`; each page builder passes the appropriate schema list to the existing `head(json_ld=...)` parameter. The landing-page FAQ is refactored to a single source (`faq_items`) that feeds both the visible HTML and the FAQPage schema, guaranteeing parity.

**Tech Stack:** Python 3.11+, string-based HTML generation (no template engine), pytest, ruff. Structured data is `application/ld+json` embedded by `_layout.head()`.

## Global Constraints

- **Invisible only:** no change to any rendered `<body>` content — headings, taglines, copy, layout. Only `<head>` output changes. (Titles/descriptions live in `<head>` and are fair game.)
- **Schema/content parity:** every schema is generated from data already committed and already rendered; FAQPage answers derive from the same `faq_items` source as the visible FAQ.
- **Deterministic build:** same inputs → byte-identical HTML.
- **No `<meta name="keywords">`:** it stays absent (a test already forbids it).
- **Path resolution:** use existing `SITE_URL`, `REPO_URL` from `build/_layout.py`; no hardcoded absolute paths.
- **HTML safety:** any data interpolated into HTML uses the existing `esc()`/`html.escape` pattern; JSON-LD is emitted via `head()`'s existing `json.dumps(...).replace("</","<\\/")` path.
- **Lint/format gate:** `ruff check .` and `ruff format --check .` must pass.
- Titles ≤ ~60 chars, descriptions ≤ ~155 chars, primary keyword front-loaded, truthful.

---

## File structure

- `src/build/_layout.py` — add `organization_schema()` and `breadcrumb_schema(label, page_path)`. No change to `head()` signature.
- `src/build/build_podigami_html.py` — new title/description; extract `faq_items(...)`; extend `json_ld_schemas(...)` to add Organization + FAQPage + SportsEvent enrichment.
- `src/build/build_combos_html.py` — new title/description; add `dataset_schema(...)`; pass Organization + BreadcrumbList + Dataset.
- `src/build/build_overdue_html.py`, `build_unlikeliest.py`, `build_soulmates_html.py` — new title/description; pass Organization + BreadcrumbList.
- `tests/test_layout.py` — unit tests for the two helpers.
- `tests/test_build_podigami.py` — `faq_items` parity test.
- `tests/test_build_output.py` — per-page schema assertions.
- `RELEASE_NOTES.md`, `README.md` — docs.

**Breadcrumb scope decision:** BreadcrumbList is emitted on the four sub-pages only (`Home › <Page>`). The homepage gets Organization + WebSite + FAQPage + SportsEvent but **no** breadcrumb — a single-item "Home" breadcrumb carries no information and can trigger a Google validation warning. This is the one intentional deviation from the spec's "every page" wording.

---

## Task 1: Shared JSON-LD helpers in `_layout.py`

**Files:**
- Modify: `src/build/_layout.py` (add two functions after `wiki_url`/near the top-level helpers, before `head`)
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `SITE_URL` (already defined in `_layout.py`).
- Produces:
  - `organization_schema() -> dict` — a schema.org Organization object.
  - `breadcrumb_schema(label: str, page_path: str) -> dict` — a schema.org BreadcrumbList. `page_path` like `"combos.html"`; a falsy/`"index.html"` path yields a single Home item.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_layout.py`:

```python
def test_organization_schema_shape():
    from build._layout import organization_schema, SITE_URL

    org = organization_schema()
    assert org["@context"] == "https://schema.org"
    assert org["@type"] == "Organization"
    assert org["name"] == "F1 Podigami"
    assert org["url"] == f"{SITE_URL}/"
    assert org["logo"] == f"{SITE_URL}/apple-touch-icon.png"


def test_breadcrumb_schema_subpage():
    from build._layout import breadcrumb_schema, SITE_URL

    bc = breadcrumb_schema("Podium Combinations", "combos.html")
    assert bc["@type"] == "BreadcrumbList"
    items = bc["itemListElement"]
    assert [i["position"] for i in items] == [1, 2]
    assert items[0]["name"] == "Home"
    assert items[0]["item"] == f"{SITE_URL}/"
    assert items[1]["name"] == "Podium Combinations"
    assert items[1]["item"] == f"{SITE_URL}/combos.html"


def test_breadcrumb_schema_homepage_is_single_item():
    from build._layout import breadcrumb_schema, SITE_URL

    bc = breadcrumb_schema("Home", "index.html")
    items = bc["itemListElement"]
    assert len(items) == 1
    assert items[0]["item"] == f"{SITE_URL}/"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_layout.py -k "organization_schema or breadcrumb_schema" -v`
Expected: FAIL — `ImportError: cannot import name 'organization_schema'`.

- [ ] **Step 3: Implement the helpers**

In `src/build/_layout.py`, add after the `wiki_url` function (both are simple pure helpers; keep them above `head`):

```python
def organization_schema() -> dict:
    """schema.org Organization for the site (stable entity + logo for search)."""
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "F1 Podigami",
        "url": f"{SITE_URL}/",
        "logo": f"{SITE_URL}/apple-touch-icon.png",
    }


def breadcrumb_schema(label: str, page_path: str) -> dict:
    """schema.org BreadcrumbList: ``Home`` then, for a sub-page, this page.

    A homepage/empty ``page_path`` yields a single ``Home`` item.
    """
    items = [{"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"}]
    if page_path and page_path != "index.html":
        items.append(
            {
                "@type": "ListItem",
                "position": 2,
                "name": label,
                "item": f"{SITE_URL}/{page_path}",
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_layout.py -k "organization_schema or breadcrumb_schema" -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/build/_layout.py tests/test_layout.py
git commit -m "feat: add Organization + BreadcrumbList JSON-LD helpers"
```

---

## Task 2: Keyword-tuned titles & descriptions (all pages)

**Files:**
- Modify: `src/build/build_podigami_html.py` (the `head(...)` title + `meta_description`, ~lines 771–782)
- Modify: `src/build/build_combos_html.py:118-120`
- Modify: `src/build/build_overdue_html.py:153-156`
- Modify: `src/build/build_unlikeliest.py:155-158`
- Modify: `src/build/build_soulmates_html.py:212-215`
- Test: `tests/test_build_output.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no code interface; changes `<title>` / `<meta name="description">` text.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_build_output.py` (near the other head tests):

```python
# page -> a keyword phrase its <title> must front-load
TITLE_KEYWORDS = {
    "index.html": "F1 Podium Scorigami",
    "combos.html": "F1 Podium Combination",
    "overdue.html": "F1 Overdue Podiums",
    "unlikeliest.html": "F1 Unlikeliest Podiums",
    "soulmates.html": "F1 Podium Partnerships",
}


@pytest.mark.parametrize("page,keyword", TITLE_KEYWORDS.items())
def test_title_front_loads_keyword(dist, page, keyword):
    html = (dist / page).read_text(encoding="utf-8")
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    assert m, f"{page} has no <title>"
    title = m.group(1)
    assert keyword in title, f"{page} title missing keyword {keyword!r}: {title!r}"
    assert len(title) <= 65, f"{page} title too long ({len(title)}): {title!r}"


@pytest.mark.parametrize("page", ["index.html", "combos.html"])
def test_description_within_budget(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    m = re.search(r'<meta name="description" content="(.*?)">', html, re.DOTALL)
    assert m, f"{page} has no meta description"
    assert len(m.group(1)) <= 160, f"{page} description too long: {len(m.group(1))}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_build_output.py -k "title_front_loads or description_within" -v`
Expected: FAIL — current titles don't contain the new keyword phrases (e.g. index title is `F1 Podigami - Next Likely New Podium (2026)`).

- [ ] **Step 3: Apply the new titles & descriptions**

`build_podigami_html.py` — replace the `meta_description` block and the `head(...)` title (~lines 771–777):

```python
    meta_description = (
        f"F1 podium scorigami: tracking the podium trios Formula 1 has never seen. "
        f"A model predicts the most likely brand-new trio for the next {season} race."
    )
    page = f"""{
        head(
            f"F1 Podium Scorigami — New Trio Tracker & Predictions",
            "podigami.css",
```
(Leave the rest of the `head(...)` call — `description=`, `page_path=`, `json_ld=` — unchanged.)

`build_combos_html.py:118-120` — replace title + description:

```python
            f"Every F1 Podium Combination, {season_min}–{season_max} — Podium History",
            "index.css",
            description=f"Every unique F1 podium combination in history: all {unique_combos:,} driver trios that have shared a Formula 1 podium since {season_min}, across {total_podiums:,} races.",
```

`build_overdue_html.py` — replace title + description:

```python
            "F1 Overdue Podiums — Trios That Should Have Happened",
            "podigami.css",
            description="F1 podium history's missing trios: drivers who raced together dozens of times, each a regular podium finisher, yet never all three on the rostrum at once.",
```

`build_unlikeliest.py` — replace title + description:

```python
            "F1 Unlikeliest Podiums — Most Improbable Trios Ever",
            "podigami.css",
            description="The most statistically improbable podiums in F1 history: trios of drivers who rarely podiumed, yet once all three shared the rostrum against the odds.",
```

`build_soulmates_html.py` — replace title + description:

```python
            "F1 Podium Partnerships — Drivers Who Shared the Rostrum",
            "soulmates.css",
            description="F1 podium history by partnership: which drivers spent the most race weekends together on the rostrum across 76 years of Formula 1.",
```

- [ ] **Step 4: Rebuild and run tests**

Run: `python src/build_site.py && PYTHONPATH=src python -m pytest tests/test_build_output.py -k "title_front_loads or description_within" -v`
Expected: all PASS. Verify each title's length printed is ≤65.

- [ ] **Step 5: Commit**

```bash
git add src/build/build_*.py tests/test_build_output.py
git commit -m "feat: keyword-tune page titles and meta descriptions for SEO"
```

---

## Task 3: Wire Organization + BreadcrumbList into every builder

**Files:**
- Modify: `src/build/build_combos_html.py` (import helpers; add `json_ld=` to `head`)
- Modify: `src/build/build_overdue_html.py`
- Modify: `src/build/build_unlikeliest.py`
- Modify: `src/build/build_soulmates_html.py`
- Modify: `src/build/build_podigami_html.py` (`json_ld_schemas` prepends Organization)
- Test: `tests/test_build_output.py`

**Interfaces:**
- Consumes: `organization_schema`, `breadcrumb_schema` (Task 1).
- Produces: every indexable page emits an Organization block; sub-pages additionally emit a BreadcrumbList.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_build_output.py`:

```python
@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_has_organization_schema(dist, page):
    html = (dist / page).read_text(encoding="utf-8")
    orgs = [b for b in _json_ld_blocks(html) if b.get("@type") == "Organization"]
    assert len(orgs) == 1, f"{page} should carry exactly one Organization schema"
    assert orgs[0]["name"] == "F1 Podigami"
    assert orgs[0]["logo"].endswith("apple-touch-icon.png")


SUBPAGE_BREADCRUMB = {
    "combos.html": "Podium Combinations",
    "overdue.html": "Overdue Podiums",
    "unlikeliest.html": "Unlikeliest Podiums",
    "soulmates.html": "Podium Partnerships",
}


@pytest.mark.parametrize("page,label", SUBPAGE_BREADCRUMB.items())
def test_subpages_have_breadcrumb(dist, page, label):
    html = (dist / page).read_text(encoding="utf-8")
    crumbs = [b for b in _json_ld_blocks(html) if b.get("@type") == "BreadcrumbList"]
    assert len(crumbs) == 1, f"{page} should carry one BreadcrumbList"
    items = crumbs[0]["itemListElement"]
    assert items[0]["name"] == "Home"
    assert items[-1]["name"] == label
    assert items[-1]["item"] == f"{SITE_URL}/{page}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_build_output.py -k "organization_schema or subpages_have_breadcrumb" -v`
Expected: FAIL — sub-pages currently pass no `json_ld`, so no Organization/BreadcrumbList blocks exist.

- [ ] **Step 3a: Add Organization to the landing page**

In `build_podigami_html.py`, `json_ld_schemas` currently starts its list with the WebSite object. Import the helper and prepend Organization. At the top of the file, the builder already imports from `_layout` (find the existing `from _layout import ...` line and add the names). Then change the `schemas` list initialiser:

```python
    schemas: list[dict] = [
        organization_schema(),
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "F1 Podigami",
            "url": f"{SITE_URL}/",
            "description": description,
        },
    ]
```

Add `organization_schema` (and, for Task 5, `breadcrumb_schema` is not needed on the homepage) to the `_layout` import list in this file.

- [ ] **Step 3b: Wire the four sub-pages**

For each sub-page builder, ensure its `_layout` import includes `organization_schema, breadcrumb_schema`, then add a `json_ld=[...]` argument to its `head(...)` call. The label is the second column of `SUBPAGE_BREADCRUMB`.

`build_combos_html.py` `head(...)` — add as the final argument (Task 5 will extend this list with the Dataset):

```python
            page_path="combos.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Podium Combinations", "combos.html"),
            ],
```

`build_overdue_html.py`:

```python
            page_path="overdue.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Overdue Podiums", "overdue.html"),
            ],
```

`build_unlikeliest.py`:

```python
            page_path="unlikeliest.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Unlikeliest Podiums", "unlikeliest.html"),
            ],
```

`build_soulmates_html.py`:

```python
            page_path="soulmates.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Podium Partnerships", "soulmates.html"),
            ],
```

For each file, confirm the import line, e.g.:
```python
from _layout import FOOTER, breadcrumb_schema, head, nav, organization_schema  # plus existing names
```
(Keep whatever names each file already imports; just add the two helpers. Preserve ruff's alphabetical import order.)

- [ ] **Step 4: Rebuild and run tests**

Run: `python src/build_site.py && PYTHONPATH=src python -m pytest tests/test_build_output.py -k "organization_schema or subpages_have_breadcrumb or json_ld_website" -v`
Expected: all PASS (including the existing `test_index_json_ld_website`, proving Organization didn't displace WebSite).

- [ ] **Step 5: Commit**

```bash
git add src/build/build_*.py tests/test_build_output.py
git commit -m "feat: emit Organization + BreadcrumbList structured data on every page"
```

---

## Task 4: FAQ single-source refactor + FAQPage schema (landing)

**Files:**
- Modify: `src/build/build_podigami_html.py` (extract `faq_items`; `render_faq` uses it; `json_ld_schemas` gains a `faq` param; `main` passes it)
- Test: `tests/test_build_podigami.py`, `tests/test_build_output.py`

**Interfaces:**
- Consumes: existing FAQ inputs.
- Produces:
  - `faq_items(data: dict, ev: dict, total_combos: int, total_races: int, possible_trios: int, grid_size: int, lo: int) -> list[tuple[str, str]]` — ordered (question, answer-HTML) pairs, including the post-quali insert.
  - `json_ld_schemas(schedule, asof, description, faq)` — now takes the `faq` pairs and appends a FAQPage.
  - `render_faq(...)` — unchanged signature and output.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_build_podigami.py`:

```python
def test_faq_items_matches_rendered_faq():
    import build.build_podigami_html as bp

    pairs = bp.faq_items({}, bp.EVAL if hasattr(bp, "EVAL") else {}, 123, 456, 789, 20, 1950)
    html = bp.render_faq({}, {}, 123, 456, 789, 20, 1950)
    # Every question produced by faq_items is rendered verbatim as a <summary>.
    pairs = bp.faq_items({}, {}, 123, 456, 789, 20, 1950)
    for q, _a in pairs:
        assert f'<summary class="faq-q">{q}</summary>' in html
    assert len(pairs) >= 5
```

Add to `tests/test_build_output.py`:

```python
def test_index_faqpage_schema_matches_visible_faq(dist):
    html = (dist / "index.html").read_text(encoding="utf-8")
    faqs = [b for b in _json_ld_blocks(html) if b.get("@type") == "FAQPage"]
    assert len(faqs) == 1, "index.html should carry exactly one FAQPage schema"
    q_entities = faqs[0]["mainEntity"]
    assert len(q_entities) >= 5
    for qe in q_entities:
        assert qe["@type"] == "Question"
        assert qe["name"]  # question text
        assert qe["acceptedAnswer"]["@type"] == "Answer"
        assert qe["acceptedAnswer"]["text"]
        # schema answer is plain text (no HTML tags leaked in)
        assert "<" not in qe["acceptedAnswer"]["text"]
    # Parity: each schema question is a visible FAQ <summary> on the page.
    for qe in q_entities:
        assert f'<summary class="faq-q">{qe["name"]}</summary>' in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_build_podigami.py -k faq_items tests/test_build_output.py -k faqpage -v`
Expected: FAIL — `faq_items` doesn't exist; no FAQPage schema on the page.

- [ ] **Step 3a: Extract `faq_items` and have `render_faq` use it**

In `build_podigami_html.py`, move the body of `render_faq` that builds `items` (including the `is_v2` `how_it_works` branch and the post-quali `items.insert(2, ...)`) into a new pure function `faq_items(...)` with the same parameter list as `render_faq`. `faq_items` returns the final `items` list. Then `render_faq` becomes:

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
    items = faq_items(data, ev, total_combos, total_races, possible_trios, grid_size, lo)
    entries = []
    for q, a in items:
        entries.append(
            f'<details class="faq-item">'
            f'<summary class="faq-q">{q}</summary>'
            f'<div class="faq-a"><p>{a}</p></div>'
            f"</details>"
        )
    return (
        f'<section class="panel faq-section">'
        f"  <h2>Frequently asked questions</h2>"
        f"  {''.join(entries)}"
        f"</section>"
    )
```

`faq_items` holds everything from `mp = ev.get("modelParams", {})` through the `items.insert(2, ...)` block, ending `return items`. (Cut-and-paste; the logic is unchanged, so existing `render_faq` tests keep passing.)

- [ ] **Step 3b: Add a plain-text helper and FAQPage to `json_ld_schemas`**

Add near the top of `build_podigami_html.py` (it already imports `html` and `re`; if not, add `import re`):

```python
def _plain(text: str) -> str:
    """Strip HTML tags and unescape entities → plain text for JSON-LD answers."""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
```

Change `json_ld_schemas` to accept the FAQ pairs and append a FAQPage:

```python
def json_ld_schemas(
    schedule: dict,
    asof: dict | None,
    description: str,
    faq: list[tuple[str, str]] | None = None,
) -> list[dict]:
    schemas: list[dict] = [
        organization_schema(),
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "F1 Podigami",
            "url": f"{SITE_URL}/",
            "description": description,
        },
    ]
    if faq:
        schemas.append(
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": _plain(q),
                        "acceptedAnswer": {"@type": "Answer", "text": _plain(a)},
                    }
                    for q, a in faq
                ],
            }
        )
    # ... existing SportsEvent block unchanged ...
    return schemas
```
(Keep the existing `nxt = pick_next_race(...)` SportsEvent append exactly as-is, after the FAQPage block.)

- [ ] **Step 3c: Pass the FAQ pairs from `main`**

In `main()`, the FAQ is already computed for HTML at ~line 758:
```python
    faq = render_faq(data, model_eval, total_combos, total_races, possible_trios, grid_size, lo)
```
Add, right before it, the pairs and pass them to the schema call:
```python
    faq_pairs = faq_items(data, model_eval, total_combos, total_races, possible_trios, grid_size, lo)
    faq = render_faq(data, model_eval, total_combos, total_races, possible_trios, grid_size, lo)
```
and update the `head(json_ld=...)` argument (~line 781):
```python
            json_ld=json_ld_schemas(schedule, data.get("asOf"), meta_description, faq_pairs),
```

- [ ] **Step 4: Rebuild and run tests**

Run: `python src/build_site.py && PYTHONPATH=src python -m pytest tests/test_build_podigami.py tests/test_build_output.py -v`
Expected: all PASS — the `faq_items` parity test, the FAQPage schema test, and every pre-existing `render_faq` test.

- [ ] **Step 5: Commit**

```bash
git add src/build/build_podigami_html.py tests/test_build_podigami.py tests/test_build_output.py
git commit -m "feat: emit FAQPage structured data from a single FAQ source"
```

---

## Task 5: Dataset schema on combos + SportsEvent enrichment

**Files:**
- Modify: `src/build/build_combos_html.py` (add `dataset_schema(...)`; append it to the `json_ld` list)
- Modify: `src/build/build_podigami_html.py` (enrich the SportsEvent object)
- Test: `tests/test_build_output.py`

**Interfaces:**
- Consumes: `organization_schema` (Task 1), `SITE_URL`, `REPO_URL` (`_layout`).
- Produces: combos page carries a Dataset schema; landing SportsEvent carries `sport`, `url`, `eventStatus`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_build_output.py`:

```python
def test_combos_dataset_schema(dist):
    html = (dist / "combos.html").read_text(encoding="utf-8")
    datasets = [b for b in _json_ld_blocks(html) if b.get("@type") == "Dataset"]
    assert len(datasets) == 1, "combos.html should carry exactly one Dataset schema"
    ds = datasets[0]
    assert "podium combination" in ds["name"].lower()
    assert ds["url"] == f"{SITE_URL}/combos.html"
    assert ds["creator"]["@type"] == "Organization"
    assert ds["license"]
    assert "/" in ds["temporalCoverage"]  # e.g. "1950/2026"
    assert isinstance(ds["keywords"], list) and ds["keywords"]


def test_index_sportsevent_enriched(dist, data):
    from build.build_podigami_html import pick_next_race

    html = (dist / "index.html").read_text(encoding="utf-8")
    nxt = pick_next_race(data["schedule"], data["podigami"].get("asOf"))
    events = [b for b in _json_ld_blocks(html) if b.get("@type") == "SportsEvent"]
    if nxt is None:
        assert events == []
        return
    ev = events[0]
    assert ev["sport"] == "Formula 1"
    assert ev["eventStatus"] == "https://schema.org/EventScheduled"
    assert ev["url"] == f"{SITE_URL}/"
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_build_output.py -k "combos_dataset or sportsevent_enriched" -v`
Expected: FAIL — no Dataset block; SportsEvent lacks `sport`/`eventStatus`/`url`.

- [ ] **Step 3a: Dataset on combos**

In `build_combos_html.py`, add a helper (near the top, after imports) and append it to the `head(json_ld=[...])` list from Task 3. Ensure `REPO_URL` is imported from `_layout`.

```python
def dataset_schema(season_min: int, season_max: int, unique_combos: int, total_podiums: int) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"Every unique F1 podium combination, {season_min}–{season_max}",
        "description": (
            f"All {unique_combos:,} unique three-driver podium combinations in Formula 1 "
            f"World Championship history, derived from {total_podiums:,} race results "
            f"since {season_min}."
        ),
        "url": f"{SITE_URL}/combos.html",
        "creator": organization_schema(),
        "license": REPO_URL,
        "temporalCoverage": f"{season_min}/{season_max}",
        "keywords": [
            "F1 podium combinations",
            "F1 podium history",
            "podium scorigami",
            "Formula 1 statistics",
        ],
    }
```

Update the `head(...)` `json_ld` list (from Task 3) to append the dataset:

```python
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Podium Combinations", "combos.html"),
                dataset_schema(season_min, season_max, unique_combos, total_podiums),
            ],
```

- [ ] **Step 3b: Enrich SportsEvent on landing**

In `build_podigami_html.py` `json_ld_schemas`, the `schemas.append({... "@type": "SportsEvent" ...})` object gains three keys:

```python
        schemas.append(
            {
                "@context": "https://schema.org",
                "@type": "SportsEvent",
                "name": nxt["raceName"],
                "sport": "Formula 1",
                "url": f"{SITE_URL}/",
                "eventStatus": "https://schema.org/EventScheduled",
                "startDate": _iso_datetime(nxt),
                "location": {
                    "@type": "Place",
                    "name": nxt["circuitName"],
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": nxt["locality"],
                        "addressCountry": nxt["country"],
                    },
                },
            }
        )
```

- [ ] **Step 4: Rebuild and run tests**

Run: `python src/build_site.py && PYTHONPATH=src python -m pytest tests/test_build_output.py -k "combos_dataset or sportsevent" -v`
Expected: all PASS (including the existing `test_index_json_ld_next_race_event`).

- [ ] **Step 5: Commit**

```bash
git add src/build/build_combos_html.py src/build/build_podigami_html.py tests/test_build_output.py
git commit -m "feat: add Dataset schema on combos and enrich next-race SportsEvent"
```

---

## Task 6: Docs + full verification gate

**Files:**
- Modify: `RELEASE_NOTES.md`
- Modify: `README.md` (only if it enumerates SEO/structured-data behaviour — verify)

**Interfaces:** none.

- [ ] **Step 1: Add a RELEASE_NOTES entry**

Under a `## 2026-07-22` heading (create if absent), `### Improvements`:

```markdown
- SEO: keyword-tuned page titles/descriptions and added FAQPage, Dataset, BreadcrumbList, and Organization structured data across the site (#<PR>)
```

- [ ] **Step 2: Check README**

Run: `grep -in "structured data\|json-ld\|schema\|open graph\|seo\|sitemap" README.md`
If a section enumerates structured-data types or SEO behaviour, update it to mention Organization/BreadcrumbList/FAQPage/Dataset. If README does not describe this (likely), make no change and note that in the PR.

- [ ] **Step 3: Full CI-mirroring gate**

Run each and confirm green:
```bash
python -m ruff check .
python -m ruff format --check .
PYTHONPATH=src python -m datalib.validate
python -m pytest -q
```
Expected: ruff clean, format clean, validate reports all datasets valid, full suite passes.

- [ ] **Step 4: Manual structured-data spot check (optional but recommended)**

Serve `dist/` (or open the built files) and paste `index.html` and `combos.html` into Google's Rich Results Test / Schema Markup Validator to confirm FAQPage and Dataset are recognised with no errors.

- [ ] **Step 5: Commit**

```bash
git add RELEASE_NOTES.md README.md
git commit -m "docs: release notes for SEO structured-data pass"
```

---

## Self-review

**Spec coverage:**
- Keyword titles/descriptions → Task 2. ✓
- Organization sitewide → Tasks 1, 3. ✓
- BreadcrumbList → Tasks 1, 3 (sub-pages; homepage deviation documented). ✓
- FAQPage from single source → Task 4. ✓
- Dataset on combos → Task 5. ✓
- SportsEvent enrichment → Task 5. ✓
- og:image:alt / OG-Twitter description keyword tuning → the description change in Task 2 flows into `og:description`/`twitter:description` automatically via `head()`; `og:image:alt` is already keyworded ("Formula 1 podium scorigami tracker") and unchanged — acceptable, no separate task needed.
- Skip `<meta name="keywords">` → already enforced by `test_no_dead_keywords_meta`; no task needed. ✓
- Sitemap lastmod → already implemented; out of scope. ✓
- Tests → each task is TDD. ✓
- RELEASE_NOTES / README → Task 6. ✓

**Placeholder scan:** no TBD/TODO; every code step shows full code; `<PR>` in the release note is a genuine at-merge value, not a code placeholder.

**Type consistency:** `organization_schema()`/`breadcrumb_schema(label, page_path)` used with matching signatures in Tasks 3/5; `faq_items(...)` parameter list matches `render_faq`'s and its use in `main` and `json_ld_schemas`; `json_ld_schemas(schedule, asof, description, faq)` call in `main` matches the new signature.
