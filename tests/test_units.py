"""Unit tests for the pipeline's pure helper functions (no IO, no network)."""

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
