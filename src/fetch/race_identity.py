"""Map an F1 result-page *slug* to the race it actually is, so a round can be
paired with its correct slug by identity rather than by guessing from ID order.

Why this exists: F1's per-year results index gives each race a URL like
``/en/results/2021/races/1086/spain/race-result``. The numeric ID is internal and
is NOT assigned in round order (rescheduled or late-added races get out-of-order
IDs), and the page's DOM order pins the "latest race" first for the current
season -- so neither ID sort nor page position reliably recovers the round. What
*is* reliable is the slug's identity: "spain" is the Spanish GP, "great-britain"
is the British GP. We already know each round's race name (schedule for the
current season, podiums for history), so we assign each round the slug whose
identity matches, and refuse (fall back to Wikipedia) when it can't be done
cleanly. See issue #158.

``ACCEPTABLE_SLUGS`` maps each race name to the set of slugs F1 may use for it.
It is a set (not a single value) only because a race name can legitimately map to
different slugs across eras -- e.g. the US GP was ``usa-east`` in 1976-80 (when a
separate "West" race also ran) and ``united-states`` otherwise. Within any single
season exactly one of a name's acceptable slugs is present, so the assignment is
unambiguous.
"""

from __future__ import annotations

from collections.abc import Iterable

# race name (as it appears in our schedule/podiums) -> acceptable F1 slug(s)
ACCEPTABLE_SLUGS: dict[str, frozenset[str]] = {
    "70th Anniversary Grand Prix": frozenset({"70th-anniversary"}),
    "Abu Dhabi Grand Prix": frozenset({"abu-dhabi"}),
    "Argentine Grand Prix": frozenset({"argentina"}),
    "Australian Grand Prix": frozenset({"australia"}),
    "Austrian Grand Prix": frozenset({"austria"}),
    "Azerbaijan Grand Prix": frozenset({"azerbaijan"}),
    "Bahrain Grand Prix": frozenset({"bahrain"}),
    "Barcelona Grand Prix": frozenset({"barcelona-catalunya"}),
    "Belgian Grand Prix": frozenset({"belgium"}),
    "Brazilian Grand Prix": frozenset({"brazil"}),
    "British Grand Prix": frozenset({"great-britain"}),
    "Caesars Palace Grand Prix": frozenset({"caesar-s-palace"}),
    "Canadian Grand Prix": frozenset({"canada"}),
    "Chinese Grand Prix": frozenset({"china"}),
    "Dallas Grand Prix": frozenset({"dallas"}),
    "Detroit Grand Prix": frozenset({"detroit"}),
    "Dutch Grand Prix": frozenset({"netherlands"}),
    "Eifel Grand Prix": frozenset({"eifel"}),
    "Emilia Romagna Grand Prix": frozenset({"emilia-romagna"}),
    "European Grand Prix": frozenset({"europe"}),
    "French Grand Prix": frozenset({"france"}),
    "German Grand Prix": frozenset({"germany"}),
    "Hungarian Grand Prix": frozenset({"hungary"}),
    "Indian Grand Prix": frozenset({"india"}),
    "Indianapolis 500": frozenset({"indianapolis"}),
    "Italian Grand Prix": frozenset({"italy"}),
    "Japanese Grand Prix": frozenset({"japan"}),
    "Korean Grand Prix": frozenset({"south-korea"}),
    "Las Vegas Grand Prix": frozenset({"las-vegas"}),
    "Luxembourg Grand Prix": frozenset({"luxembourg"}),
    "Malaysian Grand Prix": frozenset({"malaysia"}),
    "Mexican Grand Prix": frozenset({"mexico"}),
    "Mexico City Grand Prix": frozenset({"mexico"}),
    "Miami Grand Prix": frozenset({"miami"}),
    "Monaco Grand Prix": frozenset({"monaco"}),
    "Moroccan Grand Prix": frozenset({"morocco"}),
    "Pacific Grand Prix": frozenset({"pacific"}),
    "Pescara Grand Prix": frozenset({"pescara"}),
    "Portuguese Grand Prix": frozenset({"portugal"}),
    "Qatar Grand Prix": frozenset({"qatar"}),
    "Russian Grand Prix": frozenset({"russia"}),
    "Sakhir Grand Prix": frozenset({"sakhir"}),
    "San Marino Grand Prix": frozenset({"san-marino"}),
    "Saudi Arabian Grand Prix": frozenset({"saudi-arabia"}),
    "Singapore Grand Prix": frozenset({"singapore"}),
    "South African Grand Prix": frozenset({"south-africa"}),
    "Spanish Grand Prix": frozenset({"spain"}),
    "Styrian Grand Prix": frozenset({"styria"}),
    "Swedish Grand Prix": frozenset({"sweden"}),
    "Swiss Grand Prix": frozenset({"switzerland"}),
    "São Paulo Grand Prix": frozenset({"brazil"}),
    "Turkish Grand Prix": frozenset({"turkey"}),
    "Tuscan Grand Prix": frozenset({"tuscany"}),
    "United States Grand Prix": frozenset({"united-states", "usa-east"}),
    "United States Grand Prix West": frozenset({"usa-west"}),
}


def acceptable_slugs(race_name: str) -> frozenset[str]:
    """Slugs F1 may use for ``race_name`` (empty for a name we don't know)."""
    return ACCEPTABLE_SLUGS.get(race_name, frozenset())


def slug_matches(slug: str, race_name: str) -> bool:
    """True if ``slug`` is a valid F1 slug for ``race_name``."""
    return slug in acceptable_slugs(race_name)


def match_season(
    round_names: dict[str, str], pairs: Iterable[tuple[str, str]]
) -> dict[str, dict[str, str]] | None:
    """Assign each round its ``{id, slug}`` by matching slug identity.

    ``round_names`` maps ``round -> raceName`` for one season; ``pairs`` is that
    season's ``(id, slug)`` pairs from F1, in any order. Returns
    ``{round: {"id", "slug"}}`` only when every round is matched by exactly one
    slug and no slug is left over; otherwise ``None`` (the caller then falls back
    to Wikipedia for the whole season). This is deliberately strict: a partial or
    ambiguous match is treated as no match so a wrong link can never ship.
    """
    result: dict[str, dict[str, str]] = {}
    claimed: set[str] = set()
    for rid, slug in pairs:
        rounds = [rnd for rnd, name in round_names.items() if slug in acceptable_slugs(name)]
        if len(rounds) != 1:
            return None  # slug matches no round (unknown/cancelled) or is ambiguous
        rnd = rounds[0]
        if rnd in claimed:
            return None  # two slugs claim the same round
        claimed.add(rnd)
        result[rnd] = {"id": rid, "slug": slug}
    if claimed != set(round_names):
        return None  # some round had no matching slug
    return result
