# Technical reference

Companion to the [README](../README.md). It describes how the prototype talks to Sijilat,
how each output field maps to the source, and the exact rules behind every status.

## 1. Request flow (live mode)

```
                         www.sijilat.bh                      api.sijilat.bh
                         --------------                      --------------
 0. GET  search-cr-3.aspx?cr_no=&branch_no=  ──► page HTML: var SessionID = '0x…'   (once per run)
 1. POST /token  (username, HMAC password)   ──► access_token, expires_in ≈ 1800 s   (reused, refreshed)
 2. POST /api/CRdetails/AdvanceSearchCR_Paging   plain JSON, 10 rows/page, repeated until
                                                 rows == Total_Records             ──► branch list
 3. POST /api/CRdetails/CompleteCRDetails        body = CryptoJS AES(JSON, passphrase)
                                                 once per branch                   ──► plain JSON details
```

- Pacing: at least 1 s between any two requests (`config.MIN_INTERVAL_SECONDS`).
- Retries: one retry on a network error or HTTP 5xx; a 401 on the API triggers one token refresh.
- An API reply counts as successful only with HTTP 2xx **and** `Status_Code == "200"` in the body.
- CR 931 costs 1 page load + 1 token + 3 search pages + 30 details calls, about 40 s.

## 2. Code map

| Module | Responsibility | Network? |
|---|---|---|
| `cli.py` | Arguments, choice of fetcher, writing the file, exit code | no |
| `pipeline.py` | search → per-branch details → parse → output dict; outcomes and notes | no |
| `parser.py` | Raw JSON → five `FieldResult`s; decides `ok` / `absent_in_source` / `extraction_failed` | no |
| `client.py` | `SijilatClient`: session, token, pagination, encryption, retries | **yes** |
| `payloads.py` | Request bodies and the public page URL | no |
| `crypto.py` | CryptoJS / OpenSSL "Salted__" AES-256-CBC | no |
| `fetchers.py` | `FileFetcher` (replay), `RecordingFetcher` (save minimised raw), `FailingFetcher` (simulate) | no |
| `compare.py` | Field-by-field diff of two outputs (repeat-run check) | no |
| `benchmark.py` | Live time, request and field-status measurement over a list of CRs | **yes** |
| `models.py` | Status constants, `FieldResult`, `FetchError`, `ExtractionError` | no |
| `config.py` | URLs, politeness settings, secrets from env / `.env` | no |

All fetchers expose the same three methods (`search`, `details`, `source_url`), so the
pipeline and parser run the same way on live data, saved files and simulated failures.

## 3. Field mapping

| Output field | Source (details response) | Fallback (search row) |
|---|---|---|
| `commercial_name.en` / `.ar` | `company_summary.CR_LNM` / `CR_ANM` | `CR_LNM` / `CR_ANM` |
| `registration.cr_number` / `.branch_id` | `company_summary.CR_NO` / `BRANCH_NO` | `CR_NO` / `BRANCH_NO` |
| `registration_status` | `company_summary.STATUS` | `STATUS` |
| `business_activities[].activity_code` | `businessActivities[].ACT_CD` | not available |
| `business_activities[].isic4_code` | `businessActivities[].ISIC4_CD` | not available |
| `business_activities[].name` | `businessActivities[].ISIC4_NM` | `ACTIVITIES`, split on `~` |
| `commercial_address.flat` | `commercialAddress.CR_FLAT` | **none** → `not_retrieved` |
| `.building` / `.road` / `.road_name` | `CR_BULD` / `CR_ROAD` / `CR_ROAD_NM` | |
| `.block` / `.town` / `.po_box` | `CR_BLOCK` / `CR_TOWN_NM` / `CR_PBOX` | |

Values are copied as the source gives them (trimmed), never normalised or translated.
Every other key in the responses is ignored, and none is kept in `samples/`.

## 4. Status rules

Evaluated per field by `parser.py` (and `pipeline.py` for `not_retrieved`):

| Situation | Status |
|---|---|
| Request failed: network, HTTP 4xx/5xx, token, `Status_Code ≠ 200`, missing SessionID | `not_retrieved` |
| Response received, but `jsonData` or a whole section is missing or has the wrong type | `extraction_failed` |
| Section present but `null` or empty (`[]`, `{}`) | `absent_in_source` |
| Leaf key missing, `null` or `""` (e.g. no status) | `absent_in_source` |
| Some address parts blank, others present | `ok`, blank parts are `null` |
| Value present | `ok` |

`detail` is written only for non-`ok` fields, and `origin: "search"` only when a value came
from the search-row fallback.

## 5. Outcomes, notes and exit codes

| Level | Values |
|---|---|
| Branch `outcome` | `success` (all fields `ok`/`absent_in_source`) · `partial` · `failed` |
| Run `outcome` | `success` · `partial` (some branch not success, or search truncated) · `failed` · `not_found` |

`notes[]` entries have `step` (`search` / `details`), `kind`, `detail`, and optionally
`branch_id`, `http_status`, `simulated`. Kinds: `network`, `http`, `auth`, `api_status`,
`session`, `file`, `extraction_failed`, `pagination`, `not_found`.

A branch's `warnings[]` (only present when not empty) lists disagreements between the search row
and the details response, such as different status text. These are findings, not errors.

CLI exit codes: `0` success, `1` failed, `2` partial, `3` not found, `4` missing configuration.

## 6. Extending

- **Another field:** add the source key to the allowlist in `fetchers.py` (so it is saved), a
  `_field()` function in `parser.py`, its name in `FIELD_NAMES`, and a test in `tests/test_parser.py`.
- **Batch of CRs:** loop over `pipeline.run()` with a single `SijilatClient` so the token and
  session are reused; keep the 1 request/second pacing.
- **Source changes:** a changed response shape shows up as `extraction_failed` and a changed
  access scheme as `not_retrieved`, never as silently wrong values. Re-capture one request in
  DevTools, update `payloads.py` or `client.py`, re-run `--save-raw`, then `pytest`.
