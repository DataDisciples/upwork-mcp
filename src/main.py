#!/usr/bin/env python3
"""Upwork MCP Server.

Read tools (always on): get_user, list_contracts, get_contract, list_rooms,
get_messages, get_earnings, list_offers, search_jobs.

Binding mutations (gated behind UPWORK_ALLOW_DESTRUCTIVE=true):
send_message, respond_to_offer.

Transports:
- stdio (default): local Claude Desktop / Cursor.
- http: streamable-http for Railway. Auth via WorkOS AuthKit (OAuth 2.1 + DCR);
  requires AUTHKIT_DOMAIN and MCP_BASE_URL.

Select via MCP_TRANSPORT=stdio|http (default stdio).
"""

import os
import sys

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tools import contracts, earnings, jobs, messages, offers, user


def _build_authkit_auth():
    authkit_domain = os.getenv("AUTHKIT_DOMAIN")
    base_url = os.getenv("MCP_BASE_URL")
    if not authkit_domain or not base_url:
        raise RuntimeError(
            "AUTHKIT_DOMAIN and MCP_BASE_URL env vars are required when "
            "MCP_TRANSPORT=http. See README.md."
        )
    from fastmcp.server.auth.providers.workos import AuthKitProvider

    return AuthKitProvider(authkit_domain=authkit_domain, base_url=base_url)


def build_app(*, auth=None) -> FastMCP:
    app = FastMCP(name="upwork", auth=auth) if auth else FastMCP(name="upwork")
    for module in (user, contracts, messages, earnings, offers, jobs):
        module.register(app)
    return app


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        build_app().run()
        return

    app = build_app(auth=_build_authkit_auth())
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    from server_http import build_http_app
    import uvicorn

    uvicorn.run(
        build_http_app(app),
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
