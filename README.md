# Sijilat CR prototype

A small Python prototype that takes a Bahrain commercial-registration (CR) number, collects
five fields for every branch from the public Sijilat registry (sijilat.bh), and writes
structured JSON.

**Business used:** CR **931** (Asia Jewellers B.S.C. Closed and related trade names). It has
**30 branches**, including active, deleted and merged ones, which makes it a good test of
branch handling.

**Time spent:** about 1 h 50 min.

Technical details (request flow, field mapping, status rules): [docs/TECHNICAL.md](docs/TECHNICAL.md).

---

## 1. How to run

Requirements: Python 3.10+ (developed on 3.14, Windows 11).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt       # requests, pycryptodome (+ pytest for tests)
```

**Live runs need two values** that the site's own public JavaScript uses for anonymous
visitors (see section 2). Copy `.env.example` to `.env` and fill them in. `.env` is never
committed or submitted.

| Command | What it does |
|---|---|
| `python -m sijilat.cli --cr 931` | Live run, all branches → `output/931.json` |
| `python -m sijilat.cli --cr 931 --branch 5` | One branch only |
| `python -m sijilat.cli --cr 931 --save-raw samples` | Live run that also saves the (minimised) raw responses |
| `python -m sijilat.cli --cr 931 --from-dir samples` | **Offline** replay from saved responses (no keys needed) |
| `python -m sijilat.cli --cr 931 --from-dir samples --simulate-failure details --simulate-branch 5` | **Simulated** failure of one branch |
| `python -m sijilat.compare output/run1.json output/run2.json` | Field-by-field comparison of two runs |
| `python -m sijilat.benchmark --crs 1 931 15000` | Live measurement over several CRs → `output/benchmark.json` |
| `python -m pytest -q` | Tests (offline, use `samples/`) |

Exit codes: `0` success · `1` failed · `2` partial · `3` not found · `4` configuration error.

## 2. Approach

**Investigation.** The public "Search CR" pages render their data with JavaScript from a JSON
API, so the HTML contains no data to parse. Using the browser's DevTools network tab on the
public pages, I found the sequence the browser itself performs:

1. `GET` the public details page → a per-visit `SessionID` embedded in the page script.
2. `POST api.sijilat.bh/token` → an anonymous bearer token (~30 min). The password is an HMAC
   computed by the page's own script from values in its public `js/config.js`.
3. `POST …/AdvanceSearchCR_Paging` (plain JSON) → the list of branches for the CR (paged, 10/page).
4. `POST …/CompleteCRDetails` (body AES-encrypted in the browser with CryptoJS; the passphrase is
   a literal in the public script) → name, status, address and activities for one branch.

The prototype repeats these calls exactly as the browser does. **It uses no login, no
credentials of a person and nothing that is not delivered to every anonymous visitor.** The two
values are kept out of the code (in `.env`) because they are the site's, not because they are
private. I chose this over HTML scraping or browser automation because it is faster, more
stable to parse (structured JSON rather than rendered text), and lets me tell "the source has
no value" apart from "my code failed". A headless browser (Playwright) would be the
conservative fallback if the site objected to direct API use or changed its scheme.

**Field statuses.** Every field has a `status` and a `value`:

| Status | Meaning |
|---|---|
| `ok` | Found and extracted. Individual blank sub-parts (e.g. no road name) are `null`. |
| `absent_in_source` | The source answered, but has no value (e.g. `businessActivities: null`). |
| `not_retrieved` | We never got the data (network, HTTP, API error). |
| `extraction_failed` | We got a response but it was not in the expected structure. |

**Branches.** One record per branch, keyed by `branch_id`, each with its own `source_url`
(the public page for that branch). A failure on one branch never removes another. If the
details call for a branch fails, four of the fields fall back to the search row (marked
`origin: "search"`) and the address, which only exists in the details call, is `not_retrieved`.

**Outcome.** Branch: `success` (every field `ok` or `absent_in_source`) / `partial` / `failed`.
Run: `success` / `partial` / `failed` / `not_found`, plus `notes` explaining any non-success.

**Example (abridged):**

```json
{
  "cr_number": "931",
  "source": "https://www.sijilat.bh",
  "collected_at": "2026-10-24T18:00:32Z",
  "mode": "live",
  "outcome": "success",
  "notes": [],
  "branches": [
    {
      "branch_id": "6",
      "source_url": "https://www.sijilat.bh/public-search-cr/search-cr-3.aspx?cr_no=931&branch_no=6",
      "outcome": "success",
      "commercial_name": {"status": "ok", "value": {"en": "PHOENICIA DECOR", "ar": "فينيسيا ديكور"}},
      "registration": {"status": "ok", "value": {"cr_number": "931", "branch_id": "6"}},
      "registration_status": {"status": "ok", "value": "DELETED - MERGED WITH ANOTHER BRANCH"},
      "business_activities": {"status": "absent_in_source", "value": null, "detail": "'businessActivities' is null"},
      "commercial_address": {"status": "ok", "value": {"flat": "0", "building": "678", "road": "3918", "road_name": "ROAD 3918", "block": "439", "town": "NORTH SEHLA", "po_box": "861"}}
    }
  ]
}
```

Activities carry both `activity_code` (Sijilat's internal activity ID) and `isic4_code`
(ISIC Rev.4 with Bahraini local suffixes, e.g. `469-1`).

**Assumptions**
- The CR number is entered without the branch suffix; all branches are collected unless `--branch` is given.
- English (`EN`) is the default language; names are returned in both English and Arabic anyway.
- The details response is plain JSON (verified live; only the request body is encrypted).
- An unknown CR returns `jsonData: []` with "No Data Found." (verified live with CR 99999999), which is treated as `not_found`, not as an error.

**Manual steps:** reading the site's network calls and `config.js` in DevTools; choosing the CR;
copying the two values into `.env`.

**Politeness and data minimisation:** at most 1 request/second, one retry, identifying
User-Agent, a hard cap of 20 search pages. Only the five requested fields are read. The live
responses also contain shareholders, signatories, board members, IBAN, e-mail and phone
numbers; **the saved files in `samples/` keep only the keys the parser uses**, so none of that
personal data is stored or submitted.

## 3. Verification

**What ran where**

| Demonstration | Source | File |
|---|---|---|
| Full collection, 30 branches | **Live** | `output/run1.json` |
| Repeat run, same CR | **Live** | `output/run2.json` |
| Unknown CR (real, not simulated) | **Live** | `output/not_found_99999999.json` |
| Replay of saved responses | Local (`samples/`) | `output/replay_from_samples.json` |
| Failure of branch 5's details call | Local, **SIMULATED** | `output/simulated_failure_branch5.json` |
| 17 automated tests | Local | `tests/` |

No access obstacle was hit; everything in the live rows ran against sijilat.bh.

**Repeat run:** `python -m sijilat.compare output/run1.json output/run2.json` gives
`30 vs 30 branches … RESULT: identical data` (only `collected_at` differs: 18:00:32Z vs
18:01:20Z). The live run and the offline replay are also identical (`--ignore-mode`), which
shows the minimised samples lose nothing the output needs.

**Simulated failure** (clearly marked `"simulated": true` in the file and in the note): branch 5
becomes `partial`. Its address is `not_retrieved`, and the name, registration, status and
activities come from the search row (`origin: "search"`). The other 29 branches stay `success`.

**Not yet verified:** field-level accuracy against the website by hand. The runs above show the
output is complete, repeatable and identical to the saved source responses; they do not show
that a person reading the page would record the same values. Section 5 describes that check.

## 4. Known limitations

- **Depends on the site's client-side scheme.** If the token values, the encryption or the
  endpoint shapes change, live runs fail cleanly (`not_retrieved` / `failed` with a note), and
  the code must be updated. No HTML parsing of the rendered page is used as a fallback.
- **Branch numbers are not contiguous** (931 has 1 and 5–33; 2–4 are not listed by the source).
  The prototype reports what the source lists and does not guess the missing ones.
- **Source data is reproduced as is**: `"0"` used for "no flat", mixed English/Arabic town
  names (`AL SEEF/السيف`), inconsistent spelling (`AL-SEEF` vs `AL SEEF`). Nothing is
  normalised or translated.
- Up to 200 branches (20 search pages); beyond that the run is `partial` with a note.
- The per-visit `SessionID` is read once per run and not refreshed. If it expired during a very
  long run, the remaining branches would fall back to the search row (address `not_retrieved`).
- Not tested: Arabic-language mode (`--lang AR`) on all fields; very large CRs; rate limits under
  load. The automated tests cover the parser, pipeline and encryption; the live client
  (pagination, token refresh, pacing) was checked only through live runs, not unit tests.
- No scheduled runs, change history or database. Each run is a single JSON snapshot.

## 5. Value, human review and measurement

**What it could replace:** the manual lookup an analyst does for KYC, onboarding or due
diligence: searching the CR, opening each branch page, and copying name, status,
activities and address into a file. For a multi-branch CR like 931 that is 30 pages by hand;
the prototype did it in 34 seconds (measured, see below) with a source link per branch.

**What still needs human review:**
- Interpreting status (e.g. "DELETED WITH PAYMENT" vs "MERGED") and its consequence for a decision.
- Matching a CR to the right real-world entity when names are similar or have changed.
- Anything marked other than `ok`, and any `warnings` (search vs details disagree).
- Information beyond these five fields (ownership, signatories), which is deliberately out of scope.

**How to measure value:**
- *Time:* minutes per CR, manual vs prototype plus review, on a sample of 20–50 CRs.
- *Accuracy:* field-level agreement with a manual double check on a random sample; target ≥ 99% on `ok` fields.
- *Coverage:* share of fields `ok` vs `not_retrieved` / `extraction_failed` over many runs (the
  latter two are our failures and should trend to 0).
- *Robustness:* how often the run breaks over weeks (source changes), and time to fix.

**Measured (live, 2026-10-24).** `python -m sijilat.benchmark --crs 1 7 52 931 2500 15000 40000 75000 110000 140000 160000 999999 --max-branches 30`
(12 CR numbers spread across the range, chosen by me, not random; full results in `output/benchmark.json`):

| Metric | Result |
|---|---|
| CRs found / not found | 10 / 2 (7 and 999999; both correctly `not_found`) |
| Branches collected | 78 (1 to 30 per CR) |
| Fields collected | 390 |
| `ok` | 95.9 % (374) |
| `absent_in_source` | 4.1 % (16) |
| `not_retrieved` + `extraction_failed` (our failures) | **0 %** |
| Machine time | 119 s in total, **1.5 s per branch**, 97 HTTP requests (about 1 per branch plus setup) |

The absent values are not random gaps. In the 14 of 16 I inspected, each one belonged to an
**inactive** branch: "SOLD OR LEGAL STATUS CHANGED", "DELETED WITH PAYMENT" or "Deactivated
for Not Renewing the CR". For those branches the source drops the activities, or (once) the
whole address.

**Manual baseline (not yet measured).** The next step is to time a person collecting 5 branches
by hand (search, open the page, copy the five fields into a sheet), then compare their 25 values
with the prototype's output for the same branches. That gives both the manual minutes per branch
and a first accuracy figure.

Estimate: *time saved per CR ≈ branches × (manual minutes per branch − review minutes per branch)*.
For illustration only (assumed figures, not measured): at 2 min by hand and 0.25 min of review per
branch, CR 931 would take about 60 min by hand and about 8 min with the prototype.

What this sample does **not** show: accuracy, which needs the manual check above; behaviour on a
random or much larger sample; and stability over time.

## 6. Tools, and whether AI adds value

- **Python + `requests`**: simple, explicit HTTP with sessions and cookies.
- **`pycryptodome`**: reproduces the browser's CryptoJS AES encryption exactly.
- **No browser automation and no LLM at run time.** This is deterministic extraction from
  structured JSON. An LLM in the pipeline would add cost, latency and the risk of invented or
  altered values, with no benefit, because the fields are already labelled.
- **Where AI helps:** during development (reading the site's JavaScript, writing and
  reviewing code, listing edge cases), and possibly later on top of the output (summarising
  activities, flagging unusual status changes), always with the source values kept unchanged.

## 7. AI assistance

I used an AI coding assistant (Claude, in VS Code) as a pair programmer.

**AI-assisted:** writing and refactoring code to my design (package layout, pagination,
the minimised sample files, the comparison script, tests), reviewing edge cases, and
drafting the README and `docs/TECHNICAL.md`.

**Done or decided by me:**
- The architecture: separating fetching from parsing, the four field statuses, one record per branch, the search-row fallback.
- Investigating the source in DevTools: the network calls, `config.js`, the request shapes.
- Choosing the business (CR 931) and running every live run.
- Reviewing the code and the output, and deciding the output shape (removing fields the brief did not ask for).
- Setting the constraints the work had to respect: public, anonymous access only; at most one request per second; and no personal data (shareholders, signatories, IBAN, contact details) stored or submitted.

The AI was not used at run time. Every value in the output comes directly from the source.

## Project layout

```
sijilat/   cli.py  pipeline.py  parser.py  client.py  payloads.py  crypto.py
           fetchers.py (file replay, recording, simulated failure)  compare.py  config.py  models.py
samples/   minimised raw responses saved from the live run (used by replay and tests)
output/    sample outputs listed in section 3
tests/     pytest tests (offline)
docs/      TECHNICAL.md: request flow, field mapping, status rules
```
