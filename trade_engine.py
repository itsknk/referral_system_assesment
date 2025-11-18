from decimal import Decimal
from fee_engine import fee_engine
from referral_engine import get_lineage

TREASURY_USER_ID = "TREASURY"


def handle_trade(event, ref, processed_trades, journal, ledger):
    """
    process a single trade event:
      - bring in idempotency
      - resolve referral lineage
      - compute fee splits
      - record journal entries
      - update ledger totals

    parameters
    ----------
    event : dict  we get this via request
        {
            "trade_id": str,
            "trader_id": str,
            "chain": str,         # e.g. "arbitrum"
            "fee_token": str,     # "USDC" in this test
            "fee_amount": Decimal,
            "executed_at": datetime,
        }

    ref : dict
        mapping child_id -> parent_id (referral graph in memory)

    processed_trades : set
        set of (trade_id, chain) tuples for idempotency.

    journal : list
        append-only list of payout entries. Each entry is a dict.

    ledger : dict
        mapping (user_id, kind) -> Decimal total.
        kind ∈ {"cashback", "commission_l1", "commission_l2", "commission_l3", "treasury"}

    returns
    -------
    dict
        {
            "status": "applied" | "duplicate",
            "trade_id": str,
            "lineage": [L1, L2, L3] or None for duplicates,
            "splits": {...} or None for duplicates,
        }
    """

    key = (event["trade_id"], event["chain"])

    # 1) idempotency check
    if key in processed_trades:
        return {
            "status": "duplicate",
            "trade_id": event["trade_id"],
            "lineage": None,
            "splits": None,
        }

    # 2) mark as processed
    processed_trades.add(key)

    trader_id = event["trader_id"]
    fee_amount = event["fee_amount"]
    fee_token = event["fee_token"]
    executed_at = event["executed_at"]

    # 3) resolve lineage [L1, L2, L3]
    lineage = get_lineage(trader_id, ref) # like [C,B,A]

    # 4) calculate fee splits
    splits = fee_engine(fee_amount, trader_id, lineage)
    # splits: {"cashback": ..., "l1": ..., "l2": ..., "l3": ..., "treasury": ...}

    # 5) build list of (beneficiary, kind, amount)
    payouts = []

    # trader cashback
    if splits["cashback"] > 0:
        payouts.append((trader_id, "cashback", splits["cashback"]))

    # level 1
    if lineage[0] is not None and splits["l1"] > 0:
        payouts.append((lineage[0], "commission_l1", splits["l1"]))

    # level 2
    if lineage[1] is not None and splits["l2"] > 0:
        payouts.append((lineage[1], "commission_l2", splits["l2"]))

    # level 3
    if lineage[2] is not None and splits["l3"] > 0:
        payouts.append((lineage[2], "commission_l3", splits["l3"]))

    # treasury
    if splits["treasury"] > 0:
        payouts.append((TREASURY_USER_ID, "treasury", splits["treasury"]))

    # 6) apply payouts to journal and ledger
    for (user_id, kind, amount) in payouts:
        # journal entry
        journal.append(
            {
                "trade_id": event["trade_id"],
                "chain": event["chain"],
                "beneficiary": user_id,
                "kind": kind,
                "amount": amount,
                "token": fee_token,
                "executed_at": executed_at,
            }
        )

        # ledger aggregate
        ledger_key = (user_id, kind)
        ledger[ledger_key] = ledger.get(ledger_key, Decimal("0")) + amount

    return {
        "status": "applied",
        "trade_id": event["trade_id"],
        "lineage": lineage,
        "splits": splits,
    }

