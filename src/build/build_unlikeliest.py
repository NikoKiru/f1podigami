"""Render data/unlikeliest.json into dist/unlikeliest.html.

The mirror of the Overdue page: podium trios that *did* happen, ranked by how
statistically unlikely they were (races together x career podium rates). #1 is
the single most improbable podium in F1 history, shown as a hero; the rest follow
as a ranked list, each carrying the breakdown of why the maths said no.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
from _layout import FOOTER, asset, head, nav, wiki_url  # noqa: E402

from datalib import UnlikeliestTrio, load_unlikeliest  # noqa: E402

OUT_PATH = ROOT / "dist" / "unlikeliest.html"


def esc(s: str) -> str:
    return html.escape(str(s))


def render_trio(names: list[str]) -> str:
    parts = '<span class="sep">/</span>'.join(
        f'<span class="pdriver">{esc(n)}</span>' for n in names
    )
    return f'<span class="trio trio-sm">{parts}</span>'


def _rates(e: UnlikeliestTrio) -> str:
    return " / ".join(f"{p.rate * 100:.0f}%" for p in e.perDriver)


def _race_link(e: UnlikeliestTrio) -> str:
    h = e.happened
    url = wiki_url(h.season, h.raceName)
    label = f"{esc(h.season)} {esc(h.raceName)}"
    return (
        f'<a class="race-link" href="{html.escape(url, quote=True)}" target="_blank" '
        f'rel="noopener" title="{label} &mdash; race report">{label}</a>'
    )


def render_hero(e: UnlikeliestTrio) -> str:
    note = f" &mdash; and did it {e.count}&times; in all" if e.count > 1 else ""
    return (
        f'<section class="hero unlikely-hero">'
        f'  <div class="hero-chance">'
        f'    <span class="hc-num">{e.score:g}</span>'
        f'    <span class="hc-label">expected co-podiums</span>'
        f"  </div>"
        f'  <div class="hero-pick">'
        f'    <div class="hp-label"><span class="accent">#1</span> Most improbable podium in F1 history</div>'
        f'    <div class="cand-names">{render_trio(e.names)}</div>'
        f'    <p class="hero-why">Raced together <b>{e.racesTogether}</b> times '
        f"&middot; career podium rates {_rates(e)} &middot; yet all three reached the "
        f"rostrum together at the {_race_link(e)}{note}.</p>"
        f"  </div>"
        f"</section>"
    )


def render_list(entries: list[UnlikeliestTrio], start_rank: int = 2) -> str:
    if not entries:
        return '<p class="panel-sub">No trios.</p>'
    top = max(e.score for e in entries) or 1
    rows = []
    for i, e in enumerate(entries, start_rank):
        pct = round(100 * e.score / top)
        rows.append(
            f'<li class="cand">'
            f'<span class="cand-rank">{i}</span>'
            f'<div class="cand-body">'
            f'  <div class="cand-names">{render_trio(e.names)}</div>'
            f'  <div class="cand-bar-wrap"><div class="cand-bar" style="width:{pct}%"></div></div>'
            f'  <div class="cand-meta">raced <b>{e.racesTogether}</b>&times; together '
            f"&middot; {_rates(e)} podium rates &middot; expected <b>{e.score:g}</b> "
            f"vs actual <b>{e.count}</b> &middot; {_race_link(e)}</div>"
            f"</div>"
            f'<span class="cand-prob" title="unlikeliness score = races together &times; podium rates (lower = more improbable)">{e.score:g}</span>'
            f"</li>"
        )
    return f'<ol class="cand-list" start="{start_rank}">{"".join(rows)}</ol>'


def main() -> int:
    data = load_unlikeliest()
    as_of = data.asOf
    trios = data.trios

    if not trios:
        body = '<p class="panel-sub">No data.</p>'
    else:
        hero = render_hero(trios[0])
        rest = render_list(trios[1:], start_rank=2)
        body = (
            f"{hero}"
            f'<section class="panel">'
            f"  <h2>The rest of the improbable</h2>"
            f'  <p class="panel-sub">Podiums that happened against the odds, '
            f"most improbable first. Each shows the three drivers' career podium rates, "
            f"how often they raced together, and the expected co-podium count the maths gave "
            f"&mdash; versus how many times it actually happened.</p>"
            f"  {rest}"
            f"</section>"
        )

    page = f"""{
        head(
            "F1 Unlikeliest Podiums - The Most Improbable Trios That Actually Happened",
            "podigami.css",
            description="The most statistically improbable F1 podiums that actually happened. Trios of drivers who rarely podiumed, yet once all three shared the rostrum against the odds.",
            page_path="unlikeliest.html",
            keywords="F1, Formula 1, unlikeliest podiums, improbable podiums, F1 statistics, podium trios, fluke podiums, F1 data",
        )
    }
<body>
{nav("unlikeliest.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Unlikeliest Podiums</h1>
        <p class="tagline">The podiums that <em>almost shouldn't have happened</em> &mdash; trios who barely podiumed, or barely raced together, yet once all three lined up on the rostrum against the odds.</p>
    </div>
</header>
<main>
    <div class="container">
        {body}
        <p class="as-of">Unlikeliness is a ranking heuristic (races together &times; each driver's career podium rate); a low score that nonetheless happened is the surprise. Up to date through the {
        esc(as_of.season)
    } {esc(as_of.raceName)} (round {esc(as_of.round)}).</p>
    </div>
</main>
{FOOTER}
<script src="{asset("theme.js")}"></script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  trios: {len(trios)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
