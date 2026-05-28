"""Upwork GraphQL client with OAuth2 auto-refresh and token persistence.

Shared by:
- The MCP server (src/main.py + src/tools/*)
- The Domo pipeline (pipeline/*)

Token persistence:
    Upwork rotates the refresh token on every refresh. Storing only env vars
    means a single restart after a refresh wipes out the new refresh_token and
    locks the integration out. We persist the latest pair to a file
    (UPWORK_TOKEN_FILE, default /data/upwork_tokens.json on Railway) so the
    container can survive restarts. Falls back to env-only if the path is not
    writable -- fine for local dev.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://api.upwork.com/graphql"
TOKEN_ENDPOINT = "https://www.upwork.com/api/v3/oauth2/token"
DEFAULT_TOKEN_FILE = "/data/upwork_tokens.json"


class UpworkAuthError(RuntimeError):
    """Raised when auth cannot be initialized or refreshed."""


class UpworkClient:
    """Thread-safe Upwork GraphQL client with auto-refresh."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        access_token: str = "",
        org_uid: str = "",
        token_file: Optional[str] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.org_uid = org_uid
        self._token_file = Path(token_file) if token_file else None
        self._lock = threading.Lock()

        self._load_persisted_tokens()

    @classmethod
    def from_env(cls) -> "UpworkClient":
        client_id = os.environ.get("UPWORK_CLIENT_ID")
        client_secret = os.environ.get("UPWORK_CLIENT_SECRET")
        refresh_token = os.environ.get("UPWORK_REFRESH_TOKEN")
        missing = [
            n
            for n, v in (
                ("UPWORK_CLIENT_ID", client_id),
                ("UPWORK_CLIENT_SECRET", client_secret),
                ("UPWORK_REFRESH_TOKEN", refresh_token),
            )
            if not v
        ]
        if missing:
            raise UpworkAuthError(
                f"Missing required env vars: {', '.join(missing)}. "
                "Apply at https://www.upwork.com/developer/keys/apply"
            )
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            access_token=os.environ.get("UPWORK_ACCESS_TOKEN", ""),
            org_uid=os.environ.get("UPWORK_ORG_UID", ""),
            token_file=os.environ.get("UPWORK_TOKEN_FILE", DEFAULT_TOKEN_FILE),
        )

    def _load_persisted_tokens(self) -> None:
        if not self._token_file or not self._token_file.exists():
            return
        try:
            data = json.loads(self._token_file.read_text())
            if data.get("access_token"):
                self.access_token = data["access_token"]
            if data.get("refresh_token"):
                self.refresh_token = data["refresh_token"]
            logger.info("Loaded persisted Upwork tokens from %s", self._token_file)
        except Exception as exc:
            logger.warning("Could not read token file %s: %s", self._token_file, exc)

    def _persist_tokens(self) -> None:
        if not self._token_file:
            return
        try:
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            self._token_file.write_text(
                json.dumps(
                    {
                        "access_token": self.access_token,
                        "refresh_token": self.refresh_token,
                        "updated_at": int(time.time()),
                    }
                )
            )
        except Exception as exc:
            logger.warning("Could not persist token file %s: %s", self._token_file, exc)

    def _headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if self.org_uid:
            h["X-Upwork-API-TenantId"] = self.org_uid
        return h

    def refresh(self) -> None:
        with self._lock:
            resp = requests.post(
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                raise UpworkAuthError(
                    f"Token refresh failed: {resp.status_code} {resp.text[:300]}"
                )
            data = resp.json()
            self.access_token = data["access_token"]
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
            self._persist_tokens()
            logger.info("Refreshed Upwork access token")

    def gql(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query, auto-refreshing once on 401."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        if not self.access_token:
            self.refresh()

        resp = requests.post(
            GRAPHQL_ENDPOINT, json=payload, headers=self._headers(), timeout=60
        )
        if resp.status_code == 401:
            self.refresh()
            resp = requests.post(
                GRAPHQL_ENDPOINT, json=payload, headers=self._headers(), timeout=60
            )

        if resp.status_code != 200:
            return {
                "error": f"{resp.status_code} {resp.reason}",
                "response_body": resp.text[:500],
            }
        data = resp.json()
        if "errors" in data:
            return {"errors": data["errors"], "data": data.get("data")}
        return data.get("data", data)


_singleton: Optional[UpworkClient] = None


def get_client() -> UpworkClient:
    global _singleton
    if _singleton is None:
        _singleton = UpworkClient.from_env()
    return _singleton
