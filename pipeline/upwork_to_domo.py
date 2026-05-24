"""Pull Upwork client/org data -> CSVs -> (optionally) Domo datasets.

Built for a CLIENT/BUYER organization (you hire freelancers). Produces:

  transactions.csv  Financial ledger rows from `transactionHistory`
                    (your money in/out -- revenue + expenses).
  time_report.csv   Per-day hours + charges per worker from
                    `organization.clientContractTimeReport` (what you spent,
                    by freelancer, by day -- the core "expenses by worker").
  contracts.csv     Contract details (freelancer, status, dates, terms) from
                    `contractList`, using contract IDs gathered from the time
                    report.

Auth: reuses src/upwork_client.py (UPWORK_* env vars, same as the MCP server).
Domo push (--push): reuses pipeline/domo_push.py (DOMO_* env vars).

Credentials: export the env vars, OR drop a `.env` file in the repo root and
this script loads it automatically (it's gitignored). See `.env.example`.

Field selections are built by introspecting each GraphQL object type's SCALAR
fields at runtime, so we pull every available column without hard-coding field
lists that drift as Upwork changes the schema. The query *structure* and the
required filter inputs are pinned from schema discovery:
  - DateTimeRange = { rangeStart, rangeEnd }  (ISO-8601 strings)
  - transactionHistory(transactionHistoryFilter: { aceIds_any:[ID!]!,
      transactionDateTime_bt: DateTimeRange! })
  - organization.clientContractTimeReport(timeReportDate_bt: DateTimeRange!)
  - contractList(ids: [ID!]) -> { contracts }

Usage:
    python pipeline/upwork_to_domo.py --start 2026-04-01 --end 2026-04-30
    python pipeline/upwork_to_domo.py --start 2026-04-01 --end 2026-04-30 --push

When --push creates a NEW Domo dataset it prints the GUID; set
DOMO_DATASET_<NAME>=<guid> (e.g. DOMO_DATASET_TIME_REPORT) so the next run
replaces that dataset instead of creating a duplicate.

Run from a host with internet to api.upwork.com + api.domo.com (laptop, Domo
Jupyter Workspace, Railway cron, or a GitHub Action).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal, dependency-free .env loader. Sets KEY=VALUE pairs that aren't
    already in the environment. Ignores blank lines and `#` comments; strips
    surrounding quotes. So you can keep creds in a gitignored `.env` instead of
    exporting them every shell session."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# Load a local .env (gitignored) before anything reads the environment.
_load_dotenv(_REPO_ROOT / ".env")

# Make src/ importable so we reuse upwork_client.py without packaging.
sys.path.insert(0, str(_REPO_ROOT / "src"))

from upwork_client import get_client  # noqa: E402


# ---------------------------------------------------------------------------
# Introspection-driven field selection
# ---------------------------------------------------------------------------

_TYPE_FIELDS = """
query TypeFields($n: String!) {
  __type(name: $n) {
    fields {
      name
      type { kind name ofType { kind name ofType { kind name } } }
    }
  }
}
"""

_SCALARISH = {"SCALAR", "ENUM"}
_scalar_cache: dict[str, list[str]] = {}


def _core_kind(type_ref: dict | None) -> str | None:
    """Unwrap NON_NULL / LIST wrappers and return the core type's kind."""
    t = type_ref
    while t and t.get("kind") in ("NON_NULL", "LIST"):
        t = t.get("ofType")
    return (t or {}).get("kind")


def scalar_fields(client, type_name: str) -> list[str]:
    """Return the names of a GraphQL object type's scalar/enum fields."""
    if type_name in _scalar_cache:
        return _scalar_cache[type_name]
    resp = client.gql(_TYPE_FIELDS, {"n": type_name})
    fields = ((resp.get("__type") or {}) or {}).get("fields") or []
    names = [f["name"] for f in fields if _core_kind(f.get("type")) in _SCALARISH]
    _scalar_cache[type_name] = names
    return names


def selection(client, type_name: str, nested: dict[str, str] | None = None) -> str:
    """Build a GraphQL selection set: all scalar fields of `type_name`, plus
    a one-level scalar subselection for each {field_name: object_type} in
    `nested`. Falls back to __typename if a type exposes no scalars."""
    parts = list(scalar_fields(client, type_name))
    for field, tname in (nested or {}).items():
        sub = scalar_fields(client, tname)
        if sub:
            parts.append(f"{field} {{ {' '.join(sub)} }}")
    return " ".join(parts) if parts else "__typename"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_range(start: str, end: str) -> dict:
    """YYYY-MM-DD -> DateTimeRange covering the full inclusive day span."""
    return {"rangeStart": f"{start}T00:00:00Z", "rangeEnd": f"{end}T23:59:59Z"}


def _err(resp) -> bool:
    return isinstance(resp, dict) and ("errors" in resp or "error" in resp)


# ---------------------------------------------------------------------------
# Fetchers (each returns {"rows": [...]} or {"error": <payload>})
# ---------------------------------------------------------------------------

def fetch_transactions(client, ace_id: str, date_range: dict) -> dict:
    row_sel = selection(client, "TransactionHistoryRow")
    q = f"""
    query Tx($f: TransactionHistoryFilter!) {{
      transactionHistory(transactionHistoryFilter: $f) {{
        transactionDetail {{ transactionHistoryRow {{ {row_sel} }} }}
      }}
    }}
    """
    resp = client.gql(
        q,
        {"f": {"aceIds_any": [ace_id], "transactionDateTime_bt": date_range}},
    )
    if _err(resp):
        return {"error": resp}
    detail = (resp.get("transactionHistory") or {}).get("transactionDetail") or {}
    return {"rows": detail.get("transactionHistoryRow") or []}


def fetch_time_report(client, date_range: dict) -> dict:
    node_sel = selection(
        client,
        "TimeReport",
        nested={
            "freelancer": "GenericUser",
            "team": "GenericOrganization",
            "contract": "ContractDetails",
            "billRate": "BillRate",
        },
    )
    q = f"""
    query TR($r: DateTimeRange!) {{
      organization {{
        clientContractTimeReport(timeReportDate_bt: $r) {{
          totalCount
          edges {{ node {{ {node_sel} }} }}
        }}
      }}
    }}
    """
    resp = client.gql(q, {"r": date_range})
    if _err(resp):
        return {"error": resp}
    conn = (resp.get("organization") or {}).get("clientContractTimeReport") or {}
    rows = [e.get("node") or {} for e in (conn.get("edges") or [])]
    return {"rows": rows, "totalCount": conn.get("totalCount")}


def fetch_contracts(client, contract_ids: list[str]) -> dict:
    if not contract_ids:
        return {"rows": []}
    node_sel = selection(
        client,
        "ContractDetails",
        nested={
            "freelancer": "ContractUser",
            "clientOrganization": "GenericOrganization",
            "vendorOrganization": "GenericOrganization",
            "hiringManager": "ContractUser",
        },
    )
    q = f"""
    query Contracts($ids: [ID!]) {{
      contractList(ids: $ids) {{ contracts {{ {node_sel} }} }}
    }}
    """
    resp = client.gql(q, {"ids": contract_ids})
    if _err(resp):
        return {"error": resp}
    return {"rows": ((resp.get("contractList") or {}).get("contracts")) or []}


# ---------------------------------------------------------------------------
# Flatten + CSV
# ---------------------------------------------------------------------------

def flatten(row: dict, parent: str = "", out: dict | None = None) -> dict:
    """Flatten nested dicts into prefixed columns; JSON-encode lists."""
    out = {} if out is None else out
    for k, v in (row or {}).items():
        key = f"{parent}{k}"
        if isinstance(v, dict):
            flatten(v, f"{key}_", out)
        elif isinstance(v, list):
            out[key] = json.dumps(v, default=str)
        else:
            out[key] = v
    return out


def write_csv(path: Path, rows: list[dict]) -> int:
    flat = [flatten(r) for r in rows]
    cols: list[str] = []
    for r in flat:
        for k in r:
            if k not in cols:
                cols.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in flat:
            w.writerow(r)
    return len(flat)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

BOOTSTRAP = """
query Bootstrap {
  organization { id name type legacyType }
  accountingEntity { id }
}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive).")
    ap.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive).")
    ap.add_argument("--out", default="./out", help="Output directory (default ./out).")
    ap.add_argument("--push", action="store_true", help="Push CSVs to Domo (needs DOMO_* env).")
    ap.add_argument("--dataset-prefix", default="Upwork", help="Domo dataset name prefix on create.")
    args = ap.parse_args()

    out = Path(args.out)
    date_range = _iso_range(args.start, args.end)
    client = get_client()

    boot = client.gql(BOOTSTRAP)
    if _err(boot):
        print("Bootstrap query failed:", json.dumps(boot, indent=2), file=sys.stderr)
        return 1
    org = boot.get("organization") or {}
    ace_id = (boot.get("accountingEntity") or {}).get("id")
    print(
        f"Org: {org.get('name')!r} legacyType={org.get('legacyType')} "
        f"id={org.get('id')} | accountingEntity={ace_id}"
    )

    tx = fetch_transactions(client, ace_id, date_range) if ace_id else {"error": "no accountingEntity id"}
    tr = fetch_time_report(client, date_range)

    contract_ids = sorted(
        {
            (r.get("contract") or {}).get("id")
            for r in tr.get("rows", [])
            if (r.get("contract") or {}).get("id")
        }
    )
    co = fetch_contracts(client, contract_ids)

    datasets = {"transactions": tx, "time_report": tr, "contracts": co}
    for name, res in datasets.items():
        if res.get("error"):
            print(f"[{name}] ERROR (recorded, not fatal): {json.dumps(res['error'])[:500]}")
            continue
        n = write_csv(out / f"{name}.csv", res.get("rows", []))
        extra = f" (totalCount={res['totalCount']})" if res.get("totalCount") is not None else ""
        print(f"[{name}] wrote {n} rows -> {out}/{name}.csv{extra}")

    if args.push:
        sys.path.insert(0, str(_REPO_ROOT / "pipeline"))
        from domo_push import push_csv  # noqa: E402

        for name in datasets:
            p = out / f"{name}.csv"
            if not p.exists():
                continue
            env_key = f"DOMO_DATASET_{name.upper()}"
            ds_id = os.environ.get(env_key)
            guid = push_csv(
                p,
                dataset_id=ds_id,
                dataset_name=None if ds_id else f"{args.dataset_prefix} {name.replace('_', ' ').title()}",
            )
            if ds_id:
                print(f"[{name}] replaced Domo dataset {guid}")
            else:
                print(f"[{name}] created Domo dataset {guid}  -> set {env_key}={guid} to reuse")

    print("\nDone. Build Domo cards on the resulting datasets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
