"""Tests for calendar-year season detection in fetch scripts."""

import json  # noqa: F401

from fetch import fetch_constructor_standings as fcs  # noqa: F401
from fetch import fetch_current_drivers as fcd  # noqa: F401
from fetch import fetch_schedule as fs


def test_fetch_schedule_has_no_podiums_dependency():
    assert not hasattr(fs, "current_season"), "current_season() must be removed"
    assert not hasattr(fs, "PODIUMS_PATH"), "PODIUMS_PATH must be removed"
