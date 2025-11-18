import pytest
from referral_engine import register_referral, get_lineage


def test_simple_chain_lineage():
    """
    A -> B -> C -> D
    A referred B, B referred C, C referred D
    """
    ref = {}

    register_referral("B", "A", ref)  # A → B
    register_referral("C", "B", ref)  # B → C
    register_referral("D", "C", ref)  # C → D

    # D's upline: [C, B, A]
    assert get_lineage("D", ref) == ["C", "B", "A"]

    # C's upline: [B, A, None]
    assert get_lineage("C", ref) == ["B", "A", None]

    # B's upline: [A, None, None]
    assert get_lineage("B", ref) == ["A", None, None]

    # A has no referrer
    assert get_lineage("A", ref) == [None, None, None]


def test_user_with_no_referrer():
    """
    user that has never been registered as a child has no parent,
    so their lineage is all None.
    """
    ref = {}

    # no links at all
    assert get_lineage("X", ref) == [None, None, None]

    # even if others exist, an isolated node has no referrer
    register_referral("B", "A", ref)
    assert get_lineage("X", ref) == [None, None, None]


def test_register_referral_cannot_overwrite_existing_parent():
    """
    a child can only have ONE referrer.
    trying to re-attach them under someone else should raise.
    """
    ref = {}

    register_referral("B", "A", ref)  # A → B

    with pytest.raises(ValueError):
        register_referral("B", "C", ref)  # attempt B → C (should fail)

    # still the original parent
    assert ref["B"] == "A"


def test_register_referral_prevents_cycles():
    """
    A -> B -> C
    trying to make A a child of C (C -> A) would create a cycle:
    A → B → C → A
    this must be rejected.
    """
    ref = {}

    register_referral("B", "A", ref)  # A → B
    register_referral("C", "B", ref)  # B → C

    # this would close the loop: A → B → C → A
    with pytest.raises(ValueError):
        register_referral("A", "C", ref)

    assert ref["B"] == "A"
    assert ref["C"] == "B"
    assert "A" not in ref  # A still has no parent

