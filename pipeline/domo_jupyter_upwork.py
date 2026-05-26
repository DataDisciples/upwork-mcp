"""
Upwork -> Domo : historical transactions pull, for a DOMO JUPYTER WORKSPACE.

HOW TO USE
----------
This is NOT a Magic ETL "Python scripting" tile. Magic ETL tiles are
sandboxed with NO outbound internet, so they cannot call the Upwork API.
They can only transform data already inside Domo. The API pull must run in a
**Domo Jupyter Workspace**, which has internet + the `domojupyter` library.

Steps (full walkthrough in the chat / README):
  1. Domo > More (...) > Jupyter Workspaces > New Workspace (Python).
  2. In the workspace's Input/Output panel, add ONE output dataset and name
     its alias to match OUTPUT_DATASET below (e.g. "upwork_transactions").
  3. Paste this file's contents into a notebook cell.
  4. Fill the CONFIG block with your Upwork OAuth creds (or, better, attach a
     Domo Account and read them via domojupyter.get_account_property_value).
  5. Run the cell. It backfills month-by-month from START_YEAR to today and
     writes one tidy dataset to Domo.

This file is committed with PLACEHOLDER creds on purpose -- never commit real
secrets. Put the real values in the Domo cell (notebooks aren't in git) or in
a Domo Account.
"""

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# CONFIG  (fill these in the Domo cell)
# ---------------------------------------------------------------------------
UPWORK_CLIENT_ID = "REPLACE_ME"
UPWORK_CLIENT_SECRET = "REPLACE_ME"
UPWORK_REFRESH_TOKEN = "REPLACE_ME"
UPWORK_ORG_UID = "REPLACE_ME"          # X-Upwork-API-TenantId

START_YEAR = 2019                       # earliest year to backfill from
OUTPUT_DATASET = "upwork_transactions"  # must match the workspace output alias

GRAPHQL_URL = "https://api.upwork.com/graphql"
TOKEN_URL = "https://www.upwork.com/api/v3/oauth2/token"


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------
def get_access_token() -> str:
    """Exchange the refresh token for a fresh access token. Upwork rotates the
    refresh token on refresh; if you wire a Domo Account, persist the new one."""
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": UPWORK_REFRESH_TOKEN,
            "client_id": UPWORK_CLIENT_ID,
            "client_secret": UPWORK_CLIENT_SECRET,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


_ACCESS = get_access_token()
_HEADERS = {
    "Authorization": f"Bearer {_ACCESS}",
    "Content-Type": "application/json",
    "X-Upwork-API-TenantId": UPWORK_ORG_UID,
}


def gql(query: str, variables: dict | None = None) -> dict:
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers=_HEADERS,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]


# ---------------------------------------------------------------------------
# DISCOVER  (accounting-entity id + which scalar fields a transaction row has)
# ---------------------------------------------------------------------------
ACE_ID = gql("{ accountingEntity { id } }")["accountingEntity"]["id"]

_INTROSPECT_ROW = """
{ __type(name: "TransactionHistoryRow") {
    fields { name type { kind name ofType { kind name ofType { kind name } } } }
} }
"""

# Fields the standard token isn't scoped for (extend if the API complains).
_DENY = {"ciphertext"}


def _is_scalar(field: dict) -> bool:
    t = field["type"]
    while t and t.get("kind") in ("NON_NULL", "LIST"):
        t = t.get("ofType")
    return bool(t) and t.get("kind") in ("SCALAR", "ENUM")


_row_fields = [
    f["name"]
    for f in gql(_INTROSPECT_ROW)["__type"]["fields"]
    if _is_scalar(f) and f["name"] not in _DENY
]
_ROW_SELECTION = " ".join(_row_fields)
print(f"Transaction row columns: {_row_fields}")


# ---------------------------------------------------------------------------
# BACKFILL  (month by month from START_YEAR to now)
# ---------------------------------------------------------------------------
_TX_QUERY = f"""
query Tx($f: TransactionHistoryFilter!) {{
  transactionHistory(transactionHistoryFilter: $f) {{
    transactionDetail {{ transactionHistoryRow {{ {_ROW_SELECTION} }} }}
  }}
}}
"""


def _month_spans(start_year: int):
    cursor = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    while cursor < now:
        nxt = (
            cursor.replace(year=cursor.year + 1, month=1)
            if cursor.month == 12
            else cursor.replace(month=cursor.month + 1)
        )
        yield cursor, min(nxt - timedelta(seconds=1), now)
        cursor = nxt


def pull_transactions() -> pd.DataFrame:
    rows: list[dict] = []
    for start, end in _month_spans(START_YEAR):
        variables = {
            "f": {
                "aceIds_any": [ACE_ID],
                "transactionDateTime_bt": {
                    "rangeStart": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "rangeEnd": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            }
        }
        data = gql(_TX_QUERY, variables)
        detail = (data.get("transactionHistory") or {}).get("transactionDetail") or {}
        month_rows = detail.get("transactionHistoryRow") or []
        for r in month_rows:
            r["_pull_month"] = start.strftime("%Y-%m")
        rows.extend(month_rows)
        print(f"{start:%Y-%m}: {len(month_rows):>4} rows  (running total {len(rows)})")
        time.sleep(0.2)  # be gentle with rate limits
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# PROCESS  (type the columns; add revenue/expense sign)
# ---------------------------------------------------------------------------
def process(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    for col in df.columns:
        low = col.lower()
        if "amount" in low or "charge" in low or "total" in low:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif "date" in low or low.endswith("at") or low.endswith("time"):
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    # Convenience: a signed money column + direction, if an amount field exists.
    amount_col = next((c for c in df.columns if c.lower() == "amount"), None)
    if amount_col:
        df["direction"] = df[amount_col].apply(
            lambda v: "inflow" if pd.notna(v) and v >= 0 else "outflow"
        )
    return df


# ---------------------------------------------------------------------------
# RUN
# ---------------------------------------------------------------------------
transactions = process(pull_transactions())
print(f"\nTotal transactions: {len(transactions)} rows, {transactions.shape[1]} cols")
print(transactions.head(10).to_string())

# Write to Domo. In a Jupyter Workspace, write_dataframe targets the output
# dataset alias you configured in the Input/Output panel.
import domojupyter as domo  # noqa: E402  (only available inside Domo)

domo.write_dataframe(transactions, OUTPUT_DATASET)
print(f"\nWrote {len(transactions)} rows to Domo dataset alias '{OUTPUT_DATASET}'.")
