import httpx
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class AetherAPI:
    def __init__(self, base_url: str = "https://to-aether.com"):
        self.base_url = base_url.rstrip("/")
        self.api_base = urljoin(self.base_url + "/", "api/v1/")
        self._client = httpx.Client(
            base_url=self.api_base,
            timeout=60,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
            },
        )
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self.current_email: Optional[str] = None

    def _update_auth_header(self):
        if self._access_token:
            self._client.headers["Authorization"] = f"Bearer {self._access_token}"

    # --- Auth ---

    def get_public_settings(self) -> dict:
        resp = self._client.get("/settings/public")
        resp.raise_for_status()
        return resp.json()["data"]

    def send_verify_code(
        self, email: str, turnstile_token: Optional[str] = None
    ) -> dict:
        payload = {"email": email}
        if turnstile_token:
            payload["turnstile_token"] = turnstile_token
        resp = self._client.post("/auth/send-verify-code", json=payload)
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(
                f"send-verify-code failed: {data.get('message', resp.text)}"
            )
        return data

    def register(
        self,
        email: str,
        password: str,
        verify_code: Optional[str] = None,
        turnstile_token: Optional[str] = None,
        promo_code: Optional[str] = None,
        invitation_code: Optional[str] = None,
    ) -> dict:
        payload = {"email": email, "password": password}
        if verify_code:
            payload["verify_code"] = verify_code
        if turnstile_token:
            payload["turnstile_token"] = turnstile_token
        if promo_code:
            payload["promo_code"] = promo_code
        if invitation_code:
            payload["invitation_code"] = invitation_code

        resp = self._client.post("/auth/register", json=payload)
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"register failed: {data.get('message', resp.text)}")
        result = data.get("data", {})
        if "access_token" in result:
            self._access_token = result["access_token"]
            self._refresh_token = result.get("refresh_token")
            self.current_email = email
            self._update_auth_header()
        return result

    def login(
        self, email: str, password: str, turnstile_token: Optional[str] = None
    ) -> dict:
        payload = {"email": email, "password": password}
        if turnstile_token:
            payload["turnstile_token"] = turnstile_token
        resp = self._client.post("/auth/login", json=payload)
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"login failed: {data.get('message', resp.text)}")
        result = data.get("data", {})
        if "access_token" in result:
            self._access_token = result["access_token"]
            self._refresh_token = result.get("refresh_token")
            self.current_email = email
            self._update_auth_header()
        elif result.get("requires_2fa"):
            raise RuntimeError("2FA required but not supported")
        return result

    # --- Groups ---

    def get_available_groups(self) -> List[Dict[str, Any]]:
        if not self._access_token:
            raise RuntimeError("Not authenticated")
        resp = self._client.get("/groups/available")
        resp.raise_for_status()
        return resp.json().get("data", [])

    # --- API Keys ---

    def create_api_key(
        self,
        name: str,
        group_id: Optional[int] = None,
        ip_whitelist: Optional[List[str]] = None,
        ip_blacklist: Optional[List[str]] = None,
        quota: Optional[int] = None,
        expires_in_days: Optional[int] = None,
        rate_limit_5h: Optional[int] = None,
        rate_limit_1d: Optional[int] = None,
        rate_limit_7d: Optional[int] = None,
    ) -> dict:
        if not self._access_token:
            raise RuntimeError("Not authenticated")
        payload: Dict[str, Any] = {"name": name}
        if group_id is not None:
            payload["group_id"] = group_id
        if ip_whitelist:
            payload["ip_whitelist"] = ip_whitelist
        if ip_blacklist:
            payload["ip_blacklist"] = ip_blacklist
        if quota is not None and quota > 0:
            payload["quota"] = quota
        if expires_in_days is not None and expires_in_days > 0:
            payload["expires_in_days"] = expires_in_days
        if rate_limit_5h and rate_limit_5h > 0:
            payload["rate_limit_5h"] = rate_limit_5h
        if rate_limit_1d and rate_limit_1d > 0:
            payload["rate_limit_1d"] = rate_limit_1d
        if rate_limit_7d and rate_limit_7d > 0:
            payload["rate_limit_7d"] = rate_limit_7d

        resp = self._client.post("/keys", json=payload)
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(
                f"create api key failed: {data.get('message', resp.text)}"
            )
        return data.get("data", data)

    def close(self):
        self._client.close()


def solve_turnstile_capsolver(
    site_key: str, page_url: str, capsolver_key: str
) -> Optional[str]:
    import capsolver

    capsolver.api_key = capsolver_key
    try:
        solution = capsolver.solve(
            {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": site_key,
            }
        )
        token = solution.get("token")
        if token:
            logger.info("CapSolver Turnstile solved successfully")
            return token
        logger.error(f"CapSolver no token: {solution}")
        return None
    except Exception as e:
        logger.error(f"CapSolver error: {e}")
        return None
