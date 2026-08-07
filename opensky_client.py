"""
OpenSky Network API client with automatic OAuth2 token refresh.

OpenSky retired basic auth; all authenticated requests now use the
client_credentials flow. Tokens expire after 30 minutes, so this module
refreshes proactively rather than waiting for a 401.

Usage:
    client = OpenSkyClient(client_id="...", client_secret="...")
    states = client.states_all(lamin=59.8, lomin=10.5, lamax=60.3, lomax=11.3)
    own = client.states_own()  # free, no rate limit — your own receivers only
"""

import time
import requests
from dataclasses import dataclass, field
from typing import Optional

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API_ROOT = "https://opensky-network.org/api"

# Refresh this many seconds before actual expiry, to avoid racing a request
# against a token that dies mid-flight.
TOKEN_REFRESH_MARGIN_SECONDS = 30


class OpenSkyRateLimitError(Exception):
    """Raised on HTTP 429. `retry_after` is seconds to wait, from the
    X-Rate-Limit-Retry-After-Seconds header (None if the header was absent)."""

    def __init__(self, retry_after: Optional[int]):
        self.retry_after = retry_after
        super().__init__(f"OpenSky rate limit hit, retry after {retry_after}s")


@dataclass
class OpenSkyClient:
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    session: requests.Session = field(default_factory=requests.Session)

    _token: Optional[str] = field(default=None, init=False, repr=False)
    _expires_at: float = field(default=0.0, init=False, repr=False)

    # ---- auth ----

    @property
    def is_authenticated(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> Optional[str]:
        """Return a valid bearer token, refreshing if needed. Returns None
        if no credentials were configured (anonymous mode)."""
        if not self.is_authenticated:
            return None
        if self._token and time.time() < self._expires_at:
            return self._token
        return self._refresh_token()

    def _refresh_token(self) -> str:
        resp = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        expires_in = data.get("expires_in", 1800)
        self._expires_at = time.time() + expires_in - TOKEN_REFRESH_MARGIN_SECONDS
        return self._token

    def _headers(self) -> dict:
        token = self._get_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    # ---- requests ----

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        resp = self.session.get(
            f"{API_ROOT}{path}", params=params, headers=self._headers(), timeout=15
        )
        if resp.status_code == 429:
            retry_after = resp.headers.get("X-Rate-Limit-Retry-After-Seconds")
            raise OpenSkyRateLimitError(int(retry_after) if retry_after else None)
        resp.raise_for_status()
        return resp.json()

    def credits_remaining(self, resp_headers: dict) -> Optional[int]:
        """Pull remaining credits from a response's headers, if present."""
        val = resp_headers.get("X-Rate-Limit-Remaining")
        return int(val) if val is not None else None

    # ---- endpoints ----

    def states_all(
        self,
        lamin: Optional[float] = None,
        lomin: Optional[float] = None,
        lamax: Optional[float] = None,
        lomax: Optional[float] = None,
        icao24: Optional[str] = None,
        extended: bool = False,
    ) -> dict:
        """Global state vectors. Costs credits (1-4 depending on bbox area).
        Prefer states_own() for your own receiver's data — it's free."""
        params = {}
        if lamin is not None:
            params.update(lamin=lamin, lomin=lomin, lamax=lamax, lomax=lomax)
        if icao24:
            params["icao24"] = icao24
        if extended:
            params["extended"] = 1
        return self._get("/states/all", params)

    def states_own(self, serials: Optional[list] = None, extended: bool = True) -> dict:
        """State vectors from your own receiver(s) only. Requires
        authentication, but is free and has no rate limit. extended
        defaults to True here (unlike states_all) since category data is
        needed for ground-vehicle filtering and there's no credit cost to
        worry about on this endpoint."""
        if not self.is_authenticated:
            raise RuntimeError("states_own requires client_id/client_secret")
        params = {}
        if serials:
            params["serials"] = serials
        if extended:
            params["extended"] = 1
        return self._get("/states/own", params)


# ---- rate-budget helper for polling intervals ----

# Matches what we worked out for /api/matrix polling: pick an interval that
# safely spends the daily credit budget for a given tier without running out
# before the day resets. 10% margin built in.
TIER_DAILY_CREDITS = {
    "anonymous": 400,
    "registered": 4000,
    "feeder": 8000,
}
SECONDS_PER_DAY = 86400


def recommended_poll_interval_seconds(tier: str, credits_per_call: int = 1) -> int:
    daily = TIER_DAILY_CREDITS[tier]
    calls_per_day = daily / credits_per_call
    raw_interval = SECONDS_PER_DAY / calls_per_day
    return int(raw_interval * 1.1)  # 10% margin
