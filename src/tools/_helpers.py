"""Shared helpers for Upwork MCP tool modules.

NOTE on GraphQL schema:
    The Upwork GraphQL schema is private and field names are not stable across
    versions. Every query in this package was authored from public docs +
    examples and MUST be validated against the live schema once credentials
    are activated:
        https://www.upwork.com/developer/explorer/

    When a query fails, fix it here -- do NOT silently swallow the error.
"""

import os


def destructive_enabled() -> bool:
    """Gate for write/binding mutations (send_message, respond_to_offer)."""
    return os.getenv("UPWORK_ALLOW_DESTRUCTIVE", "").lower() in ("1", "true", "yes")
