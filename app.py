from datetime import datetime
from decimal import Decimal
from typing import Optional, Literal, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from trade_engine_db import handle_trade_db
from referral_db import register_referral_db
from db.db import get_conn

from db.repositories import (
    ensure_trade_row, 
    get_or_generate_referral_code,
    get_network_levels,
    perform_claim
)


app = FastAPI(title="Nika Referral System", version="0.1.0")

# CORS middleware to allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------
# pydantic models (requests)
# ---------

class ReferralRegisterRequest(BaseModel):
    child_user_id: int = Field(..., description="ID of the user being referred")
    referral_code: str = Field(..., description="Referral code used on signup")

class ReferralGenerateRequest(BaseModel):
    user_id: int = Field(..., description="User ID to generate or fetch referral code for")

class TradeWebhookRequest(BaseModel):
    trade_id: str
    trader_id: int
    chain: str
    fee_token: str
    fee_amount: Decimal
    executed_at: datetime

class ReferralClaimRequest(BaseModel):
    user_id: int = Field(..., description="User ID attempting to claim")
    token: str = Field("USDC", description="Token to claim in (default: USDC)")

class ReferralClaimExecuteRequest(BaseModel):
    user_id: int = Field(..., description="User ID attempting to claim")
    token: str = Field("USDC", description="Token to claim in (default: USDC)")


# ---------
# helpers for earnings endpoint
# ---------

KNOWN_KINDS = [
    "cashback",
    "commission_l1",
    "commission_l2",
    "commission_l3",
    "treasury",
]


def _zero_map() -> Dict[str, str]:
    return {kind: "0.000000" for kind in KNOWN_KINDS}


# ---------
# endpoints
# ---------


@app.post("/api/referral/register")
def referral_register(payload: ReferralRegisterRequest):
    """
    attach a child user to a referrer using a referral_code.
    wraps register_referral_db and normalizes errors into HTTP 400s.
    """
    try:
        result = register_referral_db(
            child_id=payload.child_user_id,
            referral_code=payload.referral_code,
        )
        return result
    except ValueError as e:
        # business rule violations (already has referrer, invalid code, cycle, etc.)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # unexpected errors
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/referral/generate")
def referral_generate(payload: ReferralGenerateRequest):
    """
    return the user's referral code, generating one if they don't have it yet.
    """
    try:
        with get_conn() as conn:
            code = get_or_generate_referral_code(conn, payload.user_id)
            conn.commit()
        return {"user_id": payload.user_id, "referral_code": code}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/webhook/trade")
def webhook_trade(payload: TradeWebhookRequest):
    """
    trade fee ingestion webhook.
    calls handle_trade_db and returns either 'applied' or 'duplicate'.
    """
    event = {
        "trade_id": payload.trade_id,
        "trader_id": payload.trader_id,
        "chain": payload.chain,
        "fee_token": payload.fee_token,
        "fee_amount": payload.fee_amount,
        "executed_at": payload.executed_at,
    }

    try:
        result = handle_trade_db(event)
    except ValueError as e:
        # e.g. unknown trader or lineage issues
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

    # decimals must serialize as strings
    if result.get("splits"):
        result["splits"] = {k: f"{v:.6f}" for k, v in result["splits"].items()}

    return result


@app.get("/api/referral/network")
def referral_network(
    user_id: int = Query(..., description="Root user ID whose network we want"),
    max_levels: int = Query(3, ge=1, le=5, description="How many levels deep to fetch"),
    limit_per_level: int = Query(50, ge=1, le=500, description="Max users per level"),
):
    """
    return the user's downline/referral network up to max_levels deep.

    response:
    {
      "user_id": 123,
      "max_levels": 3,
      "limit_per_level": 50,
      "levels": [
        {"level": 1, "users": [...]},
        {"level": 2, "users": [...]},
        {"level": 3, "users": [...]}
      ]
    }
    """
    with get_conn() as conn:
        try:
            levels = get_network_levels(
                conn,
                root_user_id=user_id,
                max_levels=max_levels,
                limit_per_level=limit_per_level,
            )
        except Exception:
            raise HTTPException(status_code=500, detail="Internal server error")

    return {
        "user_id": user_id,
        "max_levels": max_levels,
        "limit_per_level": limit_per_level,
        "levels": levels,
    }


@app.get("/api/referral/earnings")
def referral_earnings(
    user_id: int = Query(..., description="User ID to fetch earnings for"),
    include_breakdown: bool = Query(
        False,
        description="Include per-entry breakdown from accrual_entries",
    ),
    breakdown_limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Max number of breakdown entries to return",
    ),
    from_datetime: datetime | None = Query(
        None,
        alias="from",
        description="Start datetime (inclusive) for earnings window (ISO 8601). "
                    "If omitted, uses beginning of time.",
    ),
    to_datetime: datetime | None = Query(
        None,
        alias="to",
        description="End datetime (exclusive) for earnings window (ISO 8601). "
                    "If omitted, uses end of time.",
    ),
):
    """
    aggregate earnings for a user.

    - if no `from`/`to` are provided: use accrual_ledger (all-time view).
    - if `from` or `to` are provided: aggregate from accrual_entries
      in that time window [from, to).
    """
    use_range = from_datetime is not None or to_datetime is not None

    # -----------------------
    # range-based path (journal aggregation)
    # -----------------------
    if use_range:
        # 1) aggregate totals from accrual_entries
        with get_conn() as conn:
            params = [user_id]
            where_clauses = ["beneficiary_user_id = %s"]

            if from_datetime is not None:
                where_clauses.append("executed_at >= %s")
                params.append(from_datetime)
            if to_datetime is not None:
                where_clauses.append("executed_at < %s")
                params.append(to_datetime)

            where_sql = " AND ".join(where_clauses)

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT kind, token, SUM(amount)
                    FROM accrual_entries
                    WHERE {where_sql}
                    GROUP BY kind, token
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()

        if not rows:
            base = {
                "user_id": user_id,
                "token": "USDC",
                "totals": _zero_map(),
                "claimed": _zero_map(),
                "unclaimed": _zero_map(),
                "range": {
                    "from": from_datetime.isoformat() if from_datetime else None,
                    "to": to_datetime.isoformat() if to_datetime else None,
                },
            }
            if include_breakdown:
                base["breakdown"] = []
            return base

        # assume single token for now (USDC)
        token = rows[0][1]

        totals: Dict[str, Decimal] = {kind: Decimal("0") for kind in KNOWN_KINDS}
        for kind, row_token, sum_amount in rows:
            if kind not in KNOWN_KINDS:
                continue
            totals[kind] += sum_amount

        # for this MVP we don't track per-range claims; claimed = 0, unclaimed = totals
        claimed: Dict[str, Decimal] = {kind: Decimal("0") for kind in KNOWN_KINDS}
        unclaimed: Dict[str, Decimal] = {
            kind: totals[kind] - claimed[kind] for kind in KNOWN_KINDS
        }

        def fmt(d: Dict[str, Decimal]) -> Dict[str, str]:
            return {k: f"{v:.6f}" for k, v in d.items()}

        breakdown = None
        if include_breakdown:
            with get_conn() as conn:
                params_bd = [user_id]
                where_bd = ["ae.beneficiary_user_id = %s"]
                if from_datetime is not None:
                    where_bd.append("ae.executed_at >= %s")
                    params_bd.append(from_datetime)
                if to_datetime is not None:
                    where_bd.append("ae.executed_at < %s")
                    params_bd.append(to_datetime)

                where_sql_bd = " AND ".join(where_bd)

                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT
                            ae.amount,
                            ae.kind,
                            ae.token,
                            ae.executed_at,
                            ae.chain,
                            t.trade_id
                        FROM accrual_entries ae
                        JOIN trades t ON ae.trade_id = t.id
                        WHERE {where_sql_bd}
                        ORDER BY ae.executed_at DESC
                        LIMIT %s
                        """,
                        tuple(params_bd + [breakdown_limit]),
                    )
                    rows_bd = cur.fetchall()

            breakdown = [
                {
                    "trade_id": r[5],
                    "chain": r[4],
                    "kind": r[1],
                    "amount": f"{r[0]:.6f}",
                    "token": r[2],
                    "executed_at": r[3].isoformat() if r[3] else None,
                }
                for r in rows_bd
            ]

        response = {
            "user_id": user_id,
            "token": token,
            "totals": fmt(totals),
            "claimed": fmt(claimed),
            "unclaimed": fmt(unclaimed),
            "range": {
                "from": from_datetime.isoformat() if from_datetime else None,
                "to": to_datetime.isoformat() if to_datetime else None,
            },
        }

        if breakdown is not None:
            response["breakdown"] = breakdown

        return response

    # -----------------------
    # all-time path (ledger)
    # -----------------------
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT kind, token, accrued_amount, claimed_amount
                FROM accrual_ledger
                WHERE user_id = %s
                """,
                (user_id,),
            )
            rows = cur.fetchall()

    if not rows:
        base = {
            "user_id": user_id,
            "token": "USDC",
            "totals": _zero_map(),
            "claimed": _zero_map(),
            "unclaimed": _zero_map(),
        }
        if include_breakdown:
            base["breakdown"] = []
        return base

    token = rows[0][1]

    totals: Dict[str, Decimal] = {kind: Decimal("0") for kind in KNOWN_KINDS}
    claimed: Dict[str, Decimal] = {kind: Decimal("0") for kind in KNOWN_KINDS}

    for kind, row_token, accrued_amount, claimed_amount in rows:
        if kind not in KNOWN_KINDS:
            continue
        totals[kind] += accrued_amount
        claimed[kind] += claimed_amount

    unclaimed: Dict[str, Decimal] = {
        kind: totals[kind] - claimed[kind] for kind in KNOWN_KINDS
    }

    def fmt(d: Dict[str, Decimal]) -> Dict[str, str]:
        return {k: f"{v:.6f}" for k, v in d.items()}

    breakdown = None
    if include_breakdown:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        ae.amount,
                        ae.kind,
                        ae.token,
                        ae.executed_at,
                        ae.chain,
                        t.trade_id
                    FROM accrual_entries ae
                    JOIN trades t ON ae.trade_id = t.id
                    WHERE ae.beneficiary_user_id = %s
                    ORDER BY ae.executed_at DESC
                    LIMIT %s
                    """,
                    (user_id, breakdown_limit),
                )
                rows = cur.fetchall()

        breakdown = [
            {
                "trade_id": r[5],
                "chain": r[4],
                "kind": r[1],
                "amount": f"{r[0]:.6f}",
                "token": r[2],
                "executed_at": r[3].isoformat() if r[3] else None,
            }
            for r in rows
        ]

    response = {
        "user_id": user_id,
        "token": token,
        "totals": fmt(totals),
        "claimed": fmt(claimed),
        "unclaimed": fmt(unclaimed),
    }

    if breakdown is not None:
        response["breakdown"] = breakdown

    return response



@app.post("/api/referral/claim")
def referral_claim(payload: ReferralClaimRequest):
    """
    ui-only 'claim' endpoint.
    it does NOT mutate any balances.
    it only validates whether the user has a positive claimable amount.

    claimable = sum over (accrued_amount - claimed_amount) for:
      - cashback
      - commission_l1
      - commission_l2
      - commission_l3
    for the given user_id and token.
    """
    claimable_kinds = [
        "cashback",
        "commission_l1",
        "commission_l2",
        "commission_l3",
    ]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT kind, accrued_amount, claimed_amount
                FROM accrual_ledger
                WHERE user_id = %s AND token = %s
                """,
                (payload.user_id, payload.token),
            )
            rows = cur.fetchall()

    if not rows:
        # no ledger rows at all for this user/token
        raise HTTPException(
            status_code=400,
            detail=f"No claimable amount for user {payload.user_id} in {payload.token}.",
        )

    per_kind_unclaimed: Dict[str, Decimal] = {}
    total_unclaimed = Decimal("0")

    for kind, accrued, claimed in rows:
        if kind not in claimable_kinds:
            # e.g. treasury; skip
            continue
        unclaimed = accrued - claimed
        if unclaimed < 0:
            # defensive; shouldn't happen
            unclaimed = Decimal("0")
        per_kind_unclaimed[kind] = per_kind_unclaimed.get(kind, Decimal("0")) + unclaimed
        total_unclaimed += unclaimed

    if total_unclaimed <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"No claimable amount for user {payload.user_id} in {payload.token}.",
        )

    # format for JSON
    per_kind_str = {k: f"{v:.6f}" for k, v in per_kind_unclaimed.items()}

    return {
        "user_id": payload.user_id,
        "token": payload.token,
        "claimable": f"{total_unclaimed:.6f}",
        "kinds": per_kind_str,
    }


@app.post("/api/referral/claim/execute")
def referral_claim_execute(payload: ReferralClaimExecuteRequest):
    """
    real claim processing.

    - locks the user's accrual_ledger rows for the given token.
    - moves all unclaimed cashback + commission amounts into claimed_amount.
    - creates a payout_batches row marked 'pending'.

    returns the batch and per-kind breakdown.
    """
    try:
        with get_conn() as conn:
            result = perform_claim(conn, payload.user_id, payload.token)
            conn.commit()
    except ValueError as e:
        # business-rule failures: no ledger rows, nothing claimable, etc.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        # unexpected errors
        raise HTTPException(status_code=500, detail="Internal server error")

    # format decimals for JSON
    amount = result["amount"]
    per_kind = result["per_kind"]

    result["amount"] = f"{amount:.6f}"
    result["per_kind"] = {k: f"{v:.6f}" for k, v in per_kind.items()}
    if "created_at" in result and result["created_at"] is not None:
        result["created_at"] = result["created_at"].isoformat()

    return result
