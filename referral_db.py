from typing import Dict, Any

from db.db import get_conn
from db.repositories import (
    get_user_by_referral_code,
    get_user_referrer_id,
    set_user_referrer_id,
)


def register_referral_db(child_id: int, referral_code: str) -> Dict[str, Any]:
    """
    DB-backed referral registration.

    child_id: user_id of the new user
    referral_code: code of the referrer (e.g. 'REF_A')

    rules:
      - child must exist
      - referrer must exist
      - child cannot already have a referrer
      - child cannot refer themselves (directly or via cycle)
    """
    with get_conn() as conn:
        try:
            # 1) resolve parent_id from referral_code
            parent_id = get_user_by_referral_code(conn, referral_code)

            if parent_id == child_id:
                raise ValueError("User cannot refer themselves.")

            # 2) ensure child has no existing referrer
            existing_ref = get_user_referrer_id(conn, child_id)
            if existing_ref is not None:
                raise ValueError(
                    f"User {child_id} already has a referrer ({existing_ref})."
                )

            # 3) cycle check: walk up from parent; must never hit child
            current = parent_id
            while current is not None:
                if current == child_id:
                    raise ValueError(
                        f"Registering {parent_id} as referrer of {child_id} would create a cycle."
                    )
                current = get_user_referrer_id(conn, current)

            # 4) safe to link
            set_user_referrer_id(conn, child_id, parent_id)

            conn.commit()
            return {"status": "linked", "child_id": child_id, "parent_id": parent_id}
        except Exception:
            conn.rollback()
            raise

