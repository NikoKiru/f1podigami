"""Minimal, fail-closed OpenF1 client (https://openf1.org) for the fast lane.

Every call returns the parsed list on success and ``None`` otherwise: an HTTP
error or timeout, a body that is not a list of objects, or OpenF1's
``{"detail": "No results found."}`` sentinel (served with a 404). Callers treat
``None`` as "no fast data", never as an error — OpenF1 is an optional
accelerator and the Jolpica path must keep working without it.

Rate limit: the free tier allows 30 requests per minute and answers beyond that
with HTTP 429 and ``Retry-After: 60`` (measured 2026-09-13: requests 1-30
succeeded, the 31st was refused). Requests are spaced at least ``MIN_INTERVAL``
apart, and a 429 is retried after the advertised delay a bounded number of times
before failing closed.

Free-tier data for a session opens 30 min after it ends; earlier requests hit the
paid live window and come back as errors, i.e. ``None``.
"""

from __future__ import annotations

import time

import requests

API_ROOT = "https://api.openf1.org/v1"
USER_AGENT = "f1podigami/0.1 (https://github.com/NikoKiru/f1podigami)"
MIN_INTERVAL = 2.1  # seconds between request starts, so fewer than 30 per minute
MAX_RATE_LIMIT_RETRIES = 2
MAX_RETRY_AFTER = 65.0  # cap on a single Retry-After sleep

_last_request = float("-inf")


def _pace() -> None:
    """Sleep until MIN_INTERVAL has passed since the previous request started."""
    global _last_request
    wait = _last_request + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _retry_after(resp: requests.Response) -> float:
    try:
        return min(float(resp.headers.get("Retry-After", 60)), MAX_RETRY_AFTER)
    except (TypeError, ValueError):
        return 60.0


def get(endpoint: str, **params) -> list[dict] | None:
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        _pace()
        try:
            resp = requests.get(
                f"{API_ROOT}/{endpoint}",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
        except requests.RequestException as exc:
            print(f"  OpenF1 {endpoint}: {exc}")
            return None
        if resp.status_code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
            delay = _retry_after(resp)
            print(f"  OpenF1 {endpoint}: rate limited, retrying in {delay:.0f}s")
            time.sleep(delay)
            continue
        break
    if resp.status_code != 200:
        print(f"  OpenF1 {endpoint}: HTTP {resp.status_code}")
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    if not isinstance(body, list) or not all(isinstance(row, dict) for row in body):
        return None
    return body


def sessions(year: int, name: str) -> list[dict] | None:
    return get("sessions", year=year, session_name=name)


def session_result(session_key: int) -> list[dict] | None:
    return get("session_result", session_key=session_key)


def drivers(session_key: int) -> list[dict] | None:
    return get("drivers", session_key=session_key)


def race_control(session_key: int) -> list[dict] | None:
    return get("race_control", session_key=session_key)


def starting_grid(quali_session_key: int) -> list[dict] | None:
    """The official starting grid, keyed by the *qualifying* session."""
    return get("starting_grid", session_key=quali_session_key)
