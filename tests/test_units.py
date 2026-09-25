"""Unit tests for the pipeline's pure helper functions (no IO, no network)."""

import json

import pytest

from build import _layout  # noqa: E402
from build import build_combos_html as bc
from compute import compute_podigami as cp
from fetch import fetch_podiums as fp

# --- build_combos_html.wiki_url ------------------------------------------------


@pytest.mark.parametrize(
    "season,name,expected",
    [
        (
            "2021",
            "Saudi Arabian Grand Prix",
            "https://en.wikipedia.org/wiki/2021_Saudi_Arabian_Grand_Prix",
        ),
        ("1950", "Indianapolis 500", "https://en.wikipedia.org/wiki/1950_Indianapolis_500"),
        (
            "2020",
            "70th Anniversary Grand Prix",
            "https://en.wikipedia.org/wiki/2020_70th_Anniversary_Grand_Prix",
        ),
    ],
)
def test_wiki_url_builds_article_title(season, name, expected):
    assert _layout.wiki_url(season, name) == expected


def test_wiki_url_percent_encodes_accents():
    url = _layout.wiki_url("2021", "São Paulo Grand Prix")
    assert url == "https://en.wikipedia.org/wiki/2021_S%C3%A3o_Paulo_Grand_Prix"
    assert " " not in url  # spaces must never survive into a URL


# --- build_combos_html.short_race_name -----------------------------------------


def test_short_race_name_trims_grand_prix():
    assert bc.short_race_name("Spanish Grand Prix") == "Spanish GP"


def test_short_race_name_leaves_non_gp_untouched():
    assert bc.short_race_name("Indianapolis 500") == "Indianapolis 500"


# --- compute_podigami.trio_key -------------------------------------------------


def test_trio_key_is_order_independent():
    assert cp.trio_key(["c", "a", "b"]) == cp.trio_key(["a", "b", "c"]) == ("a", "b", "c")


# --- fetch_podiums.driver_record -----------------------------------------------


def test_driver_record_extracts_id_and_full_name():
    obj = {"Driver": {"driverId": "max_verstappen", "givenName": "Max", "familyName": "Verstappen"}}
    assert fp.driver_record(obj) == {"driverId": "max_verstappen", "name": "Max Verstappen"}


# --- podium fetcher: response-cache bypass -------------------------------------


def test_mutable_season_podiums_bypass_the_response_cache(monkeypatch):
    """podiums.json sets ``asOf``. A cached body means the run finds no new race
    and the site waits another cron hour for a result that is already published."""
    from fetch import fetch_podiums as fp
    from fetch.api_cache import CACHE_BUSTER

    calls = []

    def fake_get(url, params):
        calls.append(params)
        return {"MRData": {"total": "1", "RaceTable": {"Races": []}}}

    monkeypatch.setattr(fp, "get", fake_get)
    monkeypatch.setattr(fp.time, "sleep", lambda *_: None)

    fp.fetch_all_for_position(1, 2026, fresh_data=True)
    assert calls and all(CACHE_BUSTER in p for p in calls)

    calls.clear()
    fp.fetch_all_for_position(1, None)  # unscoped history rebuild
    assert calls and not any(CACHE_BUSTER in p for p in calls)


# --- podium fetcher: confirming rounds OpenF1 filled ---------------------------


def test_podiums_confirm_only_rounds_whose_three_steps_arrived(tmp_path, monkeypatch):
    """A round OpenF1 filled counts as confirmed once the API returned P1, P2 and P3.
    The three position feeds lag one another, so a partial answer leaves it pending."""
    from datalib import repository
    from fetch import fetch_podiums as fp

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fp, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fp, "OUT_PATH", tmp_path / "podiums.json")
    monkeypatch.setattr(fp.time, "sleep", lambda *_: None)

    def race(rnd, position):
        driver = {"driverId": f"d{position}", "givenName": "A", "familyName": f"B{position}"}
        return {
            "season": "2026",
            "round": rnd,
            "raceName": f"Grand Prix {rnd}",
            "Results": [{"Driver": driver}],
        }

    def fake_fetch(position, season=None, *, fresh_data=False):
        # Round 14 comes back complete; round 15 has only its winner so far.
        extra = [race("15", position)] if position == 1 else []
        return [race("14", position), *extra]

    monkeypatch.setattr(fp, "fetch_all_for_position", fake_fetch)
    pending = {
        "kind": "race",
        "pending": ["podiums", "race_results"],
        "since": "2026-09-13T15:00:00+00:00",
    }
    repository.save_unconfirmed(
        [{"season": "2026", "round": "14", **pending}, {"season": "2026", "round": "15", **pending}]
    )

    assert fp.main(["--full"]) == 0
    assert [(u.round, u.pending) for u in repository.load_unconfirmed()] == [
        ("14", ["race_results"]),
        ("15", ["podiums", "race_results"]),
    ]


def test_current_drivers_request_bypasses_the_response_cache(monkeypatch):
    """The grid feeds the prediction hero; a cached round would silently drop a
    mid-season seat change."""
    from fetch import fetch_current_drivers as fcd
    from fetch.api_cache import CACHE_BUSTER

    calls = []

    def fake_get(url, params):
        calls.append(params)
        return {"MRData": {"RaceTable": {"Races": []}}}

    monkeypatch.setattr(fcd, "get", fake_get)
    fcd.fetch_round_drivers(2026, 11)
    assert calls and all(CACHE_BUSTER in p for p in calls)


# --- fetch_current_drivers: a driver back from an absence ------------------------


def _qualifying(*rounds: tuple[str, str, list[str]]) -> list[dict]:
    return [
        {
            "season": season,
            "round": rnd,
            "results": [
                {"driverId": d, "constructorId": "red_bull", "position": i}
                for i, d in enumerate(ids, 1)
            ],
        }
        for season, rnd, ids in rounds
    ]


def _driver(driver_id: str, given: str, family: str, code: str, number: str) -> dict:
    return {
        "driverId": driver_id,
        "givenName": given,
        "familyName": family,
        "code": code,
        "permanentNumber": number,
    }


def test_pending_qualifiers_are_the_entrants_of_a_round_after_the_last_race(tmp_path, monkeypatch):
    from fetch import fetch_current_drivers as fcd

    f = tmp_path / "qualifying.json"
    f.write_text(
        json.dumps(
            _qualifying(
                ("2026", "14", ["max_verstappen", "tsunoda"]),
                ("2026", "15", ["max_verstappen", "hadjar"]),
            )
        )
    )
    monkeypatch.setattr(fcd, "QUALIFYING_PATH", f)

    assert fcd.pending_qualifiers(2026, [12, 13, 14]) == ("2026", ["max_verstappen", "hadjar"])
    assert fcd.pending_qualifiers(2026, [13, 14, 15]) is None


def test_pending_qualifiers_reach_into_the_next_season(tmp_path, monkeypatch):
    """The opener's grid falls back to last season's starters, so its rookies
    are only known from the new season's first qualifying."""
    from fetch import fetch_current_drivers as fcd

    f = tmp_path / "qualifying.json"
    f.write_text(json.dumps(_qualifying(("2025", "24", ["norris"]), ("2026", "1", ["rookie"]))))
    monkeypatch.setattr(fcd, "QUALIFYING_PATH", f)

    assert fcd.pending_qualifiers(2025, [22, 23, 24]) == ("2026", ["rookie"])


def test_grid_keeps_a_driver_who_qualified_after_missing_the_last_rounds(tmp_path, monkeypatch):
    """Hadjar sat out 2026 R12-R14 and qualified for R15: dropping him from the
    grid blanked his car number on the site and would fail the OpenF1 fast lane
    closed on car #6 for the whole race."""
    from datalib import repository
    from fetch import fetch_current_drivers as fcd

    (tmp_path / "qualifying.json").write_text(
        json.dumps(_qualifying(("2026", "15", ["max_verstappen", "hadjar"])))
    )
    monkeypatch.setattr(fcd, "QUALIFYING_PATH", tmp_path / "qualifying.json")
    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fcd, "SLEEP_BETWEEN", 0)
    monkeypatch.setattr(fcd, "season_and_recent_rounds", lambda: (2026, [12, 13, 14]))

    verstappen = _driver("max_verstappen", "Max", "Verstappen", "VER", "3")
    tsunoda = _driver("tsunoda", "Yuki", "Tsunoda", "TSU", "22")
    hadjar = _driver("hadjar", "Isack", "Hadjar", "HAD", "6")
    urls = []

    def fake_get(url, params):
        urls.append(url)
        if url.endswith("/2026/drivers.json"):
            return {"MRData": {"DriverTable": {"Drivers": [verstappen, tsunoda, hadjar]}}}
        starters = [{"Driver": verstappen}, {"Driver": tsunoda}]
        return {"MRData": {"RaceTable": {"Races": [{"Results": starters}]}}}

    monkeypatch.setattr(fcd, "get", fake_get)
    assert fcd.main() == 0

    grid = json.loads((tmp_path / "current_drivers.json").read_text())
    assert {d["driverId"]: d.get("number") for d in grid["drivers"]} == {
        "hadjar": "6",
        "max_verstappen": "3",
        "tsunoda": "22",
    }
    assert grid["drivers"][0] == {
        "driverId": "hadjar",
        "name": "Isack Hadjar",
        "code": "HAD",
        "number": "6",
    }
    assert sum(u.endswith("/drivers.json") for u in urls) == 1


def test_grid_skips_the_roster_request_when_every_qualifier_already_raced(tmp_path, monkeypatch):
    from datalib import repository
    from fetch import fetch_current_drivers as fcd

    (tmp_path / "qualifying.json").write_text(
        json.dumps(_qualifying(("2026", "15", ["max_verstappen"])))
    )
    monkeypatch.setattr(fcd, "QUALIFYING_PATH", tmp_path / "qualifying.json")
    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fcd, "SLEEP_BETWEEN", 0)
    monkeypatch.setattr(fcd, "season_and_recent_rounds", lambda: (2026, [14]))
    urls = []

    def fake_get(url, params):
        urls.append(url)
        starters = [{"Driver": _driver("max_verstappen", "Max", "Verstappen", "VER", "3")}]
        return {"MRData": {"RaceTable": {"Races": [{"Results": starters}]}}}

    monkeypatch.setattr(fcd, "get", fake_get)
    assert fcd.main() == 0
    assert not any(u.endswith("/drivers.json") for u in urls)
