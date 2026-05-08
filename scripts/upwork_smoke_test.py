#!/usr/bin/env python3
"""Verify Upwork credentials end-to-end.

1. Bootstrap the auth client from env vars.
2. Force a token refresh (proves CLIENT_ID/SECRET + REFRESH_TOKEN are valid).
3. Issue a trivial `{ user { id name email } }` query.

Exit codes:
  0 = success
  1 = missing env vars
  2 = refresh failed
  3 = query failed
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "src"))

from upwork_client import UpworkAuthError, UpworkClient  # noqa: E402


def main() -> int:
    try:
        client = UpworkClient.from_env()
    except UpworkAuthError as exc:
        print(f"ERROR (config): {exc}", file=sys.stderr)
        return 1

    try:
        client.refresh()
        print(f"OK  refresh succeeded  access_token=***{client.access_token[-6:]}")
    except Exception as exc:
        print(f"ERROR (refresh): {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2

    result = client.gql("query { user { id name email } organization { id name } }")
    if "errors" in result or "error" in result:
        print(f"ERROR (query): {json.dumps(result, indent=2)}", file=sys.stderr)
        return 3

    print("OK  smoke test passed")
    print(json.dumps(result, indent=2)[:500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
