"""Cursor-paginated extractors for the Upwork->Domo pipeline.

Each function fully drains a connection (handles pageInfo) and returns a
flat list of dicts ready to feed into pandas. Schema fields below are
unverified and must be reconciled against the live GraphQL schema once
Upwork activates the credentials. See src/tools/_helpers.py.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Optional

# Allow running this module both as `python -m pipeline.extractors` and via
# scripts/* that import it after extending sys.path to include src/.
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from upwork_client import UpworkClient  # noqa: E402

logger = logging.getLogger(__name__)


def _drain(
    client: UpworkClient,
    query: str,
    connection_path: list[str],
    variables: Optional[dict] = None,
    page_size: int = 100,
    sleep_between: float = 0.2,
) -> Iterator[dict]:
    """Walk a cursor-paginated GraphQL connection and yield each node."""
    cursor: Optional[str] = None
    variables = dict(variables or {})
    variables.setdefault("first", page_size)

    while True:
        variables["after"] = cursor
        result = client.gql(query, variables)
        if "errors" in result:
            logger.error("GraphQL errors: %s", result["errors"])
            return
        node = result
        for key in connection_path:
            if not isinstance(node, dict):
                logger.error("Unexpected response shape at %s: %s", key, node)
                return
            node = node.get(key) or {}
        edges = node.get("edges") or []
        for edge in edges:
            n = edge.get("node")
            if n:
                yield n
        page_info = node.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break
        time.sleep(sleep_between)


def extract_contracts(client: UpworkClient) -> list[dict]:
    query = """
        query Contracts($first: Int!, $after: String) {
            engagements(first: $first, after: $after) {
                edges {
                    node {
                        id title status startDate endDate
                        client { name companyName }
                        weeklyBudget totalCharges hoursPerWeek
                        feedback { score comment }
                    }
                }
                pageInfo { hasNextPage endCursor }
            }
        }
    """
    return list(_drain(client, query, ["engagements"]))


def extract_offers(client: UpworkClient) -> list[dict]:
    # Drain twice -- pending and recent decisions.
    out: list[dict] = []
    for status in ("PENDING", "ACCEPTED", "DECLINED"):
        query = """
            query Offers($first: Int!, $after: String, $status: OfferStatus!) {
                offers(status: $status, first: $first, after: $after) {
                    edges {
                        node {
                            id title status createdAt
                            client { name companyName }
                            budget duration description
                        }
                    }
                    pageInfo { hasNextPage endCursor }
                }
            }
        """
        out.extend(_drain(client, query, ["offers"], {"status": status}))
    return out


def extract_earnings(client: UpworkClient) -> dict:
    """Returns a single dict (financialOverview is not paginated)."""
    return client.gql(
        """
        query Earnings {
            financialOverview {
                totalEarnings pendingPayments availableBalance
                recentTransactions(first: 200) {
                    edges { node { id amount description date type } }
                }
            }
        }
        """
    )


def extract_time_logs(
    client: UpworkClient, start_date: str, end_date: str
) -> list[dict]:
    """SCHEMA UNVERIFIED. Upwork exposes time logs under different names per
    org (timeLogs, workDiary, hourlyEntries). Confirm against the Explorer."""
    query = """
        query TimeLogs($first: Int!, $after: String, $start: Date!, $end: Date!) {
            timeLogs(first: $first, after: $after, startDate: $start, endDate: $end) {
                edges {
                    node {
                        id contractId workDate hours
                        memo freelancerId
                    }
                }
                pageInfo { hasNextPage endCursor }
            }
        }
    """
    return list(
        _drain(client, query, ["timeLogs"], {"start": start_date, "end": end_date})
    )


def extract_rooms(client: UpworkClient) -> list[dict]:
    query = """
        query Rooms($first: Int!, $after: String) {
            rooms(first: $first, after: $after) {
                edges {
                    node {
                        id topic roomType lastActivity
                        unreadCount
                        participants { name }
                    }
                }
                pageInfo { hasNextPage endCursor }
            }
        }
    """
    return list(_drain(client, query, ["rooms"]))
