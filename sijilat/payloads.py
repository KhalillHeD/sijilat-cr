"""Builds the request bodies exactly like the browser does (shapes taken from
the browser captures). Pure functions: no network."""
from __future__ import annotations

from urllib.parse import urlencode

from . import config

_SEARCH_COLUMNS = ["CR_NO", "CR_LNM", "CR_ANM", "CM_TYP_DESC", "REG_DATE",
                   "EXPIRE_DATE", "STATUS", "ACTIVITIES", "SECTOR"]

# Search filters the browser always sends, empty unless we use them.
_EMPTY_SEARCH_FILTERS = [
    "CR_LNM", "CR_ANM", "CM_TYP_CD", "STATUS", "CR_MUNCP_CD", "CR_BLOCK", "CM_NAT_CD",
    "FIRST_LEV", "PTNER_LNM", "PTNER_ANM", "PTNER_NAT_CD", "REG_DATE_FROM", "REG_DATE_TO",
    "CR_ROAD", "CR_FLAT", "CR_BULD", "PSPORT_NO", "PTNER_CR_NO", "VCR_YN", "ISIC4_CD", "cpr_no",
]

# Keys the site's request() helper adds to every details call; empty for an anonymous visitor.
_EMPTY_DETAILS_KEYS = [
    "cpr_no", "CPR_NO_LOGIN", "CPR_GCC_NO", "CPR_OR_GCC_NO", "Login_CPR_No", "Login_CPR",
    "APPCNT_CPR_NO", "cprno", "LOGIN_PB_NO", "PB_NO", "Input_PB_NO",
]


def page_url(cr_no: str, branch_no: str) -> str:
    """Human-readable details page for one branch (also our `source_url`)."""
    return config.DETAILS_PAGE + "?" + urlencode({"cr_no": cr_no, "branch_no": branch_no})


def build_search_body(cr_no: str, lang: str = "EN") -> dict:
    body = {
        "draw": 1,
        "columns": [{"data": c, "name": "", "searchable": True, "orderable": False,
                     "search": {"value": "", "regex": False}} for c in _SEARCH_COLUMNS],
        "order": [],
        "start": 0,
        "length": 10,
        "search": {"value": "", "regex": False},
    }
    body.update({k: "" for k in _EMPTY_SEARCH_FILTERS})
    body.update({
        "CR_NO": cr_no,
        "CurrentMenuType": "A",
        "CULT_LANG": lang,
        "PaginationParams": {"Page": 1, "ItemPerPage": 10},
    })
    return body


def build_details_body(cr_no: str, branch_no: str, session_id: str, lang: str = "EN") -> dict:
    body = {
        "cr_no": cr_no,
        "branch_no": branch_no,
        "cult_lang": lang,
        "Input_CULT_LANG": lang,
        "CULT_LANG": lang,
        "cultLang": lang,
        "CurrentMenuTyp": "A",
        "CurrentMenu_Type": "A",
        "MENU_TYPE": "A",
    }
    body.update({k: "" for k in _EMPTY_DETAILS_KEYS})
    body["SESSION_ID"] = session_id
    return body
