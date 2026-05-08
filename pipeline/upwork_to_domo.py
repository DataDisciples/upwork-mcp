"""Upwork -> Domo orchestrator.

Daily ETL. Pulls everything in datasets.json that has a non-empty GUID and
pushes via pydomo. Snapshot tables go through replace_data; event tables
(time_logs) go through append_data.

Run locally:
    python -m pipeline.upwork_to_domo --dry-run
    python -m pipeline.upwork_to_domo

Required env (in addition to UPWORK_*):
    DOMO_CLIENT_ID, DOMO_CLIENT_SECRET
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "src"))

from upwork_client import UpworkClient  # noqa: E402
from pipeline import extractors  # noqa: E402

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("upwork_to_domo")

DATASETS_PATH = ROOT / "datasets.json"
APPEND_DATASETS = {"upwork_time_logs"}  # everything else is replace-snapshot


def _load_registry() -> dict[str, str]:
    raw = json.loads(DATASETS_PATH.read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_") and v}


def _flatten_contracts(rows: list[dict]) -> pd.DataFrame:
    return pd.json_normalize(rows, sep="_")


def _flatten_offers(rows: list[dict]) -> pd.DataFrame:
    return pd.json_normalize(rows, sep="_")


def _flatten_earnings(payload: dict) -> pd.DataFrame:
    fo = (payload or {}).get("financialOverview") or {}
    overview = {
        "total_earnings": fo.get("totalEarnings"),
        "pending_payments": fo.get("pendingPayments"),
        "available_balance": fo.get("availableBalance"),
        "snapshot_date": date.today().isoformat(),
    }
    txs = [
        edge["node"]
        for edge in (fo.get("recentTransactions") or {}).get("edges") or []
    ]
    if not txs:
        return pd.DataFrame([overview])
    df = pd.json_normalize(txs, sep="_")
    for k, v in overview.items():
        df[k] = v
    return df


def _flatten_time_logs(rows: list[dict]) -> pd.DataFrame:
    return pd.json_normalize(rows, sep="_")


def _flatten_rooms(rows: list[dict]) -> pd.DataFrame:
    df = pd.json_normalize(rows, sep="_")
    if "participants" in df.columns:
        df["participant_names"] = df["participants"].map(
            lambda ps: ",".join(p.get("name", "") for p in (ps or []))
        )
        df = df.drop(columns=["participants"])
    return df


EXTRACT_FNS = {
    "upwork_contracts": lambda c: _flatten_contracts(extractors.extract_contracts(c)),
    "upwork_offers": lambda c: _flatten_offers(extractors.extract_offers(c)),
    "upwork_earnings": lambda c: _flatten_earnings(extractors.extract_earnings(c)),
    "upwork_time_logs": lambda c: _flatten_time_logs(
        extractors.extract_time_logs(
            c,
            start_date=(date.today() - timedelta(days=7)).isoformat(),
            end_date=date.today().isoformat(),
        )
    ),
    "upwork_messages": lambda c: _flatten_rooms(extractors.extract_rooms(c)),
}


def _push_to_domo(domo, dataset_id: str, df: pd.DataFrame, mode: str) -> None:
    csv_bytes = df.to_csv(index=False, header=False).encode("utf-8")
    if mode == "append":
        domo.datasets.data_import(dataset_id, csv_bytes, update_method="APPEND")
    else:
        domo.datasets.data_import(dataset_id, csv_bytes, update_method="REPLACE")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Extract only, no Domo push")
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Subset of friendly names to process",
    )
    args = parser.parse_args()

    registry = _load_registry()
    if args.only:
        registry = {k: v for k, v in registry.items() if k in args.only}
    if not registry:
        logger.warning("Nothing to do -- datasets.json has no populated GUIDs.")
        return 0

    client = UpworkClient.from_env()

    domo = None
    if not args.dry_run:
        from pydomo import Domo

        domo = Domo(
            os.environ["DOMO_CLIENT_ID"],
            os.environ["DOMO_CLIENT_SECRET"],
            api_host=os.environ.get("DOMO_API_HOST", "api.domo.com"),
        )

    failures: list[str] = []
    for name, dataset_id in registry.items():
        fn = EXTRACT_FNS.get(name)
        if fn is None:
            logger.warning("No extractor wired for %s; skipping", name)
            continue
        logger.info("Extracting %s ...", name)
        try:
            df = fn(client)
        except Exception as exc:
            logger.exception("Extraction failed for %s: %s", name, exc)
            failures.append(name)
            continue
        logger.info("%s: %d rows x %d cols", name, len(df), df.shape[1])

        if args.dry_run or domo is None:
            continue

        mode = "append" if name in APPEND_DATASETS else "replace"
        try:
            _push_to_domo(domo, dataset_id, df, mode)
            logger.info("Pushed %s to Domo (%s)", name, mode)
        except Exception as exc:
            logger.exception("Domo push failed for %s: %s", name, exc)
            failures.append(name)

    if failures:
        logger.error("Pipeline finished with failures: %s", failures)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
