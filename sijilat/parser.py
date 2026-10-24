"""Turns RAW responses into the five labelled fields. Pure functions, no network.

Rules for statuses (the assignment's key distinction):
  * a whole expected SECTION is missing / wrong type  -> extraction_failed
  * the section exists but is null / empty            -> absent_in_source
  * a leaf KEY is missing, null or "" inside a section -> absent_in_source (detail says which)
  * (not_retrieved is decided elsewhere: it means we never got a response)

Data minimisation: only the five requested fields are read. Names of people, phone
numbers, e-mail addresses, capital, shareholders etc. are deliberately ignored.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import (ABSENT, EXTRACTION_FAILED, OK, ExtractionError, FieldResult)

FIELD_NAMES = ("commercial_name", "registration", "registration_status",
               "business_activities", "commercial_address")

_ADDRESS_PARTS = (("flat", "CR_FLAT"), ("building", "CR_BULD"), ("road", "CR_ROAD"),
                  ("road_name", "CR_ROAD_NM"), ("block", "CR_BLOCK"), ("town", "CR_TOWN_NM"),
                  ("po_box", "CR_PBOX"))


# ---- small helpers ---------------------------------------------------------------
def _text(d: dict, key: str) -> tuple[str, str | None]:


    """Return (state, value). state: ok | missing | blank | badtype."""

    
    if key not in d:
        return "missing", None
    v = d[key]
    if v is None:
        return "blank", None
    if isinstance(v, str):
        v = v.strip()
        return ("blank", None) if v == "" else ("ok", v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return "ok", str(v)
    return "badtype", None


def _section(data: dict, key: str) -> tuple[dict | None, FieldResult | None]:


    """Fetch an object section. Returns (section, problem). Exactly one is not None."""


    if key not in data:
        return None, FieldResult(EXTRACTION_FAILED, detail=f"section '{key}' not in response")
    v = data[key]
    if v is None:
        return None, FieldResult(ABSENT, detail=f"section '{key}' is null")
    if not isinstance(v, dict):
        return None, FieldResult(EXTRACTION_FAILED, detail=f"section '{key}' is not an object")
    if not v:
        return None, FieldResult(ABSENT, detail=f"section '{key}' is empty")
    return v, None


def _to_int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


# ---- search response -------------------------------------------------------------
@dataclass
class SearchResult:


    """Branch rows from the search, plus the total the source reports (to detect truncation)."""


    rows: list[dict]
    total: int | None


def parse_search(raw) -> SearchResult:


    """Validate the search response. Raises ExtractionError if it cannot be trusted, e.g. a
    row without CR_NO / BRANCH_NO, because then branches could not be told apart."""


    if not isinstance(raw, dict):
        raise ExtractionError("search response is not an object")
    data = raw.get("jsonData")
    # Observed live (CR 99999999): an unknown CR gives Status_Code 200, jsonData [] and
    # Message "No Data Found." That is the source saying "nothing here", not a broken response.
    if data in ([], None) and "jsonData" in raw:
        return SearchResult(rows=[], total=0)
    if not isinstance(data, dict):
        raise ExtractionError("'jsonData' missing or not an object")
    rows = data.get("CR_list")
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ExtractionError("'CR_list' missing or not a list of objects")
    for r in rows:
        if _text(r, "CR_NO")[0] != "ok" or _text(r, "BRANCH_NO")[0] != "ok":
            raise ExtractionError("a search row has no CR_NO / BRANCH_NO, cannot identify branch")
    return SearchResult(rows=rows, total=_to_int(data.get("Total_Records")))


def fields_from_search_row(row: dict) -> dict[str, FieldResult]:


    """Fallback for 4 of the 5 fields when the details call fails (address is not in search)."""


    _, en = _text(row, "CR_LNM")
    _, ar = _text(row, "CR_ANM")
    out: dict[str, FieldResult] = {}
    out["commercial_name"] = (
        FieldResult(OK, {"en": en, "ar": ar}, origin="search") if (en or ar)
        else FieldResult(ABSENT, detail="CR_LNM and CR_ANM blank in search row", origin="search"))
    out["registration"] = FieldResult(
        OK, {"cr_number": _text(row, "CR_NO")[1], "branch_id": _text(row, "BRANCH_NO")[1]},
        origin="search")
    s_state, status = _text(row, "STATUS")
    out["registration_status"] = (
        FieldResult(OK, status, origin="search") if status
        else FieldResult(ABSENT, detail=f"STATUS {s_state}", origin="search"))
    a_state, acts = _text(row, "ACTIVITIES")
    if a_state == "badtype":
        out["business_activities"] = FieldResult(EXTRACTION_FAILED, detail="ACTIVITIES has unexpected type", origin="search")
    elif not acts:
        out["business_activities"] = FieldResult(ABSENT, detail=f"ACTIVITIES {a_state}", origin="search")
    else:
        items = [{"name": p.strip()} for p in acts.split("~") if p.strip()]
        out["business_activities"] = (
            FieldResult(OK, items, origin="search") if items
            else FieldResult(ABSENT, detail="ACTIVITIES had no items", origin="search"))
    return out


# ---- details response ------------------------------------------------------------
def _name(summary: dict) -> FieldResult:
    en_s, en = _text(summary, "CR_LNM")
    ar_s, ar = _text(summary, "CR_ANM")
    if "badtype" in (en_s, ar_s):
        return FieldResult(EXTRACTION_FAILED, detail="name has unexpected type")
    if en is None and ar is None:
        return FieldResult(ABSENT, detail=f"CR_LNM {en_s}, CR_ANM {ar_s}")
    return FieldResult(OK, {"en": en, "ar": ar})


def _registration(summary: dict) -> FieldResult:
    cr_s, cr = _text(summary, "CR_NO")
    br_s, br = _text(summary, "BRANCH_NO")
    if "badtype" in (cr_s, br_s):
        return FieldResult(EXTRACTION_FAILED, detail="CR_NO/BRANCH_NO has unexpected type")
    if cr is None or br is None:
        return FieldResult(ABSENT, {"cr_number": cr, "branch_id": br},
                           detail=f"CR_NO {cr_s}, BRANCH_NO {br_s}")
    return FieldResult(OK, {"cr_number": cr, "branch_id": br})


def _status(summary: dict) -> FieldResult:
    state, value = _text(summary, "STATUS")
    if state == "badtype":
        return FieldResult(EXTRACTION_FAILED, detail="STATUS has unexpected type")
    if value is None:
        return FieldResult(ABSENT, detail=f"STATUS {state}")
    return FieldResult(OK, value)


def _activities(data: dict) -> FieldResult:

    """businessActivities -> list of {activity_code, isic4_code, name}; null/[] is absent."""

    if "businessActivities" not in data:
        return FieldResult(EXTRACTION_FAILED, detail="section 'businessActivities' not in response")
    acts = data["businessActivities"]
    if acts is None:
        return FieldResult(ABSENT, detail="'businessActivities' is null")
    if not isinstance(acts, list):
        return FieldResult(EXTRACTION_FAILED, detail="'businessActivities' is not a list")
    if not acts:
        return FieldResult(ABSENT, detail="'businessActivities' is an empty list")
    items = []
    for a in acts:
        if not isinstance(a, dict):
            return FieldResult(EXTRACTION_FAILED, detail="an activity entry is not an object")
        item = {"activity_code": _text(a, "ACT_CD")[1], "isic4_code": _text(a, "ISIC4_CD")[1],
                "name": _text(a, "ISIC4_NM")[1]}
        if not any(item.values()):
            return FieldResult(EXTRACTION_FAILED, detail="an activity entry has no code or name")
        items.append(item)
    return FieldResult(OK, items)



def _address(data: dict) -> FieldResult:

    """commercialAddress -> the seven parts in _ADDRESS_PARTS; absent only if all are blank."""

    addr, problem = _section(data, "commercialAddress")
    if problem:
        return problem
    parts = {}
    for out_key, src_key in _ADDRESS_PARTS:
        state, value = _text(addr, src_key)
        if state == "badtype":
            return FieldResult(EXTRACTION_FAILED, detail=f"{src_key} has unexpected type")
        parts[out_key] = value                      # blank parts stay null in the value
    if all(v is None for v in parts.values()):
        return FieldResult(ABSENT, detail="all address parts blank or missing")
    return FieldResult(OK, parts)


def parse_details(raw) -> dict[str, FieldResult]:


    """Never raises. Always returns all five fields, each with a status."""


    data = raw.get("jsonData") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        fail = lambda: FieldResult(EXTRACTION_FAILED, detail="'jsonData' missing or not an object")  # noqa: E731
        result = {name: fail() for name in FIELD_NAMES}
    else:
        summary, problem = _section(data, "company_summary")
        if problem:
            result = {"commercial_name": FieldResult(problem.status, detail=problem.detail),
                      "registration": FieldResult(problem.status, detail=problem.detail),
                      "registration_status": FieldResult(problem.status, detail=problem.detail)}
        else:
            result = {"commercial_name": _name(summary), "registration": _registration(summary),
                      "registration_status": _status(summary)}
        result["business_activities"] = _activities(data)
        result["commercial_address"] = _address(data)
    return {name: result[name] for name in FIELD_NAMES}
