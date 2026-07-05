"""Contract tests for the typed data-access layer (src/datalib).

The linchpin is `test_dataset_roundtrips_byte_identical`: loading a committed
dataset through its schema and re-serialising it must reproduce the file
byte-for-byte. That proves the schemas are faithful (exact types + key order),
which is what guarantees the builder migration leaves dist/ unchanged and that
validate-on-write never reformats the committed data.
"""

import json

import pytest
from pydantic import ValidationError

from datalib import (
    COMPACT,
    DATA_DIR,
    REGISTRY,
    Combo,
    ModelEval,
    Podigami,
    Podium,
    RaceRef,
    Schedule,
    Soulmates,
    load_combos,
    load_constructor_standings,
    load_current_drivers,
    load_driver_races,
    load_model_eval,
    load_overdue,
    load_podigami,
    load_podiums,
    load_schedule,
    load_soulmates,
)


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_dataset_roundtrips_byte_identical(name):
    """load -> dump reproduces the committed file exactly (no reformatting)."""
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not yet backfilled (run its fetcher)")
    raw = path.read_text(encoding="utf-8")
    adapter = REGISTRY[name]
    model = adapter.validate_python(json.loads(raw))
    dumped = adapter.dump_python(model, mode="json")
    if name in COMPACT:
        redumped = json.dumps(dumped, separators=(",", ":"), ensure_ascii=False)
    else:
        redumped = json.dumps(dumped, indent=2, ensure_ascii=False)
    assert redumped == raw


def test_loaders_return_typed_objects():
    combos = load_combos()
    assert isinstance(combos, list) and isinstance(combos[0], Combo)
    assert isinstance(combos[0].count, int)
    assert isinstance(combos[0].lastRace, RaceRef)
    assert isinstance(combos[0].lastRace.season, str)

    assert isinstance(load_podiums()[0], Podium)
    assert isinstance(load_soulmates(), Soulmates)
    assert isinstance(load_schedule(), Schedule)
    assert isinstance(load_model_eval(), ModelEval)

    pod = load_podigami()
    assert isinstance(pod, Podigami)
    assert isinstance(pod.chanceNextRaceNew, float)

    # smoke: the remaining loaders run and validate without error
    load_current_drivers()
    load_driver_races()
    load_overdue()
    load_constructor_standings()


def test_registry_covers_every_committed_dataset():
    on_disk = {p.name for p in DATA_DIR.glob("*.json")}
    assert on_disk <= set(REGISTRY), "unregistered dataset on disk — add a schema for it"
    missing = set(REGISTRY) - on_disk
    if missing:
        pytest.skip(f"registered datasets awaiting backfill: {sorted(missing)}")


def test_extra_key_is_rejected():
    with pytest.raises(ValidationError):
        RaceRef.model_validate({"season": "2020", "round": "1", "raceName": "X", "unexpected": 1})


def test_missing_field_is_rejected():
    with pytest.raises(ValidationError):
        RaceRef.model_validate({"season": "2020", "round": "1"})


def test_current_drivers_allows_missing_code_and_number():
    """The API omits code/number for some drivers (fetch_current_drivers adds them
    only when present), so the schema must accept a driver with neither — otherwise
    save_current_drivers would crash on a legitimate fetch."""
    payload = {"season": "2026", "drivers": [{"driverId": "x", "name": "Foo Bar"}]}
    REGISTRY["current_drivers.json"].validate_python(payload)  # must not raise


# --- race_results.json / qualifying.json (model v2 raw datasets) -------------

_RACE_RESULTS_SAMPLE = [
    {
        "season": "1950",
        "round": "1",
        "raceName": "British Grand Prix",
        "date": "1950-05-13",
        "circuitId": "silverstone",
        "results": [
            {
                "driverId": "farina",
                "constructorId": "alfa",
                "grid": 1,
                "position": 1,
                "laps": 70,
                "status": "Finished",
            },
            {
                "driverId": "fagioli",
                "constructorId": "alfa",
                "grid": 2,
                "position": None,
                "laps": 62,
                "status": "Engine",
            },
        ],
    },
    {
        "season": "1950",
        "round": "2",
        "raceName": "Monaco Grand Prix",
        "date": "1950-05-21",
        "circuitId": "monaco",
        "results": [
            {
                "driverId": "fangio",
                "constructorId": "alfa",
                "grid": 1,
                "position": 1,
                "laps": 100,
                "status": "Finished",
            },
        ],
    },
]

_QUALIFYING_SAMPLE = [
    {
        "season": "1994",
        "round": "1",
        "results": [
            {"driverId": "senna", "constructorId": "williams", "position": 1},
            {"driverId": "michael_schumacher", "constructorId": "benetton", "position": 2},
        ],
    },
    {"season": "1994", "round": "2", "results": []},
]


def test_save_race_results_writes_compact_and_roundtrips(tmp_path, monkeypatch):
    """The bulky raw datasets are stored compact (one line, no indent) and the
    schema is faithful: save -> load -> dump reproduces the payload exactly."""
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_race_results(_RACE_RESULTS_SAMPLE)

    raw = (tmp_path / "race_results.json").read_text(encoding="utf-8")
    assert "\n" not in raw.strip(), "race_results.json must be written compact"
    assert raw == json.dumps(_RACE_RESULTS_SAMPLE, separators=(",", ":"), ensure_ascii=False)

    loaded = repository.load_race_results()
    assert loaded[0].circuitId == "silverstone"
    assert loaded[0].results[0].position == 1
    assert loaded[0].results[1].position is None  # retirement keeps its row
    assert loaded[0].results[1].status == "Engine"


def test_save_qualifying_writes_compact_and_roundtrips(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_qualifying(_QUALIFYING_SAMPLE)

    raw = (tmp_path / "qualifying.json").read_text(encoding="utf-8")
    assert "\n" not in raw.strip(), "qualifying.json must be written compact"
    assert raw == json.dumps(_QUALIFYING_SAMPLE, separators=(",", ":"), ensure_ascii=False)

    loaded = repository.load_qualifying()
    assert loaded[0].results[0].driverId == "senna"
    assert loaded[1].results == []  # a race with no qualifying rows is legal


def test_save_race_results_rejects_bad_row(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    bad = [dict(_RACE_RESULTS_SAMPLE[0], results=[{"driverId": "farina"}])]  # missing fields
    with pytest.raises(ValidationError):
        repository.save_race_results(bad)
    assert not (tmp_path / "race_results.json").exists(), "validation must gate the write"


def test_save_qualifying_rejects_extra_key(tmp_path, monkeypatch):
    """We deliberately do not store lap times — an unexpected key must fail loudly."""
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    row = {"driverId": "senna", "constructorId": "williams", "position": 1, "q1": "1:20.0"}
    bad = [{"season": "1994", "round": "1", "results": [row]}]
    with pytest.raises(ValidationError):
        repository.save_qualifying(bad)


def test_validate_cli_succeeds_on_committed_data():
    from datalib import validate

    missing = sorted(n for n in REGISTRY if not (DATA_DIR / n).exists())
    if missing:
        pytest.skip(f"registered datasets awaiting backfill: {missing}")
    assert validate.main() == 0


def test_validate_cli_reports_failure(tmp_path, monkeypatch, capsys):
    """Point the CLI at a bad data dir: it must exit nonzero and say what failed."""
    from datalib import validate

    (tmp_path / "podiums.json").write_text("[{}]", encoding="utf-8")  # invalid Podium
    monkeypatch.setattr(validate, "DATA_DIR", tmp_path)

    assert validate.main() == 1
    assert "FAILED" in capsys.readouterr().err


# --- v2 params unions (model v2) ---------------------------------------------


_V2_KNOBS = {
    "sigma0_drv": 0.7,
    "sigma0_con": 1.2,
    "rookie_mu": -0.4,
    "newteam_mu": -0.8,
    "tau_drv": 0.04,
    "tau_con": 0.08,
    "season_var_drv": 0.03,
    "season_var_con": 0.1,
    "reg_var_con": 0.5,
    "depth_race": 6,
    "w_attr": 0.5,
    "depth_qual": 6,
    "w_qual": 0.3,
    "rel_half_life": 20.0,
    "chaos_gamma": 0.5,
    "chaos_eta": 0.7,
    "p_wild": 0.05,
    "t_wild": 2.5,
}


def test_podigami_params_union_accepts_v1_and_v2():
    from datalib import Podigami, PodigamiParams, PodigamiParamsV2

    v1 = {
        "model": "plackett-luce",
        "alpha": 0.1,
        "halfLife": 8.0,
        "offSeason": 0.65,
        "seasonBoost": 0.4,
        "temperature": 1.2,
        "usingConstructors": True,
        "carOverlay": True,
    }
    v2 = {
        "model": "dbpl-v2",
        **_V2_KNOBS,
        "usingQualifying": True,
        "circuitId": "silverstone",
        "nDraws": 512,
        "seed": 20260704,
    }
    assert isinstance(PodigamiParams.model_validate(v1), PodigamiParams)
    assert isinstance(PodigamiParamsV2.model_validate(v2), PodigamiParamsV2)
    # the Podigami.params union must route each shape to the right model
    fields = Podigami.model_fields["params"].annotation
    assert PodigamiParams in getattr(fields, "__args__", (fields,))


def test_model_eval_params_union_and_chosen_model():
    from datalib import ModelParamsV2

    assert isinstance(ModelParamsV2.model_validate(_V2_KNOBS), ModelParamsV2)
    ev = json.loads((DATA_DIR / "model_eval.json").read_text(encoding="utf-8"))
    REGISTRY["model_eval.json"].validate_python(ev)  # committed file still validates


def test_driver_strength_accepts_v2_reliability_fields():
    from datalib import DriverStrength

    ds = DriverStrength.model_validate(
        {
            "driverId": "max_verstappen",
            "name": "Max Verstappen",
            "weight": 2.5,
            "seasonPodiums": 5,
            "recentPodiums": 4,
            "constructorId": "red_bull",
            "constructor": "Red Bull",
            "constructorStrength": 0.9,
            "finishProb": 0.96,
            "uncertainty": 0.21,
        }
    )
    assert ds.finishProb == 0.96 and ds.uncertainty == 0.21
