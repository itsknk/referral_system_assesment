from decimal import Decimal
from datetime import datetime

import pytest

from referral_engine import register_referral
from trade_engine import handle_trade, TREASURY_USER_ID


def _make_base_structures():
    """helper to create fresh in-memory 'tables' for each test."""
    ref = {}
    processed_trades = set()
    journal = []
    ledger = {}
    return ref, processed_trades, journal, ledger


def test_full_lineage_trade_distribution():
    """
    A -> B -> C -> D
    D makes a trade with 200 USDC fee.
    expect:
      - D: cashback 20
      - C: commission_l1 60
      - B: commission_l2 6
      - A: commission_l3 4
      - TREASURY: 110
    """
    ref, processed_trades, journal, ledger = _make_base_structures()

    # build referral chain: A → B → C → D
    register_referral("B", "A", ref)
    register_referral("C", "B", ref)
    register_referral("D", "C", ref)

    event = {
        "trade_id": "T1",
        "trader_id": "D",
        "chain": "arbitrum",
        "fee_token": "USDC",
        "fee_amount": Decimal("200.000000"),
        "executed_at": datetime.utcnow(),
    }

    result = handle_trade(event, ref, processed_trades, journal, ledger)

    assert result["status"] == "applied"
    assert result["lineage"] == ["C", "B", "A"]

    # check ledger totals
    assert ledger[("D", "cashback")] == Decimal("20.000000")
    assert ledger[("C", "commission_l1")] == Decimal("60.000000")
    assert ledger[("B", "commission_l2")] == Decimal("6.000000")
    assert ledger[("A", "commission_l3")] == Decimal("4.000000")
    assert ledger[(TREASURY_USER_ID, "treasury")] == Decimal("110.000000")

    # sum of all payouts == fee
    total_paid = sum(entry["amount"] for entry in journal)
    assert total_paid == event["fee_amount"]

    # we expect exactly 5 journal entries: cashback, l1, l2, l3, treasury
    assert len(journal) == 5

