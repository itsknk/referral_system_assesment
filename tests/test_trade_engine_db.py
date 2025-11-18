from decimal import Decimal
from datetime import datetime

from db.db import get_conn
from db.repositories import get_user_id_by_username
from trade_engine_db import handle_trade_db


def test_db_trade_flow_full_lineage():
    """
    assumes db/seed.sql created users A, B, C, D and treasury,
    and that referrer_id has been wired manually for A->B->C->D.
    for now, we can UPDATE users in SQL to set:
      B.referrer_id = A.id
      C.referrer_id = B.id
      D.referrer_id = C.id
    """

    with get_conn() as conn:
        # look up IDs by username
        a_id = get_user_id_by_username(conn, "A")
        b_id = get_user_id_by_username(conn, "B")
        c_id = get_user_id_by_username(conn, "C")
        d_id = get_user_id_by_username(conn, "D")

        # for the very first test, we can manually set referrer chain via SQL:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET referrer_id = %s WHERE id = %s", (a_id, b_id))
            cur.execute("UPDATE users SET referrer_id = %s WHERE id = %s", (b_id, c_id))
            cur.execute("UPDATE users SET referrer_id = %s WHERE id = %s", (c_id, d_id))
        conn.commit()

    event = {
        "trade_id": "DB_T1",
        "trader_id": d_id,
        "chain": "arbitrum",
        "fee_token": "USDC",
        "fee_amount": Decimal("200.000000"),
        "executed_at": datetime.utcnow(),
    }

    result = handle_trade_db(event)
    assert result["status"] == "applied"
    assert result["lineage"] == [c_id, b_id, a_id]

    # additionally, can query ledger & entries here to assert the amounts if we want

