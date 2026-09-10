"""Tests for the podium revision alert (src/check_revisions.py).

Jolpica rewrote the 2026 Monaco GP's third place twice: Hadjar (Jun 8) -> Gasly
(Jun 16) -> Hadjar (Sep 6). Both edits rode in on routine data PRs and nobody
noticed, so for 82 days the site listed a trio that never officially happened.
These lock in the check that makes such an edit loud.
"""

from __future__ import annotations

import json
from pathlib import Path

import check_revisions
from check_revisions import (
    describe,
    issue_markdown,
    issue_title,
    podium_revisions,
    pr_title_suffix,
    verdict,
)

NAMES = {
    "antonelli": "Andrea Kimi Antonelli",
    "hamilton": "Lewis Hamilton",
    "hadjar": "Isack Hadjar",
    "gasly": "Pierre Gasly",
    "russell": "George Russell",
    "piastri": "Oscar Piastri",
    "leclerc": "Charles Leclerc",
    "max_verstappen": "Max Verstappen",
    "norris": "Lando Norris",
}


def pod(season: str, rnd: str, race: str, p1: str, p2: str, p3: str) -> dict:
    def ref(driver_id: str) -> dict:
        return {"driverId": driver_id, "name": NAMES[driver_id]}

    return {
        "season": season,
        "round": rnd,
        "raceName": race,
        "p1": ref(p1),
        "p2": ref(p2),
        "p3": ref(p3),
    }


def combo(ids: list[str], races: list[tuple[str, str, str]]) -> dict:
    """The two combos.json fields the verdict reads."""
    return {
        "driverIds": ids,
        "races": [{"season": s, "round": r, "raceName": n} for s, r, n in races],
    }


MONACO = ("2026", "6", "Monaco Grand Prix")
JUN8 = [pod(*MONACO, "antonelli", "hamilton", "hadjar")]
JUN16 = [pod(*MONACO, "antonelli", "hamilton", "gasly")]
SEP6 = [pod(*MONACO, "antonelli", "hamilton", "hadjar")]


def test_identical_data_has_no_revisions():
    assert podium_revisions(JUN8, JUN8) == []


def test_a_new_round_is_not_a_revision():
    later = [*JUN8, pod("2026", "7", "Barcelona Grand Prix", "hamilton", "russell", "norris")]
    assert podium_revisions(JUN8, later) == []


def test_the_real_monaco_history_flags_both_edits():
    first = podium_revisions(JUN8, JUN16)
    second = podium_revisions(JUN16, SEP6)
    assert [describe(r) for r in first] == ["Hadjar → Gasly"]
    assert [describe(r) for r in second] == ["Gasly → Hadjar"]
    assert first[0]["trioChanged"] is True
    assert first[0]["beforeIds"] == ["antonelli", "hamilton", "hadjar"]
    assert first[0]["afterIds"] == ["antonelli", "hamilton", "gasly"]


def test_a_disqualification_names_the_driver_who_dropped_out():
    """Spa 2024: Russell crossed the line first and was disqualified hours later."""
    spa = ("2024", "14", "Belgian Grand Prix")
    rev = podium_revisions(
        [pod(*spa, "russell", "hamilton", "piastri")], [pod(*spa, "hamilton", "piastri", "leclerc")]
    )
    assert [describe(r) for r in rev] == ["Russell → Leclerc"]


def test_an_order_only_change_is_flagged_but_keeps_the_trio():
    race = ("2026", "11", "Hungarian Grand Prix")
    rev = podium_revisions(
        [pod(*race, "max_verstappen", "norris", "leclerc")],
        [pod(*race, "norris", "max_verstappen", "leclerc")],
    )
    assert len(rev) == 1
    assert rev[0]["trioChanged"] is False
    assert describe(rev[0]) == "order changed"


def test_a_two_driver_change_lists_both_trios():
    rev = podium_revisions(JUN8, [pod(*MONACO, "antonelli", "russell", "piastri")])
    assert describe(rev[0]) == "Antonelli / Hamilton / Hadjar → Antonelli / Russell / Piastri"


def test_verdict_is_the_trios_occurrence_at_that_race():
    trio = ["antonelli", "hamilton", "hadjar"]
    debut = [combo(trio, [MONACO])]
    third = [
        combo(["hadjar", "antonelli", "hamilton"], [("2025", "3", "A"), ("2025", "9", "B"), MONACO])
    ]
    assert verdict(trio, "2026", "6", debut) == "PODIGAMI (first time)"
    assert verdict(trio, "2026", "6", third) == "3rd time"
    assert verdict(trio, "2026", "6", []) == "unknown"


def test_revisions_carry_the_verdict_from_each_side():
    before_combos = [combo(["antonelli", "hamilton", "hadjar"], [MONACO])]
    after_combos = [combo(["antonelli", "hamilton", "gasly"], [MONACO])]
    rev = podium_revisions(JUN8, JUN16, before_combos, after_combos)[0]
    assert rev["verdictBefore"] == "PODIGAMI (first time)"
    assert rev["verdictAfter"] == "PODIGAMI (first time)"


def test_titles():
    rev = podium_revisions(JUN8, JUN16)
    assert issue_title(rev[0]) == "Podium revised: 2026 R6 Monaco Grand Prix — Hadjar → Gasly"
    assert pr_title_suffix([]) == ""
    assert pr_title_suffix(rev) == issue_title(rev[0])
    assert pr_title_suffix(rev + rev) == "Podium revised: 2 races"


def test_issue_markdown_puts_the_title_first_then_a_table():
    rev = podium_revisions(JUN8, JUN16)[0]
    lines = issue_markdown(rev).splitlines()
    assert lines[0] == issue_title(rev)
    assert lines[1] == ""
    assert "| Before | Kimi Antonelli / Lewis Hamilton / Isack Hadjar | unknown |" in lines
    assert "| After | Kimi Antonelli / Lewis Hamilton / Pierre Gasly | unknown |" in lines


def _cli(tmp_path, monkeypatch, head: dict[str, list | None], tree: dict[str, list]):
    """Run main() against a fake HEAD (git show) and a fake working tree."""
    (tmp_path / "data").mkdir()
    for name, payload in tree.items():
        (tmp_path / "data" / name).write_text(json.dumps(payload), encoding="utf-8")

    def fake_git_show(path: str) -> str | None:
        payload = head.get(Path(path).name)
        return None if payload is None else json.dumps(payload)

    out = tmp_path / "github_output"
    monkeypatch.setattr(check_revisions, "REPO", tmp_path)
    monkeypatch.setattr(check_revisions, "_git_show", fake_git_show)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert check_revisions.main(["--out-dir", str(tmp_path / "issues")]) == 0
    return out.read_text(encoding="utf-8").splitlines()


def test_cli_reports_a_revision_and_writes_its_issue(tmp_path, monkeypatch):
    lines = _cli(
        tmp_path,
        monkeypatch,
        head={
            "podiums.json": JUN8,
            "combos.json": [combo(["antonelli", "hamilton", "hadjar"], [MONACO])],
        },
        tree={
            "podiums.json": JUN16,
            "combos.json": [combo(["antonelli", "hamilton", "gasly"], [MONACO])],
        },
    )
    assert "revised=true" in lines
    assert "title=Podium revised: 2026 R6 Monaco Grand Prix — Hadjar → Gasly" in lines
    issue = (tmp_path / "issues" / "2026-6.md").read_text(encoding="utf-8")
    assert issue.startswith("Podium revised: 2026 R6 Monaco Grand Prix — Hadjar → Gasly\n\n")
    assert "PODIGAMI (first time)" in issue


def test_cli_is_quiet_when_nothing_changed(tmp_path, monkeypatch):
    lines = _cli(
        tmp_path,
        monkeypatch,
        head={"podiums.json": JUN8, "combos.json": []},
        tree={"podiums.json": JUN8, "combos.json": []},
    )
    assert lines == ["revised=false", "title="]
    assert list((tmp_path / "issues").iterdir()) == []


def test_cli_treats_a_missing_head_file_as_no_revision(tmp_path, monkeypatch):
    """A first-ever run (or a git hiccup) must not invent revisions or crash."""
    lines = _cli(
        tmp_path,
        monkeypatch,
        head={"podiums.json": None, "combos.json": None},
        tree={"podiums.json": JUN16, "combos.json": []},
    )
    assert lines == ["revised=false", "title="]
