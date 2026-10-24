"""Shared types: field statuses, the error type, and the per-field result."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The four honest answers for every field.
OK = "ok"                              # found and extracted
ABSENT = "absent_in_source"            # source answered, but has no value for it
NOT_RETRIEVED = "not_retrieved"        # we never got the data (network, HTTP, API error)
EXTRACTION_FAILED = "extraction_failed"  # we got a response but could not read it


class ExtractionError(ValueError):
    """A response arrived but its structure is not what we expect."""


class FetchError(Exception):
    """A request could not be completed. `kind` says why.

    kinds: network | http | auth | api_status | session | file
    """

    def __init__(self, kind: str, detail: str, http_status: int | None = None,
                 simulated: bool = False):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail
        self.http_status = http_status
        self.simulated = simulated

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "detail": self.detail}
        if self.http_status is not None:
            d["http_status"] = self.http_status
        if self.simulated:
            d["simulated"] = True
        return d


@dataclass
class FieldResult:
    """One output field: its status (see constants above), the value, and why if not ok."""
    status: str
    value: Any = None
    detail: str | None = None
    origin: str | None = None   # "search" when the value fell back to the search row

    def to_dict(self) -> dict:
        """Lean form: `detail` only when not ok, `origin` only for the search fallback."""
        d: dict = {"status": self.status, "value": self.value}
        if self.detail and self.status != OK:
            d["detail"] = self.detail
        if self.origin:
            d["origin"] = self.origin
        return d
