"""Parser rules: ok vs absent_in_source vs extraction_failed. No network."""
import json
from pathlib import Path

import pytest

from sijilat.models import ABSENT, EXTRACTION_FAILED, OK, ExtractionError
from sijilat.parser import parse_details, parse_search

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def _details(**sections):
    base = {
        "company_summary": {"CR_NO": "1", "BRANCH_NO": "1", "CR_LNM": "ACME", "CR_ANM": "أكمي",
                            "STATUS": "ACTIVE"},
        "commercialAddress": {"CR_FLAT": "1", "CR_BULD": "2", "CR_ROAD": "3", "CR_ROAD_NM": "",
                              "CR_BLOCK": "4", "CR_TOWN_NM": "MANAMA", "CR_PBOX": None},
        "businessActivities": [{"ACT_CD": "200360", "ISIC4_CD": "469-1", "ISIC4_NM": "General Trade"}],
    }
    base.update(sections)
    return {"Status_Code": "200", "jsonData": {k: v for k, v in base.items() if v != "DROP"}}


def test_real_sample_branch_1_all_ok():
    f = parse_details(_sample("details_931_1.json"))
    assert all(r.status == OK for r in f.values())
    assert f["registration"].value == {"cr_number": "931", "branch_id": "1"}
    assert f["registration_status"].value == "ACTIVE"


def test_real_sample_branch_6_activities_absent_in_source():
    f = parse_details(_sample("details_931_6.json"))
    assert f["business_activities"].status == ABSENT
    assert f["registration_status"].value == "DELETED - MERGED WITH ANOTHER BRANCH"


def test_blank_address_parts_are_null_but_field_ok():
    f = parse_details(_details())
    addr = f["commercial_address"]
    assert addr.status == OK
    assert addr.value["road_name"] is None and addr.value["po_box"] is None


def test_null_section_is_absent_missing_section_is_extraction_failed():
    assert parse_details(_details(businessActivities=None))["business_activities"].status == ABSENT
    assert parse_details(_details(businessActivities="DROP"))["business_activities"].status == EXTRACTION_FAILED
    assert parse_details(_details(commercialAddress=None))["commercial_address"].status == ABSENT
    assert parse_details(_details(commercialAddress="DROP"))["commercial_address"].status == EXTRACTION_FAILED


def test_wrong_type_is_extraction_failed():
    assert parse_details(_details(businessActivities="text"))["business_activities"].status == EXTRACTION_FAILED


def test_garbage_response_never_raises():
    f = parse_details({"unexpected": True})
    assert all(r.status == EXTRACTION_FAILED for r in f.values())


def test_search_real_sample_has_all_branches():
    res = parse_search(_sample("search_931.json"))
    assert res.total == 30 and len(res.rows) == 30
    assert len({r["BRANCH_NO"] for r in res.rows}) == 30


def test_search_no_data_found_is_empty_not_error():
    res = parse_search({"Status_Code": "200", "jsonData": [], "Message": "No Data Found."})
    assert res.rows == [] and res.total == 0


def test_search_malformed_raises():
    with pytest.raises(ExtractionError):
        parse_search({"Status_Code": "200"})
