"""Unit tests for the combos page's pure render helpers and full build (no network)."""

from build import build_combos_html as bc
from datalib import Combo, RaceLink, RaceRef


def race_ref(season, rnd, name):
    return RaceRef(season=season, round=rnd, raceName=name)


def combo(drivers, driver_ids, count, last, first, last_key, races):
    return Combo(
        drivers=drivers,
        driverIds=driver_ids,
        count=count,
        lastRace=last,
        firstRace=first,
        lastRaceKey=last_key,
        races=races,
    )


# ── short_race_name ───────────────────────────────────────────────────────────


def test_short_race_name_trims_grand_prix():
    assert bc.short_race_name("Monaco Grand Prix") == "Monaco GP"


def test_short_race_name_leaves_other_names_unchanged():
    assert bc.short_race_name("Indianapolis 500") == "Indianapolis 500"


# ── render_race_pills ─────────────────────────────────────────────────────────


def test_render_race_pills_groups_by_season():
    races = [
        race_ref("2021", "1", "Bahrain Grand Prix"),
        race_ref("2021", "2", "Emilia Romagna Grand Prix"),
        race_ref("2020", "5", "Spanish Grand Prix"),
    ]
    out = bc.render_race_pills(races)
    assert out.index('class="season-row"') < out.index("2021")
    # races are sorted ascending, so the older season (2020) renders first
    assert out.index("2020") < out.index("2021")


def test_render_race_pills_count_badge_only_when_multiple():
    races = [
        race_ref("2021", "1", "Bahrain Grand Prix"),
        race_ref("2021", "2", "Emilia Romagna Grand Prix"),
    ]
    out = bc.render_race_pills(races)
    assert 'class="ct"' in out
    assert "x2" in out

    single = [race_ref("2021", "1", "Bahrain Grand Prix")]
    out_single = bc.render_race_pills(single)
    assert 'class="ct"' not in out_single


def test_render_race_pills_short_names_and_round():
    races = [race_ref("2021", "3", "Monaco Grand Prix")]
    out = bc.render_race_pills(races)
    assert "Monaco GP" in out
    assert 'class="round"' in out
    assert "R3" in out


def test_render_race_pills_uses_official_link_when_available():
    races = [race_ref("2021", "1", "Bahrain Grand Prix")]
    links = {"2021": {"1": RaceLink(id="1125", slug="bahrain")}}
    out = bc.render_race_pills(races, links)
    assert 'target="_blank"' in out
    assert "race-pill" in out


def test_render_race_pills_escapes_race_name():
    races = [race_ref("2021", "1", "A & B Grand Prix")]
    out = bc.render_race_pills(races)
    assert "A &amp; B" in out


# ── render_combo ──────────────────────────────────────────────────────────────


def _sample_combo():
    last = race_ref("2022", "10", "British Grand Prix")
    first = race_ref("2019", "3", "Chinese Grand Prix")
    return combo(
        ["Lewis Hamilton", "Max Verstappen", "Charles Leclerc"],
        ["hamilton", "max_verstappen", "leclerc"],
        4,
        last,
        first,
        2022010,
        [first, last],
    )


def test_render_combo_row_has_rank_drivers_count():
    out = bc.render_combo(1, _sample_combo())
    assert '<td class="rank">1</td>' in out
    assert 'class="dn-full"' in out
    assert 'class="dn-abbr"' in out
    assert '<td class="count">4</td>' in out


def test_render_combo_data_attributes():
    c = _sample_combo()
    out = bc.render_combo(5, c)
    assert 'data-count="4"' in out
    assert f'data-last="{c.lastRaceKey}"' in out
    drivers_data = out.split('data-drivers="')[1].split('"')[0]
    assert "lewis hamilton" in drivers_data
    assert "max verstappen" in drivers_data


def test_render_combo_includes_detail_row_with_races():
    out = bc.render_combo(1, _sample_combo())
    assert 'class="detail"' in out
    assert 'colspan="5"' in out
    assert "British GP" in out


def test_render_combo_escapes_driver_names():
    c = combo(
        ["A & B", "C Driver", "D Driver"],
        ["a", "c", "d"],
        1,
        race_ref("2020", "1", "Test Grand Prix"),
        race_ref("2020", "1", "Test Grand Prix"),
        2020001,
        [race_ref("2020", "1", "Test Grand Prix")],
    )
    out = bc.render_combo(1, c)
    assert "A &amp; B" in out


# ── main (full build, in-process) ─────────────────────────────────────────────


def test_main_writes_full_page(tmp_path, monkeypatch):
    out_path = tmp_path / "combos.html"
    monkeypatch.setattr(bc, "OUT_PATH", out_path)

    assert bc.main() == 0

    html = out_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert 'class="combo"' in html
    assert 'class="detail"' in html
    assert "<table" in html
    assert 'id="visible-count"' in html
