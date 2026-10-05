"""Contract checks on .github/workflows/update.yml that no unit test can execute.

The grid hand-over runs after a watch gave up waiting for results to republish F1's
official starting grid. On race morning that watch was the results watch, so the
hand-over must survive a failed later step (a red test, or `--fail-on-stale` during
a Jolpica outage, when the OpenF1 fast lane matters most). Otherwise the race result
waits for the next throttled cron run.
"""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "update.yml"


def _step(name: str) -> str:
    """The text of the update.yml step called ``name``, up to the next step."""
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = f"- name: {name}\n"
    start = text.index(marker)
    end = text.find("- name: ", start + len(marker))
    return text[start : end if end != -1 else len(text)]


def test_the_grid_hand_over_survives_a_failed_later_step():
    check = _step("Check whether a session is still pending after a grid update")
    assert "!cancelled()" in check
    assert "steps.wait.outputs.published == 'grid'" in check
    assert "steps.pipeline.outcome == 'success'" in check  # never after a failed pipeline
    hand_over = _step("Hand over after a grid update")
    assert "!cancelled()" in hand_over
    assert "steps.regrid.outputs.successor == 'true'" in hand_over
