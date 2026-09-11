"""Tests for the in-run results watcher (wait_for_results).

GitHub delivers only a fraction of the requested cron slots (observed ~1/hour
against a 15-min schedule), so a run that fetches before the API has published
the finished race costs a *full hour* before the next retry. The watcher closes
that gap: once the guard says a race is due, the update job holds the runner and
polls the aggregate results feed itself until the round appears, then runs the
pipeline exactly once.

Time and network are injected so these tests are instant and offline.
"""

from datetime import UTC, datetime

from wait_for_results import latest_published_round, wait_for_round, wait_target


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


# --- cache bypass: the poll must see live data, not a cached body


def test_the_poll_request_bypasses_the_response_cache(monkeypatch):
    """Without a nonce the watcher re-reads one cached body every 3 minutes and
    burns the whole budget on it — the 2026-07-26 hour of nothing."""
    import wait_for_results as wfr
    from fetch.api_cache import CACHE_BUSTER

    seen = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload("11")

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["params"] = kwargs.get("params") or {}
        return Resp()

    monkeypatch.setattr(wfr.requests, "get", fake_get)
    assert wfr._fetch_last_results(2026) is not None
    assert "2026/last/results.json" in seen["url"]
    assert CACHE_BUSTER in seen["params"]


# --- what to wait for (race first, then qualifying) --------------------------------

SCHEDULE = {
    "season": "2026",
    "races": [
        {
            "round": "13",
            "date": "2026-09-06",
            "time": "13:00:00Z",
            "qualifyingDate": "2026-09-05",
            "qualifyingTime": "14:00:00Z",
        },
        {
            "round": "14",
            "date": "2026-09-13",
            "time": "13:00:00Z",
            "qualifyingDate": "2026-09-12",
            "qualifyingTime": "14:00:00Z",
        },
    ],
}


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def test_wait_target_is_the_armed_race_newer_than_the_data():
    podigami = {"asOf": {"season": "2026", "round": "12"}, "postQuali": None}
    assert wait_target(SCHEDULE, podigami, at("2026-09-06 10:00")) == ("race", 2026, 13)


def test_wait_target_falls_back_to_the_next_qualifying():
    podigami = {"asOf": {"season": "2026", "round": "13"}, "postQuali": None}
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 11:00")) == ("qualifying", 2026, 14)


def test_nothing_to_wait_for_once_post_quali_covers_the_round():
    """The quali-day short-circuit: a covered round must not hold the runner."""
    podigami = {
        "asOf": {"season": "2026", "round": "13"},
        "postQuali": {"season": "2026", "round": "14"},
    }
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 18:00")) is None


def test_nothing_to_wait_for_before_any_window_opens():
    podigami = {"asOf": {"season": "2026", "round": "13"}, "postQuali": None}
    assert wait_target(SCHEDULE, podigami, at("2026-09-12 10:59")) is None


# --- the qualifying poll: two cache-busted requests, only the last row -------------


class _Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_qualifying_poll_reads_only_the_final_row(monkeypatch):
    import wait_for_results as wfr
    from fetch.api_cache import CACHE_BUSTER

    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        rnd = "3" if params.get("offset") is not None else "1"
        return _Resp({"MRData": {"total": "45", "RaceTable": {"Races": [{"round": rnd}]}}})

    monkeypatch.setattr(wfr.requests, "get", fake_get)
    assert latest_published_round(wfr._fetch_last_qualifying(2026)) == 3
    assert all("2026/qualifying.json" in url for url, _ in calls)
    assert calls[1][1]["offset"] == 44 and calls[1][1]["limit"] == 1
    assert all(CACHE_BUSTER in params for _, params in calls)


def test_qualifying_poll_is_none_on_garbage(monkeypatch):
    import wait_for_results as wfr

    monkeypatch.setattr(
        wfr.requests, "get", lambda url, params=None, timeout=None: _Resp({"nope": 1})
    )
    assert wfr._fetch_last_qualifying(2026) is None


def test_report_tells_the_workflow_whether_the_round_was_seen(tmp_path, monkeypatch):
    import wait_for_results as wfr

    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    wfr.report("false")
    wfr.report("true")
    assert out.read_text(encoding="utf-8").splitlines() == ["published=false", "published=true"]
