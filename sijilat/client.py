"""All network behaviour for the live source. Returns RAW responses; never interprets data.

Flow for one company:
  0. GET the details page         -> read the per-visit SessionID, keep cookies
  1. POST /token                  -> bearer token (about 30 minutes)
  2. POST search (plain JSON)     -> list of branches
  3. POST details (AES body)      -> address, activity codes, ...

Politeness: identifying User-Agent, at most one request per second, a single retry.
Secrets are never logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time

import requests

from . import config
from .crypto import encrypt_cryptojs
from .models import FetchError
from .payloads import build_details_body, build_search_body, page_url

log = logging.getLogger(__name__)

# The page contains:  var SessionID = '0x....' !== 'null' ? '0x....' : null;
_SESSION_RE = re.compile(r"var\s+SessionID\s*=\s*'([^']*)'")


def extract_session_id(html: str) -> str | None:
    """Return the SessionID literal from the page HTML, or None if absent/'null'."""
    match = _SESSION_RE.search(html or "")
    if not match:
        return None
    value = match.group(1).strip()
    return None if value in ("", "null") else value


class SijilatClient:
    mode = "live"

    def __init__(self, session: requests.Session | None = None, clock=time.monotonic,
                 sleep=time.sleep):
        self.http = session or requests.Session()      # a Session keeps cookies for us
        self.http.headers["User-Agent"] = config.USER_AGENT
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None
        self._token: str | None = None
        self._token_expiry = 0.0
        self._session_id: str | None = None

    # ---- low level ---------------------------------------------------------------
    def _pace(self) -> None:
        if self._last_call is not None:
            wait = config.MIN_INTERVAL_SECONDS - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _send(self, method: str, url: str, **kwargs) -> requests.Response:
        """One HTTP call with pacing and a single retry on network error / 5xx."""
        for attempt in range(config.RETRIES + 1):
            self._pace()
            try:
                resp = self.http.request(method, url, timeout=config.TIMEOUT, **kwargs)
            except requests.RequestException as exc:
                if attempt < config.RETRIES:
                    log.warning("network error (%s), retrying", type(exc).__name__)
                    self._sleep(config.RETRY_BACKOFF_SECONDS)
                    continue
                raise FetchError("network", f"{type(exc).__name__}: {str(exc)[:150]}") from exc
            if resp.status_code >= 500 and attempt < config.RETRIES:
                log.warning("HTTP %s, retrying", resp.status_code)
                self._sleep(config.RETRY_BACKOFF_SECONDS)
                continue
            return resp
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _raise_for_http(resp: requests.Response, what: str) -> None:
        if resp.status_code >= 400:
            kind = "auth" if resp.status_code in (401, 403) else "http"
            raise FetchError(kind, f"{what}: HTTP {resp.status_code}", http_status=resp.status_code)

    # ---- step 0: session id ------------------------------------------------------
    def _ensure_session_id(self, cr_no: str, branch_no: str) -> str:
        if self._session_id:
            return self._session_id
        resp = self._send("GET", page_url(cr_no, branch_no))
        self._raise_for_http(resp, "details page")
        session_id = extract_session_id(resp.text)
        if not session_id:
            raise FetchError("session", "SessionID not found in the details page")
        self._session_id = session_id
        return session_id

    # ---- step 1: token -----------------------------------------------------------
    def _ensure_token(self, force: bool = False) -> None:
        if (not force and self._token
                and self._clock() < self._token_expiry - config.TOKEN_REFRESH_MARGIN_SECONDS):
            return
        password = hmac.new(config.token_hmac_key().encode("utf-8"),
                            config.TOKEN_PASSWORD_MESSAGE.encode("utf-8"),
                            hashlib.sha256).hexdigest()
        resp = self._send("POST", config.TOKEN_URL, data={
            "username": config.TOKEN_USERNAME,
            "password": password,
            "grant_type": "password",
        })
        self._raise_for_http(resp, "token")
        try:
            payload = resp.json()
            token = payload["access_token"]
            ttl = int(payload["expires_in"])      # trust expires_in, NOT 'expirey_date'
        except (ValueError, KeyError, TypeError) as exc:
            raise FetchError("auth", "token response not understood") from exc
        self._token = token
        self._token_expiry = self._clock() + ttl

    # ---- steps 2 and 3: API calls ------------------------------------------------
    def _post_api(self, url: str, body: dict, encrypted: bool, what: str) -> dict:
        resp = None
        for attempt in (1, 2):
            self._ensure_token(force=(attempt == 2))
            headers = {"Authorization": f"Bearer {self._token}", "Accept": "*/*"}
            text = json.dumps(body, ensure_ascii=False)
            if encrypted:
                data = encrypt_cryptojs(text, config.aes_passphrase())
                headers["Content-Type"] = "application/encrypted+json; charset=utf-8"
            else:
                data = text
                headers["Content-Type"] = "application/json; charset=UTF-8"
            resp = self._send("POST", url, data=data.encode("utf-8"), headers=headers)
            if resp.status_code == 401 and attempt == 1:
                log.info("token rejected, refreshing once")
                continue
            break
        self._raise_for_http(resp, what)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise FetchError("api_status", f"{what}: response is not JSON") from exc
        code = str(payload.get("Status_Code", "")) if isinstance(payload, dict) else ""
        if code != "200":
            message = str(payload.get("Message", ""))[:100] if isinstance(payload, dict) else ""
            raise FetchError("api_status", f"{what}: Status_Code={code or '?'} {message}".strip())
        return payload

    # ---- public interface (same as FileFetcher) ----------------------------------
    def search(self, cr_no: str, lang: str = "EN") -> dict:
        return self._post_api(config.SEARCH_URL, build_search_body(cr_no, lang),
                              encrypted=False, what="search")

    def details(self, cr_no: str, branch_no: str, lang: str = "EN") -> dict:
        session_id = self._ensure_session_id(cr_no, branch_no)
        body = build_details_body(cr_no, branch_no, session_id, lang)
        return self._post_api(config.DETAILS_URL, body, encrypted=True, what="details")

    def source_url(self, cr_no: str, branch_no: str) -> str:
        return page_url(cr_no, branch_no)
