import pytest

from build._names import short_names_by_season, surname


@pytest.mark.parametrize(
    ("full", "want"),
    [
        ("Max Verstappen", "Verstappen"),
        ("Andrea Kimi Antonelli", "Antonelli"),
        ("Wolfgang von Trips", "von Trips"),
        ("Pedro de la Rosa", "de la Rosa"),
        ("Andrea de Cesaris", "de Cesaris"),
        ("Nelson Piquet Jr.", "Piquet Jr."),
        ("Juan Pablo Montoya", "Montoya"),
        ("José Froilán González", "González"),
    ],
)
def test_surname(full, want):
    assert surname(full) == want


def _pod(season, *names):
    return {
        "season": season,
        "round": "1",
        "raceName": "X GP",
        **{f"p{i}": {"driverId": n.lower(), "name": n} for i, n in enumerate(names, 1)},
    }


def test_initial_only_when_a_surname_is_shared_that_season():
    s = short_names_by_season(
        [
            _pod("1962", "Graham Hill", "Phil Hill", "Trevor Taylor"),
            _pod("1963", "Graham Hill", "Jim Clark", "Dan Gurney"),
        ]
    )
    assert s["1962"] == {
        "Graham Hill": "G. Hill",
        "Phil Hill": "P. Hill",
        "Trevor Taylor": "Taylor",
    }
    assert s["1963"]["Graham Hill"] == "Hill"


def test_colliding_initials_fall_back_to_the_display_name():
    s = short_names_by_season(
        [_pod("2000", "Ralf Schumacher", "Rubens Barrichello", "Rob Schumacher")]
    )
    assert s["2000"]["Ralf Schumacher"] == "Ralf Schumacher"
    assert s["2000"]["Rob Schumacher"] == "Rob Schumacher"


def test_both_drivers_of_a_shared_car_are_collected():
    pod = _pod("1955", "Juan Fangio", "Jose Farina", "Maurice Trintignant")
    pod["coDrivers"] = {"p2": [{"driverId": "jean", "name": "Jean Behra"}]}
    pod2 = _pod("1955", "Graham Hill", "Phil Hill", "Dan Gurney")
    s = short_names_by_season([pod, pod2])
    assert s["1955"]["Jean Behra"] == "Behra"
    assert s["1955"]["Graham Hill"] == "G. Hill"
