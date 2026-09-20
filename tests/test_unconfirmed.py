"""Bookkeeping for rounds OpenF1 filled ahead of Jolpica (src/fetch/unconfirmed.py).

Confirmation is per dataset on purpose: two Jolpica feeds can disagree about the
same race for an hour (#239), so podiums arriving must not confirm race results.
"""

from fetch.unconfirmed import confirm, confirm_on_disk

RACE = {
    "season": "2026",
    "round": "14",
    "kind": "race",
    "pending": ["podiums", "race_results"],
    "since": "2026-09-13T15:00:00+00:00",
}
QUALI = {
    "season": "2026",
    "round": "15",
    "kind": "qualifying",
    "pending": ["qualifying"],
    "since": "2026-09-25T13:00:00+00:00",
}


def test_confirming_one_dataset_keeps_the_round_pending():
    assert confirm([RACE], "podiums", {("2026", "14")}) == [{**RACE, "pending": ["race_results"]}]


def test_confirming_the_last_dataset_drops_the_round():
    once = confirm([RACE], "podiums", {("2026", "14")})
    assert confirm(once, "race_results", {("2026", "14")}) == []


def test_other_rounds_and_datasets_are_untouched():
    assert confirm([RACE, QUALI], "qualifying", {("2026", "14")}) == [RACE, QUALI]
    assert confirm([RACE, QUALI], "qualifying", {("2026", "15")}) == [RACE]


def test_confirm_does_not_mutate_its_input():
    entries = [{**RACE, "pending": list(RACE["pending"])}]
    confirm(entries, "podiums", {("2026", "14")})
    assert entries[0]["pending"] == ["podiums", "race_results"]


def test_confirm_on_disk_updates_the_file(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_unconfirmed([RACE])
    confirm_on_disk("race_results", [("2026", "14")])
    assert [u.model_dump() for u in repository.load_unconfirmed()] == [
        {**RACE, "pending": ["podiums"]}
    ]


def test_confirm_on_disk_accepts_rounds_as_a_generator(tmp_path, monkeypatch, capsys):
    """The rounds are used twice, to confirm and then to log, so a one-shot
    iterable must still update the file and name the round it confirmed."""
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    repository.save_unconfirmed([RACE])
    confirm_on_disk("race_results", (key for key in [("2026", "14")]))
    assert [u.model_dump() for u in repository.load_unconfirmed()] == [
        {**RACE, "pending": ["podiums"]}
    ]
    assert "Jolpica confirmed race_results for 2026 R14" in capsys.readouterr().out


def test_confirm_on_disk_without_the_file_is_a_no_op(tmp_path, monkeypatch):
    from datalib import repository

    monkeypatch.setattr(repository, "DATA_DIR", tmp_path)
    confirm_on_disk("podiums", [("2026", "14")])
    assert not (tmp_path / "unconfirmed.json").exists()
