"""Command line entry point:  python -m sijilat.cli --cr 12345 --out output/12345.json"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import MissingSecret
from .fetchers import FailingFetcher, FileFetcher, RecordingFetcher
from .pipeline import run

# exit codes
EXIT = {"success": 0, "failed": 1, "partial": 2, "not_found": 3}
EXIT_CONFIG = 4


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect one company from Bahrain's Sijilat registry.")
    ap.add_argument("--cr", required=True, help="commercial registration number, WITHOUT the branch")
    ap.add_argument("--branch", help="only this branch (default: every branch found)")
    ap.add_argument("--lang", default="EN", choices=["EN", "AR"])
    ap.add_argument("--out", help="output JSON path (default: output/<cr>.json)")
    ap.add_argument("--from-dir", help="read saved responses from this folder instead of the live site")
    ap.add_argument("--save-raw", help="also save the raw live responses into this folder")
    ap.add_argument("--simulate-failure", choices=["search", "details"],
                    help="make this step fail on purpose and mark the run as simulated")
    ap.add_argument("--simulate-branch", help="with --simulate-failure details: only this branch fails")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")

    try:
        if args.from_dir:
            fetcher = FileFetcher(args.from_dir)
        else:
            from .client import SijilatClient   # imported late: live mode needs secrets
            fetcher = SijilatClient()
            if args.save_raw:
                fetcher = RecordingFetcher(fetcher, args.save_raw)
        if args.simulate_failure:
            fetcher = FailingFetcher(fetcher, fail_on=args.simulate_failure,
                                     only_branch=args.simulate_branch)
        result = run(fetcher, args.cr, branch=args.branch, lang=args.lang,
                     simulated=bool(args.simulate_failure))
    except MissingSecret as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    out_path = Path(args.out or f"output/{args.cr}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = result["outcome"]["status"]
    print(f"outcome: {status}  ->  {out_path}")
    for b in result["branches"]:
        marks = ", ".join(f"{k}={v['status']}" for k, v in b["fields"].items())
        print(f"  branch {b['branch_id']}: {b['outcome']}  [{marks}]")
    for e in result["outcome"]["errors"]:
        print(f"  note: {e.get('step')}: {e.get('kind')}: {e.get('detail')}")
    return EXIT[status]


if __name__ == "__main__":
    raise SystemExit(main())
