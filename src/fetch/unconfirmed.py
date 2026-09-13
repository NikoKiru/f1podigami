"""Bookkeeping for rounds OpenF1 filled ahead of Jolpica (data/unconfirmed.json).

fetch_openf1.py records each round it writes together with the datasets it
wrote (``pending``). Each Jolpica fetcher calls :func:`confirm_on_disk` with the
rounds the API actually returned this run: its dataset leaves ``pending`` for
those rounds, and an entry with nothing left pending is dropped. Per dataset on
purpose — two Jolpica feeds can disagree about the same race for an hour (#239),
so podiums arriving does not confirm race results.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from datalib import repository  # noqa: E402


def confirm(entries: list[dict], dataset: str, rounds: set[tuple[str, str]]) -> list[dict]:
    """``entries`` with ``dataset`` confirmed for ``rounds``; emptied entries dropped."""
    kept = []
    for e in entries:
        pending = list(e["pending"])
        if (e["season"], e["round"]) in rounds and dataset in pending:
            pending.remove(dataset)
        if pending:
            kept.append({**e, "pending": pending})
    return kept


def confirm_on_disk(dataset: str, rounds: Iterable[tuple[str, str]]) -> None:
    """Apply :func:`confirm` to data/unconfirmed.json; a no-op when nothing changes."""
    if not (repository.DATA_DIR / "unconfirmed.json").exists():
        return
    entries = [u.model_dump() for u in repository.load_unconfirmed()]
    updated = confirm(entries, dataset, set(rounds))
    if updated == entries:
        return
    repository.save_unconfirmed(updated)
    confirmed = sorted(
        f"{e['season']} R{e['round']}"
        for e in entries
        if dataset in e["pending"] and (e["season"], e["round"]) in set(rounds)
    )
    print(f"Jolpica confirmed {dataset} for {', '.join(confirmed)}")
