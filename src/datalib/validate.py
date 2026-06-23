"""CLI gate: load + validate every committed ``data/*.json`` against its schema.

Run with ``python -m datalib.validate``. Exits 0 when all datasets are valid,
1 (with the validation errors) otherwise. Wired into CI as a fast, explicit
data-integrity check independent of the test matrix.
"""

from __future__ import annotations

import json
import sys

from .repository import DATA_DIR, REGISTRY


def main() -> int:
    failures: list[tuple[str, Exception]] = []
    for name in sorted(REGISTRY):
        try:
            raw = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
            REGISTRY[name].validate_python(raw)
        except Exception as exc:  # noqa: BLE001 - report any dataset that won't validate
            failures.append((name, exc))

    if failures:
        print(f"Dataset validation FAILED ({len(failures)} of {len(REGISTRY)}):", file=sys.stderr)
        for name, exc in failures:
            print(f"\n--- {name} ---\n{exc}", file=sys.stderr)
        return 1

    print(f"Validated {len(REGISTRY)} datasets OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
