"""
Upwork MCP Server — Contracts, Messages, Earnings
Stack: FastMCP + python-upwork + Railway

⚠️ Upwork API is GraphQL-only (REST is deprecated/sunset).
⚠️ Cannot submit proposals or apply to jobs via API (TOS restriction).
⚠️ No sandbox — all calls hit production.

Env vars required:
  UPWORK_CLIENT_ID
  UPWORK_CLIENT_SECRET
  UPWORK_ACCESS_TOKEN
  UPWORK_REFRESH_TOKEN
  UPWORK_ORG_UID  (organization tenant ID)
"""

import os
import json
import requests
from typing import Optional
from mcp.server.fastmcp import FastMCP

# ── Config ──────────────────────────────────────────────────────────────────

GRAPHQL_ENDPOINT = "https://api.upwork.com/graphql"

mcp = FastMCP(
    "Upwork MCP",
    description="Upwork freelancer tools — contracts, messages, earnings, job search (read-only)",
)


# ── Auth ────────────────────────────────────────────────────────────────────

class UpworkAuth:
    """Manages Upwork OAuth2 tokens with auto-refresh."""

    def __init__(self):
        self.client_id = os.environ["UPWORK_CLIENT_ID"]
        self.client_secret = os.environ["UPWORK_CLIENT_SECRET"]
        self.access_token = os.environ.get("UPWORK_ACCESS_TOKEN", "")
        self.refresh_token = os.environ["UPWORK_REFRESH_TOKEN"]
        self.org_uid = os.environ.get("UPWORK_ORG_UID", "")

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Upwork-API-TenantId": self.org_uid,
        }

    def refresh(self):
        """Refresh the access token using the refresh token."""
        resp = requests.post(
            "https://www.upwork.com/api/v3/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]
        return data


auth = UpworkAuth()


def _gql(query: str, variables: Optional[dict] = None) -> dict:
    """Execute a GraphQL query against Upwork API with auto-retry on 401."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(GRAPHQL_ENDPOINT, json=payload, headers=auth.get_headers())

    # Auto-refresh on 401
    if resp.status_code == 401:
        auth.refresh()
        resp = requests.post(GRAPHQL_ENDPOINT, json=payload, headers=auth.get_headers())

    if resp.status_code != 200:
        return {
            "error": f"{resp.status_code} {resp.reason}",
            "response_body": resp.text[:500],
        }

    data = resp.json()
    if "errors" in data:
        return {"errors": data["errors"]}
    return data.get("data", data)


# ── Tools ───────────────────────────────────────────────────────────────────

@mcp.tool()
def get_user() -> dict:
    """Get current authenticated user's profile and organization info."""
    return _gql("""
        {
            user {
                id
                nid
                rid
                name
                email
            }
            organization {
                id
                name
            }
        }
    """)


@mcp.tool()
def list_contracts(status: Optional[str] = "active") -> dict:
    """
    List freelancer contracts/engagements.
    status: 'active', 'closed', or 'all'
    """
    # Note: actual field names depend on Upwork's current GraphQL schema
    # Use the GraphQL Explorer to verify: https://www.upwork.com/developer/explorer/
    status_filter = ""
    if status and status != "all":
        status_filter = f'(status: "{status.upper()}")'

    return _gql(f"""
        {{
            engagements{status_filter} {{
                edges {{
                    node {{
                        id
                        title
                        status
                        startDate
                        endDate
                        client {{
                            name
                            companyName
                        }}
                        weeklyBudget
                        totalCharges
                    }}
                }}
            }}
        }}
    """)


@mcp.tool()
def get_contract(contract_id: str) -> dict:
    """Get detailed information about a specific contract."""
    return _gql("""
        query GetEngagement($id: ID!) {
            engagement(id: $id) {
                id
                title
                status
                startDate
                endDate
                description
                client {
                    name
                    companyName
                }
                weeklyBudget
                totalCharges
                hoursPerWeek
                feedback {
                    score
                    comment
                }
            }
        }
    """, {"id": contract_id})


@mcp.tool()
def list_rooms(limit: int = 20) -> dict:
    """List message rooms/threads."""
    return _gql(f"""
        {{
            rooms(first: {limit}) {{
                edges {{
                    node {{
                        id
                        topic
                        roomType
                        lastActivity
                        participants {{
                            name
                        }}
                        unreadCount
                    }}
                }}
            }}
        }}
    """)


@mcp.tool()
def get_messages(room_id: str, limit: int = 50) -> dict:
    """Read messages in a specific room/thread."""
    return _gql("""
        query GetMessages($roomId: ID!, $limit: Int!) {
            room(id: $roomId) {
                id
                topic
                messages(first: $limit) {
                    edges {
                        node {
                            id
                            body
                            createdAt
                            author {
                                name
                            }
                        }
                    }
                }
            }
        }
    """, {"roomId": room_id, "limit": limit})


@mcp.tool()
def send_message(room_id: str, body: str) -> dict:
    """
    Send a message in a room. ⚠️ This sends a real message on your Upwork account.
    Requires explicit user confirmation before calling.
    """
    return _gql("""
        mutation SendMessage($roomId: ID!, $body: String!) {
            sendMessage(roomId: $roomId, body: $body) {
                id
                body
                createdAt
            }
        }
    """, {"roomId": room_id, "body": body})


@mcp.tool()
def get_earnings(period: Optional[str] = "last_30_days") -> dict:
    """
    Get earnings/financial summary.
    period: 'last_7_days', 'last_30_days', 'last_90_days', 'this_year'
    """
    # Note: Financial reporting fields vary — verify against GraphQL Explorer
    return _gql("""
        {
            financialOverview {
                totalEarnings
                pendingPayments
                availableBalance
                recentTransactions(first: 20) {
                    edges {
                        node {
                            id
                            amount
                            description
                            date
                            type
                        }
                    }
                }
            }
        }
    """)


@mcp.tool()
def list_offers(status: Optional[str] = "pending") -> dict:
    """List incoming client offers."""
    return _gql(f"""
        {{
            offers(status: "{status.upper() if status else 'PENDING'}") {{
                edges {{
                    node {{
                        id
                        title
                        client {{
                            name
                            companyName
                        }}
                        budget
                        duration
                        description
                        createdAt
                    }}
                }}
            }}
        }}
    """)


@mcp.tool()
def respond_to_offer(offer_id: str, action: str) -> dict:
    """
    Accept or decline an offer. ⚠️ This is a binding action on your Upwork account.
    action: 'accept' or 'decline'
    Requires explicit user confirmation before calling.
    """
    if action.lower() not in ("accept", "decline"):
        return {"error": "action must be 'accept' or 'decline'"}

    mutation_name = "acceptOffer" if action.lower() == "accept" else "declineOffer"
    return _gql(f"""
        mutation {{
            {mutation_name}(offerId: "{offer_id}") {{
                id
                status
            }}
        }}
    """)


@mcp.tool()
def search_jobs(query: str, limit: int = 20) -> dict:
    """
    Search for job postings (read-only).
    ⚠️ Cannot submit proposals via API — this is for research only.
    """
    return _gql("""
        query SearchJobs($query: String!, $limit: Int!) {
            jobPostings(search: $query, first: $limit) {
                edges {
                    node {
                        id
                        title
                        description
                        budget
                        hourlyRate
                        skills
                        category
                        postedAt
                        client {
                            name
                            rating
                            totalSpent
                        }
                    }
                }
            }
        }
    """, {"query": query, "limit": limit})


# ── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
