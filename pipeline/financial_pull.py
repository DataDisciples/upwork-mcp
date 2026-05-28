"""Pull Upwork earnings + incoming offers + contracts; write CSVs and a
funnel summary.

Reuses src/upwork_client.py (same auth + token-refresh logic as the MCP
server). Run locally with the same env vars Railway uses:
    UPWORK_CLIENT_ID
    UPWORK_CLIENT_SECRET
    UPWORK_REFRESH_TOKEN
    UPWORK_ACCESS_TOKEN   (optional; auto-refreshes if stale)
    UPWORK_ORG_UID
    UPWORK_TOKEN_FILE     (optional; persisted token store)

Usage:
    python pipeline/financial_pull.py --out ./out

TOS NOTE: Upwork's API does NOT expose outbound proposals/applications.
"proposals.csv" in this script reflects INCOMING client offers, which is
the only "lead" signal the API exposes. The funnel summary is therefore
offers -> contracts -> earnings, not applications -> hires.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make src/ importable so we can reuse upwork_client.py without packaging.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from upwork_client import get_client  # noqa: E402


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

EARNINGS_QUERY = """
query Earnings($first: Int!) {
  financialOverview {
    totalEarnings
    pendingPayments
    availableBalance
    recentTransactions(first: $first) {
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
"""

OFFERS_QUERY = """
query Offers($status: OfferStatus!) {
  offers(status: $status) {
    edges {
      node {
        id
        title
        client { name companyName }
        budget
        duration
        createdAt
      }
    }
  }
}
"""

ENGAGEMENTS_QUERY = """
query Engagements($first: Int!, $status: EngagementStatus) {
  engagements(status: $status, first: $first) {
    edges {
      node {
        id
        title
        status
        startDate
        endDate
        client { name companyName }
        weeklyBudget
        totalCharges
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_earnings(client, first_n: int) -> dict:
    return client.gql(EARNINGS_QUERY, {"first": first_n})


def fetch_offers(client) -> list[dict]:
    rows: list[dict] = []
    for status in ("PENDING", "ACCEPTED", "DECLINED", "EXPIRED"):
        resp = client.gql(OFFERS_QUERY, {"status": status})
        if "errors" in resp:
            # Don't abort the whole run on a single status failure; record it.
            rows.append({"_status": status, "_error": json.dumps(resp["errors"])[:300]})
            continue
        edges = ((resp.get("offers") or {}).get("edges")) or []
        for e in edges:
            node = dict(e.get("node") or {})
            node["_status"] = status
            rows.append(node)
    return rows


def fetch_contracts(client) -> list[dict]:
    rows: list[dict] = []
    for status in ("ACTIVE", "CLOSED"):
        resp = client.gql(ENGAGEMENTS_QUERY, {"first": 100, "status": status})
        if "errors" in resp:
            rows.append({"_status": status, "_error": json.dumps(resp["errors"])[:300]})
            continue
        edges = ((resp.get("engagements") or {}).get("edges")) or []
        for e in edges:
            rows.append(dict(e.get("node") or {}))
    return rows


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def _flatten(row: dict) -> dict:
    out = dict(row)
    client = out.pop("client", None)
    if isinstance(client, dict):
        out["client_name"] = client.get("name")
        out["client_company"] = client.get("companyName")
    return out


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(_flatten(r))
            written += 1
    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="./out", help="Output directory (default ./out)")
    ap.add_argument(
        "--earnings-window",
        type=int,
        default=200,
        help="Number of recent transactions to pull (default 200)",
    )
    args = ap.parse_args()
    out_dir = Path(args.out)

    client = get_client()

    earnings = fetch_earnings(client, args.earnings_window)
    offers = fetch_offers(client)
    contracts = fetch_contracts(client)

    overview = earnings.get("financialOverview") or {}
    txn_edges = (overview.get("recentTransactions") or {}).get("edges") or []
    txn_rows = [dict(e.get("node") or {}) for e in txn_edges]

    earnings_n = write_csv(
        out_dir / "earnings.csv",
        txn_rows,
        ["id", "date", "amount", "type", "description"],
    )
    proposals_n = write_csv(
        out_dir / "proposals.csv",
        offers,
        [
            "id",
            "_status",
            "createdAt",
            "title",
            "client_name",
            "client_company",
            "budget",
            "duration",
            "_error",
        ],
    )
    contracts_n = write_csv(
        out_dir / "contracts.csv",
        contracts,
        [
            "id",
            "status",
            "startDate",
            "endDate",
            "title",
            "client_name",
            "client_company",
            "weeklyBudget",
            "totalCharges",
            "_error",
        ],
    )

    def _count(rows: list[dict], status: str) -> int:
        return sum(1 for r in rows if r.get("_status") == status or r.get("status") == status)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "earnings": {
            "totalEarnings": overview.get("totalEarnings"),
            "pendingPayments": overview.get("pendingPayments"),
            "availableBalance": overview.get("availableBalance"),
            "transactions_fetched": len(txn_rows),
            "earnings_window_requested": args.earnings_window,
        },
        "funnel": {
            "offers_pending": _count(offers, "PENDING"),
            "offers_accepted": _count(offers, "ACCEPTED"),
            "offers_declined": _count(offers, "DECLINED"),
            "offers_expired": _count(offers, "EXPIRED"),
            "contracts_active": _count(contracts, "ACTIVE"),
            "contracts_closed": _count(contracts, "CLOSED"),
        },
        "files": {
            "earnings_rows": earnings_n,
            "proposals_rows": proposals_n,
            "contracts_rows": contracts_n,
        },
        "caveats": [
            "Upwork TOS forbids querying outbound proposals -- proposals.csv "
            "reflects INCOMING client offers, not freelancer applications.",
            "GraphQL field names are unverified against the live schema; "
            "validate at https://www.upwork.com/developer/explorer/ if any "
            "query returns errors.",
        ],
    }

    summary_path = out_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"Wrote {out_dir}/earnings.csv ({earnings_n} rows)")
    print(f"Wrote {out_dir}/proposals.csv ({proposals_n} rows)")
    print(f"Wrote {out_dir}/contracts.csv ({contracts_n} rows)")
    print(f"Wrote {out_dir}/summary.json")
    print()
    print("Funnel:")
    print(json.dumps(summary["funnel"], indent=2))


if __name__ == "__main__":
    main()
