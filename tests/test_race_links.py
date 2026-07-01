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


from fetch import fetch_race_links as frl  # noqa: E402

# --- fetch_race_links pure logic ----------------------------------------------

_SAMPLE_HTML = """
<a href="/en/results/2026/races/1288/austria/race-result">latest</a>
<ul>
  <a href="/en/results/2026/races/1279/australia/race-result">AUS</a>
  <a href="/en/results/2026/races/1279/australia/race-result">AUS dup</a>
  <a href="/en/results/2026/races/1288/austria/race-result">AUT</a>
  <a href="/en/results/2026/races/1284/miami/race-result">MIA</a>
  <a href="/en/results/2025/races/1200/somewhere/race-result">other year</a>
</ul>
"""


def test_parse_race_links_dedupes_and_sorts_by_id():
    pairs = frl.parse_race_links(_SAMPLE_HTML, 2026)
    assert pairs == [("1279", "australia"), ("1284", "miami"), ("1288", "austria")]


def test_build_season_map_assigns_rounds_when_count_matches():
    pairs = [("1279", "australia"), ("1284", "miami"), ("1288", "austria")]
    m = frl.build_season_map(pairs, expected_count=3)
    assert m == {
        "1": {"id": "1279", "slug": "australia"},
        "2": {"id": "1284", "slug": "miami"},
        "3": {"id": "1288", "slug": "austria"},
    }


def test_build_season_map_empty_on_count_mismatch():
    pairs = [("1279", "australia"), ("1288", "austria")]
    assert frl.build_season_map(pairs, expected_count=3) == {}


def test_season_counts_uses_schedule_for_current_and_podiums_for_history():
    schedule = {"season": "2026", "races": [{"round": "1"}, {"round": "2"}]}
    podiums = [{"season": "1950"}, {"season": "1950"}, {"season": "2026"}]
    counts = frl.season_counts(schedule, podiums)
    assert counts[1950] == 2
    assert counts[2026] == 2  # schedule wins for the current season


def test_compute_targets_modes():
    counts = {1950: 7, 2025: 22, 2026: 24}
    existing = {"1950": {str(i): {} for i in range(1, 8)}}  # 1950 complete
    assert frl.compute_targets("incremental", existing, counts, 2026) == [(2026, 24)]
    # backfill: current + seasons missing/incomplete (1950 complete -> skipped)
    assert frl.compute_targets("backfill", existing, counts, 2026) == [(2026, 24), (2025, 22)]
    assert frl.compute_targets("refetch-all", existing, counts, 2026) == [
        (1950, 7),
        (2025, 22),
        (2026, 24),
    ]


def test_update_map_keeps_existing_on_fetch_failure():
    def boom(year):
        raise RuntimeError("network down")

    existing = {"2025": {"1": {"id": "9", "slug": "x"}}}
    out = frl.update_map(existing, [(2026, 22)], boom, sleep=0)
    assert out == existing  # unchanged; no crash


def test_update_map_adds_season_on_success():
    def ok(year):
        return _SAMPLE_HTML

    out = frl.update_map({}, [(2026, 3)], ok, sleep=0)
    assert out["2026"]["1"] == {"id": "1279", "slug": "australia"}
