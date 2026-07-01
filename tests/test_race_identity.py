"""Race-identity matching: the guardrail that every official F1 race-report link
resolves to the *correct* race.

The link URL is built from a per-round ``{id, slug}`` taken from
``data/f1_race_links.json``. Historically the round<->slug assignment was derived
by sorting F1's internal race IDs, on the false assumption that IDs increase with
round number. They do not (rescheduled/late-added races get out-of-order IDs), so
that scrambled the mapping and links pointed at the wrong race (issue #158).

The fix maps each round to the slug whose *race identity* matches (slug is an
acceptable slug for that round's race name), and validates the whole dataset so a
wrong link can never ship again.
"""

import json

from datalib import DATA_DIR, load_podiums, load_schedule
from fetch import race_identity as ri

# --- slug <-> race-name identity ---------------------------------------------


def test_slug_matches_plain_country_name():
    assert ri.slug_matches("great-britain", "British Grand Prix")
    assert ri.slug_matches("netherlands", "Dutch Grand Prix")
    assert not ri.slug_matches("belgium", "British Grand Prix")


def test_slug_matches_distinguishes_two_spanish_country_races():
    # 2026 runs both: Barcelona keeps its own slug, Madrid takes "spain".
    assert ri.slug_matches("barcelona-catalunya", "Barcelona Grand Prix")
    assert ri.slug_matches("spain", "Spanish Grand Prix")
    assert not ri.slug_matches("spain", "Barcelona Grand Prix")


def test_slug_matches_us_grand_prix_accepts_both_east_and_plain():
    # 1976-80 the US GP (East, Watkins Glen) used slug "usa-east"; otherwise
    # the single US GP uses "united-states".
    assert ri.slug_matches("united-states", "United States Grand Prix")
    assert ri.slug_matches("usa-east", "United States Grand Prix")
    assert ri.slug_matches("usa-west", "United States Grand Prix West")
    assert not ri.slug_matches("indianapolis", "United States Grand Prix West")


# --- match_season: assign rounds by identity, order-independent ---------------


def test_match_season_ignores_input_order():
    # Pairs supplied in scrambled (id) order must still land on the right round.
    round_names = {"1": "Bahrain Grand Prix", "2": "Spanish Grand Prix", "3": "Monaco Grand Prix"}
    pairs = [("1067", "monaco"), ("1064", "bahrain"), ("1086", "spain")]
    assert ri.match_season(round_names, pairs) == {
        "1": {"id": "1064", "slug": "bahrain"},
        "2": {"id": "1086", "slug": "spain"},
        "3": {"id": "1067", "slug": "monaco"},
    }


def test_match_season_none_when_slug_has_no_matching_round():
    # An F1-listed race we don't have a round for (e.g. a cancelled event) makes
    # the season unmatchable -> the caller falls back to Wikipedia.
    round_names = {"1": "Bahrain Grand Prix", "2": "Monaco Grand Prix"}
    pairs = [("1", "bahrain"), ("2", "monaco"), ("3", "emilia-romagna")]
    assert ri.match_season(round_names, pairs) is None


def test_match_season_none_when_a_round_is_unmatched():
    round_names = {"1": "Bahrain Grand Prix", "2": "Monaco Grand Prix"}
    pairs = [("1", "bahrain")]  # nothing for round 2
    assert ri.match_season(round_names, pairs) is None


def test_match_season_resolves_us_east_west_pair():
    round_names = {"1": "United States Grand Prix", "2": "United States Grand Prix West"}
    pairs = [("10", "usa-west"), ("9", "usa-east")]
    assert ri.match_season(round_names, pairs) == {
        "1": {"id": "9", "slug": "usa-east"},
        "2": {"id": "10", "slug": "usa-west"},
    }


# --- table completeness -------------------------------------------------------


def test_every_slug_in_committed_data_is_recognised():
    """Every slug we ship must be an acceptable slug for some race name, or the
    identity guardrail could never validate it."""
    links = json.loads((DATA_DIR / "f1_race_links.json").read_text(encoding="utf-8"))
    all_accepted = set().union(*ri.ACCEPTABLE_SLUGS.values())
    unknown = {
        entry["slug"]
        for rounds in links.values()
        for entry in rounds.values()
        if entry["slug"] not in all_accepted
    }
    assert not unknown, f"slugs not in the identity table: {sorted(unknown)}"


# --- the guardrail: committed links point at the CORRECT race ------------------


def _round_names():
    """season -> {round: raceName} from our own committed data (schedule for the
    current season, podiums for completed history)."""
    names: dict[str, dict[str, str]] = {}
    for p in load_podiums():
        names.setdefault(p.season, {})[p.round] = p.raceName
    sched = load_schedule()
    for r in sched.races:
        names.setdefault(sched.season, {})[r.round] = r.raceName
    return names


def test_every_committed_link_matches_its_round_identity():
    links = json.loads((DATA_DIR / "f1_race_links.json").read_text(encoding="utf-8"))
    names = _round_names()
    wrong = []
    for season, rounds in links.items():
        for rnd, entry in rounds.items():
            race_name = names.get(season, {}).get(rnd)
            if race_name is None:
                continue  # a mapped round we have no race for is caught elsewhere
            if not ri.slug_matches(entry["slug"], race_name):
                wrong.append(f"{season} R{rnd}: {race_name!r} -> {entry['slug']!r}")
    assert not wrong, "race links pointing at the wrong race:\n" + "\n".join(wrong)
