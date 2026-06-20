"""Refresh the F1 podigami data and rebuild the site.

Fetches new podium data and the current grid, recomputes the podium-driven
datasets (combos, soulmates, podigami), then rebuilds the site into dist/.

Pass --full to re-fetch the entire podium history from 1950 (slow); otherwise
podiums are fetched incrementally for the current season.

The build step always renders all pages from the current data/*.json.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import build_site

PYTHON = sys.executable
SRC = Path(__file__).resolve().parent

STEPS = [
    ("Fetching podiums", "fetch/fetch_podiums.py"),
    ("Counting combos", "compute/count_combos.py"),
    ("Computing soulmates", "compute/compute_soulmates.py"),
    ("Fetching current grid", "fetch/fetch_current_drivers.py"),
    ("Fetching constructor standings", "fetch/fetch_constructor_standings.py"),
    ("Computing podigami", "compute/compute_podigami.py"),
    ("Fetching driver races", "fetch/fetch_driver_races.py"),
    ("Computing overdue podiums", "compute/compute_overdue.py"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full", action="store_true", help="re-fetch the entire podium history from 1950 (slow)"
    )
    args = parser.parse_args()

    total = len(STEPS) + 1  # +1 for the build step
    for i, (label, script) in enumerate(STEPS, 1):
        print(f"\n[{i}/{total}] {label}...")
        cmd = [PYTHON, str(SRC / script)]
        if args.full and script.endswith("fetch_podiums.py"):
            cmd.append("--full")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"\nFailed at step {i}: {label}", file=sys.stderr)
            sys.exit(result.returncode)

    print(f"\n[{total}/{total}] Building site...")
    build_site.build()
    print("\nDone. Open dist/index.html in your browser.")


if __name__ == "__main__":
    main()
