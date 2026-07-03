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

# "austria" is pinned first (the current-season "latest race" highlight) even
# though it is round 3 — proof that neither DOM order nor ID order gives the round.
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

# round -> raceName, the identity source rounds are assigned from.
_NAMES_2026 = {
    2026: {"1": "Australian Grand Prix", "2": "Miami Grand Prix", "3": "Austrian Grand Prix"}
}


def test_parse_race_links_dedupes_first_seen_and_filters_year():
    pairs = frl.parse_race_links(_SAMPLE_HTML, 2026)
    assert sorted(pairs) == [("1279", "australia"), ("1284", "miami"), ("1288", "austria")]
    # first-seen order, NOT round order: the pinned latest race comes first.
    assert pairs[0] == ("1288", "austria")


def test_update_map_assigns_rounds_by_identity_not_order():
    out = frl.update_map({}, [(2026, 3)], lambda y: _SAMPLE_HTML, _NAMES_2026, sleep=0)
    assert out["2026"] == {
        "1": {"id": "1279", "slug": "australia"},
        "2": {"id": "1284", "slug": "miami"},
        "3": {"id": "1288", "slug": "austria"},  # round 3, despite appearing first
    }


def test_update_map_wiki_fallback_when_a_slug_has_no_round():
    # F1 lists only a slug we can't identify -> nothing mapped for the season,
    # so it falls back to Wikipedia at render time (never a wrong link).
    html = '<a href="/en/results/2020/races/1/mystery/race-result"></a>'
    out = frl.update_map({}, [(2020, 1)], lambda y: html, {2020: {"1": "Austrian Grand Prix"}}, 0)
    assert "2020" not in out


def test_update_map_maps_known_races_even_with_an_unknown_new_name():
    # A season gaining a brand-new race name (e.g. a 2027 venue our identity
    # table doesn't know yet) must not cost every other race its official link.
    html = (
        '<a href="/en/results/2027/races/1300/bahrain/race-result"></a>'
        '<a href="/en/results/2027/races/1301/gotham-city/race-result"></a>'
        '<a href="/en/results/2027/races/1302/monaco/race-result"></a>'
    )
    names = {
        2027: {"1": "Bahrain Grand Prix", "2": "Gotham City Grand Prix", "3": "Monaco Grand Prix"}
    }
    out = frl.update_map({}, [(2027, 3)], lambda y: html, names, sleep=0)
    assert out["2027"] == {
        "1": {"id": "1300", "slug": "bahrain"},
        "3": {"id": "1302", "slug": "monaco"},  # round 2 -> Wikipedia fallback
    }


def test_update_map_refresh_keeps_previously_mapped_rounds():
    # A partial refresh must merge with what we already know, never drop it.
    existing = {"2026": {"3": {"id": "999", "slug": "japan"}}}
    html = '<a href="/en/results/2026/races/1279/australia/race-result"></a>'
    names = {2026: {"1": "Australian Grand Prix", "3": "Japanese Grand Prix"}}
    out = frl.update_map(existing, [(2026, 2)], lambda y: html, names, sleep=0)
    assert out["2026"] == {
        "1": {"id": "1279", "slug": "australia"},
        "3": {"id": "999", "slug": "japan"},
    }


def test_season_counts_uses_schedule_for_current_and_podiums_for_history():
    schedule = {"season": "2026", "races": [{"round": "1"}, {"round": "2"}]}
    podiums = [{"season": "1950"}, {"season": "1950"}, {"season": "2026"}]
    counts = frl.season_counts(schedule, podiums)
    assert counts[1950] == 2
    assert counts[2026] == 2  # schedule wins for the current season


def test_season_round_names_uses_schedule_for_current_and_podiums_for_history():
    schedule = {"season": "2026", "races": [{"round": "1", "raceName": "Australian Grand Prix"}]}
    podiums = [{"season": "1950", "round": "1", "raceName": "British Grand Prix"}]
    names = frl.season_round_names(schedule, podiums)
    assert names[1950] == {"1": "British Grand Prix"}
    assert names[2026] == {"1": "Australian Grand Prix"}


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
    out = frl.update_map(existing, [(2026, 22)], boom, {}, sleep=0)
    assert out == existing  # unchanged; no crash


def test_update_map_skips_cancelled_race_so_season_matches():
    # F1's archive lists a race that never happened (2023 Imola, cancelled).
    # Identity matching skips it — it matches no round of ours — and the
    # remaining slugs still map 1:1, no hardcoded cancellation table needed.
    slugs = ["bahrain", "emilia-romagna", "monaco"]  # emilia-romagna = cancelled
    html = "".join(
        f'<a href="/en/results/2023/races/{i}/{slug}/race-result"></a>'
        for i, slug in enumerate(slugs, start=100)
    )
    names = {2023: {"1": "Bahrain Grand Prix", "2": "Monaco Grand Prix"}}
    out = frl.update_map({}, [(2023, 2)], lambda y: html, names, sleep=0)
    assert out["2023"] == {
        "1": {"id": "100", "slug": "bahrain"},
        "2": {"id": "102", "slug": "monaco"},  # emilia-romagna skipped
    }
