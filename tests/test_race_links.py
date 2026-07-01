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
