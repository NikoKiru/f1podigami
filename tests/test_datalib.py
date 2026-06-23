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
    raw = (DATA_DIR / name).read_text(encoding="utf-8")
    adapter = REGISTRY[name]
    model = adapter.validate_python(json.loads(raw))
    redumped = json.dumps(adapter.dump_python(model, mode="json"), indent=2, ensure_ascii=False)
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
    assert on_disk == set(REGISTRY), "REGISTRY and data/*.json have drifted"


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


def test_validate_cli_succeeds_on_committed_data():
    from datalib import validate

    assert validate.main() == 0


def test_validate_cli_reports_failure(tmp_path, monkeypatch, capsys):
    """Point the CLI at a bad data dir: it must exit nonzero and say what failed."""
    from datalib import validate

    (tmp_path / "podiums.json").write_text("[{}]", encoding="utf-8")  # invalid Podium
    monkeypatch.setattr(validate, "DATA_DIR", tmp_path)

    assert validate.main() == 1
    assert "FAILED" in capsys.readouterr().err
