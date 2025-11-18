def register_referral(child_id, parent_id, ref):
    """
    register that `parent_id` referred `child_id`.
    ref: dict mapping cuhild_id -> parent_id
    rules:
      - a child can only have ONE referrer (cannot be overwritten)
      - adding the edge child -> parent must NOT create a cycle
    """

    # 1) child cannot already have a referrer
    if child_id in ref and ref[child_id] is not None:
        raise ValueError(f"User {child_id} already has a referrer ({ref[child_id]}).")

    # 2) cycle check: walk UP from parent, make sure we never hit child
    current = parent_id
    while current is not None:
        if current == child_id:
            # this might create a loop
            raise ValueError(
                f"Registering {parent_id} as referrer of {child_id} would create a cycle."
            )
        current = ref.get(current)  # move to current's parent, so this way we can see if that guy can be the child in above loop.

    # 3) child is referred by parent
    ref[child_id] = parent_id


def get_lineage(trader_id, ref, max_levels=3):
    """
    given a trader_id and a mapping ref: child -> parent,
    return [L1, L2, L3,...] up to max_levels.
    if there is no referrer at some level, the rest are None.
    """
    lineage = []
    current = trader_id

    for _ in range(max_levels):
        parent = ref.get(current)
        if not parent:
            lineage.append(None)
            # fill remaining levels with None
            lineage.extend([None] * (max_levels - len(lineage)))
            break
        lineage.append(parent)
        current = parent

    # if we never broke early and filled less than max_levels (shouldn't happen, but safe)
    if len(lineage) < max_levels:
        lineage.extend([None] * (max_levels - len(lineage)))

    return lineage

