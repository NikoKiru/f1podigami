"""Run the F1 podigami pipeline after a race or season has finished.

Default (post-race) mode skips the slow seasonal steps (fetch_top10,
fetch_standings, compute_alignments, build_alignments_html) since those
data only change when a season ends.

Pass --full to also run the seasonal steps (e.g. after the last race of a season).
"""

import argparse
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
ROOT = Path(__file__).parent

POST_RACE_STEPS = [
    ("Fetching podiums",          ["fetch_podiums.py"]),
    ("Counting combos",            ["count_combos.py"]),
    ("Computing career podiums",   ["compute_career_podiums.py"]),
    ("Computing soulmates",        ["compute_soulmates.py"]),
    ("Building index.html",        ["build_html.py"]),
    ("Building soulmates.html",    ["build_soulmates_html.py"]),
    ("Building charts.html",       ["build_charts_page.py"]),
]

SEASONAL_STEPS = [
    ("Fetching standings",         ["fetch_standings.py"]),
    ("Fetching top-10 results",    ["fetch_top10.py"]),
    ("Computing alignments",       ["compute_alignments.py"]),
    ("Building seasons.html",      ["build_alignments_html.py"]),
]


def run_steps(steps: list[tuple[str, list[str]]], offset: int = 0, total: int = 0) -> None:
    for i, (label, args) in enumerate(steps, offset + 1):
        print(f"\n[{i}/{total}] {label}...")
        result = subprocess.run([PYTHON, ROOT / args[0]], cwd=ROOT)
        if result.returncode != 0:
            print(f"\nFailed at step {i}: {label}", file=sys.stderr)
            sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="also run seasonal steps (fetch_standings, fetch_top10, compute_alignments, build_alignments_html)",
    )
    args = parser.parse_args()

    steps = POST_RACE_STEPS + (SEASONAL_STEPS if args.full else [])
    total = len(steps)

    run_steps(POST_RACE_STEPS, offset=0, total=total)
    if args.full:
        run_steps(SEASONAL_STEPS, offset=len(POST_RACE_STEPS), total=total)

    print("\nDone. Open index.html in your browser.")


if __name__ == "__main__":
    main()
