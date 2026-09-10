"""Unit tests for the soulmates page's pure render helpers (no IO)."""

import pytest

from build import build_soulmates_html as bs
from datalib import Soulmates


def pair(a, b, count, first, last):
    return {"a": a, "b": b, "count": count, "firstYear": first, "lastYear": last}


def soulmates(pairs, names=None):
    """A minimal but schema-valid Soulmates document around ``pairs``."""
    names = names or sorted({n for p in pairs for n in (p["a"], p["b"])})
    n = len(names)
    idx = {nm: i for i, nm in enumerate(names)}
    matrix = [[0] * n for _ in range(n)]
    for p in pairs:
        i, j = idx[p["a"]], idx[p["b"]]
        matrix[i][j] = matrix[j][i] = p["count"]
    return Soulmates.model_validate(
        {
            "drivers": [
                {"name": nm, "total": 10 + i, "medianYear": 2000 + i} for i, nm in enumerate(names)
            ],
            "matrix": matrix,
            "max": max((p["count"] for p in pairs), default=0),
            "topPairs": pairs,
        }
    )


def fact(facts, label):
    return next(f for f in facts if f["label"] == label)


@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [(2007, 2023, 17), (2010, 2010, 1), (1999, 2000, 2)],
)
def test_seasons_span_is_inclusive_of_both_endpoints(first, last, expected):
    p = bs.SoulmatePair(a="A B", b="C D", count=5, firstYear=first, lastYear=last)
    assert bs._seasons(p) == expected


def test_longest_partnership_fact_matches_the_row_it_describes():
    """The card and the row's "Seasons active" stat count the same partnership.

    They are the same claim about the same pair, so a span measured one way in
    the table and another way on the card makes the page contradict itself.
    """
    long_pair = pair("Fernando Alonso", "Lewis Hamilton", 20, 2007, 2023)
    short_pair = pair("Ayrton Senna", "Alain Prost", 30, 1988, 1990)
    facts = bs._compute_facts(soulmates([short_pair, long_pair]))

    longest = fact(facts, "Longest partnership")
    seasons = bs._seasons(bs.SoulmatePair(**long_pair))

    assert seasons == 17
    assert longest["num"] == str(seasons)
    assert f"across {seasons} seasons" in longest["detail"]
    # The same pair's row drawer states the span the same way.
    assert bs._pair_stats(bs.SoulmatePair(**long_pair)).count(f">{seasons}<") == 1


def test_longest_partnership_picks_the_widest_span_not_the_biggest_count():
    facts = bs._compute_facts(
        soulmates(
            [
                pair("Ayrton Senna", "Alain Prost", 30, 1988, 1990),
                pair("Fernando Alonso", "Lewis Hamilton", 5, 2007, 2023),
            ]
        )
    )
    longest = fact(facts, "Longest partnership")
    assert "Fernando Alonso" in longest["detail"]
    assert longest["num"] == "17"


def test_render_pair_bills_antonelli_as_kimi():
    p = bs.SoulmatePair(
        a="Andrea Kimi Antonelli", b="George Russell", count=9, firstYear=2025, lastYear=2026
    )
    out = bs.render_pair(p)
    assert '<span class="dn-full">Kimi Antonelli</span>' in out
    assert ">K. Antonelli<" in out
    assert "Andrea" not in out


def test_fact_cards_bill_antonelli_as_kimi():
    """Every card that names a driver uses the name the site shows everywhere else."""
    facts = bs._compute_facts(
        soulmates([pair("Andrea Kimi Antonelli", "George Russell", 9, 2025, 2026)])
    )
    details = " ".join(f["detail"] for f in facts)
    assert "Kimi Antonelli" in details
    assert "Andrea" not in details


def test_facts_survive_a_single_season_partnership():
    """A pair that shared podiums in one season spans one season, never zero."""
    facts = bs._compute_facts(soulmates([pair("A One", "B Two", 3, 2021, 2021)]))
    longest = fact(facts, "Longest partnership")
    assert longest["num"] == "1"
    assert longest["unit"] == "season"
    assert "across 1 season (" in longest["detail"]
