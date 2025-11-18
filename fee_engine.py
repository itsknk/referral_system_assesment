from decimal import Decimal, ROUND_DOWN, getcontext

getcontext().prec = 12  # enough precision for our use case


def fee_engine(fee_amount, trader_id, lineage):
    """
    fee_amount: Decimal (USDC)
    trader_id: str
    lineage: list like [l1, l2, l3] (can include None)
    """
    fee = Decimal(fee_amount)
    cashback = (fee * Decimal("0.10")).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)

    l1 = l2 = l3 = Decimal("0")
    if len(lineage) > 0 and lineage[0]:
        l1 = (fee * Decimal("0.30")).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    if len(lineage) > 1 and lineage[1]:
        l2 = (fee * Decimal("0.03")).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    if len(lineage) > 2 and lineage[2]:
        l3 = (fee * Decimal("0.02")).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)

    treasury = fee - (cashback + l1 + l2 + l3)
    treasury = treasury.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)

    return {
        "cashback": cashback,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "treasury": treasury
    }
