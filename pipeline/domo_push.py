"""Push a CSV (or DataFrame) into a Domo dataset for dashboarding.

Decoupled from Upwork on purpose: this only knows about Domo. The Upwork
pull writes CSVs; this lands them in Domo. Works the same whether the data
came from financial_pull.py, a future contractor/expense pull, or anything
else.

Auth (same as the SpotSee loader):
    DOMO_CLIENT_ID, DOMO_CLIENT_SECRET   (from https://developer.domo.com/manage-clients)
    DOMO_API_HOST                        (optional, default api.domo.com)

Usage:
    # First run: create a new dataset from a CSV, prints the new GUID.
    python pipeline/domo_push.py --csv out/earnings.csv --name "Upwork Earnings"

    # Subsequent runs: replace the data in an existing dataset.
    python pipeline/domo_push.py --csv out/earnings.csv \\
        --dataset-id 00000000-0000-0000-0000-000000000000

Save the GUID it prints (e.g. in an env var) so scheduled runs update the
same dataset instead of creating duplicates.

Run from a host with internet access to api.domo.com (laptop, Domo Jupyter
Workspace, Railway cron, GitHub Action).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from pydomo import Domo
from pydomo.datasets import Column, DataSetRequest, Schema
from pydomo.datasets import ColumnType


def _domo_client() -> Domo:
    client_id = os.environ.get("DOMO_CLIENT_ID")
    client_secret = os.environ.get("DOMO_CLIENT_SECRET")
    if not client_id or not client_secret:
        missing = ", ".join(
            n for n, v in (("DOMO_CLIENT_ID", client_id), ("DOMO_CLIENT_SECRET", client_secret)) if not v
        )
        raise RuntimeError(f"Missing required env vars: {missing}")
    api_host = os.environ.get("DOMO_API_HOST", "api.domo.com")
    return Domo(client_id, client_secret, api_host=api_host)


def _column_type_for(series: pd.Series) -> "ColumnType":
    """Map a pandas dtype to the closest Domo ColumnType."""
    dtype = str(series.dtype)
    if dtype.startswith("int"):
        return ColumnType.LONG
    if dtype.startswith("float"):
        return ColumnType.DECIMAL
    if dtype.startswith("datetime"):
        return ColumnType.DATETIME
    if dtype == "bool":
        return ColumnType.STRING
    # Best-effort date sniff for object columns named like dates.
    return ColumnType.STRING


def _schema_from_df(df: pd.DataFrame) -> Schema:
    return Schema([Column(_column_type_for(df[c]), c) for c in df.columns])


def push_dataframe(
    df: pd.DataFrame,
    *,
    dataset_id: str | None = None,
    dataset_name: str | None = None,
    description: str = "",
    domo: Domo | None = None,
) -> str:
    """Create-or-replace a Domo dataset from a DataFrame. Returns the
    dataset GUID (newly created or the one passed in)."""
    client = domo or _domo_client()
    csv_text = df.to_csv(index=False)

    if dataset_id:
        client.datasets.data_import(dataset_id, csv_text)
        return dataset_id

    if not dataset_name:
        raise ValueError("Provide either dataset_id (replace) or dataset_name (create).")

    req = DataSetRequest()
    req.name = dataset_name
    req.description = description or f"Created by upwork-mcp/pipeline/domo_push.py"
    req.schema = _schema_from_df(df)
    created = client.datasets.create(req)
    new_id = created["id"]
    client.datasets.data_import(new_id, csv_text)
    return new_id


def push_csv(
    csv_path: Path | str,
    *,
    dataset_id: str | None = None,
    dataset_name: str | None = None,
    description: str = "",
    domo: Domo | None = None,
) -> str:
    df = pd.read_csv(csv_path)
    return push_dataframe(
        df,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        description=description,
        domo=domo,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", required=True, type=Path, help="Path to the CSV to upload.")
    ap.add_argument("--dataset-id", help="Existing Domo dataset GUID to replace (omit to create new).")
    ap.add_argument("--name", help="Name for a newly created dataset (required if no --dataset-id).")
    ap.add_argument("--description", default="", help="Optional dataset description (create mode).")
    args = ap.parse_args()

    if not args.dataset_id and not args.name:
        print("ERROR: pass --dataset-id (replace) or --name (create).", file=sys.stderr)
        return 2
    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        return 2

    guid = push_csv(
        args.csv,
        dataset_id=args.dataset_id,
        dataset_name=args.name,
        description=args.description,
    )
    if args.dataset_id:
        print(f"Replaced data in Domo dataset {guid} from {args.csv}")
    else:
        print(f"Created Domo dataset {guid} from {args.csv}")
        print(f"Save this GUID and reuse it: --dataset-id {guid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
