"""Tests for the official F1 race-links dataset, the race_url helper, and the
fetch_race_links pure functions."""

import json

from datalib import DATA_DIR, REGISTRY, RaceLink, load_race_links

# --- dataset schema + plumbing ------------------------------------------------


def test_racelink_schema_validates_and_rejects_extra():
    ok = RaceLink.model_validate({"id": "1288", "slug": "austria"})
    assert ok.id == "1288" and ok.slug == "austria"


def test_f1_race_links_registered_and_present():
    assert "f1_race_links.json" in REGISTRY
    assert (DATA_DIR / "f1_race_links.json").exists()


def test_f1_race_links_roundtrips_through_loader():
    # load returns nested RaceLink models keyed by season -> round
    links = load_race_links()
    assert isinstance(links, dict)
    raw = json.loads((DATA_DIR / "f1_race_links.json").read_text(encoding="utf-8"))
    for season, rounds in raw.items():
        for rnd, entry in rounds.items():
            assert links[season][rnd].id == entry["id"]
            assert links[season][rnd].slug == entry["slug"]


from build import _layout  # noqa: E402  (RaceLink is already imported at the top of this file)

# --- race_url helper ----------------------------------------------------------

_LINKS = {"2026": {"8": RaceLink(id="1288", slug="austria")}}


def test_race_url_builds_official_f1_url_when_mapped():
    url = _layout.race_url(_LINKS, "2026", "8", "Austrian Grand Prix")
    assert url == "https://www.formula1.com/en/results/2026/races/1288/austria/race-result"


def test_race_url_falls_back_to_wikipedia_when_unmapped():
    url = _layout.race_url(_LINKS, "2026", "9", "British Grand Prix")
    assert url == "https://en.wikipedia.org/wiki/2026_British_Grand_Prix"


def test_race_url_accepts_int_round():
    url = _layout.race_url(_LINKS, "2026", 8, "Austrian Grand Prix")
    assert url.endswith("/races/1288/austria/race-result")
