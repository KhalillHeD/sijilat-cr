"""Measure the prototype on a sample of CRs (LIVE):  python -m sijilat.benchmark --crs 931 1 100

Per CR: wall time, HTTP requests, branches, outcome and the status of every field.
CRs with more branches than --max-branches are skipped (politeness), and reported as skipped.
Writes output/benchmark.json and prints a summary table.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from .client import SijilatClient
from .models import FetchError, ExtractionError
from .parser import FIELD_NAMES, parse_search
from .pipeline import run


class _CachedSearch:
    """Serves a search response already fetched (to read the branch count) without a second call."""

    def __init__(self, inner, cr_no, response):
        self.inner, self.cached, self.mode = inner, {cr_no: response}, inner.mode

    def search(self, cr_no, lang="EN"):
        return self.cached.pop(cr_no) if cr_no in self.cached else self.inner.search(cr_no, lang)

    def details(self, cr_no, branch_no, lang="EN"):
        return self.inner.details(cr_no, branch_no, lang)

    def source_url(self, cr_no, branch_no):
        return self.inner.source_url(cr_no, branch_no)


def _count_requests(client: SijilatClient) -> list[int]:
    """Wrap the client's single HTTP entry point so every request (and retry) is counted."""
    counter = [0]
    send = client._send

    def counted(*args, **kwargs):
        counter[0] += 1
        return send(*args, **kwargs)

    client._send = counted
    return counter


def measure(client: SijilatClient, counter: list[int], cr_no: str, max_branches: int) -> dict:
    """Run one CR and return its measurements."""
    start, before = time.perf_counter(), counter[0]
    row = {"cr_number": cr_no}
    try:
        raw = client.search(cr_no)
        n = len([r for r in parse_search(raw).rows if str(r["CR_NO"]).strip() == cr_no])
    except (FetchError, ExtractionError) as exc:
        n, raw = None, None
        row["error"] = str(exc)
    if n is not None and n > max_branches:
        row.update(outcome="skipped", branches=n,
                   detail=f"{n} branches > --max-branches {max_branches}")
    elif raw is not None:
        out = run(_CachedSearch(client, cr_no, raw), cr_no)
        row.update(outcome=out["outcome"], branches=len(out["branches"]),
                   field_status=dict(Counter(b[f]["status"] for b in out["branches"]
                                             for f in FIELD_NAMES)))
    else:
        row["outcome"] = "failed"
    row["seconds"] = round(time.perf_counter() - start, 1)
    row["requests"] = counter[0] - before
    return row


def main(argv=None) -> int:
    """Run the sample, write output/benchmark.json and print the table and totals."""
    ap = argparse.ArgumentParser(description="Live benchmark over a sample of CR numbers.")
    ap.add_argument("--crs", nargs="+", required=True)
    ap.add_argument("--max-branches", type=int, default=15)
    ap.add_argument("--out", default="output/benchmark.json")
    args = ap.parse_args(argv)

    client = SijilatClient()
    counter = _count_requests(client)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = [measure(client, counter, cr, args.max_branches) for cr in args.crs]

    collected = [r for r in rows if "field_status" in r]
    statuses = sum((Counter(r["field_status"]) for r in collected), Counter())
    n_fields = sum(statuses.values())
    n_branches = sum(r["branches"] for r in collected)
    secs = sum(r["seconds"] for r in collected)
    summary = {
        "started_at": started, "mode": "live", "crs_requested": len(rows),
        "outcomes": dict(Counter(r["outcome"] for r in rows)),
        "branches_collected": n_branches, "fields_collected": n_fields,
        "field_status_share": {k: round(v / n_fields, 4) for k, v in statuses.items()} if n_fields else {},
        "seconds_total_collected": round(secs, 1),
        "seconds_per_branch": round(secs / n_branches, 2) if n_branches else None,
        "requests_total": counter[0],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"summary": summary, "per_cr": rows}, ensure_ascii=False,
                                         indent=2) + "\n", encoding="utf-8")

    print(f"{'CR':>8} {'outcome':>10} {'branches':>8} {'sec':>6} {'req':>4}  field statuses")
    for r in rows:
        fs = ", ".join(f"{k}={v}" for k, v in sorted(r.get("field_status", {}).items()))
        print(f"{r['cr_number']:>8} {r['outcome']:>10} {r.get('branches', '-')!s:>8} "
              f"{r['seconds']:>6} {r['requests']:>4}  {fs or r.get('detail', r.get('error', ''))}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
