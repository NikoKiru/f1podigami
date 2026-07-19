"""Tests for the in-run results watcher (wait_for_results).

GitHub delivers only a fraction of the requested cron slots (observed ~1/hour
against a 15-min schedule), so a run that fetches before the API has published
the finished race costs a *full hour* before the next retry. The watcher closes
that gap: once the guard says a race is due, the update job holds the runner and
polls the aggregate results feed itself until the round appears, then runs the
pipeline exactly once.

Time and network are injected so these tests are instant and offline.
"""

from wait_for_results import latest_published_round, wait_for_round


def payload(round_: str | None) -> dict:
    """A minimal /{season}/last/results.json body carrying ``round_``."""
    races = [] if round_ is None else [{"round": round_}]
    return {"MRData": {"RaceTable": {"Races": races}}}


class Clock:
    """Monotonic stand-in that only advances when the watcher sleeps."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


# --- latest_published_round: reading the feed


def test_latest_published_round_reads_the_round():
    assert latest_published_round(payload("10")) == 10


def test_latest_published_round_none_when_feed_has_no_races():
    assert latest_published_round(payload(None)) is None


def test_latest_published_round_none_on_garbage():
    assert latest_published_round({"nope": True}) is None
    assert latest_published_round(payload("not-a-round")) is None


# --- wait_for_round: the poll loop


def test_returns_immediately_when_results_are_already_published():
    clock = Clock()
    calls = []

    def fetch():
        calls.append(1)
        return payload("10")

    assert wait_for_round(10, fetch, timeout_s=3600, interval_s=180, sleep=clock.sleep, now=clock)
    assert len(calls) == 1
    assert clock.slept == []  # never stalls the runner when data is ready


def test_polls_until_the_round_appears():
    clock = Clock()
    feed = [payload("9"), payload("9"), payload("10")]

    assert wait_for_round(
        10, lambda: feed.pop(0), timeout_s=3600, interval_s=180, sleep=clock.sleep, now=clock
    )
    assert clock.slept == [180, 180]


def test_gives_up_after_the_timeout():
    clock = Clock()

    assert not wait_for_round(
        10, lambda: payload("9"), timeout_s=600, interval_s=180, sleep=clock.sleep, now=clock
    )
    # Stops once another sleep would overrun the budget, rather than spinning.
    assert sum(clock.slept) <= 600


def test_a_fetch_error_is_survived_and_retried():
    clock = Clock()
    feed = [None, payload("10")]

    assert wait_for_round(
        10, lambda: feed.pop(0), timeout_s=3600, interval_s=180, sleep=clock.sleep, now=clock
    )
    assert clock.slept == [180]


def test_a_newer_round_than_expected_also_satisfies_the_wait():
    clock = Clock()
    assert wait_for_round(
        10, lambda: payload("11"), timeout_s=3600, interval_s=180, sleep=clock.sleep, now=clock
    )
