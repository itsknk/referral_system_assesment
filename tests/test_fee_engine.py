from decimal import Decimal
from fee_engine import fee_engine


def test_basic_split_full_lineage():
    """
    200 USDC fee with full lineage should match the example from docs.
    """
    fee = Decimal("200.000000")
    result = fee_engine(fee, "trader_t1", ["L1", "L2", "L3"])

    assert result["cashback"] == Decimal("20.000000")
    assert result["l1"] == Decimal("60.000000")
    assert result["l2"] == Decimal("6.000000")
    assert result["l3"] == Decimal("4.000000")
    assert result["treasury"] == Decimal("110.000000")

    total = (
        result["cashback"]
        + result["l1"]
        + result["l2"]
        + result["l3"]
        + result["treasury"]
    )
    assert total == fee  # conservation invariant


def test_conservation_with_partial_lineage():
    """
    if only L1 exists, L2/L3 get 0 and the treasury picks up the rest.
    total must still equal the original fee.
    """
    fee = Decimal("200.000000")
    result = fee_engine(fee, "trader_t1", ["L1", None, None])

    # cashback & L1 get their normal shares
    assert result["cashback"] == Decimal("20.000000")
    assert result["l1"] == Decimal("60.000000")

    # no L2/L3 -> zero
    assert result["l2"] == Decimal("0")
    assert result["l3"] == Decimal("0")

    # treasury should be the rest
    assert result["treasury"] == Decimal("120.000000")

    total = (
        result["cashback"]
        + result["l1"]
        + result["l2"]
        + result["l3"]
        + result["treasury"]
    )
    assert total == fee  # conservation invariant


def test_tiny_fee_small_split_and_rounding():
    """
    validates small splits and rounding down to 6 dp.
    """
    fee = Decimal("0.010000")
    result = fee_engine(fee, "trader_t1", ["L1", "L2", "L3"])

    assert result["cashback"] == Decimal("0.001000")
    assert result["l1"] == Decimal("0.003000")
    assert result["l2"] == Decimal("0.000300")
    assert result["l3"] == Decimal("0.000200")
    assert result["treasury"] == Decimal("0.005500")

    total = (
        result["cashback"]
        + result["l1"]
        + result["l2"]
        + result["l3"]
        + result["treasury"]
    )
    assert total == fee  # conservation + rounding correctness

