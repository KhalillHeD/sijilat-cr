"""Settings. Constants only; the two secrets come from environment variables.

PRODUCTION ONLY: config.js on the site lists many other environments (dev, test,
internal IPs, localhost). This prototype never talks to any of them.
"""
import os

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
