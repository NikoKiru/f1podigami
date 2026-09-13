"""The fail-closed OpenF1 client (src/fetch/openf1.py): pacing and rate limiting.

OpenF1's free tier allows 30 requests per minute and answers the 31st with HTTP 429
and Retry-After: 60. A client that ignores that turns every refused request into
"no data", which is how the first fixture recording came out half empty.
"""

import pytest

from fetch import openf1


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 3))
        self.now += seconds


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.fixture
def clock(monkeypatch):
    fake = FakeTime()
    monkeypatch.setattr(openf1.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(openf1.time, "sleep", fake.sleep)
    monkeypatch.setattr(openf1, "_last_request", float("-inf"))
    monkeypatch.setattr(openf1, "_retry_waited", 0.0)
    return fake


def serve(monkeypatch, responses):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(openf1.requests, "get", fake_get)
    return calls


def test_requests_are_spaced_to_stay_under_30_per_minute(monkeypatch, clock):
    calls = serve(monkeypatch, [Resp(200, []), Resp(200, [])])
    openf1.get("sessions")
    openf1.get("sessions")
    assert len(calls) == 2
    assert clock.slept == [openf1.MIN_INTERVAL]
    assert 60 / openf1.MIN_INTERVAL < 30


def test_a_429_is_retried_after_the_advertised_delay(monkeypatch, clock):
    calls = serve(monkeypatch, [Resp(429, headers={"Retry-After": "60"}), Resp(200, [{"a": 1}])])
    assert openf1.get("drivers", session_key=1) == [{"a": 1}]
    assert len(calls) == 2
    assert 60 in clock.slept


def test_persistent_rate_limiting_fails_closed(monkeypatch, clock):
    calls = serve(monkeypatch, [Resp(429, headers={"Retry-After": "60"}) for _ in range(3)])
    assert openf1.get("drivers", session_key=1) is None
    assert len(calls) == openf1.MAX_RATE_LIMIT_RETRIES + 1


def test_a_huge_retry_after_is_capped(monkeypatch, clock):
    serve(monkeypatch, [Resp(429, headers={"Retry-After": "3600"}), Resp(200, [])])
    assert openf1.get("sessions") == []
    assert max(clock.slept) == openf1.MAX_RETRY_AFTER


def test_errors_and_sentinels_are_none(monkeypatch, clock):
    serve(
        monkeypatch,
        [
            Resp(404, {"detail": "No results found."}),
            Resp(200, {"detail": "not a list"}),
            Resp(200, ValueError("bad json")),
        ],
    )
    assert openf1.get("session_result", session_key=1) is None
    assert openf1.get("session_result", session_key=1) is None
    assert openf1.get("session_result", session_key=1) is None


def test_negative_retry_after_is_clamped(monkeypatch, clock):
    serve(monkeypatch, [Resp(429, headers={"Retry-After": "-5"}), Resp(200, [{"a": 1}])])
    assert openf1.get("drivers", session_key=1) == [{"a": 1}]
    assert len(clock.slept) >= 1
    assert all(s >= 0 for s in clock.slept)


def test_total_retry_wait_budget(monkeypatch, clock):
    monkeypatch.setattr(openf1, "_retry_waited", 0.0)
    # Three calls: 1st gets 429 (waits 60, within budget); 2nd gets 429 (waits 60, budget full);
    # 3rd gets 429 (exceeds budget, fails closed immediately).
    serve(
        monkeypatch,
        [
            Resp(429, headers={"Retry-After": "60"}),
            Resp(200, [{"a": 1}]),
            Resp(429, headers={"Retry-After": "60"}),
            Resp(200, [{"b": 2}]),
            Resp(429, headers={"Retry-After": "60"}),
        ],
    )
    result1 = openf1.get("drivers", session_key=1)
    result2 = openf1.get("drivers", session_key=2)
    result3 = openf1.get("drivers", session_key=3)

    assert result1 == [{"a": 1}]
    assert result2 == [{"b": 2}]
    assert result3 is None
    # Count only the 60+ s sleeps (the rate-limit waits), not the 2.1 s pacing sleeps
    rate_limit_waits = [s for s in clock.slept if s >= 60]
    assert len(rate_limit_waits) == 2
    assert sum(rate_limit_waits) <= openf1.MAX_TOTAL_RETRY_WAIT
