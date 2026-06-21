"""Render data/overdue.json into dist/overdue.html.

Two ranked lists of podium trios that have never happened, ordered by how
statistically overdue they are (races together x podium rates).
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _layout import FOOTER, head, nav  # noqa: E402  (needs the sys.path entry above)

OVERDUE_PATH = ROOT / "data" / "overdue.json"
OUT_PATH = ROOT / "dist" / "overdue.html"


def esc(s: str) -> str:
    return html.escape(str(s))


def render_trio(names: list[str]) -> str:
    parts = '<span class="sep">/</span>'.join(
        f'<span class="pdriver">{esc(n)}</span>' for n in names
    )
    return f'<span class="trio trio-sm">{parts}</span>'


def render_list(entries: list[dict]) -> str:
    if not entries:
        return '<p class="panel-sub">No candidates.</p>'
    top = entries[0]["score"] or 1
    rows = []
    for i, e in enumerate(entries, 1):
        pct = round(100 * e["score"] / top)
        rates = " / ".join(f"{p['rate'] * 100:.0f}%" for p in e["perDriver"])
        rows.append(
            f'<li class="cand">'
            f'<span class="cand-rank">{i}</span>'
            f'<div class="cand-body">'
            f'  <div class="cand-names">{render_trio(e["names"])}</div>'
            f'  <div class="cand-bar-wrap"><div class="cand-bar" style="width:{pct}%"></div></div>'
            f'  <div class="cand-meta">raced <b>{e["racesTogether"]}</b> times together '
            f"&middot; {rates} podium rates</div>"
            f"</div>"
            f'<span class="cand-prob" title="overdue score = races together x podium rates">{e["score"]:.2f}</span>'
            f"</li>"
        )
    return f'<ol class="cand-list">{"".join(rows)}</ol>'


def panel(title: str, sub: str, entries: list[dict]) -> str:
    return (
        f'<section class="panel">'
        f"  <h2>{title}</h2>"
        f'  <p class="panel-sub">{sub}</p>'
        f"  {render_list(entries)}"
        f"</section>"
    )


def main() -> int:
    data = json.loads(OVERDUE_PATH.read_text(encoding="utf-8"))
    as_of = data["asOf"]

    all_time = panel(
        "All-time near-misses",
        "Trios from across F1 history that raced together often and each podiumed often "
        "&mdash; yet never all three on the same podium. Ranked by races together &times; podium rates.",
        data["allTime"],
    )
    grid = panel(
        "Current grid &mdash; still possible",
        "The most overdue trios among this season's drivers. These could still happen.",
        data["currentGrid"],
    )

    page = f"""{head(
        "F1 Overdue Podiums - Most Likely Trio to Never Have Happened",
        "podigami.css",
        description="The F1 podium trios that should have happened but never did. Drivers who raced together dozens of times, each a regular podium finisher, yet never all three on the rostrum.",
        page_path="overdue.html",
        keywords="F1, Formula 1, overdue podiums, F1 statistics, podium trios, near-miss podiums, F1 data",
    )}
<body>
{nav("overdue.html")}
<header>
    <div class="container">
        <h1><span class="accent">F1</span>Overdue Podiums</h1>
        <p class="tagline">The podium that <em>should</em> have happened but never did &mdash; trios who raced together time and again, each a regular podium finisher, yet never once all three on the rostrum together.</p>
    </div>
</header>
<main>
    <div class="container">
        {all_time}
        {grid}
        <p class="as-of">Score is a ranking heuristic (races together &times; each driver's career podium rate); the concrete numbers are the shared-race count and rates. Up to date through the {esc(as_of["season"])} {esc(as_of["raceName"])} (round {esc(as_of["round"])}).</p>
    </div>
</main>
{FOOTER}
<script src="theme.js"></script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  all-time: {len(data['allTime'])}, current-grid: {len(data['currentGrid'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
