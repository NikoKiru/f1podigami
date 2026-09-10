"""Flag a data update that changes a podium the site has already published.

Jolpica can revise a settled race, and not always for the better. The 2026
Monaco GP's third place went Hadjar (Jun 8) -> Gasly (Jun 16) -> Hadjar (Sep 6):
for 82 days the site listed Antonelli / Hamilton / Gasly as a new trio that
officially never happened, and both edits rode in on routine data PRs nobody
read. The fetchers re-read the whole current season on every run (and all of
history on the weekly --full run), so any upstream edit lands here silently
unless something looks.

This compares every podium already on ``main`` (``HEAD``) with the refreshed
working tree. A change never blocks the merge — the data PR still auto-merges,
since holding it would also hold every later race — but it retitles the PR and
opens an issue a human will see.

:func:`podium_revisions` works on parsed JSON (no IO) so it is trivially
unit-testable; :func:`main` is the CLI glue.
"""

from __future__ import annotations

SLOTS = ("p1", "p2", "p3")


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _surname(name: str) -> str:
    return name.split()[-1] if name.strip() else name


def verdict(driver_ids: list[str], season: str, rnd: str, combos: list[dict]) -> str:
    """What the site said about this trio at this race: its debut or the Nth time."""
    key = sorted(driver_ids)
    for c in combos:
        if sorted(c["driverIds"]) != key:
            continue
        races = [(r["season"], r["round"]) for r in c.get("races", [])]
        if (season, rnd) in races:
            n = races.index((season, rnd)) + 1
            return "PODIGAMI (first time)" if n == 1 else f"{_ordinal(n)} time"
    return "unknown"


def podium_revisions(
    before: list[dict],
    after: list[dict],
    before_combos: list[dict] | None = None,
    after_combos: list[dict] | None = None,
) -> list[dict]:
    """Every race present in both payloads whose p1/p2/p3 drivers changed.

    A race only in ``after`` is a new result, not a revision. Detection is on
    driver IDs, so a renamed driver with an unchanged podium is not flagged.
    """
    old = {(p["season"], p["round"]): p for p in before}
    revisions: list[dict] = []
    for p in sorted(after, key=lambda p: (int(p["season"]), int(p["round"]))):
        prev = old.get((p["season"], p["round"]))
        if prev is None:
            continue
        before_ids = [prev[s]["driverId"] for s in SLOTS]
        after_ids = [p[s]["driverId"] for s in SLOTS]
        if before_ids == after_ids:
            continue
        revisions.append(
            {
                "season": p["season"],
                "round": p["round"],
                "raceName": p["raceName"],
                "beforeIds": before_ids,
                "afterIds": after_ids,
                "before": [prev[s]["name"] for s in SLOTS],
                "after": [p[s]["name"] for s in SLOTS],
                "trioChanged": set(before_ids) != set(after_ids),
                "verdictBefore": verdict(before_ids, p["season"], p["round"], before_combos or []),
                "verdictAfter": verdict(after_ids, p["season"], p["round"], after_combos or []),
            }
        )
    return revisions


def describe(rev: dict) -> str:
    """'Gasly → Hadjar' when one driver swapped; otherwise the order or both trios."""
    out = [
        n for n, d in zip(rev["before"], rev["beforeIds"], strict=True) if d not in rev["afterIds"]
    ]
    new = [
        n for n, d in zip(rev["after"], rev["afterIds"], strict=True) if d not in rev["beforeIds"]
    ]
    if not out:
        return "order changed"
    if len(out) == 1:
        return f"{_surname(out[0])} → {_surname(new[0])}"
    return (
        " / ".join(_surname(n) for n in rev["before"])
        + " → "
        + " / ".join(_surname(n) for n in rev["after"])
    )


def issue_title(rev: dict) -> str:
    return f"Podium revised: {rev['season']} R{rev['round']} {rev['raceName']} — {describe(rev)}"


def pr_title_suffix(revisions: list[dict]) -> str:
    if not revisions:
        return ""
    if len(revisions) == 1:
        return issue_title(revisions[0])
    return f"Podium revised: {len(revisions)} races"


def issue_markdown(rev: dict) -> str:
    """Title on the first line, a blank line, then the body (the workflow splits them)."""
    lines = [
        issue_title(rev),
        "",
        "A data update changed a podium the site had already published.",
        "",
        "| | Podium | Verdict |",
        "|---|---|---|",
        f"| Before | {' / '.join(rev['before'])} | {rev['verdictBefore']} |",
        f"| After | {' / '.join(rev['after'])} | {rev['verdictAfter']} |",
        "",
        "The data PR still auto-merges. Check the official classification on formula1.com. "
        "If the new podium is wrong, report it upstream "
        "(https://github.com/jolpica/jolpica-f1/issues): the fetchers re-read the whole "
        "season on every run, so a local revert would be overwritten.",
    ]
    return "\n".join(lines) + "\n"
