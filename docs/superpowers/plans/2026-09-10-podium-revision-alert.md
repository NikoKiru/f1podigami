# Podium Revision Alert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flag every automated data update that changes a podium the site has already published, without ever blocking the data PR's auto-merge.

**Architecture:** A new CLI, `src/check_revisions.py`, compares `HEAD:data/podiums.json` (what `main` publishes) with the refreshed working tree. It works out each changed race's before/after trio and the site's verdict for each (from `combos.json`). `update.yml` runs it right after the pipeline: a revision retitles the data PR, labels it `podium-revised`, and opens one issue per revision. This is PR 1 of 3 from `docs/superpowers/specs/2026-09-10-openf1-fast-lane-design.md` (Section 5).

**Tech Stack:** Python 3.11+ (stdlib only), pytest, GitHub Actions + `gh` CLI.

## Global Constraints

- Python `>=3.11`; ruff `>=0.15.22,<0.16` — line length 100, rules `E,W,F,I,UP,B,C4` (so `zip()` needs `strict=`). `python -m ruff check .` and `python -m ruff format --check .` must pass.
- No new dependencies (stdlib + what `requirements*.txt` already pins).
- Tests are offline and must not depend on committed `data/` *values* — a test that can fail on live data re-creates the silent-stall class (CLAUDE.md, "Guardrail for new work").
- A revision **never** fails the run or blocks the merge: the data PR still auto-merges.
- Tokens: PR create/edit/merge uses `secrets.DATA_PUSH_TOKEN` (Contents + Pull requests only, **no Issues**); labels and issues use `secrets.GITHUB_TOKEN` (the workflow grants `issues: write`, `pull-requests: write`).
- Every PR updates `RELEASE_NOTES.md` (dated heading, category, PR number) and README/CLAUDE.md where behaviour is described.
- Branch: `feat/podium-revision-alert`, cut from `docs/openf1-fast-lane-spec` (which already carries the spec, the Sep 8 research note and these plans); PR into `develop`.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD
  ```

---

## File Structure

| File | Responsibility |
|---|---|
| `src/check_revisions.py` (create) | Pure revision detection + text rendering; thin CLI that reads git/working tree and writes `$GITHUB_OUTPUT` + one issue file per revision |
| `tests/test_check_revisions.py` (create) | Unit tests for the pure functions and the CLI glue |
| `.github/workflows/update.yml` (modify) | Run the detector; retitle/label the PR; open issues |
| `CLAUDE.md`, `README.md`, `RELEASE_NOTES.md` (modify) | Document the alert |

---

### Task 0: Branch

- [ ] **Step 1: Create the feature branch from the spec branch**

```bash
git switch docs/openf1-fast-lane-spec
git switch -c feat/podium-revision-alert
git log --oneline -4
```
Expected: the top commits are the plan/spec/research-note commits on top of `develop`'s tip.

---

### Task 1: Revision detection core

**Files:**
- Create: `src/check_revisions.py`
- Test: `tests/test_check_revisions.py`

**Interfaces:**
- Produces (used by Task 2 and nothing else):
  - `podium_revisions(before: list[dict], after: list[dict], before_combos: list[dict] | None = None, after_combos: list[dict] | None = None) -> list[dict]`. Each revision dict has keys `season, round, raceName, beforeIds, afterIds, before, after, trioChanged, verdictBefore, verdictAfter`.
  - `verdict(driver_ids: list[str], season: str, rnd: str, combos: list[dict]) -> str`
  - `describe(rev: dict) -> str`, `issue_title(rev: dict) -> str`, `pr_title_suffix(revisions: list[dict]) -> str`, `issue_markdown(rev: dict) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_check_revisions.py`:

```python
"""Tests for the podium revision alert (src/check_revisions.py).

Jolpica rewrote the 2026 Monaco GP's third place twice: Hadjar (Jun 8) -> Gasly
(Jun 16) -> Hadjar (Sep 6). Both edits rode in on routine data PRs and nobody
noticed, so for 82 days the site listed a trio that never officially happened.
These lock in the check that makes such an edit loud.
"""

from __future__ import annotations

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

    return {"season": season, "round": rnd, "raceName": race, "p1": ref(p1), "p2": ref(p2), "p3": ref(p3)}


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
    third = [combo(["hadjar", "antonelli", "hamilton"], [("2025", "3", "A"), ("2025", "9", "B"), MONACO])]
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
    assert "| Before | Andrea Kimi Antonelli / Lewis Hamilton / Isack Hadjar | unknown |" in lines
    assert "| After | Andrea Kimi Antonelli / Lewis Hamilton / Pierre Gasly | unknown |" in lines
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_check_revisions.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'check_revisions'`.

- [ ] **Step 3: Write the implementation**

Create `src/check_revisions.py`:

```python
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

REPO = Path(__file__).resolve().parents[1]
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
    out = [n for n, d in zip(rev["before"], rev["beforeIds"], strict=True) if d not in rev["afterIds"]]
    new = [n for n, d in zip(rev["after"], rev["afterIds"], strict=True) if d not in rev["beforeIds"]]
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_check_revisions.py -q`
Expected: `10 passed`.

- [ ] **Step 5: Lint, format, commit**

```bash
python -m ruff check src/check_revisions.py tests/test_check_revisions.py
python -m ruff format src/check_revisions.py tests/test_check_revisions.py
git add src/check_revisions.py tests/test_check_revisions.py
git commit -m "Detect podium revisions between two podiums.json payloads" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 2: CLI glue

**Files:**
- Modify: `src/check_revisions.py` (append)
- Test: `tests/test_check_revisions.py` (append)

**Interfaces:**
- Consumes: everything from Task 1.
- Produces: `python src/check_revisions.py --out-dir DIR`. Writes `revised=true|false` and `title=<pr_title_suffix>` to `$GITHUB_OUTPUT`, and `DIR/<season>-<round>.md` (`issue_markdown`) per revision. Exits 0 always.

- [ ] **Step 1: Write the failing tests**

Replace the import block at the top of `tests/test_check_revisions.py` (everything from `from __future__ import annotations` down to the closing `)` of `from check_revisions import (...)`) with:

```python
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
```

Then append to the end of the file:

```python
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
        head={"podiums.json": JUN8, "combos.json": [combo(["antonelli", "hamilton", "hadjar"], [MONACO])]},
        tree={"podiums.json": JUN16, "combos.json": [combo(["antonelli", "hamilton", "gasly"], [MONACO])]},
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_check_revisions.py -q`
Expected: the three new tests fail with `AttributeError: module 'check_revisions' has no attribute 'main'` (or `_git_show`).

- [ ] **Step 3: Write the implementation**

Append to `src/check_revisions.py`:

```python
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, required=True, help="one issue file per revision")
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

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for rev in revisions:
        print(issue_title(rev))
        issue = args.out_dir / f"{rev['season']}-{rev['round']}.md"
        issue.write_text(issue_markdown(rev), encoding="utf-8")
    if not revisions:
        print("No published podium changed.")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        # Titles are single-line by construction; never hand API-derived text to
        # the key=value format of $GITHUB_OUTPUT unflattened.
        title = pr_title_suffix(revisions).replace("\n", " ")
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"revised={'true' if revisions else 'false'}\n")
            fh.write(f"title={title}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_check_revisions.py -q`
Expected: `13 passed`.

- [ ] **Step 5: Smoke-test against the real repo**

Run: `python src/check_revisions.py --out-dir "$TMPDIR/rev-smoke"` (PowerShell: `python src/check_revisions.py --out-dir "$env:TEMP\rev-smoke"`)
Expected: `No published podium changed.` (the working tree equals `HEAD`).

- [ ] **Step 6: Lint, format, commit**

```bash
python -m ruff check src/check_revisions.py tests/test_check_revisions.py
python -m ruff format src/check_revisions.py tests/test_check_revisions.py
git add src/check_revisions.py tests/test_check_revisions.py
git commit -m "Add the check_revisions CLI for the data-update workflow" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

---

### Task 3: Wire the alert into `update.yml`

**Files:**
- Modify: `.github/workflows/update.yml` (the `update` job's steps between "Fetch latest data and rebuild site" and "Validate datasets")

**Interfaces:**
- Consumes: the Task 2 CLI and its `revised` / `title` outputs.

- [ ] **Step 1: Add the detector step**

Insert immediately **after** the `Fetch latest data and rebuild site` step:

```yaml
      # Jolpica can rewrite a race the site already published: the 2026 Monaco
      # GP's P3 went Hadjar -> Gasly -> Hadjar and both edits merged unread, so
      # the site listed a trio that never officially happened for 82 days.
      # Compare every podium already on main with the refreshed data. A change
      # retitles the PR and opens an issue (below) but never blocks the merge —
      # holding this PR would hold every later race too.
      #
      # Guarded: a scheduled run takes this workflow from develop but checks out
      # main's scripts, so between merging to develop and promoting to main the
      # script is not there yet. Skip rather than fail every data update.
      - name: Detect podium revisions
        id: revisions
        run: |
          if [ -f src/check_revisions.py ]; then
            python src/check_revisions.py --out-dir "$RUNNER_TEMP/podium-revisions"
          else
            echo "check_revisions.py is not on main yet; skipping."
            echo "revised=false" >> "$GITHUB_OUTPUT"
          fi
```

- [ ] **Step 2: Retitle the data PR on a revision**

In the `Open or refresh the data PR and arm auto-merge` step, add `REVISION_TITLE` to `env:` and replace the part of `run:` from `BRANCH="auto/update-data"` to the end with:

```yaml
        env:
          GH_TOKEN: ${{ secrets.DATA_PUSH_TOKEN }}
          REVISION_TITLE: ${{ steps.revisions.outputs.title }}
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/
          if git diff --cached --quiet; then
            echo "No data changes; nothing to do."
            exit 0
          fi
          BRANCH="auto/update-data"
          DATE="$(date -u +%Y-%m-%dT%H:%MZ)"
          TITLE="Update race data $DATE"
          if [ -n "$REVISION_TITLE" ]; then
            TITLE="$TITLE · $REVISION_TITLE"
          fi
          # Dedicated bot-only branch, serialized by the workflow concurrency group,
          # so a plain force-push is safe.
          git checkout -B "$BRANCH"
          git commit -m "$TITLE"
          git push --force origin "$BRANCH"
          if [ -z "$(gh pr list --head "$BRANCH" --state open --json number --jq '.[0].number')" ]; then
            gh pr create --base main --head "$BRANCH" \
              --title "$TITLE" \
              --body "Automated race-data refresh. Auto-merges once all required checks pass."
          else
            # A refresh keeps the title current, so a revision shows even when it
            # lands on a PR that was already open (and clears once it is gone).
            gh pr edit "$BRANCH" --title "$TITLE"
          fi
          gh pr merge --auto --squash --delete-branch "$BRANCH"
```

- [ ] **Step 3: Add the label + issue step**

Insert immediately **after** the PR step (before `Validate datasets`):

```yaml
      # The built-in token, not the PAT: DATA_PUSH_TOKEN carries no Issues
      # permission. One issue per revision, deduplicated by title, left open for
      # a human — it's a notification, not a failure, so nothing auto-closes it.
      - name: Flag podium revisions for a human
        if: steps.revisions.outputs.revised == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REVISIONS_DIR: ${{ runner.temp }}/podium-revisions
        run: |
          gh label create podium-revised --repo "$GITHUB_REPOSITORY" \
            --color FBCA04 --description "A data update changed an already-published podium" 2>/dev/null || true
          gh pr edit auto/update-data --repo "$GITHUB_REPOSITORY" --add-label podium-revised
          existing="$(gh issue list --repo "$GITHUB_REPOSITORY" --label podium-revised \
            --state all --limit 200 --json title --jq '.[].title')"
          for f in "$REVISIONS_DIR"/*.md; do
            [ -e "$f" ] || continue
            title="$(head -n 1 "$f")"
            if printf '%s\n' "$existing" | grep -Fxq -- "$title"; then
              echo "Already reported: $title"
              continue
            fi
            tail -n +3 "$f" > "$RUNNER_TEMP/issue-body.md"
            gh issue create --repo "$GITHUB_REPOSITORY" --title "$title" \
              --label podium-revised --body-file "$RUNNER_TEMP/issue-body.md"
          done
```

- [ ] **Step 4: Check the YAML parses and the step order is right**

Run:
```bash
python -c "import yaml,sys; wf=yaml.safe_load(open('.github/workflows/update.yml',encoding='utf-8')); print([s.get('name') for s in wf['jobs']['update']['steps']])"
```
(If PyYAML is missing: `python -m pip install pyyaml` — dev-only, do not add it to requirements.)
Expected order: `…, 'Fetch latest data and rebuild site', 'Detect podium revisions', 'Open or refresh the data PR and arm auto-merge', 'Flag podium revisions for a human', 'Validate datasets', 'Run tests'`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/update.yml
git commit -m "Flag podium revisions on the data PR and open an issue" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
```

(actionlint runs in CI's `Lint workflows` job; fix anything it reports before merging.)

---

### Task 4: Docs, full verification, PR

**Files:**
- Modify: `CLAUDE.md` (section "Automated data updates (`update.yml`)" and the ⚠️ silent-stall list)
- Modify: `README.md` (the `update.yml` row of the workflow table)
- Modify: `RELEASE_NOTES.md`

- [ ] **Step 1: CLAUDE.md**

In "### Automated data updates (`update.yml`)", after the `watchdog` bullet, add:

```markdown
- A **`Detect podium revisions`** step (`src/check_revisions.py`) compares every podium already on `main` with the refreshed data. A change — Jolpica editing a settled race — retitles the data PR (`Update race data … · Podium revised: 2026 R6 Monaco Grand Prix — Hadjar → Gasly`), labels it `podium-revised`, and opens one issue per revision (deduplicated by title, left open for a human). It never blocks the auto-merge. Issues/labels use `GITHUB_TOKEN` because `DATA_PUSH_TOKEN` has no Issues permission.
```

In the "⚠️ When a finished race doesn't appear" list, after the `#245` bullet, add:

```markdown
- **Silent upstream revisions (#<PR>).** Jolpica rewrote Monaco 2026's P3 twice (Hadjar Jun 8 → Gasly Jun 16 → Hadjar Sep 6); both edits merged in routine data PRs and the site showed a trio that never officially happened for 82 days. Now flagged by the revision alert. The fix for a *wrong* revision is upstream — the fetchers re-read the whole season every run, so a local revert is overwritten.
- **Develop's workflow, main's scripts.** A scheduled run takes `update.yml` from the default branch (`develop`) but the `update` job checks out `main`, so between merging a PR to `develop` and promoting it, the workflow can call a script or flag `main` doesn't have yet. Every data update then fails. Guard any new step that calls a new script (`if [ -f src/<script>.py ]; then …; fi`, with the skip path writing safe step outputs), and after merging to `develop` run a forced update to prove it: `gh workflow run update.yml -f mode=auto -f force=true`.
```

- [ ] **Step 2: README.md**

In the workflow table's `update.yml` row, append this sentence at the end of the cell (before the closing `|`):

```markdown
 A data update that changes an **already-published podium** is flagged — the PR is retitled and labelled `podium-revised` and an issue opens — without blocking the merge.
```

- [ ] **Step 3: RELEASE_NOTES.md**

Under the current date heading (create `## YYYY-MM-DD` at the top if today's is missing), in `### Improvements`:

```markdown
- **A data update that changes a podium the site already published now raises an alert.** Jolpica can edit a settled race after the fact: the 2026 Monaco GP's third place went Hadjar → Gasly → Hadjar in its data, and both edits merged in routine automated updates, so for 82 days the site listed Antonelli / Hamilton / Gasly as a new trio that never officially happened. Each automated refresh now compares every published podium with the new data; a change retitles the data PR, labels it `podium-revised` and opens an issue showing the before/after trio and both verdicts. The update still merges on its own (#<PR>)
```

- [ ] **Step 4: Full verification (mirrors CI)**

```bash
python -m ruff check .
python -m ruff format --check .
PYTHONPATH=src python -m datalib.validate
python -m pytest -q
```
Expected: ruff clean; `Validated N datasets OK.`; all tests pass (the suite builds `dist/` once via the `dist` fixture).

- [ ] **Step 5: Commit and open the PR**

```bash
git add CLAUDE.md README.md RELEASE_NOTES.md
git commit -m "Document the podium revision alert" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
git push -u origin feat/podium-revision-alert
gh pr create --base develop --title "Flag data updates that change an already-published podium" --body-file - <<'EOF'
## Summary
PR 1 of 3 from the OpenF1 fast-lane spec (`docs/superpowers/specs/2026-09-10-openf1-fast-lane-design.md`). Jolpica rewrote Monaco 2026's P3 twice and both edits merged unread; the site showed a trio that never officially happened for 82 days. Every automated refresh now compares published podiums with the new data and makes any change loud, without blocking the merge. Also lands the spec, the Sep 8 latency research note and the three implementation plans.

## Changes
- `src/check_revisions.py`: detects changed podiums (HEAD vs working tree), with before/after trio and the site's verdict for each
- `update.yml`: retitles the data PR, labels it `podium-revised`, opens one issue per revision (built-in token; the PAT has no Issues permission)
- Docs: CLAUDE.md, README, RELEASE_NOTES; spec + research note + plans under `docs/`

## Testing
- `python -m pytest -q` (13 new tests replay the real Monaco history, a Spa-2024-style disqualification, order-only and two-driver changes, and the CLI glue)
- `python -m ruff check .` / `python -m ruff format --check .`
- `PYTHONPATH=src python -m datalib.validate`

## Checklist
- [x] Lint and format pass
- [x] Tests pass
- [x] No security issues introduced (issue/label writes use the least-privileged built-in token)
- [x] RELEASE_NOTES.md updated

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD
EOF
```

- [ ] **Step 6: Put the PR number in the docs**

Replace `#<PR>` in `CLAUDE.md` and `RELEASE_NOTES.md` with the number `gh pr create` printed, then:

```bash
git add CLAUDE.md RELEASE_NOTES.md
git commit -m "Reference #<number> in the release note" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pzWdc2NQZLoSKCEQGuHsD"
git push
```

- [ ] **Step 7: Merge, promote, clean up**

1. Wait for the 7 required checks: `gh pr checks <number> --watch`. Merge: `gh pr merge <number> --squash --delete-branch`.
   Then prove the develop-workflow/main-scripts window is safe. The merged workflow now runs against `main`, which lacks `check_revisions.py`, so the guarded step must skip:
   ```bash
   gh workflow run update.yml -f mode=auto -f force=true
   sleep 20; run=$(gh run list --workflow=update.yml --limit 1 --json databaseId --jq '.[0].databaseId')
   gh run watch "$run" --exit-status
   gh run view "$run" --log | grep -E "check_revisions.py is not on main yet|No published podium changed"
   ```
   Expected: the run is green and the log shows the skip line. If it fails, revert the merge on `develop` right away; a Spanish-GP-weekend data update depends on it.
2. Promote only when no qualifying or race is within the next 48 h (this changes the race-day workflow):
   ```bash
   gh pr create --base main --head develop --title "Promote develop to main: podium revision alert" \
     --body "Promotes #<number>: data updates that change an already-published podium now retitle the data PR, label it podium-revised and open an issue, without blocking the merge. No data files change."
   gh pr checks <promotion number> --watch   # all 9 required checks, CodeQL included
   gh pr merge <promotion number> --merge    # merge commit, like past promotions
   ```
3. `git switch develop && git pull && git branch -d feat/podium-revision-alert docs/openf1-fast-lane-spec`.
