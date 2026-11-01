"""Render data/scorecard.json into dist/scorecard.html.

What the site said before each race against what actually happened. Every row is
a published prediction, frozen at lights out, so this page is the site marking
its own homework in public. The copy reports the numbers whichever way they fall:
a verdict is computed from them, never written in advance.

Rows go through the shared ranked table (``_rows``), newest race first. A top pick
that landed gets the accent rail the other pages give their #1.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
from _hooks import explore_grid, hook_card  # noqa: E402
from _layout import (  # noqa: E402
    FOOTER,
    WELCOME,
    abbr_name,
    asset,
    breadcrumb_schema,
    combos_link,
    head,
    nav,
    organization_schema,
    race_url,
)
from _rows import (  # noqa: E402
    render_link,
    render_race_link,
    render_row,
    render_section,
    render_stat,
    render_table,
)
from build_unlikeliest import render_trio  # noqa: E402

from datalib import (  # noqa: E402
    DATA_DIR,
    Scorecard,
    ScorecardNext,
    ScorecardTotals,
    ScoredRace,
    load_model_eval,
    load_race_links,
    load_scorecard,
)

OUT_PATH = ROOT / "dist" / "scorecard.html"

# Grid tracks shared by the label strip and every row face: trio, odds, race,
# chevron. The race track fits the longest race, as Combinations' Last seen does.
COLS = "minmax(0,1fr) 110px 284px 26px"

# Below this a season's worth of races still says more about luck than skill.
SMALL_SAMPLE = 30


def esc(s) -> str:
    return html.escape(str(s))


def format_odds(race: ScoredRace) -> str:
    """What the site gave the trio that happened. A dash means it published nothing
    to read that from: before the trio board, only new trios were ranked."""
    if race.podiumProb is not None:
        return f"{race.podiumProb:.1f}%"
    if race.boardFloor is not None:
        return f"under {race.boardFloor:.1f}%"
    return "&mdash;"


def trio_line(names: list[str]) -> str:
    return " / ".join(esc(abbr_name(n)) for n in names)


def times(n: int) -> str:
    return {0: "never", 1: "once", 2: "twice"}.get(n, f"{n} times")


def render_tags(race: ScoredRace) -> str:
    tags = []
    if race.isNew:
        tags.append('<span class="sc-tag sc-new">New trio</span>')
    if race.topPickHit:
        tags.append('<span class="sc-tag sc-hit">Called it</span>')
    return "".join(tags)


def _stats(race: ScoredRace, race_link: str) -> str:
    cells = [
        render_stat("Chance of a new trio", f"{race.chanceNew:.0f}%"),
        render_stat(
            "Top new pick",
            f"{trio_line(race.topPick)} &middot; {race.topPickProb:.1f}%",
            extra_class="rr-stat-wide",
        ),
        render_stat("Drivers right", f"{race.driversRight} of 3"),
    ]
    if race.boardSize:
        place = f"#{race.boardRank} of {race.boardSize}" if race.boardRank else "Not on it"
        cells.append(render_stat("Trio board", place))
    made = "After qualifying" if race.stage == "post-quali" else "Before qualifying"
    cells.append(render_stat("Prediction from", made))
    if race.model != "dbpl-v2":
        cells.append(render_stat("Model", "The earlier one"))
    cells.append(render_stat("Race", race_link, extra_class="rr-stat-race"))
    cells.append(render_link(combos_link(race.podium), "See this trio"))
    return "".join(cells)


def render_race(race: ScoredRace, links: dict) -> str:
    url = race_url(links, race.season, race.round, race.raceName)
    race_link = render_race_link(url, race.season, race.raceName)
    return render_row(
        render_trio(race.podium) + render_tags(race),
        format_odds(race),
        _stats(race, race_link),
        race_html=race_link,
        hero=race.topPickHit,
    )


def render_races(races: list[ScoredRace], links: dict) -> str:
    if not races:
        return '<p class="rank-sub">No races scored yet.</p>'
    rows = "".join(render_race(r, links) for r in races)
    return render_table(
        rows, value_label="We gave it", cols=COLS, group_label="Podium", race_label="Race"
    )


def _brier_verdict(t: ScorecardTotals) -> str:
    """One sentence against the guess the model has to beat, whichever way it falls."""
    if t.baselineBrierNew is None or t.baseRateNew is None:
        return ""
    if t.brierNew == t.baselineBrierNew:
        word = "matches"
    else:
        word = "beats" if t.brierNew < t.baselineBrierNew else "trails"
    return (
        f" Its Brier score of {t.brierNew:.3f} {word} the {t.baselineBrierNew:.3f} from always"
        f" guessing the long-run {t.baseRateNew:.0f}% (lower is better)."
    )


def fact_cards(t: ScorecardTotals) -> list[dict]:
    new_share = round(100 * t.newTrios / t.races) if t.races else 0
    facts = [
        {
            "label": "New or repeat",
            "num": f"{t.meanChanceNew:.0f}%",
            "unit": "average chance",
            "detail": f"That&rsquo;s the chance given to a brand-new trio before each race, and "
            f"<b>{t.newTrios} of {t.races}</b> podiums ({new_share}%) were new."
            + _brier_verdict(t),
        },
        {
            "label": "Top new pick",
            "num": str(t.topPickHits),
            "unit": f"of {t.races} races",
            "detail": f"The single most likely new trio stood on the podium "
            f"<b>{times(t.topPickHits)}</b>. At the odds it was given, you&rsquo;d expect "
            f"{t.topPickExpected:.1f}.",
        },
        {
            "label": "Drivers right",
            "num": f"{t.meanDriversRight:.1f}",
            "unit": "of 3",
            "detail": "How many of the top new pick&rsquo;s three drivers made the podium, "
            "on average.",
        },
    ]
    if t.boardRaces:
        facts.append(
            {
                "label": "Trio board",
                "num": f"{t.onBoard} of {t.boardRaces}",
                "unit": "races",
                "detail": f"Since the board arrived, that&rsquo;s how often the real trio was on "
                f"it, and it was in the top three <b>{times(t.boardTopThree)}</b>.",
            }
        )
    return facts


def render_facts(t: ScorecardTotals) -> str:
    cards = "".join(
        f'<div class="fact-card">'
        f'<div class="fc-label">{f["label"]}</div>'
        f'<div class="fc-num">{f["num"]} <span class="fc-unit">{f["unit"]}</span></div>'
        f'<div class="fc-detail">{f["detail"]}</div>'
        f"</div>"
        for f in fact_cards(t)
    )
    return f'<div class="sm-facts sc-facts">{cards}</div>'


def render_next(nxt: ScorecardNext | None) -> str:
    if nxt is None:
        return ""
    stat = (
        f"<b>{nxt.chanceNew:.0f}%</b> chance of a brand-new trio, with "
        f"<b>{trio_line(nxt.topPick)}</b> the top new pick at {nxt.topPickProb:.1f}%."
    )
    card = hook_card(f"Next up: {nxt.raceName}", stat, "index.html", "See the full prediction")
    return f'<div class="sc-next">{card}</div>'


def _long_run_note() -> str:
    """The backtest, for scale: far more races, but a replay rather than a record."""
    if not (DATA_DIR / "model_eval.json").exists():
        return ""
    ev = load_model_eval()
    return (
        f" For the longer view, a walk-forward backtest of {ev.chosen.n} races since "
        f"{ev.evalWindow.test[0]} put the real trio in the model&rsquo;s top three "
        f"{round(100 * ev.chosen.top3)}% of the time."
    )


def method_note(card: Scorecard) -> str:
    t = card.totals
    first = (
        f" Records start at the {card.races[-1].season} {esc(card.races[-1].raceName)}."
        if (card.races)
        else ""
    )
    sample = (
        f" {t.races} races is a small sample, so treat these as early numbers."
        if t.races < SMALL_SAMPLE
        else ""
    )
    return (
        "Each row is the last prediction published before lights out, frozen there and never "
        f"rewritten.{first} Until the trio board arrived the site only ranked new trios, so a "
        f"repeat podium from those races shows a dash.{sample}{_long_run_note()}"
    )


def main() -> int:
    card = load_scorecard()
    links = load_race_links()

    summary = render_section(
        "So far",
        "Exact trios are long shots, so judge the odds rather than the misses: a trio given "
        "5% should still miss 19 times in 20.",
        render_facts(card.totals),
    )
    table = render_section(
        "Race by race",
        "The podium that happened and the chance the site gave it beforehand. Open a race to "
        "see the prediction.",
        render_races(card.races, links),
    )

    page = f"""{
        head(
            "F1 Prediction Scorecard — How the Podium Model Did, Race by Race",
            "podigami.css",
            description="How F1 Podigami's podium predictions held up: every prediction as published before the race, frozen at lights out and scored against the real result.",
            page_path="scorecard.html",
            json_ld=[
                organization_schema(),
                breadcrumb_schema("Prediction Scorecard", "scorecard.html"),
            ],
        )
    }
<body>
{nav("scorecard.html")}
{WELCOME}
<header>
    <div class="container">
        <h1><span class="accent">F1</span> Prediction Scorecard</h1>
        <p class="tagline">What the site said before each race, and what actually happened. Frozen at lights out and never rewritten.</p>
    </div>
</header>
<main>
    <div class="container">
        {render_next(card.next)}
        {summary}
        {table}
        <p class="as-of">{method_note(card)}</p>
        {explore_grid("scorecard.html")}
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
    print(f"  races scored: {card.totals.races}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
