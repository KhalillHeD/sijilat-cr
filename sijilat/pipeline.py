"""Orchestration: search -> (per branch) details -> parse -> output dict.

Rules:
  * One output record per branch; a failure on one branch never erases another.
  * If the details call fails, name/registration/status/activities fall back to the
    search row (marked origin="search") and the address is "not_retrieved".
  * Overall outcome: success | partial | failed | not_found
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from . import config
from .models import (ABSENT, EXTRACTION_FAILED, NOT_RETRIEVED, OK, ExtractionError, FetchError,
                     FieldResult)
from .parser import FIELD_NAMES, fields_from_search_row, parse_details, parse_search

log = logging.getLogger(__name__)
SCHEMA_VERSION = "1.0"
TOOL_VERSION = "0.1"


def _sha256(obj) -> str:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _branch_outcome(fields: dict[str, FieldResult]) -> str:
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


def _collect_branch(fetcher, cr_no: str, row: dict, lang: str, errors: list) -> dict:
    branch_id = str(row["BRANCH_NO"]).strip()
    record = {"cr_number": cr_no, "branch_id": branch_id,
              "source_url": fetcher.source_url(cr_no, branch_id),
              "warnings": [], "raw_sha256": {"search_row": _sha256(row)}}
    try:
        raw = fetcher.details(cr_no, branch_id, lang)
    except FetchError as exc:
        errors.append({"step": "details", "branch_id": branch_id, **exc.to_dict()})
        fields = fields_from_search_row(row)
        fields["commercial_address"] = FieldResult(
            NOT_RETRIEVED, detail=f"{exc.kind}: {exc.detail}", origin="details")
    else:
        fields = parse_details(raw)
        record["raw_sha256"]["details"] = _sha256(raw.get("jsonData") if isinstance(raw, dict) else raw)
        record["warnings"] = _cross_checks(row, fields)
    record["outcome"] = _branch_outcome(fields)
    record["fields"] = {name: fields[name].to_dict() for name in FIELD_NAMES}
    return record


def run(fetcher, cr_no: str, branch: str | None = None, lang: str = "EN",
        now=None, simulated: bool = False) -> dict:
    """Collect one company. `now` is injectable for tests."""
    cr_no = str(cr_no).strip()
    stamp = (now() if now else datetime.now(timezone.utc))
    out = {
        "schema_version": SCHEMA_VERSION,
        "query": {"cr_number": cr_no, "branch_number": branch, "language": lang},
        "source": {"site": config.SITE, "search_api": config.SEARCH_URL,
                   "details_api": config.DETAILS_URL},
        "tool": {"name": "sijilat-prototype", "version": TOOL_VERSION,
                 "mode": getattr(fetcher, "mode", "unknown"), "simulated": simulated},
        "collected_at": stamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "outcome": {"status": "failed", "errors": []},
        "branches": [],
    }
    errors = out["outcome"]["errors"]

    try:
        res = parse_search(fetcher.search(cr_no, lang))
    except FetchError as exc:
        errors.append({"step": "search", **exc.to_dict()})
        return out
    except ExtractionError as exc:
        errors.append({"step": "search", "kind": EXTRACTION_FAILED, "detail": str(exc)})
        return out

    rows = [r for r in res.rows if str(r["CR_NO"]).strip() == cr_no]
    if branch is not None:
        rows = [r for r in rows if str(r["BRANCH_NO"]).strip() == str(branch)]
    if not rows:
        out["outcome"]["status"] = "not_found"
        errors.append({"step": "search", "kind": "not_found",
                       "detail": "no matching CR/branch in the source (not a retrieval failure)"})
        return out

    paginated = res.total is not None and res.total > len(res.rows)
    if paginated:
        errors.append({"step": "search", "kind": "pagination",
                       "detail": f"source reports {res.total} records, only {len(res.rows)} returned"})

    for row in rows:
        out["branches"].append(_collect_branch(fetcher, cr_no, row, lang, errors))

    outcomes = [b["outcome"] for b in out["branches"]]
    if all(o == "success" for o in outcomes) and not paginated:
        out["outcome"]["status"] = "success"
    elif any(o in ("success", "partial") for o in outcomes):
        out["outcome"]["status"] = "partial"
    else:
        out["outcome"]["status"] = "failed"
    return out
