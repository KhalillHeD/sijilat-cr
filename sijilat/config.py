"""Settings. Constants only; the two secrets come from environment variables
(or a local, git-ignored .env file in the folder you run from).

PRODUCTION ONLY: config.js on the site lists many other environments (dev, test,
internal IPs, localhost). This prototype never talks to any of them.
"""
import os
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Read KEY=VALUE lines from .env into os.environ. Real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

SITE = "https://www.sijilat.bh"
API = "https://api.sijilat.bh"

DETAILS_PAGE = SITE + "/public-search-cr/search-cr-3.aspx"
TOKEN_URL = API + "/token"                                   # note: no /api prefix
SEARCH_URL = API + "/api/CRdetails/AdvanceSearchCR_Paging"   # plain JSON body
DETAILS_URL = API + "/api/CRdetails/CompleteCRDetails"       # AES-encrypted body

# Values the site's own public script uses for the anonymous visitor token.
TOKEN_USERNAME = "sijilat"
TOKEN_PASSWORD_MESSAGE = "sijilat_test"

USER_AGENT = os.environ.get("SIJILAT_USER_AGENT", "sijilat-prototype/0.1 (assessment exercise)")
MIN_INTERVAL_SECONDS = 1.0       # politeness: at most one request per second
TIMEOUT = (5, 30)                # (connect, read) seconds
RETRIES = 1                      # one retry on network error or HTTP 5xx
RETRY_BACKOFF_SECONDS = 2.0
TOKEN_REFRESH_MARGIN_SECONDS = 60
MAX_SEARCH_PAGES = 20            # safety cap: 20 pages x 10 rows = 200 branches


class MissingSecret(RuntimeError):
    """A required environment variable is not set."""


def _secret(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise MissingSecret(
            f"Environment variable {name} is not set. Copy the value from the site's "
            "own js/config.js (see README, step 'Live run')."
        )
    return value


def token_hmac_key() -> str:
    return _secret("SIJILAT_TOKEN_HMAC_KEY")


def aes_passphrase() -> str:
    return _secret("SIJILAT_AES_PASSPHRASE")
