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

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from build._layout import driver_name

REPO = Path(__file__).resolve().parents[1]
SLOTS = ("p1", "p2", "p3")
MAX_ISSUES = 5
# GitHub caps issue bodies at 65,536 characters; a table row is ~190 bytes, so
# cap the summary table well under that and say how many rows were dropped.
MAX_SUMMARY_ROWS = 100


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


def _race_label(rev: dict) -> str:
    return f"{rev['season']} R{rev['round']}"


def pr_title_suffix(revisions: list[dict]) -> str:
    if not revisions:
        return ""
    if len(revisions) == 1:
        return issue_title(revisions[0])
    # Revisions are already sorted by season/round, so the first and last
    # entries bound the span.
    first, last = _race_label(revisions[0]), _race_label(revisions[-1])
    span = f"({first})" if first == last else f"({first}–{last})"
    return f"Podium revised: {len(revisions)} races {span}"


def issue_markdown(rev: dict) -> str:
    """Title on the first line, a blank line, then the body (the workflow splits them).

    Driver names are shown as the site bills them (via build._layout.driver_name);
    the data keeps the API's spelling.
    """
    lines = [
        issue_title(rev),
        "",
        "A data update changed a podium the site had already published.",
        "",
        "| | Podium | Verdict |",
        "|---|---|---|",
        f"| Before | {' / '.join(driver_name(n) for n in rev['before'])} | {rev['verdictBefore']} |",
        f"| After | {' / '.join(driver_name(n) for n in rev['after'])} | {rev['verdictAfter']} |",
        "",
        "The data PR still auto-merges. Check the official classification on formula1.com. "
        "If the new podium is wrong, report it upstream "
        "(https://github.com/jolpica/jolpica-f1/issues): the fetchers re-read the whole "
        "season on every run, so a local revert would be overwritten.",
    ]
    return "\n".join(lines) + "\n"


def summary_markdown(revisions: list[dict]) -> str:
    """One file for a mass revision (a mid-season renumbering, a --full run).

    Title on the first line, a blank line, then one table row per race —
    same shape as :func:`issue_markdown` but covering every revision instead
    of opening one issue each (which could hit GitHub's secondary rate limit
    mid-loop).
    """
    lines = [
        pr_title_suffix(revisions),
        "",
        "A data update changed several podiums the site had already published.",
        "",
        "| Race | Before | After | Verdict |",
        "|---|---|---|---|",
    ]
    for rev in revisions[:MAX_SUMMARY_ROWS]:
        race = f"{rev['season']} R{rev['round']} {rev['raceName']}"
        before = " / ".join(driver_name(n) for n in rev["before"])
        after = " / ".join(driver_name(n) for n in rev["after"])
        lines.append(
            f"| {race} | {before} | {after} | {rev['verdictBefore']} → {rev['verdictAfter']} |"
        )
    if len(revisions) > MAX_SUMMARY_ROWS:
        lines.append(f"…and {len(revisions) - MAX_SUMMARY_ROWS} more.")
    lines += [
        "",
        "The data PR still auto-merges. Check the official classification on formula1.com. "
        "If a new podium is wrong, report it upstream "
        "(https://github.com/jolpica/jolpica-f1/issues): the fetchers re-read the whole "
        "season on every run, so a local revert would be overwritten.",
    ]
    return "\n".join(lines) + "\n"


def write_revision_files(out_dir: Path, revisions: list[dict]) -> None:
    """One ``<season>-<round>.md`` per revision, or a single ``summary.md``
    when there are more than :data:`MAX_ISSUES` (see :func:`summary_markdown`).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if len(revisions) > MAX_ISSUES:
        (out_dir / "summary.md").write_text(summary_markdown(revisions), encoding="utf-8")
        return
    for rev in revisions:
        issue = out_dir / f"{rev['season']}-{rev['round']}.md"
        issue.write_text(issue_markdown(rev), encoding="utf-8")


def _git_show(path: str) -> str | None:
    """``HEAD:<path>`` as text, or None when git or the file is unavailable."""
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout


def _parse_list(text: str | None) -> list[dict]:
    """A JSON list, or [] for anything missing or unparseable (fail quiet, like the guards)."""
    try:
        data = json.loads(text) if text else []
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def main(argv: list[str] | None = None) -> int:
    # A GitHub Actions runner is UTF-8, but this also runs from a plain
    # PowerShell/cp1252 console; titles below carry "—" and "→". Widen what
    # stdout can encode before anything is printed, rather than risk losing
    # the $GITHUB_OUTPUT/issue-file writes below to a UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="one issue file per revision, or one summary file above MAX_ISSUES",
    )
    args = ap.parse_args(argv)

    data = REPO / "data"

    def tree(name: str) -> list[dict]:
        path = data / name
        return _parse_list(path.read_text(encoding="utf-8") if path.exists() else None)

    revisions = podium_revisions(
        _parse_list(_git_show("data/podiums.json")),
        tree("podiums.json"),
        _parse_list(_git_show("data/combos.json")),
        tree("combos.json"),
    )

    write_revision_files(args.out_dir, revisions)

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        # Titles are single-line by construction; never hand API-derived text to
        # the key=value format of $GITHUB_OUTPUT unflattened.
        title = pr_title_suffix(revisions).replace("\n", " ")
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"revised={'true' if revisions else 'false'}\n")
            fh.write(f"title={title}\n")

    # Printing last: everything a caller needs (issue files, $GITHUB_OUTPUT)
    # is already on disk, so a console that still can't encode this text
    # loses nothing but the log line.
    if revisions:
        for rev in revisions:
            print(issue_title(rev))
    else:
        print("No published podium changed.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
