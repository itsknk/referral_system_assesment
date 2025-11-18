from fastapi.testclient import TestClient
from datetime import datetime

from app import app
from db.db import get_conn

client = TestClient(app)


def reset_db_state():
    """
    clear ledger, entries, trades so tests are deterministic.
    does NOT delete users (seeded users remain).
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE accrual_entries, accrual_ledger, trades RESTART IDENTITY CASCADE;"
            )
            # reset referrers for A,B,C,D before each test
            cur.execute(
                "UPDATE users SET referrer_id = NULL WHERE username IN ('A','B','C','D');"
            )
        conn.commit()


def get_user_id(username: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            return cur.fetchone()[0]


def _wire_chain_via_api():
    """
    helper to wire A -> B -> C -> D using /api/referral/register.
    returns (a_id, b_id, c_id, d_id).
    """
    a_id = get_user_id("A")
    b_id = get_user_id("B")
    c_id = get_user_id("C")
    d_id = get_user_id("D")

    # 1) link B <- A
    res = client.post(
        "/api/referral/register",
        json={"child_user_id": b_id, "referral_code": "REF_A"},
    )
    assert res.status_code == 200

    # 2) link C <- B
    res = client.post(
        "/api/referral/register",
        json={"child_user_id": c_id, "referral_code": "REF_B"},
    )
    assert res.status_code == 200

    # 3) link D <- C
    res = client.post(
        "/api/referral/register",
        json={"child_user_id": d_id, "referral_code": "REF_C"},
    )
    assert res.status_code == 200

    return a_id, b_id, c_id, d_id


def test_full_api_flow():
    """
    end-to-end flow:
      - wire A->B->C->D
      - trade from D
      - check splits & earnings
    """
    reset_db_state()

    a_id, b_id, c_id, d_id = _wire_chain_via_api()

    # 4) ingest a trade from D
    res = client.post(
        "/api/webhook/trade",
        json={
            "trade_id": "API_T1",
            "trader_id": d_id,
            "chain": "arbitrum",
            "fee_token": "USDC",
            "fee_amount": "200.000000",
            "executed_at": datetime.utcnow().isoformat(),
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "applied"
    assert data["lineage"] == [c_id, b_id, a_id]  # D -> C -> B -> A

    splits = data["splits"]
    assert splits["cashback"] == "20.000000"
    assert splits["l1"] == "60.000000"
    assert splits["l2"] == "6.000000"
    assert splits["l3"] == "4.000000"
    assert splits["treasury"] == "110.000000"

    # 5) query earnings for C (L1)
    res = client.get(f"/api/referral/earnings?user_id={c_id}")
    assert res.status_code == 200
    earnings = res.json()
    assert earnings["totals"]["commission_l1"] == "60.000000"

    # 6) query earnings for B (L2)
    res = client.get(f"/api/referral/earnings?user_id={b_id}")
    assert res.status_code == 200
    earnings = res.json()
    assert earnings["totals"]["commission_l2"] == "6.000000"

    # 7) query earnings for A (L3)
    res = client.get(f"/api/referral/earnings?user_id={a_id}")
    assert res.status_code == 200
    earnings = res.json()
    assert earnings["totals"]["commission_l3"] == "4.000000"

    # 8) query earnings for D (cashback)
    res = client.get(f"/api/referral/earnings?user_id={d_id}")
    assert res.status_code == 200
    earnings = res.json()
    assert earnings["totals"]["cashback"] == "20.000000"


def test_referral_generate_returns_existing_code():
    """
    /api/referral/generate should return an existing referral_code for a seeded user.
    """
    a_id = get_user_id("A")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT referral_code FROM users WHERE id = %s", (a_id,))
            row = cur.fetchone()
            existing_code = row[0]

    res = client.post(
        "/api/referral/generate",
        json={"user_id": a_id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == a_id
    assert data["referral_code"] == existing_code


def test_referral_network_three_levels():
    """
    /api/referral/network should show B, C, D at levels 1, 2, 3 from A after wiring the chain.
    """
    reset_db_state()
    a_id, b_id, c_id, d_id = _wire_chain_via_api()

    res = client.get(
        f"/api/referral/network?user_id={a_id}&max_levels=3&limit_per_level=10"
    )
    assert res.status_code == 200
    data = res.json()

    assert data["user_id"] == a_id
    assert len(data["levels"]) == 3

    level1_users = {u["user_id"] for u in data["levels"][0]["users"]}
    level2_users = {u["user_id"] for u in data["levels"][1]["users"]}
    level3_users = {u["user_id"] for u in data["levels"][2]["users"]}

    assert b_id in level1_users
    assert c_id in level2_users
    assert d_id in level3_users


def test_earnings_with_breakdown():
    """
    /api/referral/earnings with include_breakdown=true should include accrual_entries info.
    """
    reset_db_state()
    a_id, b_id, c_id, d_id = _wire_chain_via_api()

    # Post a trade from D
    res = client.post(
        "/api/webhook/trade",
        json={
            "trade_id": "API_T2",
            "trader_id": d_id,
            "chain": "arbitrum",
            "fee_token": "USDC",
            "fee_amount": "200.000000",
            "executed_at": datetime.utcnow().isoformat(),
        },
    )
    assert res.status_code == 200

    # now get earnings for C with breakdown
    res = client.get(
        f"/api/referral/earnings?user_id={c_id}&include_breakdown=true&breakdown_limit=10"
    )
    assert res.status_code == 200
    data = res.json()

    assert "breakdown" in data
    breakdown = data["breakdown"]
    assert len(breakdown) >= 1

    # find at least one commission_l1 entry with expected amount
    kinds = {(entry["kind"], entry["amount"]) for entry in breakdown}
    assert ("commission_l1", "60.000000") in kinds


def test_claim_fails_when_no_earnings():
    """
    /api/referral/claim should return 400 when user has no claimable amount.
    """
    reset_db_state()
    # choose a seeded user (e.g. C), but do NOT create any trades
    c_id = get_user_id("C")

    res = client.post(
        "/api/referral/claim",
        json={"user_id": c_id, "token": "USDC"},
    )
    assert res.status_code == 400
    data = res.json()
    assert "No claimable amount" in data["detail"]


def test_claim_succeeds_when_user_has_unclaimed():
    """
    /api/referral/claim should return total claimable amount when user has unclaimed earnings.
    we'll:
      - reset state
      - wire A->B->C->D
      - post a trade from D with 200 USDC fee
      - claim for C (L1) and expect 60.000000 claimable
    """
    reset_db_state()
    a_id, b_id, c_id, d_id = _wire_chain_via_api()

    # post a trade from D
    res = client.post(
        "/api/webhook/trade",
        json={
            "trade_id": "CLAIM_T1",
            "trader_id": d_id,
            "chain": "arbitrum",
            "fee_token": "USDC",
            "fee_amount": "200.000000",
            "executed_at": datetime.utcnow().isoformat(),
        },
    )
    assert res.status_code == 200

    # now attempt claim for C (L1 beneficiary)
    res = client.post(
        "/api/referral/claim",
        json={"user_id": c_id, "token": "USDC"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["user_id"] == c_id
    assert data["token"] == "USDC"
    # C should have 60 USDC as commission_l1
    assert data["claimable"] == "60.000000"
    assert "commission_l1" in data["kinds"]
    assert data["kinds"]["commission_l1"] == "60.000000"


def test_earnings_date_range_filters_correctly():
    """
    range-based /api/referral/earnings should only include trades whose executed_at
    falls inside [from, to).
    """
    reset_db_state()
    a_id, b_id, c_id, d_id = _wire_chain_via_api()

    # trade 1: 2025-01-01
    res = client.post(
        "/api/webhook/trade",
        json={
            "trade_id": "RANGE_T1",
            "trader_id": d_id,
            "chain": "arbitrum",
            "fee_token": "USDC",
            "fee_amount": "200.000000",
            "executed_at": "2025-01-01T00:00:00Z",
        },
    )
    assert res.status_code == 200

    # trade 2: 2025-02-01
    res = client.post(
        "/api/webhook/trade",
        json={
            "trade_id": "RANGE_T2",
            "trader_id": d_id,
            "chain": "arbitrum",
            "fee_token": "USDC",
            "fee_amount": "200.000000",
            "executed_at": "2025-02-01T00:00:00Z",
        },
    )
    assert res.status_code == 200

    # all-time for C (L1) would be 120.000000, but we ask only for mid-Jan to mid-Feb,
    # so only RANGE_T2 should be counted.
    res = client.get(
        f"/api/referral/earnings"
        f"?user_id={c_id}"
        f"&from=2025-01-15T00:00:00Z"
        f"&to=2025-02-15T00:00:00Z"
    )
    assert res.status_code == 200
    data = res.json()

    assert data["totals"]["commission_l1"] == "60.000000"
    # sanity: other kinds zero
    assert data["totals"]["cashback"] == "0.000000"
    assert data["totals"]["commission_l2"] == "0.000000"
    assert data["totals"]["commission_l3"] == "0.000000"
