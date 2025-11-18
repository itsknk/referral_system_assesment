from decimal import Decimal
from typing import Optional, Dict, Any

from psycopg import Connection

from fee_engine import fee_engine
from db.repositories import (
    ensure_trade_row,
    get_lineage_db,
    insert_accrual_entry,
    upsert_ledger_delta,
)
from db.db import get_conn


def handle_trade_db(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    DB-backed variant of handle_trade.

    event: dict with keys:
      - trade_id: str
      - trader_id: int (DB user_id)
      - chain: str
      - fee_token: str
      - fee_amount: Decimal
      - executed_at: datetime
    """
    with get_conn() as conn:
        try:
            result = _handle_trade_db_in_tx(conn, event)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise


def _handle_trade_db_in_tx(conn: Connection, event: Dict[str, Any]) -> Dict[str, Any]:
    trade_id = event["trade_id"]
    trader_id = event["trader_id"]  # integer user_id
    chain = event["chain"]
    fee_token = event["fee_token"]
    fee_amount: Decimal = event["fee_amount"]
    executed_at = event["executed_at"]

    # 1) idempotent trade insert
    trade_pk_id, created = ensure_trade_row(
        conn,
        trade_id=trade_id,
        chain=chain,
        trader_id=trader_id,
        fee_token=fee_token,
        fee_amount=fee_amount,
        executed_at=executed_at,
    )

    if not created:
        return {
            "status": "duplicate",
            "trade_id": trade_id,
            "lineage": None,
            "splits": None,
        }

    # 2) lineage from DB
    lineage = get_lineage_db(conn, trader_id)  # [L1, L2, L3] as user_ids or None

    # 3) fee splits (same pure logic as before)
    splits = fee_engine(fee_amount, trader_id, lineage)

    # 4) beneficiary mapping
    payouts = []

    # trader cashback
    if splits["cashback"] > 0:
        payouts.append((trader_id, "cashback", splits["cashback"]))

    # L1
    if lineage[0] is not None and splits["l1"] > 0:
        payouts.append((lineage[0], "commission_l1", splits["l1"]))

    # L2
    if lineage[1] is not None and splits["l2"] > 0:
        payouts.append((lineage[1], "commission_l2", splits["l2"]))

    # L3
    if lineage[2] is not None and splits["l3"] > 0:
        payouts.append((lineage[2], "commission_l3", splits["l3"]))

    # treasury
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE is_treasury = TRUE")
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Treasury user not configured")
        treasury_user_id = row[0]

    if splits["treasury"] > 0:
        payouts.append((treasury_user_id, "treasury", splits["treasury"]))

    # 5) insert journal entries + update ledger
    for (user_id, kind, amount) in payouts:
        insert_accrual_entry(
            conn,
            trade_pk_id=trade_pk_id,
            chain=chain,
            beneficiary_user_id=user_id,
            kind=kind,
            token=fee_token,
            amount=amount,
            executed_at=executed_at,
        )
        upsert_ledger_delta(
            conn,
            user_id=user_id,
            kind=kind,
            token=fee_token,
            amount_delta=amount,
        )

    return {
        "status": "applied",
        "trade_id": trade_id,
        "lineage": lineage,
        "splits": splits,
    }

