from decimal import Decimal
from typing import Optional, Tuple, Dict, Any, List
import secrets
import string

from psycopg import Connection


def get_user_referrer_id(conn: Connection, user_id: int) -> Optional[int]:
    """
    fetch referrer_id for a user, or None if they have no referrer.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT referrer_id FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"User {user_id} not found")
        return row[0]


def get_lineage_db(conn: Connection, trader_id: int, max_levels: int = 3):
    """
    DB-backed lineage lookup: follow referrer_id up to max_levels.
    returns [L1, L2, L3] (user_ids or None).
    """
    lineage = []
    current = trader_id

    for _ in range(max_levels):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT referrer_id FROM users WHERE id = %s",
                (current,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"User {current} not found")
            parent_id = row[0]

        if parent_id is None:
            lineage.append(None)
            # pad the rest with None
            lineage.extend([None] * (max_levels - len(lineage)))
            break

        lineage.append(parent_id)
        current = parent_id

    if len(lineage) < max_levels:
        lineage.extend([None] * (max_levels - len(lineage)))

    return lineage


def ensure_trade_row(
    conn: Connection,
    trade_id: str,
    chain: str,
    trader_id: int,
    fee_token: str,
    fee_amount: Decimal,
    executed_at,
) -> Tuple[Optional[int], bool]:
    """
    insert a row into trades if not already present (idempotent).
    returns (trade_pk_id, created: bool).

    uses unique constraint on (trade_id, chain) to enforce idempotency.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trades (trade_id, chain, trader_id, fee_token, fee_amount, executed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (trade_id, chain) DO NOTHING
            RETURNING id
            """,
            (trade_id, chain, trader_id, fee_token, fee_amount, executed_at),
        )
        row = cur.fetchone()
        if row is None:
            # conflict: trade already exists
            cur.execute(
                "SELECT id FROM trades WHERE trade_id = %s AND chain = %s",
                (trade_id, chain),
            )
            existing = cur.fetchone()
            return (existing[0] if existing else None, False)
        else:
            return (row[0], True)


def insert_accrual_entry(
    conn: Connection,
    trade_pk_id: int,
    chain: str,
    beneficiary_user_id: int,
    kind: str,
    token: str,
    amount: Decimal,
    executed_at,
):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO accrual_entries
                (trade_id, chain, beneficiary_user_id, kind, token, amount, executed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                trade_pk_id,
                chain,
                beneficiary_user_id,
                kind,
                token,
                amount,
                executed_at,
            ),
        )


def upsert_ledger_delta(
    conn: Connection,
    user_id: int,
    kind: str,
    token: str,
    amount_delta: Decimal,
):
    """
    increment accrued_amount by amount_delta for (user_id, kind, token).
    creates the row if it doesn't exist.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO accrual_ledger (user_id, kind, token, accrued_amount, claimed_amount)
            VALUES (%s, %s, %s, %s, 0)
            ON CONFLICT (user_id, kind, token)
            DO UPDATE SET
                accrued_amount = accrual_ledger.accrued_amount + EXCLUDED.accrued_amount,
                updated_at = NOW()
            """,
            (user_id, kind, token, amount_delta),
        )


def get_user_id_by_username(conn: Connection, username: str) -> int:
    """
    convenience helper for tests / demo:
    look up a user's id from username (A, B, C, D, treasury).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"User with username {username} not found")
        return row[0]


def get_user_by_referral_code(conn: Connection, referral_code: str) -> int:
    """
    return user_id for a given referral_code.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE referral_code = %s",
            (referral_code,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"No user found with referral_code={referral_code}")
        return row[0]


def get_user_referrer_id(conn: Connection, user_id: int) -> Optional[int]:
    """
    fetch referrer_id for a user, or None if they have no referrer.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT referrer_id FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"User {user_id} not found")
        return row[0]


def set_user_referrer_id(conn: Connection, child_id: int, parent_id: int) -> None:
    """
    set referrer_id for child to parent. assumes all checks already done.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET referrer_id = %s, updated_at = NOW() WHERE id = %s",
            (parent_id, child_id),
        )
        if cur.rowcount != 1:
            raise ValueError(f"Failed to update referrer for child {child_id}")


def get_or_generate_referral_code(conn: Connection, user_id: int) -> str:
    """
    return the user's existing referral_code if present.
    if missing/empty (shouldn't happen with current seed), generate a new unique code,
    persist it, and return it.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT referral_code FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"User {user_id} not found")
        existing = row[0]

    # if they already have one, just return it
    if existing:
        return existing

    # otherwise, generate a unique code
    alphabet = string.ascii_uppercase + string.digits
    while True:
        candidate = "REF_" + "".join(secrets.choice(alphabet) for _ in range(8))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM users WHERE referral_code = %s",
                (candidate,),
            )
            if cur.fetchone() is None:
                # unique; assign it
                cur.execute(
                    "UPDATE users SET referral_code = %s WHERE id = %s",
                    (candidate, user_id),
                )
                return candidate


def get_direct_referrals(
    conn: Connection,
    parent_user_id: int,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    return direct referrals (children) of a given user.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, username, created_at
            FROM users
            WHERE referrer_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (parent_user_id, limit),
        )
        rows = cur.fetchall()

    return [
        {
            "user_id": r[0],
            "username": r[1],
            "joined_at": r[2].isoformat() if r[2] else None,
        }
        for r in rows
    ]


def get_network_levels(
    conn: Connection,
    root_user_id: int,
    max_levels: int = 3,
    limit_per_level: int = 50,
) -> List[Dict[str, Any]]:
    """
    return up to max_levels of downline for a root user.

    structure:
    [
      {"level": 1, "users": [...]},
      {"level": 2, "users": [...]},
      {"level": 3, "users": [...]},
    ]
    """

    levels: List[Dict[str, Any]] = []
    current_level_ids = [root_user_id]

    for level in range(1, max_levels + 1):
        if not current_level_ids:
            levels.append({"level": level, "users": []})
            continue

        # get all children of the current level in one query using IN
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, username, created_at, referrer_id
                FROM users
                WHERE referrer_id = ANY(%s)
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (current_level_ids, limit_per_level),
            )
            rows = cur.fetchall()

        users = [
            {
                "user_id": r[0],
                "username": r[1],
                "joined_at": r[2].isoformat() if r[2] else None,
                "referrer_id": r[3],
            }
            for r in rows
        ]

        levels.append({"level": level, "users": users})
        current_level_ids = [u["user_id"] for u in users]

    return levels
