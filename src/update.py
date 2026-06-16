"""Refresh the F1 podigami data and rebuild the site.

Default (post-race) mode fetches new podium data and recomputes the
podium-driven datasets, then rebuilds the whole site into dist/.

Pass --full to also run the slow seasonal steps (fetch_standings, fetch_top10,
compute_alignments) — only needed after the last race of a season.

The build step always renders all four pages from the current data/*.json.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import build_site

PYTHON = sys.executable
SRC = Path(__file__).resolve().parent

POST_RACE_STEPS = [
    ("Fetching podiums",          "fetch/fetch_podiums.py"),
    ("Counting combos",           "compute/count_combos.py"),
    ("Computing career podiums",  "compute/compute_career_podiums.py"),
    ("Computing soulmates",       "compute/compute_soulmates.py"),
]

SEASONAL_STEPS = [
    ("Fetching standings",        "fetch/fetch_standings.py"),
    ("Fetching top-10 results",   "fetch/fetch_top10.py"),
    ("Computing alignments",      "compute/compute_alignments.py"),
]


def run_steps(steps: list[tuple[str, str]], offset: int, total: int) -> None:
    for i, (label, script) in enumerate(steps, offset + 1):
        print(f"\n[{i}/{total}] {label}...")
        result = subprocess.run([PYTHON, str(SRC / script)])
        if result.returncode != 0:
            print(f"\nFailed at step {i}: {label}", file=sys.stderr)
            sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="also run seasonal steps (fetch_standings, fetch_top10, compute_alignments)",
    )
    args = parser.parse_args()

    data_steps = POST_RACE_STEPS + (SEASONAL_STEPS if args.full else [])
    total = len(data_steps) + 1  # +1 for the build step

    run_steps(POST_RACE_STEPS, offset=0, total=total)
    if args.full:
        run_steps(SEASONAL_STEPS, offset=len(POST_RACE_STEPS), total=total)

    print(f"\n[{total}/{total}] Building site...")
    build_site.build()

    print("\nDone. Open dist/index.html in your browser.")


if __name__ == "__main__":
    main()
