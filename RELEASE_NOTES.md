# Release Notes

## 2026-09-10

### Improvements
- **A data update that changes a podium the site already published now raises an alert.** Jolpica can edit a settled race after the fact: the 2026 Monaco GP's third place went Hadjar → Gasly → Hadjar in its data, and both edits merged in routine automated updates, so for 82 days the site listed Antonelli / Hamilton / Gasly as a new trio that never officially happened. Each automated refresh now compares every published podium with the new data; a change retitles the data PR, labels it `podium-revised` and opens an issue showing the before/after trio and both verdicts. The update still merges on its own (#<PR>)
- **On phones a podium trio now lists its three drivers one per line, with a hairline between them**, on the combinations table, the Overdue and Unlikeliest leaderboards, and the landing page's "New podiums through the years" timeline. Laid out inline, a trio that ran out of room broke wherever a space fell, so a name could split across two lines (`K. Antonelli / L. Hamilton / M.` above `Verstappen`). Each name is now one unbreakable unit. The hairlines inside a trio are faint and the rule between trios uses the stronger border, so each trio reads as its own block rather than blurring into the next three names. Wider screens keep the inline `A / B / C` form, which now wraps only after a `/`, never before one. The combinations table's shared-car badge stays beside the last name (#319)
- The landing page's tagline now reads **"Keeping track of every F1 podium trio ever and predicting the next one."** — it says what the site does in plain terms, where the previous line ("Spotting the podium trio F1 has never seen — and predicting who's about to make it happen") asked the reader to work out the scorigami premise before the first data on the page (#315)
- **Andrea Kimi Antonelli is now Kimi Antonelli across the site**, the name F1 and Mercedes use for him: in the hero, the trio board's tooltips, the timeline, the combinations table (where `K. Antonelli` is the narrow-screen form and searching "kimi antonelli" finds him), and on the other pages as well. The Jolpica API still lists his full given names and the committed data keeps them. The pages swap in the billed name when they render, so the automated data refreshes are unaffected (#317)

## 2026-09-08

### Improvements
- **The next-race card now gives each of its columns something to do.** The track outline used to float small in the middle of ~200px of otherwise empty card, and the five stacked lines beside it had no focal point — the live countdown rendered at the same 14px as the static date next to it. The outline is now a framed circuit plate captioned with the circuit's name and length, and the countdown leads the left column under a small `LIGHTS OUT IN` label. The figure itself stays in text colour: the label carries the accent, so the hero's chance percentage just below remains the one big red number on the page. Race and qualifying times collapse onto one line and are **both** converted to the reader's timezone — qualifying used to ship as a UTC-only line, leaving two different clocks in one card. On phones the plate becomes a slim band, a small outline beside its caption, instead of an off-centre outline costing ~90px of scroll before the prediction. A circuit with no outline in the data drops the plate entirely and keeps its name and length on the line above
- **The mobile combinations list is one table again, not a stack of cards.** Collapsing each trio to a single line left every row still carrying its own border, rounded corners and a 6px gap, so the list read as 754 separate panels. Rows now sit flush inside the table frame divided by one hairline each — the same shape the widescreen table has — and the expanded drawer flows on inside that frame instead of breaking out of a card. About fifteen trios now fit on a phone screen (#311)
- **On mobile a combination is now one line.** Each row on the combinations page had stacked the trio, a labelled `Podiums` line and a labelled `Last` line into a three-part card, so a phone screen held about three of 754 trios and scrolling the list meant scrolling past the same two labels 750 times. The collapsed row is now just the trio, its podium count and the expand chevron; the last race moves into the expanded state, above the race pills it already showed. The count and chevron sit in fixed grid tracks so they line up down the whole list, the count keeps the sort order legible without a label, and trios too long for one line wrap without displacing the chevron. Roughly eleven trios now fit where three did (#309)
- **On mobile the combinations page opens on the table, not the filters.** The three driver boxes, the season selects, Clear and Sort stacked to roughly a full phone screen, so the first trio sat below the fold on a page whose whole point is the list. They now live in a slide-out panel behind a `Filters` trigger sitting beside the result count, which carries a badge counting the filters in force (each filled driver box, plus a narrowed season range) so a filtered table never looks like an unfiltered one. The panel closes on its `Show N trios` button, the X, the scrim or Escape, and the count on that button updates live as the filters change. The core is the same pure-CSS checkbox as the nav drawer, so it works with JS off; widescreen is untouched — above 720px the filters stay inline above the table and the trigger is hidden

### Fixes
- The last race's "happened N times" status sat at the far edge of the strip, pushed there by `margin-left: auto` — roughly 600px from the trio it describes on a widescreen. It now follows the trio directly, with a spacer taking up the slack
- A trio board bubble could open hundreds of pixels away from its own row. The bubble is `position: fixed`, so any transformed ancestor becomes its containing block and its viewport coordinates land relative to that instead — and the scroll-reveal animation puts a transform on the enclosing panel for half a second as it fades in. Hovering a row inside that window detached the bubble. Placement now measures where the bubble actually landed and corrects by the difference, which holds for a mask or filter on any ancestor too
- The landing page's prediction hero called its pick the **Most likely trio** when the whole hero is about brand-new trios; it now reads **Most likely new trio** (#311)
- The trio board no longer traps the page's scroll on mobile. It set `overscroll-behavior: contain`, which suits a modal but not a panel in the middle of a page: reaching the end of the list stranded the reader inside the board with no way to keep scrolling by dragging over it. The gesture now chains back to the page at the end of the list, as it already did at the top, while a drag mid-list still scrolls the board (#311)

## 2026-09-07

### Features
- The landing page's ranked panel is now a **trio board**: every trio the model rates as a live chance at the next race, already-happened and brand-new ranked together, with the never-happened ones highlighted by an accent bar and a `NEW` pill and the rest muted. Hovering (or tapping, on mobile) a muted row shows how many times that trio has stood on a podium and when it last did, with a link through to its filtered view on the combinations page. Previously the panel listed only never-happened trios, so a visitor could not tell whether a trio they had in mind was missing because it already happened or because the model rated it too unlikely to list — on the current grid, six of the ten likeliest podiums have happened before. The board takes every trio at 1% or better (27 rows pre-qualifying, 21 after, which shortens itself as the grid sharpens the odds), shows 12 at a time in a scrollable card and adds `trioBoard` to `podigami.json`. No model change: `predict_race` already computed the already-happened trios' probabilities and discarded them, so the prediction, P(brand-new trio) and the backtest are untouched

### Improvements
- **The Overdue, Unlikeliest and Soulmates tables now match the combinations table.** All three rendered through a shared component that only approximated it, so the four data pages never quite read as one system. The tables no longer sit inside a panel box — on Overdue and Soulmates that was a box inside a box — and each section is now a plain heading and one-line description above a single framed table, the way the combinations page reads. Rows pick up that table's geometry and type: the value column is left-aligned directly under its own label (a shared CSS grid track list keeps the label strip and every row face on the same columns), driver names sit at the page size rather than a size down and bold, the zebra stripe is gone, and the chevron is the round button that rotates and goes accent on open. Expanding a row now opens a proper drawer on the darker ground behind an accent rail instead of a faint inline strip. On Unlikeliest the race reads like "Last seen" — bold year, dimmed name — and follows the value column rather than preceding it (#299, #297)
- The #1 entry on all three pages is now an ordinary closed row carrying only an accent rail. It was rendered open and two type sizes up, which broke the column rhythm and meant the leaderboard's rule — closed shows the headline stat, expanded shows the detail — was the one thing the top row didn't follow
- **The prediction block is one clean card instead of a card inside a card.** The chance and its sentence now share a head row, centred against each other — previously the number hung off the label's first baseline and rode high whenever the sentence wrapped. Below a single hairline the trio reads as three plain columns marked only by a team-coloured rule, each naming the driver in full with their team and, after qualifying, the grid slot they start from (front to back, so the row matches the grid you are looking at). The label names the race, and the movement line ("Updated after qualifying · was 45% before the grid was set") replaces a red pill and an arrow glyph. Gone with it: the boxed chance panel, the TLA and car-number chips, the season-podium line, the two competing footnotes and the tracked-out `BACKTESTED` badge, whose figure now reads as a sentence. The accent colour is spent once, on the chance itself
- **Current form now separates the driver from the car properly.** The driver prior `sigma0_drv` was widened from 0.5 to 1.0, lifting the driver term from ~5% to ~24% of a car+driver strength. At 0.5 the board was effectively a car ranking with a tiebreak: Antonelli gained 1.08 on Russell across 2026 — 11 podiums to 7, a championship lead — and still could not pass him, because he began the season 1.12 behind on a rookie prior and each race moved him less than the last. He now leads the board. The change wins both headline scores on the frozen 2019–2026 window (log-loss 3.891 → 3.878, Brier-new 0.2382 → 0.2379) and on each half of it separately; exact-trio top-1 slips 17.6% → 17.0% and post-qualifying top-3 40.4% → 39.4%, so probability quality improves while ordinal hit-rate gives up a little. Noted in the README: the 2010–2018 tuner still prefers 0.5, so this one knob was chosen with knowledge of post-2018 results

### Fixes
- **Seven of the twelve team colours carried the wrong ink, and six of those failed WCAG AA.** `text_on()` chose between dark and white by a luminance threshold of 0.4, but the two inks actually cross over at ~0.19 relative luminance — so every mid-brightness team colour was handed white text where dark ink reads far better. In the current-form tower that put the car-number chips at 2.8:1 on McLaren orange, 3.0:1 on Williams blue, 2.9:1 on Alpine, 3.6:1 on Aston Martin and 3.9:1 on Red Bull. The helper now picks whichever ink wins the contrast comparison, which is the question it was always meant to answer: those five land at 5.4–6.9:1 and every colour but Ferrari clears 4.5:1. Ferrari red tops out at 4.44:1 on white (4.37:1 on dark), a limit of the brand colour rather than the ink choice, and is pinned by a test so it cannot quietly get worse (#302)
- **The Soulmates "Longest partnership" card contradicted the row it described.** The card measured the span as `lastYear - firstYear` while the row's own "Seasons active" stat counts both endpoints, so Alonso & Hamilton read as 16 seasons on the card and 17 in the table — and "across 16 seasons (2007–2023)" was wrong on its face. Both now use the same inclusive count, a one-season pairing reads "1 season" instead of "0 seasons", and the card cites the real number of ranked pairs rather than a hardcoded "top 30" (#302)
- **The combinations page's Clear button left the driver deep link armed.** Arriving from a trio link elsewhere on the site puts `?d=` names in the URL; Clear emptied the three inputs and the table but not the address bar, so the page showed everything while still claiming to be filtered — and the next reload, or a shared link, silently put the filter back. The URL now mirrors the driver filters the way it already mirrored the season range: typing updates it, clearing retracts it (#302)
- `head()` now escapes the title and description it repeats into `<title>` and five `content` attributes. The landing page's own title carries a bare `&`, which is invalid there, and a quote in either string would have closed the attribute and spilled the rest into the markup (#302)
- **A brand-new constructor could never climb out of its starting prior.** Constructor log-worths are identified only up to a common factor and had drifted upward for 76 seasons — the field median went from −1.5 in 1950 to +8.2 by 2025 — while `newteam_mu` stayed an absolute constant. A 2026 debutant was therefore seeded ~9 log-units below the grid, where the Plackett–Luce gradient rounds to ~1e-5: after 13 races Cadillac's rating still sat at *exactly* its −1.200 prior, rendering Bottas and Pérez at weight 0.2 and 0.1 against Russell's 110,778. `RatingEngine.recenter()` now pins the racing field's median log-worth at 0 after every race. Subtracting one offset from every constructor leaves all orderings, gradients and probabilities untouched, so the gauge is free — but it makes `newteam_mu` mean the same thing in every era. It was re-derived to −2.0, the median end-of-debut-season standing of the 14 genuine constructor debuts since 1990; Cadillac now rates last on the grid, matching its worst-in-class average finish
- Dropped the rank number from the Overdue, Unlikeliest and Soulmates leaderboards too, so every page is consistent. Each list is an ordered `<ol>` whose position already says the same thing, and the top entry keeps its accented, open-by-default hero treatment to mark it without a numeral
- Dropped the `#` column from the combinations table for the same reason, and because it went stale: only sorting renumbered it, so filtering left the visible rows carrying their unfiltered positions (#3, #17, #42). The trio names get the width instead
- Dropped the rank number from each trio-board row. The list is already ordered and the bar and percentage carry the ranking, so the column only spent width
- The trio board's history bubble was clipped to a sliver wherever it fell outside the scrolling list. The bottom fade was implemented as a `mask-image` on the scroll container, and a mask — like a transform or a filter — makes its element a containing block for `position: fixed` descendants and clips them, so the bubble was trapped inside the very box it was designed to escape. The fade is now an overlay on a wrapper, which creates no containing block
- The bubble's "See all" link could not be reached. It sat in an 8px gap below its row that belonged to neither element, so a mouse travelling toward the link fired `pointerleave` and closed it; the bubble now sits flush against its row, with a short grace period on leave. Clicking the link also did nothing, because the document-level dismiss ran during the same click and hid the anchor mid-dispatch, cancelling its navigation — clicks inside a tip no longer count as outside ones
- Tapping a row on mobile appeared to do nothing: a tap both focuses and clicks, so the focus handler opened the bubble and the click that followed toggled it straight back shut. Hover and focus are now mouse- and keyboard-only, leaving tap to the click handler alone
- Scrolling no longer dismisses an open bubble — it re-anchors to its row and closes only once that row leaves the board's window. Closing on any scroll also shut the bubble as the browser scrolled the link into view
- The bubble was allowed to fill a phone screen (366px of a 390px viewport), where it read as a band across the list rather than a tooltip; it is now capped at 300px. The board's mobile window is six rows, sized to the 75px a row occupies once the driver chips wrap

## 2026-09-06

### Features
- The post-qualifying prediction can be refreshed **during** a race for cars that are already out. `data/retirements.json` is a new hand-curated dataset naming the drivers who have retired from a running race, and any trio containing one drops to zero: the retired car leaves the simulated field entirely, so P(brand-new trio) is recomputed over the cars still circulating rather than merely filtered afterwards. Applied to the 2026 Italian Grand Prix after Leclerc's lap-3 crash, the headline moves from 38.2% to 40.8% and the most likely brand-new trio flips from Leclerc/Norris/Russell (4.51%) to Antonelli/Piastri/Russell (5.52%)
- A retired driver keeps the grid slot he actually started from, so the field's track-position offsets stay centred on the grid that formed, and his qualifying lap still counts as evidence for everyone else's rating — only his ability to finish is removed. The override is self-expiring: once the race is classified the post-qualifying block is dropped anyway, so stale rounds are ignored like stale grid penalties

### Fixes
- The driver-races fetcher now rides out a drained API rate limit instead of aborting the run. It is the last fetcher `update.py` invokes, so on a `--full` pass it meets an hourly budget already spent by the podium, results and qualifying sweeps — but it kept only 6 retries (~1 min of backoff) where those fetchers were deliberately given 8 (~4 min). A manual full reconciliation died on `drivers/max_verstappen/results.json` after `(6/6)`, taking the whole run down at step 11 of 15 and leaving no data PR; the weekly Monday `--full` job runs the same gauntlet. Raised to 8 to match, with a regression test that survives a 7-long 429 streak (#282)

## 2026-09-05

### Features
- The combinations table can be filtered to a range of seasons: a dual-handle slider on widescreen and a pair of From/To dropdowns below 720px, both driving the same window. A trio is shown if it stood on a podium at least once inside it, and while the window is narrower than 1950–2026 the **Count** and **Last seen** columns (and the sort keys behind them) describe that window rather than the trio's whole life, with the expanded race pills trimmed to match. The range is shareable as `?from=2001&to=2003`, `Clear` resets it, and the hint line names the window it is counting

### Fixes
- The post-qualifying prediction for the 2026 Italian Grand Prix now starts every car from its real grid slot. `data/grid_penalties.json` is hand-curated and had no round 13 entry, so the stewards' penalties were invisible to the model and the qualifying classification was used as the starting grid: Piastri +3 (impeding), and power-unit quota drops for Antonelli (+30), Lawson (+35) and Albon (+20). With the penalties recorded the grid rebuilds to the official order — Piastri P3→P6, Antonelli P7→P20, Lawson P14→P21, Albon P18→P22, promoting everyone else — which moves the causal track-position term, the displayed grid chips and the headline: the most likely brand-new trio flips from Antonelli/Piastri/Russell (4.82%) to Leclerc/Norris/Russell (4.51%), and P(brand-new trio) settles at 38.2% instead of 39.5%
- Added a regression test covering several place penalties that each overshoot the field size (30/35/20 places on a 22-car grid), which must stack at the back in qualifying order rather than contest one slot

## 2026-08-30

### Features
- Podiums won by a shared car now count for every driver who drove it. Until 1961 a driver could hand his car to a team-mate mid-race and both were classified at the finishing position, so 18 races in F1 history put **more than one** three-driver trio on the podium at once — and the site had been silently keeping only the first-listed driver of each shared step. `podiums.json` now carries the co-drivers, and a shared-drive podium expands into the full cross-product of real trios through every stage: combinations, podigami status, overdue, unlikeliest and soulmates. The clearest case is the 1956 Belgian Grand Prix, where Cesare Perdisa and Stirling Moss shared the third-placed Maserati
- `combos.html` marks a trio whose podium involved a shared car, so a combination that looks like an odd pairing is explained rather than mysterious; the marker carries an accessible name for screen readers
- The last-race recap renders a shared step as one podium step holding both drivers, so the podium stays three steps tall instead of dropping a name (dormant today — the last shared drive was the 1960 Argentine Grand Prix — but it can no longer silently lose a driver)
- A new FAQ entry explains why some 1950s podiums list four drivers

## 2026-08-27

### Improvements
- Tested whether the prediction model should weight a car by its most recent races. Added an adaptive constructor-diffusion channel (`con_adapt_gain`/`con_adapt_hl`): a car whose rating keeps moving the *same* way race after race has genuinely changed, so its belief loosens and catches up faster, while noise that pushes both ways cancels in the signed EWMA and costs nothing. Tuned on the 2010–2018 validation window it improved the objective (4.4013 → 4.3853), but the frozen 2019+ hold-out rejected it on both headline scores (logLoss 3.9146 vs 3.9115, brierNew 0.2438 vs 0.2384), so the acceptance gate keeps it **dormant at gain 0** and the live prediction is unchanged. The mechanism and its ablation rung stay in the ladder so the negative result is visible and a future re-tune can revisit it — the same treatment the attrition channel gets at `w_attr` 0 (#266)
- Overdue, Unlikeliest and Soulmates now read as one family with the Combinations table instead of three variations on floating cards. All three render through a shared ranked table (`src/build/_rows.py`): a single bordered container with an uppercase column-label strip, hairline row dividers and zebra striping, matching `combos.html` value for value. Rank #1 stays the richest entry — it is the same table row, open by default and accented, so its stats show without a click
- The three bespoke hero cards (`.odcard-hero`, `.uncard-hero`, `.smcard-hero`) and their triplicated stat-cell CSS are gone, taking ~250 lines of near-duplicate CSS and three per-page `render_card` helpers with them; the stat cell now has one definition all three pages share
- Ranks read as plain `1, 2, 3` under a `#` column header rather than repeating `#1` in every row (the `#` prefix returns on phones, where the label strip is hidden — matching how the combinations table handles its stacked rows)

## 2026-08-24

### Fixes
- The "chance the next race delivers a brand-new trio" tooltip is no longer cut in half. The hero used `overflow: hidden` to round its accent bar, which also clipped the info bubble hanging below the 45% card; the bar now rounds its own corners and the hero clips nothing. A CSS-contract test walks every generated page and fails if any ancestor of an `.info-tip` clips (#261)

## 2026-08-19

### Fixes
- A driver who misses a race keeps his car. `driverConstructor` names only the latest round's starters, so a driver who sits one out drops out of it entirely and was then predicted in an unknown — i.e. brand-new — car. The 2026 Dutch GP substitution (Hadjar out injured, Lawson up to Red Bull, Tsunoda into the Racing Bull) would have cut Hadjar's rating from 7,985 to 0.2 and shown him teamless on the grid for the whole fortnight to Monza. Seats now fall back to the last car each driver started this season, with the fresher of the two feeds winning either way round (#254)
- The post-qualifying block reads car strength from the car each driver actually qualified in rather than from his season-long mapping, so a stand-in no longer carries his old team's strength — or 0.0, if he had not raced this season at all — beside the correct new team name (#254)

## 2026-08-18

### Fixes
- The official-race-links refresh can now unlearn: a carried-over round whose slug no longer identity-matches that round's race name is dropped instead of shipped. When the 2026 calendar gained "Bahrain Grand Prix in Malaysia" as round 16 (Sepang) and renumbered every later round, the merge-only refresh kept the stale `R16 → singapore` row, the race-identity guardrail (rightly) failed, and the auto-update PR sat blocked for 15 days (#252)
- The identity table knows the relocated race: F1's results index lists "Bahrain Grand Prix in Malaysia" under its `bahrain` slug (id 1308), so round 16 gets its official link instead of a Wikipedia fallback (#252)
- Auto-update alerts now reach a human instead of burying themselves: an unchanged failure no longer adds a "still failing" comment every tick (the blocked-PR incident had piled up 400+ identical comments on a month-old issue, which notifies nobody), a changed failure updates the issue and comments once, and a new `notify-recovery` job closes the issue as soon as no data PR is left open — so the next incident opens a fresh issue and actually pings (#252)

## 2026-07-26

### Improvements
- The automated data refresh now watches the PR it opens, not just the run that opens it: an `auto/update-data` PR still unmerged 45 minutes after it was created raises the same deduplicated alert issue a failed run does, naming the cause (failing required check, merge conflict, auto-merge not armed). A fully green run whose PR sat blocked — what kept the Hungarian GP result off the site for ~2h — was the last stall that nothing alerted on (#229)

### Fixes
- The landing page no longer shows a post-qualifying, grid-based chance for a race that has already been run. `asOf` is read from `podiums.json` while the prediction engine reads `race_results.json`; when the upstream aggregates published the Hungarian GP to one but not the other, the engine still thought round 11 was upcoming and re-issued its grid-aware prediction hours after the flag. The next race is now taken from whichever dataset is further ahead, and the renderer independently drops any post-qualifying block whose race is already over (#239)
- Freshness-critical API reads now bypass Jolpica's response cache. The API sets `Vary: Accept, …` and caches each request variant separately with a long TTL, so the `Accept: application/json` variant every fetcher sends can be the better part of an hour stale — measured at 57 minutes on 2026-07-26, serving a `/2026/results.json` body that was missing the finished round 11 while other variants of the same URL already had it. That is what pulled `podiums.json` and `race_results.json` a round apart, and what left the in-run results watcher polling a stale feed for an hour without noticing a published race. Current-season fetches and the watcher now carry a cache-busting nonce; settled seasons stay cacheable (#239)
- The 404 page's "DNF" message now uses the site's theme-aware muted token. It referenced `--text-muted`, which is defined nowhere, so it always painted the hardcoded `#888` fallback — ignoring the theme and failing WCAG AA in light mode (3.31:1). It now measures 6.39:1 in light and 7.62:1 in dark (#224)
- The global font stack moved into a real `--font` token, so the `font-family: var(--font)` reset on tooltip bubbles resolves instead of being dropped as an undefined reference (#224)
- The closing methodology footnote on the Overdue, Unlikeliest and Soulmates pages is styled as fine print — 13px, muted, hairline rule above it. Its `.as-of` class had no rule in any stylesheet, so the caveat rendered at full body size and brightness, louder than the captions above it (#225)

## 2026-07-25

### Improvements
- Final grid penalties for the 2026 Hungarian GP (round 11): Hamilton and Antonelli each drop 3 places (impeding Piastri in Q3 / yellow-flag infringement) (#227)

### Fixes
- Grid penalties now pin a driver to exactly (qualifying position + penalty), matching how the FIA builds the grid: unpenalised cars promoted into vacated slots compress around the pinned slot instead of dragging the penalised car up with them. The old sort-and-renumber logic put Hamilton P4 for the Hungarian GP where the official grid has him P5 (Verstappen P4) (#230)
- Pinned ruff below 0.16 in CI: the just-released 0.16.0 changed formatter output (it now reformats code blocks inside Markdown docs), so the unpinned CI install silently failed every PR's required "Lint & format" check — including the automated Hungary post-qualifying data PR, which sat blocked instead of auto-merging. Future ruff upgrades must now arrive as a deliberate PR that reformats the repo in the same change (#227)

## 2026-07-23

### Improvements
- Rebuilt the Soulmates page on the site's shared ranked-list chrome so it matches the Overdue and Unlikeliest pages: the #1 duo is now a full hero card and every rank below it is a compact leaderboard row that expands to show the partnership's stats (years active, seasons, shared podiums per season). The fun-fact "Did you know" cards move into their own panel, the bespoke bar-chart list and standalone `soulmates.css` are gone (the page now shares `podigami.css`), and the header stat strip is dropped for parity with the other pages (#222)

## 2026-07-22

### Improvements
- Unified the trio separator across the whole site on `/` (e.g. "Verstappen / Norris / Piastri"): the Overdue and Unlikeliest pages previously used a middot between driver names, which collided with the middot already used for the per-driver rates line on the same cards. Now `/` always means "these three are one trio" and `·` is reserved for separate facts (rates, dates, footer)
- Landing hero: the "chance the next race delivers a brand-new trio" number now sits in its own framed panel that fills the full hero height, so on desktop it's anchored and balances the podium cards instead of floating in dead space; the old divider between the two halves is dropped (redundant with the panel border), and the three podium cards now stretch to fill their column so neither side leaves dead space
- SEO: keyword-tuned every page's title and meta description (front-loading terms like "F1 podium scorigami" and "F1 podium history"), and added FAQPage, Dataset, BreadcrumbList, and Organization structured data across the site — the FAQ schema is generated from the same source as the visible FAQ, so the two can never drift

## 2026-07-19

### Fixes
- Cleared two long-standing CodeQL alerts in the test suite: the race-link test now matches the full official F1 URL prefix instead of a bare `formula1.com` substring (which a lookalike host would satisfy), and the data-integrity test imports `load_race_results` at module level instead of re-importing `datalib` inside the function (#208)
- Finished races now reach the site far sooner: the update run holds its runner and polls the results feed itself until the round is actually published, instead of giving up and waiting for the next cron slot — GitHub only honours ~1 of our 15-min slots per hour, so a single early fetch used to cost a full extra hour (the Belgian GP landed ~100 min after the flag). The race-finished buffer also drops from 2h to 1h40, matching a real ~100-min race (#206)

### Improvements
- Landing page: the candidates panel is now titled "Most likely new trios" — clearer about what it ranks (brand-new podium trios) than the vaguer "Most likely next combinations" (#209)
- De-cluttered the Overdue and Unlikeliest pages: only the #1 trio (per section) keeps its full card; every other rank is a compact leaderboard row that expands to show its stats — native `<details>`, no JS (the old mobile "Details" toggle script is gone) (#202)

## 2026-07-18

### Improvements
- Final grid penalties for the 2026 Belgian GP (round 10): Norris and Stroll drop 10 places (power-unit quota); Hadjar (30 places) and Alonso (20 places) exceed the 15-place threshold and start from the back of the grid

### Features
- Grid penalties now feed the post-qualifying prediction: a new hand-curated `data/grid_penalties.json` (place drops and back-of-grid starts, validated by `datalib`) rebuilds the actual starting slots for the causal grid-position term and the displayed grid chips, while the qualifying order still counts at face value through the rating channel — first entries: Norris +10 places and Hadjar to the back for the 2026 Belgian GP

## 2026-07-16

### Features
- Post-qualifying grid-aware prediction: once the next race's qualifying is classified, the headline new-trio chance, candidate trios and driver form update automatically using the starting grid — the qualifying order replays through the rating engine plus a circuit-aware grid-advantage term, validated by the walk-forward backtest (post-qualifying lifts top-3 from 35% to 40% on the frozen 2019–2026 test window). The next-race box shows the upcoming qualifying time; after qualifying the hero gains an "updated after qualifying" badge with the movement from the pre-grid number, and candidates show grid-position chips (#195)

## 2026-07-10

### Improvements
- Landing page: the "Current form" tower now lives behind a "Show current form" toggle inside the "Most likely next combinations" panel (native `<details>`, collapsed by default), shortening the page and putting the form data next to the ranking it explains (#191)

## 2026-07-09

### Improvements
- Overdue page: each grid section ("All-time near-misses" / "Current grid") is now collapsible from its header (native `<details>`, open by default) so you can hide one and navigate the other, and on mobile each trio card collapses its three stats behind a per-card "Details" toggle to cut clutter (#189)

## 2026-07-06

### Improvements
- SEO technical quick wins: the homepage now canonicalises on the bare site root (`…/f1podigami/`) in both its `<link rel="canonical">`/`og:url` tags and the sitemap, the landing page carries JSON-LD structured data (`WebSite` plus a `SportsEvent` for the next race while the season runs), the 404 page is marked `noindex`, every page gains `og:locale` + `og:image:alt`, and the dead `meta keywords` tag is gone (#185)

## 2026-07-05

### Fixes
- Auto-update no longer stalls one race behind when the Jolpica round-indexed results endpoint (`/{season}/{round}/results`) lags the aggregate feeds right after a race: `fetch_constructor_standings` now falls back to the last round that returns results (keeping the constructor overlay on), and `datalib._save` writes each dataset's canonical schema form so a payload that omits optional fields still round-trips byte-identically — previously the byte-identical test failed on the empty-constructor case, silently skipping the data PR and looping the guard forever (#178)
- Automated data updates now check out `main` in both `update.yml` jobs: the guard reads `main`'s `asOf` (the only one data PRs advance, preventing an endless re-update loop after the first post-race merge under the develop/main flow) and the data branch is cut from `main` so unpromoted `develop` commits can't ride along into a data PR (#175)

### Improvements
- `update.yml` no longer fails silently: the `auto/update-data` PR now opens **before** the validate/test gate (a bad-data run surfaces as a red PR whose required checks block auto-merge, instead of a silently-skipped step), and a new `notify-failure` job opens/refreshes a single deduplicated issue linking the failed run — so a stall pings a human within one cron tick instead of hiding in a red run (#183)
- Docs: CLAUDE.md now documents the auto-update silent-stall failure mode — a failing test gate in the `update` job skips the data PR, stalling the site one race behind while the guard loops — plus the Jolpica round-indexed endpoint lag that triggered it and a concrete diagnosis path (#182)
- Docs: CLAUDE.md prediction-model section now describes the live v2 rating engine (datasets, acceptance gate, tuned knobs, compact storage) instead of only the v1 Plackett–Luce model (#174)

### Features
- Prediction model v2: a dynamic Bayesian rating engine (driver + car Gaussian ratings filtered over every race classification since 1950 and qualifying since 1994, with DNF-hazard reliability, circuit chaos and Rao-Blackwellised podium simulation) now powers the landing-page prediction. On the frozen 2019–2026 test window it lifts exact-trio top-1 from 12.5% to 18.1%, top-3 from 29.4% to 35.0% and log-loss from 4.078 to 3.916 over the previous Plackett–Luce model, which remains as fallback. New committed datasets `race_results.json` + `qualifying.json` (compact storage), two new fetchers wired into the update pipeline, walk-forward ablation ladder + coordinate-descent tuner in `backtest.py`, and updated FAQ/README copy

## 2026-07-04

### Improvements
- Docs: CLAUDE.md page table now lists all five pages (`unlikeliest.html` was missing) and the new `_hooks.py` helper; stale "four pages" wording fixed there and in the `_layout.py` docstring (#170)
- Mobile nav is now a burger-button drawer that slides in from the left (pure-CSS core so it works without JS, with keyboard/aria/scroll-lock enhancements), replacing the cramped horizontal scroll strip (#168)

### Features
- Landing-page engagement overhaul: live-stat discovery hooks after each section, a "Keep exploring" grid, timeline quick-pick chips (first/record/current season), hero chance count-up and scroll-reveal (both honouring reduced-motion), FAQ deep links, and the previously orphaned Soulmates page added to the site nav and footer (#167)

## 2026-07-03

### Fixes
- Season-rollover proofing for the data pipeline: off-season updates no longer wipe `current_drivers.json` (which emptied the prediction hero, contenders and current-form panels all winter) or `constructor_standings.json` (which dropped team labels and the car overlay) — both now fall back to the latest season that actually has results (#165)
- `fetch_schedule` can no longer write an empty schedule in early January before the new calendar is published (that broke the next-race box and failed the data-integrity CI gate, stalling the automated updates); it falls back to the previous season instead (#165)
- Circuit outline matching now rejects matches beyond ~5 km, so a future circuit missing from the bundled f1-circuits dataset shows no track map instead of silently borrowing the nearest existing track's outline and length (#165)

### Improvements
- Once a season is complete, the schedule looks ahead to the next season's published calendar, so the landing page counts down to the new season opener over the winter instead of showing "season complete" (#165)
- Official F1 race-link matching is now partial per round: a brand-new race name (e.g. a 2027 venue) degrades only its own round to the Wikipedia fallback instead of the whole season, and the hardcoded cancelled-race table is no longer needed (#165)
- Pre-map flags for plausible future host countries (Thailand, Rwanda, Argentina, Vietnam, South Korea) and add a CI check that every mapped country has a committed flag SVG (#165)

## 2026-07-01

### Improvements
- Trim the landing page hero to a short slogan and move the podigami explainer (scorigami etymology, trio/race counts) into a new FAQ entry; also drop the same "only N have happened" framing from the page's meta description
- Show the year in the landing page's "last time" repeat pill (e.g. "last time 2025 R22 · Las Vegas Grand Prix") so a historical round isn't mistaken for the current season
- Raise unit-test coverage for `build_combos_html.py` and `backtest.py` from ~38% to ~98% with render-structure and numeric/shape assertions (#115)
- Enlarge the next-race track map on desktop so it fills the full height of its hero box instead of being capped at 88px, while keeping the box size and mobile layout unchanged
- Sync README.md with the current pipeline (Unlikeliest/Soulmates pages, file map, test count, update.yml cadence) and add a CLAUDE.md rule keeping it current on future PRs
- Race-report links across the site now point to official Formula 1 result pages instead of Wikipedia, with a per-race Wikipedia fallback (#138)
- Extend the official F1 links to the 2023 season by skipping the cancelled, never-held Emilia Romagna GP that had blocked the season's count match (#140)

### Fixes
- Fix official F1 race-report links pointing at the **wrong race**: rounds were mapped to slugs by sorting F1's internal race IDs, which are not assigned in round order, scrambling ~83 links across 7+ seasons (e.g. 2021/2022/2025 and the "last race" box). Rounds are now paired with slugs by race identity (`race_identity.match_season`), a whole-dataset guardrail test blocks any wrong link, and the committed map is corrected (#158)
- Make the "Last race" name on the landing page clickable, linking out to Wikipedia just like the "Next race" name does
- Point the landing-page timeline slider's race links to official F1 pages too — they were still linking to Wikipedia (#140)
- Remove stale `_layout.py` comment describing a Soulmates nav "trailing arrow" that was removed along with the nav link itself (#151)
- Escape dynamic strings in `build_soulmates_html.py` with `esc()`, matching every sibling builder, and neutralize `</script>` in the landing page's embedded JSON blob so it can't prematurely close its `<script>` tag (#150)
- Truncate long team names (e.g. "Cadillac F1 Team") to a single line in the mobile hero driver cards, so one card no longer grows taller than its siblings (#149)
- Fix the prediction model's teammate "halo" blend silently no-oping for a whole constructor when 3 driverIds are tracked for it during a mid-season driver-swap window — it now blends each driver toward the average of their teammates instead of requiring exactly 2 (#148)
- `fetch_driver_races.py`'s driver pool now also includes every driverId that appears in any `combos.json` trio, fixing `compute_unlikeliest.py` silently skipping ~51% of historical podium trios (149 driverIds) whose race history fell outside the top-60-by-podium-count pool (#147). Data regenerates on the next successful automated update.

## 2026-06-29

### Improvements
- Rework the Overdue page into uniform cards matching the Unlikeliest design: each leads with the expected co-podiums score ("8.2×"), driver names abbreviate to `E. Ocon` on narrow screens, and the meaningless bar and raw decimal score are gone

### Features
- Add **Unlikeliest** page: the most statistically improbable podium trios that actually happened, ranked by races-together × career podium rates, with a hero for the single biggest fluke (2020 Sakhir GP) and a per-trio breakdown of why the maths said no
- Add Playwright e2e suite for interactive JS: slider, combos filter/sort, theme, tooltips (#113)

### Fixes
- Fix doubled numbering in "Most likely next combinations" list — `.cand-*` CSS was accidentally removed in #127 (#128)
- Fix hero layout at ~602px: collapse hero to single column at 720px so driver cards are side by side in the nav-wrap dead zone (#116)

### Improvements
- Rework the Unlikeliest page into uniform improbability cards: each leads with the odds the trio would *ever* share a podium (`1 in N`, from the Poisson tail of the expected co-podium count), with every field in a fixed place; driver names abbreviate to `E. Ocon` on narrow screens and the meaningless score bar is gone
- Adopt a `develop` → `main` branching workflow (develop is the default branch; main remains the release/deploy branch) and document it in CLAUDE.md
- Remove redundant stat boxes from combos page header — info already lives on the landing page
- Harden CI: add `datalib.validate` gate to `deploy.yml`, `actionlint` workflow linter, and SHA-pin all action refs (#114)

## 2026-06-28

### Improvements
- Added release notes page with footer link across all pages
- Run Playwright e2e test in CI instead of silently skipping it

### Fixes
- Align timeline slider thumb exactly under the sparkline bars (#110)
- Cache-bust CSS/JS asset URLs with a content hash (#109)
- Collapse combos stat cards into a slim strip on mobile (#107)
- Drive next/last race hero from results, not the calendar (#105)
- Clamp info tooltip within viewport on mobile (#103)
- Clean up sort indicator arrows on combos table header (#102)

### Features
- Link happened-trios to their stats on the combos page (#108)
- Poll for race data every 15 min instead of hourly (#106)
- Abbreviate driver names on mobile combos cards (#101)
- Race-aware hourly data updates via auto-merged PR (#97)
