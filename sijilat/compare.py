"""Compare two output files field by field:  python -m sijilat.compare output/run1.json output/run2.json

Ignores keys that are expected to differ between runs (timestamp, and with --ignore-mode
also live vs file). Exit code 0 = same data, 1 = differences found.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .parser import FIELD_NAMES

_ALWAYS_IGNORED = {"collected_at"}


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare(a: dict, b: dict, ignore: set[str]) -> list[str]:
    """Return human-readable differences: top-level keys, branches present in only one
    run, and per-branch fields. Branches are matched by branch_id, not by position."""
    diffs = []
    for key in sorted((set(a) | set(b)) - ignore - {"branches"}):
        if a.get(key) != b.get(key):
            diffs.append(f"top-level '{key}': {a.get(key)!r} -> {b.get(key)!r}")

    branches_a = {br["branch_id"]: br for br in a.get("branches", [])}
    branches_b = {br["branch_id"]: br for br in b.get("branches", [])}
    for bid in sorted(set(branches_a) - set(branches_b), key=int):
        diffs.append(f"branch {bid}: only in first run")
    for bid in sorted(set(branches_b) - set(branches_a), key=int):
        diffs.append(f"branch {bid}: only in second run")
    for bid in sorted(set(branches_a) & set(branches_b), key=int):
        ba, bb = branches_a[bid], branches_b[bid]
        for key in ("source_url", "outcome", *FIELD_NAMES, "warnings"):
            if ba.get(key) != bb.get(key):
                diffs.append(f"branch {bid} '{key}': {ba.get(key)!r} -> {bb.get(key)!r}")
    return diffs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare two collector outputs.")
    ap.add_argument("first")
    ap.add_argument("second")
    ap.add_argument("--ignore-mode", action="store_true",
                    help="also ignore 'mode' (use when comparing a live run with a file replay)")
    args = ap.parse_args(argv)
    a, b = _load(args.first), _load(args.second)
    ignore = _ALWAYS_IGNORED | ({"mode"} if args.ignore_mode else set())
    diffs = compare(a, b, ignore)

    print(f"first : {args.first}  collected_at={a.get('collected_at')}  mode={a.get('mode')}")
    print(f"second: {args.second}  collected_at={b.get('collected_at')}  mode={b.get('mode')}")
    print(f"branches: {len(a.get('branches', []))} vs {len(b.get('branches', []))}")
    print(f"ignored keys: {', '.join(sorted(ignore))}")
    if not diffs:
        print("RESULT: identical data")
        return 0
    print(f"RESULT: {len(diffs)} difference(s)")
    for d in diffs:
        print("  - " + d)
    return 1


if __name__ == "__main__":
    sys.exit(main())
