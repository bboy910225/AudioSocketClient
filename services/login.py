# -*- coding: utf-8 -*-
"""
Reusable login client for your app.

Usage:
    from login import LoginClient

    client = LoginClient(app_base="https://tta-ad", username="456456", password="456456")
    token = client.get_token()            # lazy-login and return token
    headers = client.auth_headers()       # {"Authorization": "Bearer ...", ...}
    sess = client.session                 # underlying requests.Session (verify already set)

Notes:
- Password is base64-encoded to match your server-side expectation (same as old code).
- CA verification defaults to "./app.crt"; override with True/False or a custom bundle path.
"""
from __future__ import annotations

import base64
import requests
from typing import List, Optional, Tuple, Union

from util.common import resource_path


class LoginError(Exception):
    pass


class LoginClient:
    def __init__(
        self,
        app_base: str,
        username: str,
        password: str,
        *,
        ca_verify: Optional[Union[bool, str]] = None,
        log_func=None,
        timeout: int = 15,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.app_base = (app_base or "").rstrip("/")
        self.username = username
        self.password = password
        self.verify = ca_verify if ca_verify else True
        self.log_func = log_func
        self.timeout = int(timeout)
        self._token: Optional[str] = None
        self._sess: requests.Session = session or requests.Session()
        self._sess.verify = self.verify

    # --- public API ---
    def login(self) -> str:
        """Perform login and cache token; return token or raise LoginError."""
        url = f"{self.app_base}/login"
        payload = {
            "username": self.username,
            # server expects base64 like your old code
            "password": base64.b64encode(self.password.encode("utf-8")).decode("ascii"),
        }
        headers = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = self._sess.post(url, data=payload, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise LoginError(
                f"Login HTTP {resp.status_code}, Location={resp.headers.get('Location')}, "
                f"body_head={resp.text[:200]!r}"
            )
        try:
            data = resp.json()
        except Exception:
            raise LoginError(f"Login returned non-JSON body head={resp.text[:200]!r}")
        if data.get("status") != 1:
            self.log_func(f"登入失敗 payload: {data!r}")
            raise LoginError(f"Login failed payload: {data!r}")
        token = data.get("token")
        self.area_list = data.get("area")
        if not token:
            raise LoginError("Login succeeded but no token in payload")
        self.log_func(f"登入成功")
        self._token = token
        return token, self.area_list

    def get_token(self, refresh: bool = False) -> Tuple[str, List[str]]:
        """Return cached token; if missing or refresh=True, perform login."""
        if not self._token or refresh:
            return self.login()
        return self._token, self.area_list

    def auth_headers(self) -> dict:
        """Convenience: build Authorization/Accept/X-Requested-With headers."""
        token = self.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

    @property
    def session(self) -> requests.Session:
        return self._sess


__all__ = ["LoginClient", "LoginError"]
