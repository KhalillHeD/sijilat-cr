"""Offline stand-ins for SijilatClient. They have the SAME interface:
    search(cr_no, lang) / details(cr_no, branch_no, lang) / source_url(cr_no, branch_no)
so the parser and pipeline do not care where the data came from.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import FetchError
from .payloads import page_url


class FileFetcher:
    """Reads responses you saved yourself:  search_<CR>.json, details_<CR>_<BRANCH>.json"""
    mode = "file"

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)

    def _load(self, name: str) -> dict:
        path = self.dir / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FetchError("file", f"{name} not found") from exc
        except (ValueError, OSError) as exc:
            raise FetchError("file", f"{name} unreadable: {type(exc).__name__}") from exc

    def search(self, cr_no: str, lang: str = "EN") -> dict:
        return self._load(f"search_{cr_no}.json")

    def details(self, cr_no: str, branch_no: str, lang: str = "EN") -> dict:
        return self._load(f"details_{cr_no}_{branch_no}.json")

    def source_url(self, cr_no: str, branch_no: str) -> str:
        return page_url(cr_no, branch_no)


class RecordingFetcher:
    """Wraps another fetcher and saves every raw response in FileFetcher's naming,
    so a live run can later be replayed offline with --from-dir."""

    def __init__(self, inner, directory: str | Path):
        self.inner, self.dir = inner, Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.mode = inner.mode

    def _save(self, name: str, payload: dict) -> dict:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        (self.dir / name).write_text(text, encoding="utf-8")
        return payload

    def search(self, cr_no, lang="EN"):
        return self._save(f"search_{cr_no}.json", self.inner.search(cr_no, lang))

    def details(self, cr_no, branch_no, lang="EN"):
        return self._save(f"details_{cr_no}_{branch_no}.json",
                          self.inner.details(cr_no, branch_no, lang))

    def source_url(self, cr_no, branch_no):
        return self.inner.source_url(cr_no, branch_no)


class FailingFetcher:
    """Wraps another fetcher and makes one step fail ON PURPOSE (a SIMULATED failure)."""

    def __init__(self, inner, fail_on: str = "details", only_branch: str | None = None,
                 kind: str = "network"):
        if fail_on not in ("search", "details"):
            raise ValueError("fail_on must be 'search' or 'details'")
        self.inner, self.fail_on, self.only_branch, self.kind = inner, fail_on, only_branch, kind
        self.mode = f"{inner.mode}+simulated-failure"

    def _boom(self) -> FetchError:
        return FetchError(self.kind, "SIMULATED failure (not a real error)", simulated=True)

    def search(self, cr_no, lang="EN"):
        if self.fail_on == "search":
            raise self._boom()
        return self.inner.search(cr_no, lang)

    def details(self, cr_no, branch_no, lang="EN"):
        if self.fail_on == "details" and self.only_branch in (None, str(branch_no)):
            raise self._boom()
        return self.inner.details(cr_no, branch_no, lang)

    def source_url(self, cr_no, branch_no):
        return self.inner.source_url(cr_no, branch_no)
