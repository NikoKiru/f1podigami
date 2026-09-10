"""Render data/combos.json into dist/combos.html (the full combinations table).

This is the former landing page; index.html is now the podigami predictor
(build_podigami_html.py). Content is unchanged — only the nav and output path.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
from _layout import (  # noqa: E402  (needs the sys.path entry above)
    FOOTER,
    REPO_URL,
    SITE_URL,
    abbr_name,
    asset,
    breadcrumb_schema,
    driver_name,
    head,
    nav,
    organization_schema,
    race_url,
)

from datalib import Combo, RaceRef, load_combos, load_podiums, load_race_links  # noqa: E402


def dataset_schema(
    season_min: int, season_max: int, unique_combos: int, total_podiums: int
) -> dict:
    """schema.org Dataset describing the full podium-combination table (Google
    Dataset Search + topical authority)."""
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


OUT_PATH = ROOT / "dist" / "combos.html"

# Sliders glyph for the mobile "Filters" trigger, and the X that closes the
# panel. Inline (not CSS masks) so they inherit `currentColor` from the label.
_SLIDERS_ICON = (
    '<svg class="ft-icon" viewBox="0 0 24 24" width="15" height="15" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
    '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h10M18 18h2"/>'
    '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>'
    "</svg>"
)
_CLOSE_ICON = (
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" aria-hidden="true">'
    '<path d="M6 6l12 12M18 6L6 18"/></svg>'
)


def render_race_pills(
    races: list[RaceRef],
    links: dict | None = None,
    shared: dict[tuple[str, str], str] | None = None,
) -> str:
    """Group races by season; each season gets a row with year + race pills.

    ``shared`` maps (season, round) to the co-driver names for the pre-1961
    races where a podium car was shared, so the pill can say whose drive it was.
    """
    import html

    links = links or {}
    shared = shared or {}
    races_sorted = sorted(races, key=lambda r: (int(r.season), int(r.round)))
    parts: list[str] = []
    for season, group in itertools.groupby(races_sorted, key=lambda r: r.season):
        group_list = list(group)
        pill_parts: list[str] = []
        for r in group_list:
            co = shared.get((r.season, r.round))
            cls = "race-pill race-pill-shared" if co else "race-pill"
            title = f"{r.season} {r.raceName} — race report"
            if co:
                title = f"{title} (shared car with {co})"
            mark = '<span class="shared-mark" aria-hidden="true">&#8644;</span>' if co else ""
            aria_label = f' aria-label="{html.escape(title, quote=True)}"' if co else ""
            pill_parts.append(
                f'<a class="{cls}" href="{html.escape(race_url(links, r.season, r.round, r.raceName), quote=True)}"'
                f' target="_blank" rel="noopener"'
                f' title="{html.escape(title, quote=True)}"{aria_label}>'
                f'<span class="round">R{html.escape(r.round)}</span>'
                f"{html.escape(short_race_name(r.raceName))}"
                f"{mark}"
                f"</a>"
            )
        ct = len(group_list)
        ct_html = f'<span class="ct">x{ct}</span>' if ct > 1 else ""
        parts.append(
            f'<div class="season-row" data-season="{html.escape(season, quote=True)}">'
            f'<div class="season-label">{html.escape(season)}{ct_html}</div>'
            f'<div class="race-list">{"".join(pill_parts)}</div>'
            f"</div>"
        )
    return "".join(parts)


def short_race_name(name: str) -> str:
    """Trim "Grand Prix" -> "GP" for compact pill display."""
    if name.endswith(" Grand Prix"):
        return name[: -len(" Grand Prix")] + " GP"
    return name


def render_combo(
    combo: Combo,
    links: dict | None = None,
    shared: dict[tuple[str, str], str] | None = None,
) -> str:
    import html

    shared = shared or {}

    is_shared = any((r.season, r.round) in shared for r in combo.races)
    shared_desc = "One podium step was a car shared by two drivers"
    badge = (
        f'<span class="shared-badge" role="img"'
        f' aria-label="{html.escape(shared_desc, quote=True)}"'
        f' title="{html.escape(shared_desc, quote=True)}">'
        "&#8644;</span>"
        if is_shared
        else ""
    )

    names = [driver_name(d) for d in combo.drivers]
    # Each .driver is one nowrap unit that carries what follows the name: the
    # "/" for the first two, the badge for the last. Inline, a trio then wraps
    # only after a separator (never mid-name, never "/" leading a line); stacked
    # one per line on a phone, the badge stays beside its name.
    sep = '<span class="sep">/</span>'
    drivers_html = "".join(
        f'<span class="driver">'
        f'<span class="dn-full">{html.escape(d)}</span>'
        f'<span class="dn-abbr" aria-hidden="true">{html.escape(abbr_name(d))}</span>'
        f"{sep if i < len(names) - 1 else badge}"
        f"</span>"
        for i, d in enumerate(names)
    )
    drivers_data = " | ".join(names).lower()
    last = combo.lastRace
    last_html = (
        f'<span class="year">{html.escape(last.season)}</span>'
        f'<span class="race-name">{html.escape(last.raceName)}</span>'
    )
    n = combo.count

    races_data = ";".join(f"{r.season}|{r.round}|{r.raceName}" for r in combo.races)

    combo_row = (
        f'<tr class="combo" data-count="{n}"'
        f' data-last="{combo.lastRaceKey}"'
        f' data-races="{html.escape(races_data, quote=True)}"'
        f' data-drivers="{html.escape(drivers_data, quote=True)}">'
        f'<td class="drivers">{drivers_html}</td>'
        f'<td class="count">{n}</td>'
        f'<td class="last">{last_html}</td>'
        f'<td class="expand"><span class="chev">&#9662;</span></td>'
        f"</tr>"
    )
    detail_row = (
        f'<tr class="detail">'
        f'<td colspan="4">'
        f'<div class="detail-inner">{render_race_pills(combo.races, links, shared)}</div>'
        f"</td></tr>"
    )
    return combo_row + detail_row


def render_season_control(season_min: int, season_max: int) -> str:
    """The season-range filter: a dual-handle slider on widescreen, a pair of
    From/To selects on mobile (mirroring how .mobile-sort mirrors the sortable
    table headers). Both write to the same state in index.js.
    """
    opts = "".join(f'<option value="{y}">{y}</option>' for y in range(season_min, season_max + 1))
    from_opts = opts.replace(f'value="{season_min}"', f'value="{season_min}" selected', 1)
    to_opts = opts.replace(f'value="{season_max}"', f'value="{season_max}" selected', 1)
    return f"""<div class="season-range" data-min="{season_min}" data-max="{season_max}">
                    <div class="sr-head">
                        <span class="sr-label">Seasons</span>
                        <output class="sr-readout" id="season-readout" for="season-from season-to">All seasons</output>
                    </div>
                    <div class="sr-track" id="season-track">
                        <div class="sr-rail"></div>
                        <div class="sr-fill" id="season-fill"></div>
                        <input class="sr-input sr-from" id="season-from" type="range" min="{season_min}" max="{season_max}" step="1" value="{season_min}" aria-label="Earliest season">
                        <input class="sr-input sr-to" id="season-to" type="range" min="{season_min}" max="{season_max}" step="1" value="{season_max}" aria-label="Latest season">
                    </div>
                    <div class="sr-bounds"><span>{season_min}</span><span>{season_max}</span></div>
                </div>
                <div class="filter-group mobile-seasons">
                    <label for="season-from-sel">Seasons</label>
                    <div class="ms-pair">
                        <select id="season-from-sel" aria-label="Earliest season">{from_opts}</select>
                        <span class="ms-dash" aria-hidden="true">&ndash;</span>
                        <select id="season-to-sel" aria-label="Latest season">{to_opts}</select>
                    </div>
                </div>"""


def main() -> int:
    combos = load_combos()
    podiums = load_podiums()

    seasons = sorted({int(p.season) for p in podiums})
    total_podiums = len(podiums)
    unique_combos = len(combos)
    season_min, season_max = seasons[0], seasons[-1]

    # Pre-1961 races where a podium car was shared. Derived here rather than
    # stored on Combo: RaceRef is reused for firstRace/lastRace, so an optional
    # field would write "shared": null onto every race entry in combos.json.
    shared = {
        (p.season, p.round): ", ".join(
            dict.fromkeys(
                d.name for slot in ("p1", "p2", "p3") for d in ((p.coDrivers or {}).get(slot) or [])
            )
        )
        for p in podiums
        if p.coDrivers
    }

    links = load_race_links()
    rows_html = "\n".join(render_combo(c, links, shared) for c in combos)

    page = f"""{
        head(
            f"Every F1 Podium Combination, {season_min}–{season_max} — Podium History",
            "index.css",
            description=f"Every unique F1 podium combination in history: all {unique_combos:,} driver trios that have shared a Formula 1 podium since {season_min}, across {total_podiums:,} races.",
            page_path="combos.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Podium Combinations", "combos.html"),
                dataset_schema(season_min, season_max, unique_combos, total_podiums),
            ],
        )
    }
<body>
{nav("combos.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Podium Combinations</h1>
        <p class="tagline">Every unique trio that has shared an F1 World Championship podium since 1950 &mdash; order doesn't matter, only the set.</p>
    </div>
</header>
<main>
    <div class="container">
        <div class="controls">
            <input type="checkbox" id="filter-toggle" class="fp-toggle">
            <label for="filter-toggle" class="fp-scrim" aria-hidden="true"></label>
            <div class="filter-panel" id="filter-panel" tabindex="-1" aria-label="Filters and sort">
                <div class="fp-head">
                    <span class="fp-title">Filters &amp; sort</span>
                    <label for="filter-toggle" class="fp-close" role="button" tabindex="0" aria-label="Close filters">{
        _CLOSE_ICON
    }</label>
                </div>
                <div class="filters">
                    <div class="search-wrap">
                        <input data-filter type="search" placeholder="Driver 1..." aria-label="Driver 1 filter">
                    </div>
                    <div class="search-wrap">
                        <input data-filter type="search" placeholder="Driver 2..." aria-label="Driver 2 filter">
                    </div>
                    <div class="search-wrap">
                        <input data-filter type="search" placeholder="Driver 3..." aria-label="Driver 3 filter">
                    </div>
                    {render_season_control(season_min, season_max)}
                    <button id="clear-filters" type="button" class="clear-btn" disabled>Clear</button>
                    <div class="filter-group mobile-sort">
                        <label for="mobile-sort">Sort</label>
                        <select id="mobile-sort">
                            <option value="count-desc">Count (high &rarr; low)</option>
                            <option value="count-asc">Count (low &rarr; high)</option>
                            <option value="last-desc">Last seen (newest)</option>
                            <option value="last-asc">Last seen (oldest)</option>
                            <option value="drivers-asc">Trios (A &rarr; Z)</option>
                            <option value="drivers-desc">Trios (Z &rarr; A)</option>
                        </select>
                    </div>
                </div>
                <div class="fp-foot">
                    <label for="filter-toggle" class="fp-done" role="button" tabindex="0" id="filter-done">Show results</label>
                </div>
            </div>
            <div class="controls-bar">
                <div class="hint">
                    Showing <strong id="visible-count">{
        unique_combos
    }</strong><span id="of-total"> of <span id="total-count">{
        unique_combos
    }</span></span> unique podium trios<span id="range-note"></span>
                    &middot; click a row to expand
                </div>
                <label for="filter-toggle" class="filter-toggle" role="button" tabindex="0" aria-expanded="false" aria-controls="filter-panel">{
        _SLIDERS_ICON
    }<span class="ft-label">Filters</span><span class="ft-count" id="filter-count" aria-hidden="true">0</span></label>
            </div>
        </div>
        <div class="table-wrap">
            <table>
                <colgroup>
                    <col class="col-drivers">
                    <col class="col-count">
                    <col class="col-last">
                    <col class="col-expand">
                </colgroup>
                <thead>
                    <tr>
                        <th data-sort="drivers">Trios</th>
                        <th data-sort="count">Count</th>
                        <th data-sort="last">Last seen</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
{rows_html}
                </tbody>
            </table>
            <div id="empty-state" class="empty-state" style="display:none">
                <strong>No matches</strong>
                Try a different driver name.
            </div>
        </div>
    </div>
</main>
{FOOTER}
<script src="{asset("index.js")}"></script>
<script src="{asset("theme.js")}"></script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(
        f"  rendered {unique_combos} combos covering {total_podiums} races ({season_min}-{season_max})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
