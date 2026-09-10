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


def test_render_combo_row_has_drivers_and_count():
    out = bc.render_combo(_sample_combo())
    # No ordinal column: the table is ordered, and it went stale under filtering
    # because only sorting renumbered it.
    assert 'class="rank"' not in out
    assert 'class="dn-full"' in out
    assert 'class="dn-abbr"' in out
    assert '<td class="count">4</td>' in out


def test_render_combo_data_attributes():
    c = _sample_combo()
    out = bc.render_combo(c)
    assert 'data-count="4"' in out
    assert f'data-last="{c.lastRaceKey}"' in out
    drivers_data = out.split('data-drivers="')[1].split('"')[0]
    assert "lewis hamilton" in drivers_data
    assert "max verstappen" in drivers_data


def test_render_combo_bills_antonelli_as_kimi():
    """Shown, abbreviated and searched as Kimi Antonelli, not the API's
    "Andrea Kimi Antonelli" — the landing page's ?d= links filter on this."""
    race = race_ref("2026", "12", "Dutch Grand Prix")
    c = combo(
        ["Andrea Kimi Antonelli", "Lando Norris", "George Russell"],
        ["antonelli", "norris", "russell"],
        1,
        race,
        race,
        2026012,
        [race],
    )
    out = bc.render_combo(c)
    assert '<span class="dn-full">Kimi Antonelli</span>' in out
    assert ">K. Antonelli<" in out
    assert 'data-drivers="kimi antonelli | lando norris | george russell"' in out
    assert "andrea" not in out.lower()


def test_render_combo_includes_detail_row_with_races():
    out = bc.render_combo(_sample_combo())
    assert 'class="detail"' in out
    assert 'colspan="4"' in out  # one fewer column since the ordinal went
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
    out = bc.render_combo(c)
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


def test_shared_drive_race_pill_names_the_co_driver():
    from build.build_combos_html import render_race_pills
    from datalib import RaceRef

    races = [RaceRef(season="1956", round="4", raceName="Belgian Grand Prix")]
    out = render_race_pills(races, None, {("1956", "4"): "Stirling Moss"})
    assert "race-pill-shared" in out
    assert "shared car with Stirling Moss" in out


def test_normal_race_pill_has_no_shared_marker():
    from build.build_combos_html import render_race_pills
    from datalib import RaceRef

    races = [RaceRef(season="2021", round="21", raceName="Saudi Arabian Grand Prix")]
    out = render_race_pills(races, None, {})
    assert "race-pill-shared" not in out
    assert "shared car" not in out


def test_shared_race_pill_anchor_has_aria_label():
    races = [race_ref("1956", "4", "Belgian Grand Prix")]
    out = bc.render_race_pills(races, None, {("1956", "4"): "Stirling Moss"})
    assert (
        'aria-label="1956 Belgian Grand Prix — race report (shared car with Stirling Moss)"' in out
    )


def test_normal_race_pill_anchor_has_no_aria_label():
    races = [race_ref("2021", "21", "Saudi Arabian Grand Prix")]
    out = bc.render_race_pills(races, None, {})
    assert "aria-label" not in out


# ── render_combo: shared-drive badge ────────────────────────────────────────


def _shared_combo():
    """A combo whose races include a pre-1961 shared-drive race."""
    shared_race = race_ref("1955", "1", "Argentine Grand Prix")
    other_race = race_ref("1956", "2", "Monaco Grand Prix")
    return combo(
        ["Juan Manuel Fangio", "Giuseppe Farina", "Roberto Mieres"],
        ["fangio", "farina", "mieres"],
        2,
        other_race,
        shared_race,
        1956002,
        [shared_race, other_race],
    )


def test_render_combo_emits_shared_badge_for_combo_touching_shared_race():
    c = _shared_combo()
    shared = {("1955", "1"): "Froilan Gonzalez"}
    out = bc.render_combo(c, None, shared)
    assert "shared-badge" in out


def test_render_combo_omits_shared_badge_when_no_race_is_shared():
    out = bc.render_combo(_sample_combo(), None, {})
    assert "shared-badge" not in out


def test_render_combo_shared_badge_has_aria_label():
    c = _shared_combo()
    shared = {("1955", "1"): "Froilan Gonzalez"}
    out = bc.render_combo(c, None, shared)
    assert 'role="img"' in out
    assert 'aria-label="One podium step was a car shared by two drivers"' in out


# ── season control + data-races ───────────────────────────────────────────────


def test_render_combo_carries_every_race_in_data_races():
    races = [
        race_ref("2001", "3", "Brazilian Grand Prix"),
        race_ref("2003", "9", "British Grand Prix"),
    ]
    c = combo(
        ["A", "B", "C"],
        ["a", "b", "c"],
        2,
        races[1],
        races[0],
        2003009,
        races,
    )
    out = bc.render_combo(c)
    assert 'data-races="2001|3|Brazilian Grand Prix;2003|9|British Grand Prix"' in out


def test_render_combo_escapes_race_names_in_data_races():
    races = [race_ref("2020", "1", 'A "quoted" Grand Prix')]
    c = combo(["A", "B", "C"], ["a", "b", "c"], 1, races[0], races[0], 2020001, races)
    out = bc.render_combo(c)
    assert "&quot;quoted&quot;" in out
    assert 'data-races="2020|1|A &quot;quoted&quot; Grand Prix"' in out


def test_render_race_pills_tags_each_season_row():
    races = [
        race_ref("2020", "5", "Spanish Grand Prix"),
        race_ref("2021", "1", "Bahrain Grand Prix"),
    ]
    out = bc.render_race_pills(races)
    assert 'class="season-row" data-season="2020"' in out
    assert 'class="season-row" data-season="2021"' in out


def test_season_control_bounds_and_handles():
    out = bc.render_season_control(1950, 2026)
    assert 'class="season-range" data-min="1950" data-max="2026"' in out
    # two range handles, defaulting to the full window
    assert 'id="season-from" type="range" min="1950" max="2026" step="1" value="1950"' in out
    assert 'id="season-to" type="range" min="1950" max="2026" step="1" value="2026"' in out
    assert 'aria-label="Earliest season"' in out
    assert 'aria-label="Latest season"' in out


def test_season_control_mobile_selects_cover_every_season():
    out = bc.render_season_control(1950, 2026)
    assert 'id="season-from-sel"' in out
    assert 'id="season-to-sel"' in out
    # one <option> per season, in each of the two selects
    assert out.count('<option value="1998">1998</option>') == 2
    assert out.count("<option") == 2 * (2026 - 1950 + 1)
    # each select opens on its own end of the range
    assert '<option value="1950" selected>1950</option>' in out
    assert '<option value="2026" selected>2026</option>' in out
