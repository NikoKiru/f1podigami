# Landing page: trim hero to a slogan, move explanation into FAQ

## Problem

The landing page header (`src/build/build_podigami_html.py`) opens with a dense
explanatory paragraph (scorigami etymology + trio/race counts + grid-size math)
before the reader ever sees the prediction. It also frames the low count of
seen trios ("Only N unique combinations...") as if it were surprising, when a
20-driver grid producing this many possible trios makes that expected, not
noteworthy.

## Changes

1. **Hero (`<header>` tagline, ~line 588-594)**: replace the paragraph with a
   short slogan. No stats, no etymology in the hero.

2. **FAQ (`render_faq`, ~line 484-488)**: rewrite the "Why haven't most trios
   happened yet?" entry into a "What is podigami?" explainer. It keeps the
   scorigami etymology and the trio/race/grid-size numbers, stated as neutral
   background rather than "most trios are still waiting to happen."

3. **Meta description (`head()` call, ~line 574-578)**: drop the "Only N
   unique trios..." framing for consistency; keep the concept + prediction
   line, drop the raw counts.

## Out of scope

- No changes to `combos.html`, `overdue.html`, `soulmates.html`.
- No changes to the prediction model or data.
- No test assertions currently pin this copy (checked `tests/`), so no test
  updates are required beyond running the existing suite.

## Verification

- `python -m ruff check .` / `ruff format --check .`
- `python -m pytest -q`
- Visual check of the rendered `dist/index.html` header + FAQ section.
