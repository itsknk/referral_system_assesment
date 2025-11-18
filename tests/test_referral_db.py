from db.db import get_conn
from db.repositories import get_user_id_by_username, get_user_referrer_id
from referral_db import register_referral_db
import pytest


def _create_user(conn, username: str, referral_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, referral_code)
            VALUES (%s, %s)
            ON CONFLICT (username) DO UPDATE
                SET referral_code = EXCLUDED.referral_code
            RETURNING id
            """,
            (username, referral_code),
        )
        row = cur.fetchone()
        return row[0]


def test_register_referral_db_happy_path():
    with get_conn() as conn:
        # look up A (seeded)
        a_id = get_user_id_by_username(conn, "A")

        # create new user X with no referrer
        x_id = _create_user(conn, "X", "REF_X")
        conn.commit()

    # link X under A using A's referral code (REF_A from seed.sql)
    result = register_referral_db(x_id, "REF_A")
    assert result["status"] == "linked"
    assert result["child_id"] == x_id
    assert result["parent_id"] == a_id

    # verify in DB
    with get_conn() as conn:
        ref_id = get_user_referrer_id(conn, x_id)
        assert ref_id == a_id


def test_register_referral_db_cannot_overwrite():
    with get_conn() as conn:
        a_id = get_user_id_by_username(conn, "A")
        b_id = get_user_id_by_username(conn, "B")

        # create new user Y
        y_id = _create_user(conn, "Y", "REF_Y")

        # first link Y under A
        conn.commit()

    register_referral_db(y_id, "REF_A")

    # now trying to link Y under B should fail
    with pytest.raises(ValueError):
        register_referral_db(y_id, "REF_B")


def test_register_referral_db_prevents_cycles():
    """
    A -> B
    B -> C
    try to make A refer C via A's code -> would create A <- C <- B <- A (cycle)
    should be rejected.
    """
    with get_conn() as conn:
        a_id = get_user_id_by_username(conn, "A")
        b_id = get_user_id_by_username(conn, "B")
        c_id = get_user_id_by_username(conn, "C")

        # manually set B <- A, C <- B
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET referrer_id = %s WHERE id = %s", (a_id, b_id))
            cur.execute("UPDATE users SET referrer_id = %s WHERE id = %s", (b_id, c_id))
        conn.commit()

    # now trying to say "C was referred by A" (A's referral code) must fail
    with pytest.raises(ValueError):
        register_referral_db(c_id, "REF_A")

