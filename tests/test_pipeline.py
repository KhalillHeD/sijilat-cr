"""End-to-end over saved samples (no network), including a SIMULATED failure."""
from datetime import datetime, timezone
from pathlib import Path

from sijilat.fetchers import FailingFetcher, FileFetcher
from sijilat.pipeline import run

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
FIXED_NOW = lambda: datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def test_replay_success_and_branches_identifiable():
    out = run(FileFetcher(SAMPLES), "931", now=FIXED_NOW)
    assert out["outcome"] == "success" and out["mode"] == "file"
    ids = [b["branch_id"] for b in out["branches"]]
    assert len(ids) == 30 and len(set(ids)) == 30
    assert all(f"branch_no={b['branch_id']}" in b["source_url"] for b in out["branches"])


def test_repeat_run_is_deterministic():
    a = run(FileFetcher(SAMPLES), "931", now=FIXED_NOW)
    b = run(FileFetcher(SAMPLES), "931", now=FIXED_NOW)
    assert a == b


def test_simulated_details_failure_only_hits_one_branch():
    fetcher = FailingFetcher(FileFetcher(SAMPLES), fail_on="details", only_branch="5")
    out = run(fetcher, "931", now=FIXED_NOW, simulated=True)
    assert out["simulated"] is True and out["outcome"] == "partial"
    by_id = {b["branch_id"]: b for b in out["branches"]}
    b5 = by_id["5"]
    assert b5["outcome"] == "partial"
    assert b5["commercial_address"]["status"] == "not_retrieved"
    assert b5["commercial_name"]["origin"] == "search"          # fell back to the search row
    assert all(b["outcome"] == "success" for bid, b in by_id.items() if bid != "5")
    assert out["notes"][0]["simulated"] is True


def test_simulated_search_failure_is_failed_not_not_found():
    out = run(FailingFetcher(FileFetcher(SAMPLES), fail_on="search"), "931", now=FIXED_NOW)
    assert out["outcome"] == "failed" and out["branches"] == []


def test_unknown_cr_is_not_found():
    out = run(FileFetcher(SAMPLES), "99999999", now=FIXED_NOW)
    assert out["outcome"] == "not_found"
