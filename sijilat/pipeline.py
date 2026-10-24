"""Orchestration: search -> (per branch) details -> parse -> output dict.

Rules:
  * One output record per branch; a failure on one branch never erases another.
  * If the details call fails, name/registration/status/activities fall back to the
    search row (marked origin="search") and the address is "not_retrieved".
  * Overall outcome: success | partial | failed | not_found
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import config
from .models import (ABSENT, EXTRACTION_FAILED, NOT_RETRIEVED, OK, ExtractionError, FetchError,
                     FieldResult)
from .parser import FIELD_NAMES, fields_from_search_row, parse_details, parse_search


def _branch_outcome(fields: dict[str, FieldResult]) -> str:
    """success: every field ok or absent_in_source (the source fully answered);
    partial: some ok, some not; failed: nothing ok."""
    statuses = [f.status for f in fields.values()]
    if all(s in (OK, ABSENT) for s in statuses):
        return "success"
    return "partial" if any(s == OK for s in statuses) else "failed"


def _cross_checks(row: dict, fields: dict[str, FieldResult]) -> list[str]:
    """Compare search row vs details response; differences are findings, not errors."""
    warnings = []
    reg = fields["registration"]
    if reg.status == OK:
        if str(reg.value["cr_number"]) != str(row["CR_NO"]).strip():
            warnings.append("CR number differs between search and details")
        if str(reg.value["branch_id"]) != str(row["BRANCH_NO"]).strip():
            warnings.append("branch id differs between search and details")
    st = fields["registration_status"]
    row_status = str(row.get("STATUS") or "").strip()
    if st.status == OK and row_status and st.value.casefold() != row_status.casefold():
        warnings.append(f"status text differs: search='{row_status}' details='{st.value}'")
    return warnings


def _collect_branch(fetcher, cr_no: str, row: dict, lang: str, notes: list) -> dict:
    """Build one branch record. Never raises: a details failure is recorded in `notes`
    and the record falls back to the search row."""
    branch_id = str(row["BRANCH_NO"]).strip()
    warnings: list[str] = []
    try:
        raw = fetcher.details(cr_no, branch_id, lang)
    except FetchError as exc:
        notes.append({"step": "details", "branch_id": branch_id, **exc.to_dict()})
        fields = fields_from_search_row(row)
        fields["commercial_address"] = FieldResult(
            NOT_RETRIEVED, detail=f"{exc.kind}: {exc.detail}")
    else:
        fields = parse_details(raw)
        warnings = _cross_checks(row, fields)
    record = {"branch_id": branch_id,
              "source_url": fetcher.source_url(cr_no, branch_id),
              "outcome": _branch_outcome(fields)}
    record.update({name: fields[name].to_dict() for name in FIELD_NAMES})
    if warnings:
        record["warnings"] = warnings
    return record


def run(fetcher, cr_no: str, branch: str | None = None, lang: str = "EN",
        now=None, simulated: bool = False) -> dict:
    """Collect one company. `now` is injectable for tests."""
    cr_no = str(cr_no).strip()
    stamp = (now() if now else datetime.now(timezone.utc))
    out = {
        "cr_number": cr_no,
        "source": config.SITE,
        "collected_at": stamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "mode": getattr(fetcher, "mode", "unknown"),     # live | file (local replay)
        "outcome": "failed",
        "notes": [],
        "branches": [],
    }
    if simulated:
        out["simulated"] = True
    notes = out["notes"]

    try:
        res = parse_search(fetcher.search(cr_no, lang))
    except FetchError as exc:
        notes.append({"step": "search", **exc.to_dict()})
        return out
    except ExtractionError as exc:
        notes.append({"step": "search", "kind": EXTRACTION_FAILED, "detail": str(exc)})
        return out

    rows = [r for r in res.rows if str(r["CR_NO"]).strip() == cr_no]
    if branch is not None:
        rows = [r for r in rows if str(r["BRANCH_NO"]).strip() == str(branch)]
    if not rows:
        out["outcome"] = "not_found"
        notes.append({"step": "search", "kind": "not_found",
                      "detail": "no matching CR/branch in the source (not a retrieval failure)"})
        return out

    incomplete = res.total is not None and res.total > len(res.rows)
    if incomplete:
        notes.append({"step": "search", "kind": "pagination",
                      "detail": f"source reports {res.total} records, only {len(res.rows)} returned"})

    for row in rows:
        out["branches"].append(_collect_branch(fetcher, cr_no, row, lang, notes))

    outcomes = [b["outcome"] for b in out["branches"]]
    if all(o == "success" for o in outcomes) and not incomplete:
        out["outcome"] = "success"
    elif any(o in ("success", "partial") for o in outcomes):
        out["outcome"] = "partial"
    else:
        out["outcome"] = "failed"
    return out
